# xiaozhi 源码构建与部署指南

> 版本：0.7.1.beta1
> 适用场景：拿到源码，在自己的机器上构建镜像并部署全套服务

---

## 一、前置条件

| 项目 | 要求 |
| --- | --- |
| Docker | 24.0+，需支持 BuildKit |
| Docker Compose | v2（`docker compose` 子命令形式，不是 `docker-compose`） |
| 内存 | 建议 16GB 以上（Milvus + Neo4j + 后端同时跑） |
| 磁盘 | 源码 100MB + 镜像约 8GB + 数据卷若干 |
| 网络 | 首次构建需拉取基础镜像和 npm/pypi 依赖 |

确认环境：

```bash
docker --version
docker compose version
```

---

## 二、准备配置

```bash
cp .env.example .env
```

然后编辑 `.env`，**至少改这三处**：

1. **`JWT_SECRET_KEY`** —— 必须填，否则登录接口直接 500
   ```bash
   openssl rand -hex 32
   ```
   把输出粘进去。原因是 `docker-compose.yml` 里硬编码了 `XIAOZHI_ENV: production`，
   生产模式下后端不会自动生成临时密钥，缺了就直接抛异常。

2. **各种密码** —— `NEO4J_PASSWORD`、`MINIO_SECRET_KEY` 换成自己的

3. **`XIAOZHI_CORS_ORIGINS`** —— 只有浏览器直连 5050 端口时才需要配。
   前端走 nginx 反代 `/api` 属于同源请求，不受 CORS 限制。

---

## 三、构建镜像

三个服务需要本地构建，其余是公共镜像直接拉取：

```bash
docker compose build xiaozhi-api xiaozhi-web xiaozhi-sandbox-provisioner
```

首次构建约 10–20 分钟（api 镜像含完整 Python 依赖，约 6GB）。

**内网环境注意**：`postgres:16`、`redis:7-alpine`、`milvusdb/milvus:v2.5.6`、
`neo4j:5.26`、`minio/minio`、`quay.io/coreos/etcd:v3.5.5` 这些需要能访问 Docker Hub
（或已配置私有 registry 镜像加速）。离线场景请预先 `docker save` / `docker load`。

---

## 四、启动

```bash
docker compose -f docker-compose.yml -f docker-compose.api.yml up -d
```

**必须带 `-f docker-compose.api.yml`**。5050 端口映射只写在覆盖文件里，
只用 `docker-compose.yml` 启动的话，宿主机访问不到 API。

嫌每次敲太长，可以固化：

```bash
echo 'export COMPOSE_FILE=docker-compose.yml:docker-compose.api.yml' >> ~/.bashrc
source ~/.bashrc
```

之后直接用 `docker compose up -d` 即可。

首次启动建表 + 初始化约 2–3 分钟。观察状态：

```bash
docker compose ps
```

等到 `xiaozhi-api` 显示 `(healthy)`。

---

## 五、创建管理员账号

**这一步不能跳过。** 系统没有"首次启动自动建管理员"的机制，
表建好之后 `users` 表是空的，此时登录会返回 401「登录标识或密码错误」。

```bash
docker compose run --rm --no-deps --entrypoint python \
  xiaozhi-api /app/scripts/seed_admin.py
```

默认创建：

| 字段 | 值 |
| --- | --- |
| 登录标识（uid） | `admin` |
| 显示名称 | 管理员 |
| 密码 | `admin123` |
| 角色 | superadmin |
| 部门 | 研发部 |

要自定义，先在 `.env` 里设置 `SEED_ADMIN_UID` / `SEED_ADMIN_NAME` /
`SEED_ADMIN_PASSWORD` / `SEED_ADMIN_DEPT`，再执行上面的命令。

> **登录时 `username` 字段填的是 uid（`admin`），不是显示名称（`管理员`）。**
> 填错会返回「登录标识或密码错误」。

---

## 六、验证

