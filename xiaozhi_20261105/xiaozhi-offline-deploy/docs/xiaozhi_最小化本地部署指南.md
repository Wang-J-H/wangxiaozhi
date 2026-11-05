# Xiaozhi 最小化本地部署指南（仅前后端）

> 适用场景：快速在本地跑通 Xiaozhi 前后端，验证界面和对话功能
> **不部署**：MinerU 文档解析、PaddleX OCR、Ollama 本地 Embedding、TEI Reranker
> **大模型**：使用在线 API（OpenAI 兼容接口）
> 版本：v0.7.1.beta1
> 更新日期：2026-11-04

---

## 一、部署范围

### 1.1 启动的服务

| 服务 | 作用 | 是否启动 |
|------|------|---------|
| `xiaozhi-api` | 后端 API（FastAPI） | ✅ |
| `xiaozhi-worker` | 异步任务 Worker（ARQ） | ✅ |
| `xiaozhi-web` | 前端（Nginx） | ✅ |
| `xiaozhi-sandbox-provisioner` | Agent 沙盒调度 | ✅（API 强依赖） |
| `xiaozhi-postgres` | 主数据库 | ✅ |
| `xiaozhi-redis` | 缓存 + 队列 | ✅ |
| `xiaozhi-minio` | 对象存储 | ✅（API 强依赖） |
| `xiaozhi-etcd` | Milvus 元数据 | ✅ |
| `xiaozhi-milvus` | 向量数据库 | ✅ |
| `xiaozhi-graph` | Neo4j 图数据库 | ✅ |
| `xiaozhi-mineru-api` | 文档解析（GPU） | ❌ 跳过 |
| `xiaozhi-paddlex` | OCR（GPU） | ❌ 跳过 |
| `xiaozhi-ollama` | 本地 Embedding | ❌ 跳过 |
| `xiaozhi-reranker` | 本地重排 | ❌ 跳过 |

> MinerU 和 PaddleX 在 compose 里已经带了 `profiles: ["all"]`，默认不会启动。
> Ollama 和 Reranker 默认会启动，需要用本文提供的覆盖文件禁用。

### 1.2 功能可用性

| 功能 | 是否可用 | 说明 |
|------|---------|------|
| 登录、用户/部门管理 | ✅ | |
| 智能体对话 | ✅ | 需配置在线 Chat 模型 |
| 智能体配置、技能管理 | ✅ | |
| MCP 工具集成 | ✅ | |
| 文件管理 | ✅ | 上传到 MinIO 正常 |
| **文档解析（PDF/Word/图片）** | ❌ | 需要 MinerU / PaddleX |
| **知识库向量检索** | ❌ | 需要 Embedding 模型 |
| **知识图谱构建** | ❌ | 依赖解析和 Embedding |
| **知识库评估** | ❌ | 依赖检索 |

> 结论：**能登录、能对话、能配置 Agent，但知识库"上传→解析→检索"链路不完整。**
> 后续要补知识库能力，见第九章。

---

## 二、环境要求

| 项目 | 最低 | 推荐 |
|------|------|------|
| CPU | 4 核 | 8 核 |
| 内存 | 12GB | 16GB+ |
| 磁盘 | 50GB | 100GB+ SSD |
| Docker | 24.0+ | 最新稳定版 |
| Docker Compose | v2.20+ | 最新稳定版 |
| 操作系统 | Linux（Ubuntu 22.04/24.04） | 同左 |
| 网络 | 能访问在线大模型 API | 同左 |

### 2.0 平台限制（重要）

`xiaozhi-api`、`xiaozhi-worker`、`xiaozhi-sandbox-provisioner` 三个服务都挂载了：

```yaml
- /var/run/docker.sock:/var/run/docker.sock
```

因为 Agent 执行代码时需要在宿主机上动态创建沙盒容器。这带来两个限制：

1. **必须是 Linux 宿主机，或 WSL2 里的 Docker**
   - 原生 Windows（PowerShell + Docker Desktop）下 `/var/run/docker.sock` 不存在，容器会挂载失败或无法创建沙盒
   - macOS 同理，不推荐
