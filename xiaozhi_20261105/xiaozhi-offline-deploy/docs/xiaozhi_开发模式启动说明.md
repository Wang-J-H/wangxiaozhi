# Xiaozhi 开发模式启动说明

> 面向需要**改代码、看效果**的开发同事
> 适用：Ubuntu 22.04 / 24.04 + Docker Compose v2
> 版本：v0.7.1.beta1

---

## Agent Hub 联调：Windows 原生最小后端

这一模式只启动 Xiaozhi API 与 Agent Run Worker。基础设施复用本机现有 PostgreSQL、Redis 容器；不启动 Xiaozhi Web，也不依赖 RAG 服务。

### 适用边界

- 必需：Python venv、PostgreSQL 中独立的 `xiaozhi` DB、Redis 独立逻辑库 `/1`、API、Worker。
- 模型：当前联调使用 DeepSeek；`DEEPSEEK_API_KEY` 仅通过 API/Worker 进程环境注入，不写入 Git。
- 聊天与历史会话：不需要 Milvus、Neo4j、MinIO、知识库解析服务。
- Skill 仅在需要 Shell 或文件系统沙盒时才要求另启 sandbox provisioner；纯聊天 smoke 不需要。
- 禁止复制旧 `.venv`，禁止删除或重建共享 Docker volume。

### 首次准备

在新仓库根目录执行：

```powershell
# 旧配置只做本地复制；根 .gitignore 已忽略 .env
Copy-Item S:\Projects\xiaozhi-offline-deploy\.env .\.env

cd backend
$env:UV_HTTP_TIMEOUT='180'
$env:UV_CONCURRENT_DOWNLOADS='4'
uv sync --frozen --no-dev --default-index 'https://pypi.org/simple'
cd ..
```

`.env` 中共享基础设施 URL 使用宿主机已发布端口。示例：

```dotenv
POSTGRES_URL=postgresql+psycopg://postgres:<password>@127.0.0.1:5432/xiaozhi
REDIS_URL=redis://127.0.0.1:6379/1
```

`xiaozhi` 必须是独立 DB；不要把表写进 Agent Loop 原有业务 DB。Redis 使用 `/1`，避免和其他服务的 key 混用。

### 启动 API 与 Worker

打开两个 PowerShell，均从仓库根目录启动。两个进程使用同一份 `.env`；Worker 必须拿到与默认智能体模型配置对应的 DeepSeek Key。

API：

```powershell
$env:DEEPSEEK_API_KEY='<local-secret>'
.\backend\.venv\Scripts\python.exe .\scripts\dev\run_native_api.py
```

Worker：

```powershell
$env:DEEPSEEK_API_KEY='<local-secret>'
.\backend\.venv\Scripts\python.exe .\scripts\dev\run_native_worker.py
```

两个启动器都会加载当前 checkout 的 `backend/package`，并在 Windows 使用 Selector event loop。它们不包含旧版 `User.__table__` schema monkey patch。

### Agent Hub 契约 smoke

先为联调用户创建一个启用的 `yxkey_` API Key。再开第三个 PowerShell：

```powershell
$env:XIAOZHI_BASE_URL='http://127.0.0.1:5050'
$env:XIAOZHI_API_KEY='<local-yxkey-secret>'
.\backend\.venv\Scripts\python.exe .\scripts\dev\smoke_agent_hub_contract.py
```

脚本不会打印 API Key。它会真实验证：health、默认智能体、创建 thread/run、`verbose=false` SSE、最终正文、历史会话、第二轮取消终态。输出中的 run/thread ID 可用于排查。

---

## 一、先搞清楚两种模式

| | 镜像部署模式 | **开发模式（本文）** |
|---|---|---|
| 代码来源 | 打包进镜像 | 宿主机源码，挂载进容器 |
| 改代码后 | 要重新 build 镜像 | **自动生效** |
| 后端 | `uvicorn` 正常启动 | `uvicorn --reload`，改完自动重启 |
| 前端 | nginx 托管 dist | Vite dev server，HMR 热更新 |
| 访问端口 | 8081 | **5173** |
| 用途 | 给用户用 | 给自己改代码 |

**关键点：开发模式不需要在宿主机装 Python、torch、Node。**
依赖都在 `xiaozhi-api` 镜像里（torch 就有 3GB，别自己装）。宿主机只需要 Docker。

---

