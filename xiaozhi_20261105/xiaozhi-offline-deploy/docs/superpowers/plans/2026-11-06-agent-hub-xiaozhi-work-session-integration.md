# Agent Hub Xiaozhi 办公模式与历史会话接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Xiaozhi Agent Loop 安全接入 Agent Hub `mode=work`，支持真实流式回答、活动提示、中断、历史会话列表及从历史记录跳回原会话继续对话。

**Architecture:** `mode=daily` 继续使用 `projects_new` transport，`mode=work` 使用独立 `xiaozhi` transport。浏览器只访问 Agent Hub 同源 BFF；BFF 保存演示用户 API Key、固定办公 Agent slug，并把允许的请求转发给 Xiaozhi。Xiaozhi thread ID 是办公会话唯一 ID，写入 `conversation` query；会话正文、历史列表均以 Xiaozhi DB 为准。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy、PostgreSQL、Redis、ARQ、LangGraph、Next.js 16、React 19、TypeScript 5.9、Vitest、Testing Library、Playwright、pnpm 9。

**Spec:** `S:\Projects\agent-hub-web\docs\superpowers\specs\2026-10-27-agent-hub-web-design.md`；本计划“范围与既定决策”记录已批准的办公模式增量。

## 范围与既定决策

- 日常模式：继续走 `projects_new`；本计划不改其接口和会话实现。
- 办公模式：走 Xiaozhi Agent Loop；与日常模式保持会话、运行、历史完全隔离。
- 首版身份：单一演示用户，团队成员共享办公历史；后续统一认证替换 BFF 身份解析。
- 首版展示：仅展示最终可见正文；不展示模型推理、内部 prompt、完整工具参数或工具原始结果。
- 活动提示：单行、短暂、可替换；只显示安全的通用状态或工具显示名。
- 新对话：首次发送时创建 Xiaozhi thread；成功后将 URL 替换为真实 thread ID。
- 历史跳转：`/history?mode=work` 点击后进入 `/chat?mode=work&conversation=<thread_id>`。
- 首版不做：统一登录、多用户隔离、运行中会话恢复、steer、附件、RAG、动态 Skill/MCP 选择、历史搜索/删除/重命名、日常历史适配、Workflow、GIS。
- 旧无 Git 目录只作为配置和行为参考；禁止整目录覆盖远端仓库。

## Global Constraints

- Xiaozhi 基线：`S:\Projects\wangxiaozhi\xiaozhi_20261105\xiaozhi-offline-deploy` 的 `origin/main`。
- Agent Hub 基线：`S:\Projects\agent-hub-web` 的最新 `origin/main`；执行时创建独立 worktree。
- 后端本地分支建议：`codex/agent-hub-work-integration`。
- 前端本地分支建议：`codex/xiaozhi-work-integration`。
- 前端 worktree 建议：`S:\Projects\agent-hub-worktrees\xiaozhi-work-integration`。
- Xiaozhi 使用 Python/uv；Agent Hub 只用 pnpm。
- 行为改动必须 TDD：失败测试 → 最小实现 → 通过测试。
- API Key、JWT、DeepSeek Key、密码、`.env` 永不提交，永不进入 `NEXT_PUBLIC_*`。
- 浏览器不得直接访问 Xiaozhi，不得收到 Xiaozhi API Key。
- BFF 仅代理白名单接口，不得成为任意管理 API 代理。
- SSE 必须用 `fetch`/`ReadableStream`；不得使用 `EventSource`。
- SSE 使用 `verbose=false`；只映射可见正文和安全活动状态。
- 中断连接与取消运行是两个动作：先终止本地读取，再调用 Xiaozhi cancel。
- 不删除或重建已有 PostgreSQL/Redis volume；需要破坏性 DB 操作时停止并单独请求批准。
- 每个 Task 完成后提交；是否 push 由用户逐项指挥，本计划不自动 push。

## 路径约定

- Task 1、Task 2 未标前缀的路径均相对 Xiaozhi 仓库根目录。
- Task 3 至 Task 6 未标前缀的路径均相对 Agent Hub 新 worktree 根目录。
- Task 7 同时操作两个仓库，文件和命令使用 `[xiaozhi]`、`[agent-hub]` 标识。

## Review Focus