2. **沙盒镜像 `all-in-one-sandbox:latest` 必须存在**
   - 缺失时 provisioner 健康检查会失败 → `xiaozhi-api` 一直等待 → 整个部署起不来

> 如果只想要纯对话、完全不使用 Agent 代码执行能力，仍需要 provisioner 通过健康检查，否则 API 不会启动。**所以 `all-in-one-sandbox` 镜像是必装项。**

> Windows 用户请使用 **WSL2 + Docker Desktop**，并把项目放在 WSL2 的文件系统内（如 `~/xiaozhi`），不要放在 `/mnt/c/` 下（性能差且权限异常）。

### 2.1 端口占用

| 端口 | 服务 | 是否映射到宿主机 |
|------|------|-----------------|
| 8081 | 前端 Web（Nginx） | ✅ |
| 5433 | PostgreSQL（容器内 5432） | ✅ |
| 6380 | Redis（容器内 6379） | ✅ |
| 7474 / 7687 | Neo4j HTTP / Bolt | ✅ |
| 9000 / 9001 | MinIO API / 控制台 | ✅ |
| 19530 / 9091 | Milvus gRPC / 健康检查 | ✅ |
| **5050** | **后端 API** | **❌ 仅容器内** |

> ⚠️ 注意：当前 `docker-compose.yml` 里 **`xiaozhi-api` 没有配置 `ports`**，5050 只在容器网络内可达。
> 前端通过 Nginx 反代 `/api` 访问后端，所以浏览器访问 `http://localhost:8081` 即可。
> 如果你需要直接调 API 或看 `/docs`，见 4.5.3 的可选配置。

启动前确认这些端口没有被占用：

```bash
for p in 8081 5433 6380 7474 7687 9000 9001 19530 9091; do
  ss -tlnp "sport = :$p" 2>/dev/null | grep -q LISTEN && echo "端口 $p 被占用"
done
```

---

## 三、前置条件：docker 目录与镜像

### 3.0 当前已有的 `docker/` 目录

`docker/` 目录已经确认完整且无品牌残留，共 11 个文件：

```
docker/
├── api.Dockerfile
├── web.Dockerfile
├── mineru.Dockerfile          # 最小化不用
├── paddlex.Dockerfile         # 最小化不用
├── PP-StructureV3.yaml        # 最小化不用
├── nginx/
│   ├── nginx.conf
│   └── default.conf
└── sandbox_provisioner/
    ├── Dockerfile
    ├── app.py
    ├── requirements.txt
    └── sandbox.env
```

**把这个 `docker/` 目录整个放回项目根目录**（和 `docker-compose.yml` 同级）即可，不需要改动。

已核对的关键点：

| 检查项 | 结果 |
|--------|------|
| yuxi 内容残留 | 0 处 |
| yuxi 文件名 | 0 个 |
| `sandbox.env` | `CHECK_XIAOZHI_SANDBOX_ENV_EXISTS=True`，已是 XIAOZHI |
| nginx `/api/` 反代 | `proxy_pass http://xiaozhi-api:5050/api/`，含 SSE 配置 |
| Dockerfile COPY 依赖 | `backend/pyproject.toml`、`.python-version`、`uv.lock`、`package`、`server`、`web/*` 均存在 |
| uv.lock 与 pyproject 一致性 | `xiaozhi-workspace` / `xiaozhi` 版本均 0.7.1.beta1，editable 路径一致 |

### 路径 A：源码构建（推荐，docker 目录已就绪）

三个业务镜像从源码构建，基础镜像仍需拉取。

**构建前先拉基础镜像**（国内建议先单独执行，失败了好排查）：

```bash
docker pull python:3.13-slim
docker pull node:24-slim
docker pull node:24-alpine
docker pull nginx:alpine
docker pull ghcr.io/astral-sh/uv:0.11.26
docker pull postgres:16
docker pull redis:7-alpine
docker pull neo4j:5.26
docker pull minio/minio:RELEASE.2023-03-20T20-16-18Z
docker pull milvusdb/milvus:v2.5.6
docker pull quay.io/coreos/etcd:v3.5.5
docker pull enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
```

**构建三个业务镜像：**

```bash
docker compose build xiaozhi-api xiaozhi-web xiaozhi-sandbox-provisioner
```