```bash
# 1. 健康检查
curl http://localhost:5050/api/system/health

# 2. 登录拿 token
curl -i -X POST http://localhost:5050/api/auth/token \
  --data-urlencode "username=admin" \
  --data-urlencode "password=admin123"

# 3. 浏览器
#    前端      http://localhost:8081
#    接口文档  http://localhost:5050/docs
```

登录成功会返回 `access_token`、`role: "superadmin"` 等字段。

---

## 七、已知坑位

以下都是实测踩过的，不是理论推测。

### 1. 登录 500：`ValueError: JWT_SECRET_KEY 未配置`

`.env` 里 `JWT_SECRET_KEY` 为空。补上后必须 `--force-recreate`，否则容器不会重新读 `.env`：

```bash
docker compose up -d --force-recreate xiaozhi-api xiaozhi-worker
```

### 2. 前端 502：nginx 指向了旧的 api IP

nginx 在进程启动时解析一次 `xiaozhi-api` 的域名，api 容器重建后 IP 变了，
nginx 还指向旧地址。api 每次重建后，web 都要跟着重启：

```bash
docker compose restart xiaozhi-web
```

### 3. `xiaozhi-graph` 一直显示 unhealthy

neo4j 镜像里没有 `curl`，而 healthcheck 写的是 `curl -f http://localhost:7474`，
所以永远失败。**这是误报，不影响功能**，api 的 `depends_on` 也不包含它。
验证是否真的活着：

```bash
curl -s http://localhost:7474
```

能返回 `neo4j_version` 就是正常的。

### 4. 宿主机访问不到 5050

启动时漏了 `-f docker-compose.api.yml`。用 `docker ps` 看 api 的 PORTS 列是不是空的，
是空的就说明端口没映射，按第四节的命令重新启动。

### 5. 建表失败：`there is no unique constraint matching given keys for referenced table "users"`

源码里 `users.uid` 原本只有部分唯一索引（`WHERE is_deleted = 0`），
而 `agent_envs.uid` / `user_config.uid` 声明了指向它的外键。
PostgreSQL 不接受部分索引作为外键目标，导致 `create_all` 整体回滚，一张表都建不出来。

**本交付包已经修复**（`models_business.py` 中为 `uid` 补了 `UniqueConstraint`）。
如果仍遇到（例如用了旧版源码），执行兜底脚本：

```bash
docker compose stop xiaozhi-api xiaozhi-worker
docker compose run --rm --no-deps --entrypoint python \
  xiaozhi-api /app/scripts/fix_schema.py
docker compose up -d xiaozhi-api xiaozhi-worker
```

### 6. 前端 `/agent` 页面空白

原版源码存在两个问题，**本交付包已修复**：

- `stores/user.js` 与 `stores/agent.js` 循环依赖，切断方式为动态导入
- `AgentChatComponent.vue` 中 `watch` 的依赖数组引用了 377 行之后才声明的 `conversations`，
  触发 TDZ（`can't access lexical declaration 'conversations' before initialization`）

若在其他分支上再遇到类似白屏，把 `vite.config.js` 的 `build.minify` 设为 `false` 重建，
报错信息里会显示真实变量名，比压缩后的单字母名好定位得多。

---

## 八、日常运维

```bash
# 看日志
docker compose logs -f xiaozhi-api
docker compose logs -f xiaozhi-worker

# 重启全部
docker compose restart

# 停止（保留数据）
docker compose down

# 停止并清空数据（慎用）
docker compose down -v
```

数据持久化在 `docker/volumes/` 下，`docker compose down` 不会删除。

---

## 九、目录结构

```
backend/                    后端源码（Python / FastAPI）
web/                        前端源码（Vue3 + Vite）
docker/                     Dockerfile 与 nginx 配置
docker-compose.yml          服务编排主文件
docker-compose.api.yml      覆盖文件（补 5050 端口映射）
docker-compose.dev.yml      开发模式（前后端热更新）
.env.example                配置模板
scripts/                    运维脚本
  ├── fix_schema.py         建表兜底脚本
  ├── seed_admin.py         创建超级管理员
  └── seed_local_qwen.py    本地模型配置
docs/                       文档
```