- SSE 被任意切包、使用 CRLF、包含 heartbeat、多行 `data:` 时，解析器仍应保序且不丢正文；Task 4 覆盖。
- 浏览器请求、HTML、JS bundle、日志和错误正文均不得泄漏 API Key；Task 3、Task 7 覆盖。
- `mode=daily` 与 `mode=work` 切换时，不得复用对方的 conversation ID、transport 或消息；Task 5 覆盖。
- 已收到增量正文后，`end`/result 兜底不得重复正文；完全没有增量时必须显示 result.output；Task 4 覆盖。
- 历史 thread 不存在、已删除或所属 Agent 不匹配时，应显示可恢复错误，不得自动新建并伪装为原会话；Task 5、Task 6 覆盖。

---

### Task 1: 建立安全 Xiaozhi 集成基线

**Files:**
- Create: `.gitignore`
- Modify: `backend/package/xiaozhi/utils/auth_utils.py:51-56`
- Modify: `docs/xiaozhi_后端API对接指南.md`
- Test: `backend/test/unit/test_auth_utils.py`
- Test: `backend/test/integration/api/test_apikey_router.py`
- Track: `docs/superpowers/plans/2026-11-06-agent-hub-xiaozhi-work-session-integration.md`

**Interfaces:**
- Consumes: Xiaozhi `origin/main`，旧目录 `S:\Projects\xiaozhi-offline-deploy` 仅作只读参考。
- Produces: 可认证的 `yxkey_` API Key；不会误提交本地密钥/venv/runtime 的后端分支基线。

- [ ] **Step 1: 创建后端本地分支并确认基线**

在 Xiaozhi 仓库 fetch；确认 `main == origin/main` 且除本计划外无未知改动；创建 `codex/agent-hub-work-integration`。不得复制旧目录源码。

- [ ] **Step 2: 运行现有 API Key 测试，记录真实失败**

Run:

```powershell
cd backend
uv run pytest test/unit/test_auth_utils.py::test_generate_api_key_returns_secret_hash_and_prefix -q
```

Expected: FAIL；当前实现生成 `xzk_`，测试及鉴权中间件要求 `yxkey_`。

- [ ] **Step 3: 修复 API Key 生成前缀**

将 `AuthUtils.generate_api_key() -> tuple[str, str, str]` 恢复为 `yxkey_{48 hex chars}`。不扩大鉴权兼容面，不同时接受未知前缀。

- [ ] **Step 4: 添加根忽略规则**

`.gitignore` 至少覆盖：`.env`、`.env.local`、`backend/.venv/`、`backend/.runtime/`、`backend/saves/`、`**/__pycache__/`、`*.pyc`、`*.log`、`*.pid`。保留已有 `web/.gitignore`。

- [ ] **Step 5: 修正文档中的两个契约偏差**

文档必须明确：

- `POST /api/chat/thread` 必传 `agent_id`。
- SSE 顶层主要事件是 `messages`，正文增量位于 `payload.chunk.stream_event` 或 `payload.items[*].stream_event`。
- `stream_event.type=message_delta` 的 `content` 才是首版可见正文。
- heartbeat 需要忽略，游标来自 SSE `id:`。

- [ ] **Step 6: 验证 API Key 与忽略规则**

Run:

```powershell
cd backend
uv run pytest test/unit/test_auth_utils.py test/integration/api/test_apikey_router.py -q
cd ..
git check-ignore -v .env backend/.venv backend/.runtime backend/saves/config/base.toml
git diff --check
```

Expected: tests PASS；四个本地产物均被 ignore；`git diff --check` 无输出。

- [ ] **Step 7: 提交 Task 1**

```powershell
git add .gitignore backend/package/xiaozhi/utils/auth_utils.py backend/test/unit/test_auth_utils.py backend/test/integration/api/test_apikey_router.py docs/xiaozhi_后端API对接指南.md docs/superpowers/plans/2026-11-06-agent-hub-xiaozhi-work-session-integration.md
git commit -m "fix: prepare xiaozhi for agent hub integration"
```

---

### Task 2: 固化最小本地 API/Worker 启动与契约 Smoke

**Files:**
- Create: `scripts/dev/run_native_api.py`
- Create: `scripts/dev/run_native_worker.py`
- Create: `scripts/dev/smoke_agent_hub_contract.py`
- Modify: `docs/xiaozhi_开发模式启动说明.md`