预估：`xiaozhi-api` 10-25 分钟（最大），`xiaozhi-web` 5-10 分钟，`xiaozhi-sandbox-provisioner` 1-2 分钟。
磁盘预留 **15GB** 以上（构建缓存 + 镜像）。

**两个已知的构建卡点：**

1. **`ghcr.io/astral-sh/uv:0.11.26` 拉不到**
   国内访问 ghcr.io 经常超时。解决方案：
   ```bash
   # 配置 Docker 代理，或使用镜像加速
   # 也可以从能联网的机器上 save/load
   docker pull ghcr.io/astral-sh/uv:0.11.26
   ```

2. **`uv sync --frozen` 走默认 PyPI 源**
   `api.Dockerfile` 里没有指定国内源，依赖较多（LangChain、Milvus SDK 等），容易超时。
   在构建时注入镜像源：
   ```bash
   docker compose build \
     --build-arg UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
     xiaozhi-api
   ```
   如果上面不生效，直接改 `docker/api.Dockerfile`，把：
   ```dockerfile
   RUN uv sync --no-cache --group test --no-dev --frozen
   ```
   改成：
   ```dockerfile
   RUN uv sync --no-cache --group test --no-dev --frozen \
       --index-url https://pypi.tuna.tsinghua.edu.cn/simple
   ```

**构建前建议加 `.dockerignore`**（项目根目录新建），否则构建上下文会把 `docker/volumes/` 里的数据一起发给 Docker daemon：

```
.git
**/__pycache__
**/*.pyc
web/node_modules
docker/volumes
docker/models
xiaozhi-images
```

### 路径 B：导入现成镜像（有镜像包时更快）

如果提供方已经导出了镜像，优先用这个方式，跳过构建。

**业务镜像：**

| 镜像 | 说明 |
|------|------|
| `xiaozhi-api:0.7.1.beta1` | 后端 API + Worker |
| `xiaozhi-web:0.7.1.beta1` | 前端 |
| `xiaozhi-sandbox-provisioner:0.7.1.beta1` | 沙盒调度 |

**基础镜像（与路径 A 相同）：** postgres:16、redis:7-alpine、neo4j:5.26、minio、milvus:v2.5.6、etcd:v3.5.5、all-in-one-sandbox:latest。

**最小化部署不需要：** `mineru-vllm:latest`、`paddlex:latest`、`ollama/ollama`、`text-embeddings-inference`。

**导入命令：**

```bash
# 方式 1：使用项目自带脚本
bash load-images.sh /path/to/xiaozhi-images/

# 方式 2：手动导入
for f in /path/to/xiaozhi-images/*.tar; do
  echo "导入 $f ..."
  docker load -i "$f"
done

# 校验
docker images | grep -E "xiaozhi|postgres|redis|neo4j|milvus|etcd|minio"
```

---

## 四、部署步骤

### 4.1 解压并放置 `docker/` 目录

```bash
unzip xiaozhi-offline-deploy_已修改_20261104.zip
cd xiaozhi-offline-deploy

# 把 docker 目录放到项目根（和 docker-compose.yml 同级）
# 最终结构应为：
# xiaozhi-offline-deploy/
# ├── docker-compose.yml
# ├── .env
# ├── backend/
# ├── web/
# └── docker/
#     ├── api.Dockerfile
#     ├── web.Dockerfile
#     ├── nginx/
#     └── sandbox_provisioner/
```

确认 docker 目录就位：

```bash
ls docker/api.Dockerfile docker/web.Dockerfile docker/nginx/default.conf \
   docker/sandbox_provisioner/Dockerfile docker/sandbox_provisioner/app.py
```

四个文件都存在，才能继续构建。

### 4.2 创建数据目录

```bash
mkdir -p docker/volumes/{xiaozhi,postgresql,redis,models}
mkdir -p docker/volumes/neo4j/{data,logs}
mkdir -p docker/volumes/milvus/{milvus,logs,etcd,minio,minio_config}
```

> `docker/sandbox_provisioner/sandbox.env` **已经存在**（内容为 `CHECK_XIAOZHI_SANDBOX_ENV_EXISTS=True`），不需要再 `touch`。
> 只有在拿到的是不完整目录时，才需要手动创建这个文件，否则 Docker 会把挂载点当成目录，导致 provisioner 启动失败。

