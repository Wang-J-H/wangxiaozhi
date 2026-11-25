#!/bin/bash
# dev-sandbox.sh —— 带 Docker 沙箱后端的本地开发启动脚本。
#
# 解决什么问题：智能体技能（Agent Skills）需要 shell_exec 在沙箱里执行代码，
# 而沙箱默认关闭。这个脚本把三件事集中在一处，不改仓库跟踪的文件，也不把
# 改动留在 .env 里：
#
#   1. docker-compose.sandbox.yml —— 给 app 挂 /var/run/docker.sock
#   2. 环境变量 WEKNORA_SANDBOX_DOCKER_ENABLED=1 —— 只对本次 docker compose 生效
#   3. --profile neo4j —— app 启动时会连 neo4j，不加 profile 会反复重启
#
# 风险：挂载 docker.sock 等同给 app 容器宿主机 root 权限。仅限单机私有化。
#
# 用法:
#   scripts/dev-sandbox.sh up [--no-build]   # 启动（默认用现有镜像）
#   scripts/dev-sandbox.sh down              # 停止
#   scripts/dev-sandbox.sh logs              # 跟随 app 日志
#   scripts/dev-sandbox.sh ps                # 状态

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -f .env ]; then
    echo "错误: $PROJECT_ROOT/.env 不存在，请先从 .env.example 复制并填写。" >&2
    exit 1
fi

# 沙箱开关只经由环境变量进入 compose，不写进 .env。
export WEKNORA_SANDBOX_DOCKER_ENABLED=true

compose() {
    docker compose \
        -f docker-compose.yml \
        -f docker-compose.sandbox.yml \
        --profile neo4j \
        --env-file .env \
        "$@"
}

case "${1:-up}" in
    up)
        shift || true
        # 默认不重建镜像；传 --build 才构建（构建耗时数分钟）。
        if [[ " $* " == *" --build "* ]]; then
            compose up -d "$@"
        else
            compose up -d --no-build "$@"
        fi
        echo
        echo "等待 app 健康检查..."
        for _ in $(seq 1 60); do
            if docker inspect wangxiaozhi-app --format '{{.State.Health.Status}}' 2>/dev/null | grep -q healthy; then
                echo "app 已健康。访问 http://localhost/"
                exit 0
            fi
            sleep 2
        done
        echo "警告: app 60 秒内未报告 healthy，请运行 '$0 logs' 查看。" >&2
        exit 1
        ;;
    down)   compose down ;;
    logs)   shift || true; compose logs -f app "$@" ;;
    ps)     compose ps ;;
    *)
        echo "用法: $0 {up [--build]|down|logs|ps}" >&2
        exit 2
        ;;
esac