**Interfaces:**
- Consumes: Task 1 的有效 `yxkey_`；现有 PostgreSQL `xiaozhi` DB、Redis `/1`、DeepSeek provider 配置。
- Produces: Windows 本地可重复启动的 API/Worker；覆盖 Agent Hub 所需端点的真实 smoke 命令。

- [ ] **Step 1: 在新仓库重建 Python 环境**

不得复制旧 `.venv`。在新仓库执行：

```powershell
cd backend
$env:UV_HTTP_TIMEOUT='180'
$env:UV_CONCURRENT_DOWNLOADS='4'
uv sync --frozen --no-dev --default-index 'https://pypi.org/simple'
cd ..
```

Expected: `backend/.venv` 创建成功；`uv sync` exit 0。

- [ ] **Step 2: 提炼 Windows Selector event loop 启动器**

创建 `run_native_api.py` 与 `run_native_worker.py`。两者仅负责：加入 `backend/package` 到 `sys.path`、Windows 下使用 `asyncio.SelectorEventLoop`、启动现有 server/worker。禁止保留旧版 `User.__table__` schema monkey patch。

- [ ] **Step 3: 验证启动器可导入和编译**

Run:

```powershell
backend\.venv\Scripts\python.exe -m py_compile scripts/dev/run_native_api.py scripts/dev/run_native_worker.py
```

Expected: exit 0，无语法错误。

- [ ] **Step 4: 编写真实契约 smoke 脚本**

`smoke_agent_hub_contract.py` 从环境变量读取 `XIAOZHI_BASE_URL`、`XIAOZHI_API_KEY`；不得打印密钥。依次验证：

1. health；
2. default agent；
3. 创建 thread（含 `agent_id`）；
4. 创建 run；
5. 订阅 `verbose=false` SSE，至少观察 `messages` 与终态；
6. `/result` 的 `status=completed` 且 `output` 非空；
7. thread 出现在 `/threads?agent_id=...`；
8. `/history` 含本轮 user/assistant 正文；
9. 新建第二个 run 后调用 cancel，终态不得继续显示为成功运行中。

- [ ] **Step 5: 更新最小启动文档**

写明：

- 复用共享 Postgres/Redis 时的 URL；
- DeepSeek Key 通过进程环境注入；
- `.env` 从旧目录本地复制但已被 ignore；
- API、Worker 都必须启动；
- 仅聊天/历史不需要 RAG、Milvus、Neo4j、MinIO；
- Skill 若依赖 Shell/文件系统，需要另启 sandbox provisioner。

- [ ] **Step 6: 启动基础设施并执行 smoke**

Docker 当前已停止；执行到此步骤时先由用户确认启动。不得自动删除 volume。启动 API/Worker 后运行：

```powershell
backend\.venv\Scripts\python.exe scripts/dev/smoke_agent_hub_contract.py
```

Expected: 所有检查 PASS；输出 run/thread ID 可以记录，不能输出密钥。

- [ ] **Step 7: 提交 Task 2**

```powershell
git add scripts/dev docs/xiaozhi_开发模式启动说明.md
git commit -m "test: add repeatable xiaozhi integration smoke"
```

---

### Task 3: 增加 Agent Hub 服务端安全代理

**Files:**
- Create: `src/server/xiaozhi/config.ts`
- Create: `src/server/xiaozhi/proxy.ts`
- Create: `src/server/xiaozhi/proxy.test.ts`
- Create: `src/app/api/work-agent/[...path]/route.ts`
- Create: `src/app/api/work-agent/work-agent-route.test.ts`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: `XIAOZHI_API_ORIGIN: http(s) URL`、`XIAOZHI_API_KEY: yxkey_...`、`XIAOZHI_WORK_AGENT_SLUG: string`。
- Produces: 同源 `/api/work-agent/*` BFF；浏览器无需也无法取得 API Key。

- [ ] **Step 1: 执行时创建最新前端 worktree**

从 Agent Hub 最新 `origin/main` 创建 `S:\Projects\agent-hub-worktrees\xiaozhi-work-integration`，分支 `codex/xiaozhi-work-integration`。先读该 worktree 的 `AGENTS.md`。

- [ ] **Step 2: 写服务端配置失败测试**

覆盖：缺失 origin/key/slug、非 HTTP(S) origin、空 slug 均拒绝；返回对象不得把 key 暴露给 public runtime config。

