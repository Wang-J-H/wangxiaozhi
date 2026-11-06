# xiaozhi 后端 API 对接指南

> **给谁看**：需要把 xiaozhi 平台的部分能力，接入到自己新前端里的同学
> **版本**：0.7.1.beta1
> **对接方式**：xiaozhi 只作为后端服务运行，前端完全由你来做

---

## 一、先对齐：你要的是哪种模式

xiaozhi 有三种交付形态，别混了：

| 模式 | 谁在用 | 前端是谁的 | 你要改代码吗 |
| --- | --- | --- | --- |
| 镜像部署 | 只想跑起来看效果 | xiaozhi 自带（8081） | 不改 |
| 开发模式 | 要改 xiaozhi 自己的前后端 | xiaozhi 自带（5173 HMR） | 改 |
| **API 对接（本文档）** | **用 xiaozhi 当后端，前端自己写** | **你的** | 只调接口 |

你要的是第三种。所以：

- **不需要**改 xiaozhi 的任何源码
- **不需要**启动 xiaozhi 的 Vite dev server（5173 那个）
- **需要**把 xiaozhi 后端跑起来，并让你的前端能跨域访问它

xiaozhi 自带的 web（8081）建议**保留启动**，它是现成的参考实现——你 F12 打开看它怎么发请求、怎么解析流，比看文档快。

---

## 二、你要启动什么

### 2.1 服务清单

| 服务 | 作用 | 必需 | 端口 |
| --- | --- | --- | --- |
| `xiaozhi-api` | 主后端，所有 API 在这 | ✅ | **5050（需暴露）** |
| `xiaozhi-worker` | 后台任务（ARQ），对话异步执行靠它 | ✅ | 无 |
| `xiaozhi-sandbox-provisioner` | 给 Agent 分配代码执行沙箱 | ✅ | 无 |
| `xiaozhi-postgres` | 业务库 | ✅ | 5433 |
| `xiaozhi-redis` | 缓存 + 任务队列 + 事件流 | ✅ | 6380 |
| `xiaozhi-minio` | 对象存储（文件、附件） | ✅ | 9000/9001 |
| `xiaozhi-milvus` + `xiaozhi-etcd` | 向量库（知识库检索） | ✅ | 19530/9091 |
| `xiaozhi-graph` | Neo4j 图谱 | ✅ | 7474/7687 |
| `xiaozhi-web` | 自带前端，参考用 | 建议留 | 8081 |
| `xiaozhi-ollama` | 本地大模型 | ❌ 停 | 11434 |
| `xiaozhi-reranker` | 本地重排模型 | ❌ 停 | 8002 |
| `xiaozhi-mineru-api` / `xiaozhi-paddlex` | 文档解析（GPU） | ❌ 默认就不启 | 30001/8080 |

### 2.2 启动命令

我已经准备好覆盖文件 `docker-compose.api.yml`，放到项目根目录，然后：

```bash
cd /path/to/xiaozhi-offline-deploy

docker compose \
  -f docker-compose.yml \
  -f docker-compose.api.yml \
  up -d
```

这个覆盖文件干了两件事：给 api 加上 `5050:5050` 端口映射，把 ollama / reranker 推到 `full` profile（不启动）。

### 2.3 验证

```bash
# 健康检查
curl http://localhost:5050/api/system/health
# 期望：{"status":"ok","message":"服务正常运行","version":"0.7.1.beta1"}

# 接口文档
open http://localhost:5050/docs
```

> **注意**：api 容器启动时 healthcheck 的 `start_period` 是 180 秒，首次启动（要建表、初始化数据）等 2～3 分钟是正常的。`docker compose ps` 看到 api 是 `starting` 别急着判定失败。

---

## 三、必须改的两个配置

### 3.1 CORS（最容易踩的坑）

**xiaozhi 默认只放行 `http://localhost:5173` 和 `http://127.0.0.1:5173`。**

你的前端如果跑在 3000、8080 或别的机器上，浏览器会直接报跨域，接口连不上。

在 `.env` 里加：

```bash
# 逗号分隔，多个用逗号隔开，不要有空格
XIAOZHI_CORS_ORIGINS=http://localhost:3000,http://192.168.1.50:8080
```