### 4.3 创建最小化覆盖文件

新建 `docker-compose.min.yml`：

```yaml
# 最小化部署：禁用 Ollama 和 Reranker
services:
  xiaozhi-ollama:
    profiles: ["full"]
  xiaozhi-reranker:
    profiles: ["full"]
```

> MinerU 和 PaddleX 已在主 compose 里声明 `profiles: ["all"]`，无需额外处理。
> 注意：`mineru.Dockerfile`、`paddlex.Dockerfile` 虽然存在，但因为没启动对应服务，构建时不会用到。

### 4.4 修改 `.env`

```bash
cp .env .env.bak
```

编辑 `.env`，至少修改这几项：

```bash
# ===== 必改：JWT 密钥（换成随机字符串）=====
JWT_SECRET_KEY=<用 openssl rand -hex 32 生成>

# ===== 管理员账号 =====
# 注意：系统没有"自动创建管理员"机制，XIAOZHI_SUPER_ADMIN_* 在代码里无引用。
# 数据表建好后需手动执行一次 scripts/seed_admin.py，
# 详见 docs/xiaozhi_源码构建与部署指南.md 第五节。

# ===== 必改：数据库密码 =====
# 注意：原 .env 里没有这三项，需要自己新增。
# 不新增时 compose 会用默认值 postgres/postgres/xiaozhi。
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<设置一个强密码>
POSTGRES_DB=xiaozhi

# ===== 必改：Neo4j 密码（原值是 0123456789）=====
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<设置一个强密码>

# ===== 建议改：MinIO 密钥（原值是 minioadmin）=====
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=<设置一个强密码>

# ===== 保持 false（保留完整界面）=====
LITE_MODE=false

# ===== 品牌配置（保持默认）=====
XIAOZHI_BRAND_FILE_PATH=package/xiaozhi/config/static/info.local.yaml
```

生成随机密钥：

```bash
openssl rand -hex 32
```

> ⚠️ **密码必须前后一致**：`POSTGRES_PASSWORD` 同时被 API 的 `POSTGRES_URL` 和 postgres 容器读取，两边不一致会导致 API 连不上数据库、一直 unhealthy。
> 如果之前已经启动过并生成了 `docker/volumes/postgresql` 数据，改密码后旧数据卷仍用旧密码，需要清空数据目录或进库改密码。**首次部署无此问题。**
> `LITE_MODE=true` 会隐藏知识库/图谱/评估相关路由，最小化部署建议保持 `false`，让界面完整，只是相关功能点进去会报错。

### 4.5 构建并启动最小服务集

> ❌ **不要运行 `deploy.sh`**。它是为完整部署设计的：会检查 11 个镜像（含 MinerU GPU 镜像）、并 `up -d` 启动全部服务。最小化部署请按下面手动执行。

#### 4.5.1 构建三个业务镜像

如果走的是「路径 A：源码构建」，先构建：

```bash
docker compose build xiaozhi-api xiaozhi-web xiaozhi-sandbox-provisioner
```

构建过程会依次完成：

| 镜像 | 主要动作 | 预估耗时 |
|------|---------|---------|
| `xiaozhi-sandbox-provisioner` | pip install 6 个包 | 1-2 分钟 |
| `xiaozhi-web` | pnpm install + vite build | 5-10 分钟 |
| `xiaozhi-api` | apt 装 libreoffice/ffmpeg + uv sync 全量依赖 | 10-25 分钟 |

构建完成后确认：

```bash
docker images | grep xiaozhi
# 应看到三行：
# xiaozhi-api                    0.7.1.beta1
# xiaozhi-web                    0.7.1.beta1
# xiaozhi-sandbox-provisioner    0.7.1.beta1
```

> 如果走的是「路径 B：导入镜像」，跳过这一步，直接执行 4.5.2。

#### 4.5.2 启动

```bash
docker compose -f docker-compose.yml -f docker-compose.min.yml up -d
```

确认启动的容器：

```bash
docker compose ps
```

预期看到 10 个容器（不含 mineru/paddlex/ollama/reranker）：