## 二、你需要拿到的东西

### 2.1 源码

```
xiaozhi-offline-deploy/
├── backend/
├── web/
├── docker/                    ← 11 个构建文件
├── docker-compose.yml
├── docker-compose.min.yml     ← 最小化（禁用 ollama/reranker）
├── docker-compose.dev.yml     ← 开发模式（源码挂载）
├── .env
└── deploy-min.sh
```

### 2.2 镜像

只需要两个业务镜像 + 七个基础镜像：

**业务镜像（必需）**

| 镜像 | 用途 |
|------|------|
| `xiaozhi-api:0.7.1.beta1` | 后端运行时（Python 3.13 + 全部依赖 + torch） |
| `xiaozhi-sandbox-provisioner:0.7.1.beta1` | 沙盒调度（api 强依赖） |

**基础镜像（必需）**

```
postgres:16
redis:7-alpine
neo4j:5.26
minio/minio:RELEASE.2023-03-20T20-16-18Z
milvusdb/milvus:v2.5.6
quay.io/coreos/etcd:v3.5.5
enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
```

**不需要：** `xiaozhi-web`（前端用 Vite 跑）、`mineru-vllm`、`paddlex`、`ollama`、`tei`、`xiaozhi-model-data`。

### 2.3 导入镜像

```bash
bash load-images.sh /path/to/images/
# 或
docker load -i xiaozhi-api_0.7.1.beta1.tar.gz
docker load -i xiaozhi-sandbox-provisioner_0.7.1.beta1.tar.gz
```

确认：

```bash
docker images | grep -E "xiaozhi|postgres|redis|neo4j|milvus|etcd|minio"
```

---

## 三、首次启动

### 3.1 准备目录

```bash
cd xiaozhi-offline-deploy

mkdir -p docker/volumes/{xiaozhi,postgresql,redis,models}
mkdir -p docker/volumes/neo4j/{data,logs}
mkdir -p docker/volumes/milvus/{milvus,logs,etcd,minio,minio_config}
```

### 3.2 配置前端 API 代理

Vite 的 `vite.config.js` 默认把 `/api` 代理到 `http://api:5050`（容器名），需要改成实际的容器名。

在 `web/` 下新建 `.env.development.local`：

```bash
echo "VITE_API_URL=http://xiaozhi-api:5050" > web/.env.development.local
```

> 不改这个，前端页面能打开，但所有接口都会 502。

### 3.3 配置 `.env`

```bash
cp .env .env.bak
openssl rand -hex 32
```

编辑 `.env`，至少改三项：

```bash
JWT_SECRET_KEY=<上面生成的随机串>
NEO4J_PASSWORD=<你的密码>
```

> 管理员账号不在 `.env` 里配。系统没有自动初始化机制，
> 需要手动执行 `scripts/seed_admin.py` 创建（见第三节）。

保持：

```bash
LITE_MODE=false
XIAOZHI_BRAND_FILE_PATH=package/xiaozhi/config/static/info.local.yaml
```

### 3.4 启动

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.min.yml \
  -f docker-compose.dev.yml \
  up -d
```

第一次启动会执行 `pnpm install`（前端依赖，约 2-5 分钟），后端初始化数据库约 1-3 分钟。

看进度：

```bash
docker compose logs -f xiaozhi-web-dev
docker compose logs -f xiaozhi-api
```

### 3.5 访问

| 地址 | 说明 |
|------|------|
| **http://localhost:5173** | 开发用前端（Vite，热更新） |
| http://localhost:5050/docs | 后端 Swagger 文档 |
| http://localhost:5050/api/system/health | 健康检查 |
| http://localhost:8081 | 生产版前端（如果也启动了 web 容器） |

管理员账号需要手动创建（系统没有自动初始化机制）：

```bash
docker compose run --rm --no-deps --entrypoint python \
  xiaozhi-api /app/scripts/seed_admin.py