规则（对着源码 `server/main.py` 的 `_parse_cors_origins` 来的）：

- 按 `,` 切分，每项 `strip()`
- **必须写完整 origin**：协议 + 域名/IP + 端口
- **不能带路径**，**不能带结尾斜杠**（`http://localhost:3000/` 是错的）
- 配了就用你配的；没配且 `XIAOZHI_ENV=development` 就用 5173；`XIAOZHI_ENV=production` 且没配就**一个都不放行**
- 填 `*` 可以全放行，但 `allow_credentials` 会被强制设为 `false`（如果你的前端不用 Cookie 传凭据，用 `*` 最省事）

改完要重启 api：

```bash
docker compose restart xiaozhi-api
```

放行的方法和请求头固定为：

```
方法：DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
请求头：Accept, Authorization, Content-Type, Last-Event-ID, X-Requested-With
```

如果你要往请求里加自定义头（比如 `X-Trace-Id`），会被 CORS 拦掉，别加。

### 3.2 端口

`docker-compose.yml` 里 `xiaozhi-api` **原本没有 ports 映射**，5050 只有容器内可达。必须用上面的 `docker-compose.api.yml` 补上，否则你从宿主机/局域网根本连不进去。

---

## 四、登录与鉴权

### 4.1 拿 token

```
POST /api/auth/token
Content-Type: application/x-www-form-urlencoded
```

**注意是 form-data，不是 JSON。** 这是 OAuth2 标准密码模式。

| 字段 | 说明 |
| --- | --- |
| `username` | 用户 uid **或** 手机号，两者都行 |
| `password` | 密码 |

```bash
curl -X POST http://localhost:5050/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=你的密码"
```

返回：

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

### 4.2 带 token

之后所有业务请求：

```
Authorization: Bearer eyJhbGciOi...
```

只有 `Authorization` 这一个途径，**不支持 Cookie，也不支持 `?token=` 查询参数**。这一点直接影响你的 SSE 怎么实现，见第六节。

### 4.3 两个坑

1. **用户必须绑定部门**。后端 `get_required_user` 里硬性校验，没绑部门直接返回 400 `"当前用户未绑定部门"`。初始化时注意给账号配上部门。
2. **登录接口有频率限制**：`/api/auth/token` 每 60 秒最多 10 次，超了返回 429。调试时别写循环试密码。

---

## 五、对话主链路（这是和普通聊天 API 最大的区别）

xiaozhi 的对话不是「POST 一次拿完整回答」，而是**异步 run + SSE 订阅**：

```
① 建会话
   POST /api/chat/thread          → { id }

② 发起一次运行
   POST /api/agent/runs           → { run_id, stream_url }

③ 订阅事件流
   GET  /api/agent/runs/{run_id}/events   → SSE 持续推流，直到 event: end
```

好处是断线可以续传，坏处是你前端要多写一层状态机。

### 5.1 完整示例

```bash
TOKEN="eyJhbGciOi..."
AGENT_SLUG="你的智能体slug"

# ① 建会话
THREAD=$(curl -s -X POST http://localhost:5050/api/chat/thread \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"新会话\",\"agent_id\":\"$AGENT_SLUG\"}" | jq -r '.id')

# ② 发起运行
RUN=$(curl -s -X POST http://localhost:5050/api/agent/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_slug\": \"$AGENT_SLUG\",
    \"thread_id\": \"$THREAD\",
    \"query\": \"帮我查一下这个季度的销售数据\"
  }" | jq -r '.run_id')

# ③ 订阅流
curl -N "http://localhost:5050/api/agent/runs/$RUN/events?after_seq=0-0&verbose=false" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream"
```

`POST /api/chat/thread` 的 `agent_id` 是必填字段，值与后续创建 run 时的 `agent_slug` 相同。

### 5.2 `POST /api/agent/runs` 请求体

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `agent_slug` | ✅ | 智能体标识，从 `GET /api/agent` 列表里取 |
| `thread_id` | ✅ | 会话 ID |
| `query` | 二选一 | 用户输入文本 |
| `image_content` | 二选一 | base64 图片，配合 query 一起发 |
| `meta` | ❌ | 请求追踪信息，比如 `{"request_id":"xxx"}` |
| `model_spec` | ❌ | 对话级模型覆盖，优先级高于智能体配置 |
| `resume` | ❌ | 恢复中断的 run 时传 LangGraph 输入载荷（不是布尔值） |
| `created_by_run_id` | ❌ | resume 时填被恢复的 run_id |