```
xiaozhi-api
xiaozhi-worker
xiaozhi-web
xiaozhi-sandbox-provisioner
xiaozhi-postgres
xiaozhi-redis
xiaozhi-minio
xiaozhi-etcd
xiaozhi-milvus
xiaozhi-graph
```

#### 4.5.3 可选：把后端 API 端口暴露到宿主机

如果同事需要直接调用 API、查看 Swagger 文档（`/docs`），在 `docker-compose.min.yml` 里追加：

```yaml
services:
  xiaozhi-ollama:
    profiles: ["full"]
  xiaozhi-reranker:
    profiles: ["full"]
  xiaozhi-api:
    ports:
      - "5050:5050"
```

> 暴露后可直接访问 `http://localhost:5050/docs`。
> 仅内网调试时使用，不要在生产环境对外开放。

### 4.6 等待服务就绪

首次启动需要初始化数据库，约 2-5 分钟。API 的 `start_period` 是 180 秒，请耐心等待。

```bash
# 实时看 API 日志，出现 XIAOZHI 字符画和 "startup complete" 即成功
docker compose logs -f xiaozhi-api
```

健康检查（三选一）：

```bash
# 方式 1：通过前端 Nginx 反代（默认部署可用）
curl http://localhost:8081/api/system/health
# 预期：{"status":"ok","message":"服务正常运行","version":"0.7.1.beta1"}

# 方式 2：在容器内检查
docker exec xiaozhi-api curl -s http://localhost:5050/api/system/health

# 方式 3：如果做了 4.5.3 的端口暴露
curl http://localhost:5050/api/system/health

# 前端页面
curl -I http://localhost:8081
# 预期：HTTP/1.1 200 OK
```

容器健康状态：

```bash
docker compose ps
# 关注 STATUS 列，healthy 表示通过健康检查
```

### 4.7 登录

浏览器打开：**http://localhost:8081**

使用 `scripts/seed_admin.py` 创建的超级管理员登录：

| 登录标识（uid） | 密码 |
|--------|------|
| `admin` | `admin123`（默认值，可用 `SEED_ADMIN_PASSWORD` 覆盖） |

> 登录接口 `POST /api/auth/token` 的 `username` 字段填的是 uid，
> 不是显示名称，填错会返回「登录标识或密码错误」。

---

## 五、配置在线大模型

### 5.1 方式一：Web 界面（推荐）

1. 登录后进入 **智能体管理 → 模型供应商**
2. 点击 **添加供应商**
3. 填写：

| 字段 | 示例值 | 说明 |
|------|--------|------|
| Provider ID | `online-llm` | 唯一标识，小写字母/数字/短横线 |
| 显示名称 | `在线大模型` | 界面上展示的名字 |
| 类型 | `openai` | OpenAI 兼容协议 |
| Base URL | `https://api.xxx.com/v1` | **要带 `/v1`** |
| API Key | `sk-xxxx` | 在线平台申请的密钥 |
| 能力 | 勾选 `chat` | 最小化部署只需对话能力 |
| 模型 | 填模型 ID，如 `qwen-max` / `deepseek-chat` | 以服务商文档为准 |

4. 保存后，进入 **智能体管理 → 默认智能体 → 模型设置**，选择刚添加的模型

### 5.2 方式二：SQL 直接写入（界面不可用时）

进入 PostgreSQL 容器：

```bash
docker exec -it xiaozhi-postgres psql -U postgres -d xiaozhi
```

执行（把占位符替换成实际值）：

```sql
INSERT INTO model_providers (
    provider_id,
    display_name,
    provider_type,
    default_protocol,
    base_url,
    api_key,
    capabilities,
    enabled_models,
    is_enabled,
    is_builtin
) VALUES (
    'online-llm',
    '在线大模型',
    'openai',
    'openai',
    'https://api.xxx.com/v1',
    'sk-xxxx',
    '["chat"]'::jsonb,
    '[{"id":"qwen-max","type":"chat","display_name":"qwen-max"}]'::jsonb,
    TRUE,
    FALSE
);
```

验证：

```sql
SELECT provider_id, display_name, base_url, capabilities, enabled_models, is_enabled
FROM model_providers;
```