Run:

```powershell
pnpm test -- src/server/xiaozhi/proxy.test.ts
```

Expected: FAIL，模块尚不存在。

- [ ] **Step 3: 实现服务端配置**

导出：

```ts
export interface XiaozhiServerConfig {
  origin: URL;
  apiKey: string;
  agentSlug: string;
}

export function resolveXiaozhiServerConfig(
  env: Readonly<Record<string, string | undefined>>,
): XiaozhiServerConfig;
```

只在 server 模块读取上述三个非 `NEXT_PUBLIC_*` 变量。

- [ ] **Step 4: 写代理白名单与密钥隔离失败测试**

覆盖：

- 仅允许 health、default agent、thread create/list/history、run create/events/result/cancel。
- 拒绝 `/auth`、`/users`、`/system/model-providers` 等管理路径。
- 丢弃浏览器传入的 `Authorization`、Cookie、Host；注入 server API Key。
- thread create 强制注入 `agent_id=agentSlug`。
- thread list 强制注入 `agent_id=agentSlug`。
- run create 强制注入 `agent_slug=agentSlug`。
- SSE response body 原样流转，保留 `content-type: text/event-stream`，移除 hop-by-hop headers。
- upstream 4xx/5xx 不得回显请求 Authorization。

- [ ] **Step 5: 实现 BFF proxy 与 catch-all Route Handler**

导出：

```ts
export function isAllowedWorkAgentRequest(method: string, path: string): boolean;
export async function proxyWorkAgentRequest(request: Request, path: string[]): Promise<Response>;
```

Route Handler 的 `GET`、`POST`、`PUT`、`DELETE` 只调用该 helper；首版实际白名单可少于导出的 HTTP 方法。

- [ ] **Step 6: 运行安全代理测试**

Run:

```powershell
pnpm test -- src/server/xiaozhi/proxy.test.ts src/app/api/work-agent/work-agent-route.test.ts
pnpm typecheck
```

Expected: PASS；TypeScript 无错误。

- [ ] **Step 7: 更新环境模板与安全说明**

`.env.example` 只列变量名和无密钥示例；README 明确 shared demo history、server-only key、未来统一认证替换点。

- [ ] **Step 8: 提交 Task 3**

```powershell
git add src/server/xiaozhi src/app/api/work-agent .env.example README.md
git commit -m "feat: add secure xiaozhi work agent proxy"
```

---

### Task 4: 实现 Xiaozhi Run、SSE 与 Session Transport

**Files:**
- Create: `src/features/chat/contracts/session.ts`
- Create: `src/features/chat/transports/fetch-sse-stream.ts`
- Create: `src/features/chat/transports/fetch-sse-stream.test.ts`
- Create: `src/features/chat/transports/xiaozhi-contract.ts`
- Create: `src/features/chat/transports/xiaozhi-transport.ts`
- Create: `src/features/chat/transports/xiaozhi-transport.test.ts`
- Modify: `src/features/chat/contracts/chat.ts`
- Modify: `src/features/chat/contracts/transport.ts`

**Interfaces:**
- Consumes: Task 3 `/api/work-agent/*`；现有 `ChatStreamEvent`。
- Produces: `createXiaozhiTransport()`；标准化 Run + Session 接口，供 Task 5/6 使用。

- [ ] **Step 1: 定义会话契约**

在 `session.ts` 导出：

```ts
export interface ChatSessionSummary {
  id: string;
  title: string;
  updatedAt: number;
  isPinned: boolean;
}

export interface LoadedChatSession {
  session: ChatSessionSummary;
  messages: ChatMessage[];
}

export interface ChatSessionTransport {
  listSessions(signal?: AbortSignal): Promise<ChatSessionSummary[]>;
  loadSession(sessionId: string, signal?: AbortSignal): Promise<LoadedChatSession>;
}
```

`CreateChatRunInput` 增加可选 `sessionId?: string`；`CreatedChatRun` 增加可选 `sessionId?: string`；`ChatTransport` 增加 kind `xiaozhi` 和可选 `sessions?: ChatSessionTransport`。

- [ ] **Step 2: 写通用 fetch SSE 解析失败测试**

覆盖：任意 chunk 边界、CRLF/LF、heartbeat、多个事件同 chunk、多行 `data:`、非法 JSON 后继续、`id:` 游标、AbortSignal。