返回：

```json
{
  "run_id": "abc123",
  "thread_id": "thread-456",
  "status": "queued",
  "request_id": "req-789",
  "stream_url": "/api/agent/runs/abc123/events"
}
```

`stream_url` 直接可用，不用自己拼。

### 5.3 怎么拿到 `agent_slug`

```bash
# 列出所有智能体
curl http://localhost:5050/api/agent -H "Authorization: Bearer $TOKEN"

# 或者直接拿默认智能体
curl http://localhost:5050/api/agent/default -H "Authorization: Bearer $TOKEN"
```

列表里每个对象的 `slug` 字段就是你要的。

---

## 六、SSE 事件流

### 6.1 事件类型

| event | 含义 | 你怎么处理 |
| --- | --- | --- |
| `metadata` | 元信息（模型、run 基础信息） | 忽略或记日志 |
| `messages` | 消息流 envelope | 读取 `payload.chunk.stream_event` 或 `payload.items[*].stream_event` |
| `custom` | 自定义事件，`name=xiaozhi.agent_state` 时是 Agent 状态 | 可忽略 |
| `end` | **流结束** | 收尾，关闭连接 |
| `error` | 出错 | 提示用户 |

`message_delta`、`tool_call`、`tool_call_delta` 是 `messages` envelope 内部的 `stream_event.type`，不是顶层 SSE `event`。最终可见正文只取 `stream_event.type=message_delta` 的 `content`；`reasoning_content` 不应当作最终正文展示。

`data` 是 JSON。流里还会有 `: heartbeat` 注释行（约每 15 秒一次），**解析时必须跳过**，否则会报 JSON 解析错。

### 6.2 断线续传

每个事件带 `id:`，值是 `{seq}` 形式的游标（如 `12-0`）。

重连时两种传法，任选：

```
GET /api/agent/runs/{run_id}/events?after_seq=12-0
GET /api/agent/runs/{run_id}/events
Last-Event-ID: 12-0
```

后端会从游标之后继续推，不会重头再来。**这是 xiaozhi 事件流的核心设计，别自己写重试逻辑去重新发 run**——那会重复执行。

### 6.3 前端必须用 fetch，不能用 EventSource

`EventSource` 不能带自定义请求头，而 xiaozhi 只认 `Authorization: Bearer`，所以 `EventSource` 直接废掉。

用 `fetch` + `ReadableStream` 手撸解析：