> `api_key` 会以明文存入数据库，请确保数据库访问权限受控。
> 写入后建议重启 API 让缓存刷新：`docker compose restart xiaozhi-api`。

### 5.3 验证对话

1. 打开前端，进入对话页
2. 新建会话，发送"你好"
3. 能正常返回内容即配置成功

如果报模型未配置，检查：
- `base_url` 是否带 `/v1`
- 模型 ID 是否与服务商一致
- 服务器能否访问该 API：`curl https://api.xxx.com/v1/models -H "Authorization: Bearer sk-xxxx"`

---

## 六、常用运维命令

```bash
# 查看所有容器状态
docker compose ps

# 查看 API 日志
docker compose logs -f xiaozhi-api

# 查看 Worker 日志
docker compose logs -f xiaozhi-worker

# 重启后端
docker compose restart xiaozhi-api

# 停止全部（保留数据）
docker compose down

# 停止并删除数据（⚠️ 会清空数据库，谨慎）
# docker compose down -v
# rm -rf docker/volumes

# 进入后端容器
docker exec -it xiaozhi-api /bin/bash

# 进入数据库
docker exec -it xiaozhi-postgres psql -U postgres -d xiaozhi
```

---

## 七、常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 构建报 `failed to resolve source metadata for ghcr.io/astral-sh/uv` | 国内访问 ghcr.io 超时 | 配 Docker 代理，或从能联网的机器 `docker save/load` |
| 构建报 `uv sync` 超时 / `ReadTimeout` | 走默认 PyPI 源 | 按第三章「路径 A」的说明注入 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| 构建报 `COPY failed: file not found: backend/.python-version` | 压缩包不完整或解压丢隐藏文件 | 确认 `ls -la backend/` 能看到 `.python-version` |
| `pnpm install` 失败 | npm 源或网络问题 | Dockerfile 已用 npmmirror；仍失败可换 `registry.npmmirror.com` |
| `pnpm run build` 内存不足被 kill | Node 构建需要 2GB+ | 给 Docker 分配 ≥4GB 内存 |
| 构建上下文传输极慢 | 缺少 `.dockerignore`，把 volumes 也传了 | 按第三章「路径 A」创建 `.dockerignore` |
| `缺少 docker/ 目录` | docker 目录没放到项目根 | 放到与 `docker-compose.yml` 同级 |
| `no such image: xiaozhi-api` | 既没构建也没导入 | 执行 4.5.1 构建，或 `docker load -i xxx.tar` |
| API 一直 unhealthy | PostgreSQL 未就绪 / 密码不一致 | 看 `docker compose logs xiaozhi-postgres`，确认 `.env` 密码一致 |
| API 容器起不来，卡在 `depends_on sandbox-provisioner` | provisioner 健康检查未通过 | 看 `docker compose logs xiaozhi-sandbox-provisioner`，确认 `all-in-one-sandbox` 镜像已导入、`/var/run/docker.sock` 可访问 |
| `sandbox-provisioner` 启动失败 | `sandbox.env` 被当成目录 | 删掉该目录，重新放回真实的 `sandbox.env` 文件 |
| provisioner 报 `Cannot connect to the Docker daemon` | 宿主机 socket 未挂载或权限不足 | Linux 下确认 `ls -l /var/run/docker.sock`，必要时 `sudo usermod -aG docker $USER` 后重新登录 |
| `localhost:5050` 访问不了 | compose 未映射 5050 | 属正常现象，走 8081 反代；需要直连见 4.5.3 |
| 前端 502 | API 未启动完成 | 等待 2-5 分钟，或看 API 日志 |
| 页面能开但登录失败 | 管理员未创建 | 执行 `scripts/seed_admin.py`，见源码构建与部署指南第五节 |
| 对话报"模型未配置" | 未添加模型供应商 | 按第五章配置 |
| 上传文档一直失败 | 未部署 MinerU | 最小化部署的正常现象，见第八章 |
| 端口被占用 | 宿主机已有服务 | 改 `docker-compose.yml` 左侧端口映射 |
| `deploy.sh` 报缺少镜像 | 脚本按完整部署校验（含 MinerU） | 不要用 `deploy.sh`，按 4.5 手动启动 |