Run:

```powershell
pnpm test -- src/features/chat/transports/fetch-sse-stream.test.ts
```

Expected: FAIL，解析器尚不存在。

- [ ] **Step 3: 实现 SSE 解析器**

导出：

```ts
export interface ParsedSseEvent {
  event: string;
  data: unknown;
  id?: string;
}

export function parseFetchSse(
  response: Response,
  signal?: AbortSignal,
): AsyncIterable<ParsedSseEvent>;
```

- [ ] **Step 4: 写 Xiaozhi transport 失败测试**

覆盖：

- 无 `sessionId`：先创建 thread，标题取首条用户输入压缩空白后的前 32 个字符，再创建 run。
- 有 `sessionId`：直接在原 thread 创建 run。
- `messages` 中 `message_delta.content` → `answer.delta`。
- reasoning 字段永不转成正文。
- tool call → 安全 `activity.update`；不输出 args/output。
- `custom` 空 agent state 忽略；其他内部状态最多映射为通用活动提示。
- `end` 后读取 `/result`：有增量时只发 `answer.done`；无增量时 `answer.done.content=result.output`。
- `error` → `run.failed`；cancel/stop → `run.stopped`。
- abort 调用 cancel endpoint。
- list 只接受合法 thread schema；history 只保留 human/user 与 ai/assistant，过滤 tool/system。
- history 404 抛出可识别 `SessionNotFoundError`，不得创建替代 thread。

- [ ] **Step 5: 实现 Xiaozhi schema 与 transport**

导出：

```ts
export interface XiaozhiTransportOptions {
  apiBaseUrl?: string;
  fetchFn?: typeof fetch;
  idFactory?: () => string;
}

export function createXiaozhiTransport(
  options?: XiaozhiTransportOptions,
): ChatTransport;
```

默认 `apiBaseUrl=/api/work-agent`。运行期间保存最近 SSE cursor 仅供本次连接重试；首版不实现刷新后 active run 恢复。

- [ ] **Step 6: 运行 transport 测试**

Run:

```powershell
pnpm test -- src/features/chat/transports/fetch-sse-stream.test.ts src/features/chat/transports/xiaozhi-transport.test.ts
pnpm typecheck
```

Expected: PASS。

- [ ] **Step 7: 提交 Task 4**

```powershell
git add src/features/chat/contracts src/features/chat/transports
git commit -m "feat: add xiaozhi chat and session transport"
```

---

### Task 5: 接入办公对话与真实 thread 路由

**Files:**
- Modify: `src/app/chat/page.tsx`
- Modify: `src/app/chat/chat-route.test.tsx`
- Modify: `src/components/chat/chat-page.tsx`
- Modify: `src/components/chat/chat-page.test.tsx`
- Modify: `src/components/chat/capability-selector.tsx`
- Modify: `src/components/shell/sidebar.tsx`
- Modify: `src/components/shell/app-shell.test.tsx`
- Modify: `src/features/chat/use-chat-controller.ts`
- Modify: `src/features/chat/use-chat-controller.test.tsx`
- Modify: `src/features/chat/reducer/chat-reducer.ts`
- Modify: `src/features/chat/reducer/chat-reducer.test.ts`
- Modify: `src/features/chat/reducer/chat-state.ts`
- Delete: `src/components/chat/office-loop-unavailable.tsx`

**Interfaces:**
- Consumes: Task 4 `ChatTransport.sessions`、`CreateChatRunInput.sessionId`、`CreatedChatRun.sessionId`。
- Produces: `/chat?mode=work` 新对话；`/chat?mode=work&conversation=<thread_id>` 历史加载和继续对话。

- [ ] **Step 1: 写办公模式路由失败测试**

断言：

- `mode=work` 创建 Xiaozhi transport，不再渲染 unavailable。
- `mode=daily` 仍创建原 transport。
- `conversation` 仅在当前 mode 的组件实例内使用。
- work 模式不允许 E2E `backend=real` 覆盖成 projects_new。

- [ ] **Step 2: 写 controller session 生命周期失败测试**

覆盖：