```

默认创建 uid=`admin` / 密码 `admin123`。登录接口的 `username` 字段填 uid，
不是显示名称。

---

## 四、改代码看效果

### 4.1 改后端

比如改 `backend/server/routers/system_router.py` 的返回内容：

```python
return {"status": "ok", "message": "我改过了", "version": get_version()}
```

保存后：

```bash
docker compose logs -f xiaozhi-api
# 会看到 "WatchFiles detected changes ... Reloading"
```

约 1-2 秒后生效，刷新接口或页面即可看到。

**可改的目录：**

| 目录 | 说明 |
|------|------|
| `backend/server/` | 路由、中间件、启动逻辑 |
| `backend/package/xiaozhi/` | 核心业务包（Agent、知识库、存储层） |

**改依赖**（`pyproject.toml`）不会自动生效，需要重建镜像：

```bash
docker compose build xiaozhi-api
docker compose -f docker-compose.yml -f docker-compose.min.yml -f docker-compose.dev.yml up -d xiaozhi-api
```

### 4.2 改前端

改 `web/src/` 下任何 `.vue` / `.js` 文件，保存后浏览器**自动更新**，不用刷新。

```bash
docker compose logs -f xiaozhi-web-dev
# 会看到 "hmr update /src/..."
```

**注意：** 前端 `node_modules` 用的是容器内的匿名卷，不要在宿主机执行 `pnpm install`，会冲突。

### 4.3 改 Worker

`xiaozhi-worker` 也挂了源码，并加了 `--watch`。如果改动没生效（arq 的 watch 有时不灵），手动重启：

```bash
docker compose restart xiaozhi-worker
```

---

## 五、常用命令

```bash
# 看所有容器
docker compose -f docker-compose.yml -f docker-compose.min.yml -f docker-compose.dev.yml ps

# 看后端日志（含热重载提示）
docker compose logs -f xiaozhi-api

# 看前端日志（含 HMR 提示）
docker compose logs -f xiaozhi-web-dev

# 只重启后端
docker compose restart xiaozhi-api

# 进后端容器（可以直接跑 python、看包）
docker exec -it xiaozhi-api bash

# 进数据库
docker exec -it xiaozhi-postgres psql -U postgres -d xiaozhi

# 停掉开发前端
docker compose stop xiaozhi-web-dev

# 全部停止（保留数据）
docker compose down
```

建议在项目根建个别名，省得每次写三个 `-f`：

```bash
alias dc='docker compose -f docker-compose.yml -f docker-compose.min.yml -f docker-compose.dev.yml'
# 之后直接 dc ps / dc logs -f xiaozhi-api
```

---

## 六、常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 5173 打不开 | 前端容器还在 pnpm install | `docker compose logs -f xiaozhi-web-dev` 等装完 |
| 页面能开但接口 502 | `VITE_API_URL` 没配 | 检查 `web/.env.development.local`，改完重启 web-dev |
| 改后端没反应 | 改的目录不在 `--reload-dir` 里 | 只挂载了 `backend/server` 和 `backend/package`，其他目录改了不生效 |
| `ModuleNotFoundError` | 新加了依赖但镜像里没有 | 重建 api 镜像，或在容器内 `uv sync` |
| 前端样式不更新 | 浏览器缓存 | 硬刷新 Ctrl+Shift+R |
| 端口 5173 被占用 | 本地已有 vite | 改 `docker-compose.dev.yml` 里的 `5173:5173` 左侧端口 |
| 后端启动报数据库连接失败 | `.env` 密码和已有数据卷不一致 | 首次部署删掉 `docker/volumes/postgresql` 重来 |
| `docker.sock` 权限拒绝 | 用户不在 docker 组 | `sudo usermod -aG docker $USER` 后重新登录 |

---

## 七、和镜像部署的差异清单

| 项目 | 镜像部署 | 开发模式 |
|------|---------|---------|
| 前端端口 | 8081 | 5173 |
| 后端端口 | 容器内 5050 | 宿主机 5050（开发模式建议暴露） |
| 前端代码 | 构建后的 dist | 源码，Vite 实时编译 |
| 后端代码 | 镜像内 COPY | 宿主机挂载 |
| 改代码 | 重新 build | 自动生效 |
| 依赖变更 | 重新 build | 重新 build |
| 需要的镜像 | 3 个业务 + 7 个基础 | **2 个业务** + 7 个基础 |

> 开发模式下 `xiaozhi-api` 的 5050 建议映射到宿主机，方便直接调接口和看 `/docs`。
> 如果 `docker-compose.yml` 里没映射，在 `docker-compose.dev.yml` 的 `xiaozhi-api` 下加：
> ```yaml
> ports:
>   - "5050:5050"
> ```

---

*基于 `xiaozhi-offline-deploy` v0.7.1.beta1 实际配置编写。*