---

## 八、已知限制

最小化部署**不包含**以下能力，属于预期行为：

1. **文档解析不可用**
   上传 PDF/Word/图片后，解析任务会失败，因为 `MINERU_API_URI` 指向的容器未启动。
   纯文本文件（`.txt`/`.md`）可能走内置解析器，行为取决于文件类型。

2. **知识库检索不可用**
   没有 Embedding 模型，文档无法向量化，检索会返回空或报错。

3. **知识图谱不可用**
   依赖解析 + Embedding + 实体抽取链路。

4. **知识库评估不可用**
   依赖检索结果。

5. **Reranker 不可用**
   检索降级，但最小化场景下本来就没有检索。

### 8.1 可选：进一步省内存（约 6GB 可跑）

如果机器内存只有 8GB，可以尝试再关掉 Milvus、etcd、Neo4j，并把 `LITE_MODE=true`：

```yaml
# docker-compose.min.yml
services:
  xiaozhi-ollama:
    profiles: ["full"]
  xiaozhi-reranker:
    profiles: ["full"]
  xiaozhi-milvus:
    profiles: ["full"]
  xiaozhi-etcd:
    profiles: ["full"]
  xiaozhi-graph:
    profiles: ["full"]
```

```bash
# .env
LITE_MODE=true
```

启动时只保留：postgres、redis、minio、sandbox-provisioner、api、worker、web。

⚠️ **这一档没有经过完整验证**：
- `LITE_MODE=true` 会隐藏知识库/图谱/评估路由，前端界面也会精简
- 个别启动流程可能仍尝试连接 Milvus，需要看 API 日志确认
- 如果 API 报连接 Milvus/Neo4j 失败，就退回上一档（保留这三个服务）

> 内存充足时建议用默认最小化方案（10 个服务），稳定性更好。

---

## 九、后续扩展（按需）

### 9.1 补在线 Embedding（不装本地模型）

在模型供应商里再添加一个供应商，能力勾选 `embedding`：

| 字段 | 示例 |
|------|------|
| Provider ID | `online-embedding` |
| Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 能力 | `embedding` |
| 模型 | `text-embedding-v4`，维度 `1024` |

> **维度必须与 Milvus collection 一致**，首次建库建议固定 1024。

### 9.2 补文档解析

两种选择：

- **在线解析**：配置 MinerU 官方 API 或云厂商文档解析服务
- **本地 CPU 解析**：部署 MinerU CPU 版（`MINERU_BACKEND=pipeline`），需要 8-10GB 内存

### 9.3 补 Reranker

可以配置在线 Rerank API（如 DashScope `qwen3-rerank`），不需要启动本地 TEI。

---

## 十、部署检查清单

- [ ] Docker / Compose 版本满足要求
- [ ] 端口 8081/5433/6380/7474/7687/9000/9001/19530/9091 未被占用
- [ ] `docker/` 目录已放到项目根（11 个文件齐全）
- [ ] 基础镜像已拉取（含 `all-in-one-sandbox:latest`）
- [ ] 三个业务镜像已构建或导入（`docker images | grep xiaozhi`）
- [ ] `.dockerignore` 已创建（避免 volumes 进入构建上下文）
- [ ] 宿主机是 Linux 或 WSL2，`/var/run/docker.sock` 存在且可读
- [ ] `docker/volumes/` 目录已创建
- [ ] `docker/sandbox_provisioner/sandbox.env` 存在且内容为 `CHECK_XIAOZHI_SANDBOX_ENV_EXISTS=True`
- [ ] `.env` 的 JWT 密钥、管理员密码、数据库密码已修改
- [ ] `docker-compose.min.yml` 已创建
- [ ] 10 个容器全部 Up（`docker compose ps`）
- [ ] `xiaozhi-sandbox-provisioner` 状态为 healthy
- [ ] `/api/system/health` 返回 ok（走 8081 或容器内）
- [ ] 前端 8081 可访问并登录成功
- [ ] 在线 Chat 模型已配置
- [ ] 对话测试通过

---

*本指南基于 `xiaozhi-offline-deploy` v0.7.1.beta1 源码和 `docker-compose.yml` 实际配置编写。*