- 带 session ID 进入页面时先加载历史，再允许发送。
- 加载成功按后端顺序 hydrate user/assistant 消息。
- 首次发送返回新 session ID 后调用 `onSessionResolved(id)` 一次。
- 后续发送复用同一 session ID。
- 404 显示“会话不存在或已删除”，不自动创建。
- mode/transport 改变时旧加载和旧 SSE 被 abort，旧消息不会写入新模式。

- [ ] **Step 3: 扩展 reducer 和 controller**

新增最小 session 状态：`sessionId`、`sessionStatus: idle|loading|ready|not-found|failed`。新增 reducer action：

```ts
{ type: "session.load.start" }
{ type: "session.load.success"; sessionId: string; messages: ChatMessage[] }
{ type: "session.load.not-found" }
{ type: "session.load.failed"; message: string }
{ type: "session.resolve"; sessionId: string }
```

不得把历史写入 `localStorage`。

- [ ] **Step 4: 实现 chat route 与 URL 替换**

`ChatRoute`：

- daily → 原 transport；
- work → `createXiaozhiTransport()`；
- 读取 `conversation`；
- 首次 thread 建立后使用 `router.replace('/chat?mode=work&conversation=<encoded id>')`；
- 保留其他已批准 query，仅移除临时 `draft`。

- [ ] **Step 5: 修正“新对话”路由语义**

Sidebar 新对话不得生成伪 backend ID。改为 `/chat?mode=<mode>&draft=<random nonce>`；`conversation` 只代表已持久化会话。连续点击新对话必须重置 UI。

- [ ] **Step 6: 处理办公能力选择器**

首版 Xiaozhi Agent 已预配置 Skill/MCP；work 模式隐藏或禁用 per-request 知识库/Skill/MCP 选择，并显示简短说明。不得把 UI 选择伪装成后端已支持参数。

- [ ] **Step 7: 运行对话相关测试**

Run:

```powershell
pnpm test -- src/app/chat/chat-route.test.tsx src/components/chat/chat-page.test.tsx src/features/chat/use-chat-controller.test.tsx src/features/chat/reducer/chat-reducer.test.ts src/components/shell/app-shell.test.tsx
pnpm typecheck
```

Expected: PASS。

- [ ] **Step 8: 提交 Task 5**

```powershell
git add src/app/chat src/components/chat src/components/shell src/features/chat
git commit -m "feat: connect work mode to xiaozhi threads"
```

---

### Task 6: 实现办公历史列表与跳转

**Files:**
- Modify: `src/app/history/page.tsx`
- Create: `src/app/history/history-page-client.tsx`
- Create: `src/app/history/history-page.test.tsx`
- Modify: `src/config/resource-fixtures.ts`
- Modify: `src/app/globals.css`

**Interfaces:**
- Consumes: Task 4 `transport.sessions.listSessions()`；Task 5 persisted conversation URL。
- Produces: mode-aware 历史页；work 历史点击跳回真实 thread。

- [ ] **Step 1: 写历史页失败测试**

覆盖：

- `mode=work` 加载真实 session，按 pinned 后 updatedAt 降序展示。
- 点击 session 进入 `/chat?mode=work&conversation=<encoded id>`。
- loading、empty、network error 状态明确。
- 恶意或非法 thread ID 必须 URL encode。
- `mode=daily` 显示“日常历史待 session 接入”，不展示 Xiaozhi 记录。
- mode 切换时取消旧请求，work 结果不得落到 daily 页面。

- [ ] **Step 2: 实现 HistoryPageClient**

组件只依赖 `ChatSessionTransport`；不得直接知道 Xiaozhi JSON。现有 fixture 仅保留给明确的 mock/E2E 场景，生产 work 页不回退 fixture。

- [ ] **Step 3: 添加极简列表样式**

复用现有视觉系统；桌面优先、浅色默认。每项只显示标题、更新时间、可选置顶标识；不增加搜索、删除、菜单。

- [ ] **Step 4: 运行历史与导航测试**

Run:

```powershell
pnpm test -- src/app/history/history-page.test.tsx src/components/shell/app-shell.test.tsx src/config/modes.test.ts
pnpm typecheck
```

Expected: PASS。

- [ ] **Step 5: 提交 Task 6**

```powershell
git add src/app/history src/config/resource-fixtures.ts src/app/globals.css
git commit -m "feat: add xiaozhi work conversation history"
```

---

### Task 7: 真实联调、回归与交接