```js
async function streamRun(runId, token, { afterSeq = '0-0', onEvent } = {}) {
  const res = await fetch(
    `http://localhost:5050/api/agent/runs/${runId}/events?after_seq=${afterSeq}&verbose=false`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'text/event-stream',
      },
    }
  );
  if (!res.ok) throw new Error(`SSE 连接失败: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let lastId = afterSeq;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buf += decoder.decode(value, { stream: true });

    // SSE 事件以空行分隔
    const blocks = buf.split('\n\n');
    buf = blocks.pop(); // 最后一段可能不完整，留着

    for (const block of blocks) {
      if (!block.trim()) continue;
      if (block.startsWith(':')) continue; // 心跳，跳过

      let event = 'message';
      let data = '';
      let id;

      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
        else if (line.startsWith('id:')) id = line.slice(3).trim();
      }

      if (id) lastId = id;

      let payload = null;
      try {
        payload = data ? JSON.parse(data) : null;
      } catch {
        continue; // 半包，丢掉
      }

      onEvent(event, payload, lastId);

      if (event === 'end' || event === 'error') return;
    }
  }
}
```

调用：

```js
await streamRun(runId, token, {
  onEvent: (event, data, id) => {
    if (event === 'messages') {
      const payload = data?.payload || {};
      const chunks = [payload.chunk, ...(payload.items || [])].filter(Boolean);
      for (const chunk of chunks) {
        const streamEvent = chunk.stream_event;
        if (streamEvent?.type === 'message_delta' && streamEvent.content) {
          appendText(streamEvent.content);
        } else if (
          streamEvent?.type === 'tool_call' ||
          streamEvent?.type === 'tool_call_delta'
        ) {
          showToolCall(streamEvent);
        }
      }
    } else if (event === 'end') {
      finish();
    }
  },
});
```

**断线重连**：把最后收到的 `id` 存下来，重连时传 `afterSeq`：

```js
await streamRun(runId, token, { afterSeq: lastId, onEvent });
```

---

## 七、常用接口清单

全部接口前缀是 `/api`。

### 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/token` | 登录拿 token（form-data） |
| GET | `/api/auth/me` | 当前用户信息 |

### 智能体

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/agent` | 智能体列表（拿 slug 用这个） |
| GET | `/api/agent/default` | 默认智能体 |
| GET | `/api/agent/{agent_id}` | 单个智能体详情 |
| POST | `/api/agent` | 新建智能体 |
| PUT | `/api/agent/{agent_id}` | 更新 |
| GET | `/api/agent/backends` | 可用后端类型 |

### 对话运行

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/agent/runs` | 发起运行 |
| GET | `/api/agent/runs/{run_id}` | 查运行状态 |
| GET | `/api/agent/runs/{run_id}/result` | 拿最终结果 |
| GET | `/api/agent/runs/{run_id}/events` | **SSE 事件流** |
| POST | `/api/agent/runs/{run_id}/cancel` | 取消运行 |
| GET | `/api/agent/thread/{thread_id}/active_run` | 该会话有没有正在跑的 run |

### 会话与消息

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat/thread` | 建会话 |
| GET | `/api/chat/threads` | 会话列表 |
| GET | `/api/chat/thread/{thread_id}/history` | 历史消息 |
| GET | `/api/chat/thread/{thread_id}/state` | 会话状态 |
| PUT | `/api/chat/thread/{thread_id}` | 改名等 |
| DELETE | `/api/chat/thread/{thread_id}` | 删会话 |
| GET | `/api/chat/threads/search` | 搜索会话 |

### 文件与附件

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat/attachments/tmp` | 上传临时附件 |
| POST | `/api/chat/attachments/tmp/parse` | 解析临时附件 |
| POST | `/api/chat/thread/{thread_id}/attachments` | 上传会话附件 |
| GET | `/api/chat/thread/{thread_id}/attachments` | 附件列表 |
| GET | `/api/chat/thread/{thread_id}/files` | 会话产物文件列表 |
| GET | `/api/chat/thread/{thread_id}/files/content` | 读文件内容 |

### 知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/knowledge` | 知识库列表 |
| POST | `/api/knowledge` | 建知识库 |
| POST | `/api/knowledge/{id}/documents` | 上传文档 |
| POST | `/api/knowledge/{id}/search` | 检索 |

### 其他

| 前缀 | 说明 |
| --- | --- |
| `/api/system/*` | 健康检查、全局配置 |
| `/api/system/model-providers/*` | 模型供应商配置 |
| `/api/system/mcp-servers/*` | MCP 服务管理 |
| `/api/system/skills/*`、`/api/skills/*` | Skills 管理 |
| `/api/system/tools/*` | 工具列表 |
| `/api/departments/*` | 部门与权限 |
| `/api/dashboard/*` | 仪表盘聚合 |
| `/api/tasks/*` | 后台任务 |
| `/api/workspace/*` | 个人工作区 |
| `/api/graph/*` | 图谱查询 |
| `/api/evaluation/*` | 知识库评估 |
| `/api/user/*` | 用户级配置与凭据 |
| `/api/mention/*` | 提及文件搜索 |
| `/api/viewer/filesystem/*` | 工作台文件系统 |
| `/api/agent-invocation/*` | 外部 Agent 调用与评估 |

---

## 八、完整接口文档在哪

不用我手写，FastAPI 自动生成，**永远和你跑的版本一致**：

| 地址 | 内容 |
| --- | --- |
| `http://localhost:5050/docs` | Swagger UI，可以直接点着试（先点右上角 Authorize 填 token） |
| `http://localhost:5050/openapi.json` | OpenAPI 规范文件 |

**强烈建议**：把 `openapi.json` 下载下来，直接导入 Apifox / Postman / YApi，全套接口、参数、模型定义都自动生成，比手抄快一百倍。

```bash
curl http://localhost:5050/openapi.json -o xiaozhi-openapi.json
```

注意：`/docs` 和 `/openapi.json` 是**根路径**，不带 `/api` 前缀。

---

## 九、其他实现要点

### 9.1 请求基础配置

```js
const BASE = 'http://localhost:5050';

// axios 拦截器示例
axios.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('token');
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

axios.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      // token 失效，跳登录
    }
    return Promise.reject(err);
  }
);
```

### 9.2 文件上传大小

nginx 侧限制 `client_max_body_size 500M`。如果你绕开 nginx 直连 5050，这个限制不存在，但要注意后端自己的限制。

### 9.3 长耗时请求

对话类接口都可能跑很久（几分钟）。如果你走 nginx 反代，`proxy_read_timeout` 是 600 秒，别自己再压短。直连 5050 没有这个问题。

### 9.4 版本与健康检查

```bash
GET /api/system/health
→ {"status":"ok","message":"服务正常运行","version":"0.7.1.beta1"}
```

适合做前端启动时的连通性探测。

---

## 十、常见问题

**Q1：浏览器报 CORS 错误**
`.env` 里没配 `XIAOZHI_CORS_ORIGINS`，或者格式不对（带了路径/斜杠/空格）。改完记得 `docker compose restart xiaozhi-api`。

**Q2：接口 401 无效的凭证**
- token 过期
- Header 格式错：必须是 `Bearer xxx`，`Bearer` 后面一个空格，不能漏
- 用了 Cookie 或 `?token=`，这两种后端都不认

**Q3：接口 400「当前用户未绑定部门」**
账号建了但没绑部门。去 `departments` 相关接口或直接在库里给用户补 `department_id`。

**Q4：POST /api/agent/runs 一直返回同一个 run**
正常。同一个 thread 已有活跃 run 时，后端会复用，不会重复创建。要发新问题先等上一个 `end`，或者先 `cancel`。

**Q5：SSE 收到 `: heartbeat` 就报 JSON 解析错**
解析时跳过以 `:` 开头的行。见 6.3 的代码。

**Q6：EventSource 连不上**
不支持自定义 Header，用 fetch。见 6.3。

**Q7：`/docs` 打不开**
- 确认访问的是 `http://host:5050/docs`，不是 `/api/docs`
- 确认 5050 端口已映射（`docker compose ps` 里看 api 的 PORTS 列）

**Q8：容器起来了但接口 502/超时**
api 首次启动要建表 + 初始化，`start_period` 180 秒。看日志：

```bash
docker compose logs -f xiaozhi-api
```

**Q9：能不能不用 xiaozhi 自带的 web**
能。`docker-compose.api.yml` 里给 `xiaozhi-web` 加 `profiles: ["full"]` 就不启动了。但建议第一次留着，方便对照。

---

## 十一、参考实现

xiaozhi 自带的 web（`http://localhost:8081`）是最好的接口参考：

1. 打开浏览器 F12 → Network
2. 正常用一遍对话、传文件、建知识库
3. 看它发了哪些请求、参数怎么传、SSE 怎么解析

它的前端源码在 `web/src/`，SSE 相关逻辑可以搜 `agent/runs`、`message_delta` 找到，`web/src/components/AgentChatComponent.vue` 是主对话组件。

---

## 附：最小可用清单

按这个顺序走，一小时能通：

- [ ] 项目文件就位（backend、web、docker 目录）
- [ ] `.env` 配好 `XIAOZHI_CORS_ORIGINS`
- [ ] `docker compose -f docker-compose.yml -f docker-compose.api.yml up -d`
- [ ] `curl http://localhost:5050/api/system/health` 返回 ok
- [ ] 浏览器打开 `http://localhost:5050/docs` 能看见接口
- [ ] 用 `POST /api/auth/token` 拿到 token
- [ ] `GET /api/agent` 拿到 agent_slug
- [ ] 建 thread → 发 run → 订阅 SSE，收到 `message_delta` 和 `end`
- [ ] `openapi.json` 导入 Apifox
- [ ] 自己前端接上第一个接口