**Files:**
- Create [agent-hub]: `e2e/xiaozhi-work-session.spec.ts`
- Modify [agent-hub]: `README.md`
- Modify [agent-hub]: `.env.example`
- Modify [xiaozhi]: `docs/superpowers/plans/2026-11-06-agent-hub-xiaozhi-work-session-integration.md`（只勾选已验证项）

**Interfaces:**
- Consumes: Task 2 可运行后端；Task 3-6 完整 Agent Hub 功能。
- Produces: 可重复的端到端验收证据和下一位协作者可用的启动说明。

- [ ] **Step 1: 启动真实最小环境**

启动共享 PostgreSQL/Redis、Xiaozhi API/Worker、Agent Hub。确认 sandbox/RAG 未启动时基础聊天和历史仍可用；若 Agent 主动调用依赖 sandbox 的 Skill，应得到明确错误，不能伪成功。

- [ ] **Step 2: 写真实 E2E 用例**

用例覆盖：

1. 进入 `/chat?mode=work`；
2. 发送唯一文本；
3. URL 更新为真实 conversation ID；
4. 显示单行活动提示；
5. 逐段出现可见正文且无 reasoning；
6. 进入 `/history?mode=work` 能看到该 thread；
7. 点击返回原会话，历史正文一致；
8. 在原 thread 继续发送第二轮；
9. 新建另一轮并停止，UI 停止且后端 run 被 cancel；
10. 切到 daily 后不出现 work 历史或消息。

- [ ] **Step 3: 验证密钥没有进入浏览器**

检查：构建产物、Playwright trace、页面 HTML、浏览器 Network request headers、客户端错误信息。任何位置不得出现 `yxkey_` 或真实 key hash/值。

- [ ] **Step 4: 运行完整前端回归**

Run:

```powershell
pnpm test
pnpm lint
pnpm typecheck
pnpm build
pnpm test:e2e -- e2e/xiaozhi-work-session.spec.ts
```

Expected: 全部 exit 0。

- [ ] **Step 5: 运行后端相关回归**

Run:

```powershell
cd backend
uv run pytest test/unit/test_auth_utils.py test/integration/api/test_apikey_router.py test/unit/services/test_agent_run_service.py test/unit/storage/test_conversation_repository.py -q
```

Expected: PASS。

- [ ] **Step 6: 更新 README 与交接说明**

记录：服务启动顺序、必要 env 名、shared-demo-user 限制、日常/办公后端映射、历史 URL、已知非目标、停止命令。不得写入任何 secret value。

- [ ] **Step 7: 提交 Agent Hub 验收改动**

```powershell
git add e2e README.md .env.example
git commit -m "test: verify xiaozhi work session integration"
```

- [ ] **Step 8: 回写并提交 Xiaozhi 计划状态**

只勾选已有命令输出证明通过的步骤；不得提前勾选。然后在 Xiaozhi 仓库执行：

```powershell
git add docs/superpowers/plans/2026-11-06-agent-hub-xiaozhi-work-session-integration.md
git commit -m "docs: record xiaozhi integration verification"
```

---

## 完成标准

- `mode=daily` 仍走 projects_new，原 Loop/GIS 能力无回归。
- `mode=work` 真实调用 Xiaozhi Agent Loop。
- 正文逐段输出，只展示最终可见正文。
- 活动提示安全、单行、不暴露内部推理。
- stop 同时停止浏览器读取并请求后端 cancel。
- 新会话首次发送后 URL 包含真实 Xiaozhi thread ID。
- work 历史页展示真实 thread，点击可恢复历史并继续对话。
- API Key 仅存在服务端配置；浏览器不可见。
- 后端只需要 PostgreSQL、Redis、API、Worker 即可完成本计划验收。
- 两个仓库均有独立、可审查提交；未获指令前不 push。

## 后续迭代入口

- 统一认证完成后：用真实用户 token/API Key 替换 shared demo BFF 身份。
- projects_new Session F04.5 后：为 daily 实现同一 `ChatSessionTransport`。
- Xiaozhi active run：读取 `/api/agent/thread/{thread_id}/active_run` + SSE cursor，支持刷新恢复。
- 动态 Skill/MCP/RAG：扩展 work agent 配置接口，不直接复用当前未落地的前端选择器。
- 附件、产物、历史搜索/删除/重命名：复用 Xiaozhi 已有 API，分别立项。
