#!/bin/bash
# =============================================================================
# Xiaozhi - 离线本地服务器一键部署脚本
# 完全离线部署，无需联网
# 用法:
#   1. bash load-images.sh     # 先导入镜像
#   2. bash deploy.sh          # 一键部署
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║       Xiaozhi 本地服务器一键部署（离线版）       ║"
echo "║          智能知识库与知识图谱 Agent 平台         ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ==================== 步骤 1: 检查环境 ====================
echo -e "${BLUE}【1/5】检查运行环境...${NC}"

# Docker 检查
if ! command -v docker &> /dev/null; then
  echo -e "${RED}❌ 错误: 未安装 Docker，请先安装 Docker${NC}"
  echo "   安装参考: https://docs.docker.com/engine/install/ubuntu/"
  exit 1
fi
echo -e "  ${GREEN}✅ Docker: $(docker --version)${NC}"

# Docker Compose 检查
if docker compose version &> /dev/null; then
  echo -e "  ${GREEN}✅ Docker Compose: $(docker compose version)${NC}"
  COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
  echo -e "  ${GREEN}✅ docker-compose: $(docker-compose --version)${NC}"
  COMPOSE_CMD="docker-compose"
else
  echo -e "${RED}❌ 错误: 未安装 Docker Compose${NC}"
  exit 1
fi

# NVIDIA 容器工具包检查
if docker info 2>/dev/null | grep -q "nvidia"; then
  echo -e "  ${GREEN}✅ NVIDIA Container Toolkit: 已启用${NC}"
else
  echo -e "  ${YELLOW}⚠️  未检测到 NVIDIA Container Toolkit${NC}"
  echo "     安装参考: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
fi

# 检查所有镜像是否已导入
echo -e "  ⏳ 检查 Docker 镜像..."
MISSING_IMAGES=()
REQUIRED_IMAGES=(
  "xiaozhi-api:0.7.1.beta1"
  "xiaozhi-web:0.7.1.beta1"
  "xiaozhi-sandbox-provisioner:0.7.1.beta1"
  "postgres:16"
  "redis:7-alpine"
  "neo4j:5.26"
  "minio/minio:RELEASE.2023-03-20T20-16-18Z"
  "milvusdb/milvus:v2.5.6"
  "quay.io/coreos/etcd:v3.5.5"
  "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest"
  "mineru-vllm:latest"
)
OPTIONAL_IMAGES=(
  "paddlex:latest"
)
for IMG in "${REQUIRED_IMAGES[@]}"; do
  if ! docker image inspect "$IMG" >/dev/null 2>&1; then
    MISSING_IMAGES+=("$IMG")
  fi
done
if [ ${#MISSING_IMAGES[@]} -gt 0 ]; then
  echo -e "  ${RED}❌ 缺少以下镜像，请先运行 bash load-images.sh:${NC}"
  for IMG in "${MISSING_IMAGES[@]}"; do
    echo "      - $IMG"
  done
  exit 1
fi
echo -e "  ${GREEN}✅ 所有必需镜像已就绪${NC}"

# 宿主机 Qwen vLLM 服务检查
QWEN_CHECK_PORT=${QWEN_CHECK_PORT:-8000}
if curl -s "http://localhost:${QWEN_CHECK_PORT}/health" >/dev/null 2>&1; then
  echo -e "  ${GREEN}✅ 本地 Qwen vLLM 服务: 运行中 (端口 ${QWEN_CHECK_PORT})${NC}"
else
  echo -e "  ${YELLOW}⚠️  未检测到本地 Qwen vLLM 服务 (端口 ${QWEN_CHECK_PORT})${NC}"
  echo "     部署完成后需在 Web 界面手动配置模型供应商"
  echo "     或启动 vLLM 容器后再运行本脚本"
fi

# 端口冲突检查
echo -e "  ⏳ 检查端口占用..."
PORTS=("5050" "8081" "5433" "6380" "7474" "7687" "9000" "9001" "9091" "19530" "8002" "30001")
for PORT in "${PORTS[@]}"; do
  if ss -tlnp "sport = :${PORT}" 2>/dev/null | grep -q LISTEN; then
    echo -e "  ${RED}❌ 端口 ${PORT} 已被占用！请先停止占用该端口的服务${NC}"
    echo "     或修改 docker-compose.yml 中的端口映射"
    exit 1
  fi
done
echo -e "  ${GREEN}✅ 所有端口可用${NC}"

# ==================== 步骤 2: 检查项目文件 ====================
echo ""
echo -e "${BLUE}【2/5】检查项目文件...${NC}"
REQUIRED_DIRS=("backend" "web" "docker")
for DIR in "${REQUIRED_DIRS[@]}"; do
  if [ ! -d "$DIR" ]; then
    echo -e "  ${RED}❌ 缺少目录: ${DIR}/${NC}"
    exit 1
  fi
done
echo -e "  ${GREEN}✅ 项目文件完整${NC}"

# ==================== 步骤 3: 创建数据目录 ====================
echo ""
echo -e "${BLUE}【3/5】创建数据持久化目录...${NC}"
mkdir -p docker/volumes/{xiaozhi,postgresql,redis,neo4j/{data,logs},milvus/{milvus,logs,etcd,minio,minio_config},paddlex,models}
echo -e "  ${GREEN}✅ 数据目录已创建${NC}"

# ==================== 步骤 4: 启动所有服务 ====================
echo ""
echo -e "${BLUE}【4/5】启动所有服务...${NC}"
echo -e "  ⏳ 正在启动容器（首次启动需初始化数据，约 1-3 分钟）..."

# 启动（离线模式：不使用 --build，镜像已预加载）
$COMPOSE_CMD up -d 2>&1 | tail -10

echo ""
echo -e "  ${GREEN}✅ 服务已全部启动${NC}"
echo -e "  启动的容器:"
$COMPOSE_CMD ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# ==================== 步骤 5: 等待服务就绪 ====================
echo ""
echo -e "${BLUE}【5/5】等待服务就绪并配置本地 Qwen 模型...${NC}"

echo -e "  ⏳ 等待后端 API 就绪..."
API_READY=false
for i in $(seq 1 60); do
  if curl -s "http://localhost:5050/api/system/health" >/dev/null 2>&1; then
    echo -e "  ${GREEN}✅ 后端 API 已就绪${NC}"
    API_READY=true
    break
  fi
  if [ $((i % 10)) -eq 0 ]; then
    echo -e "    还在等待中... (${i}s)"
  fi
  sleep 5
done

if [ "$API_READY" = true ]; then
  # 尝试自动注册 Qwen 模型供应商
  echo -e "  ⏳ 配置本地 Qwen 模型..."
  if [ -f ./scripts/seed_local_qwen.py ]; then
    # 将脚本复制到容器内执行
    if $COMPOSE_CMD exec -T xiaozhi-api test -f /app/scripts/seed_local_qwen.py 2>/dev/null; then
      if $COMPOSE_CMD exec -T xiaozhi-api uv run --no-sync --no-dev python /app/scripts/seed_local_qwen.py 2>/dev/null; then
        echo -e "  ${GREEN}✅ 本地 Qwen 模型已自动配置${NC}"
      else
        echo -e "  ${YELLOW}⚠️  自动配置 Qwen 模型失败，请稍后手动添加${NC}"
      fi
    else
      echo -e "  ${YELLOW}⚠️  未找到配置脚本，请稍后手动添加模型供应商${NC}"
    fi
  fi
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                   部署完成！                                ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                             ║"
echo "║  【访问地址】                                               ║"
echo "║  Web 界面:  http://$(hostname -I 2>/dev/null | awk '{print $1}'):8081  ${NC}${NC}"
echo "║              http://localhost:8081                           ║"
echo "║  API 文档:  http://localhost:5050/docs                      ║"
echo "║  Neo4j 管理: http://localhost:7474                          ║"
echo "║  MinIO 管理: http://localhost:9001                          ║"
echo "║                                                             ║"
echo "║  【管理员账号】                                             ║"
echo "║  用户名: admin                                              ║"
echo "║  密码:   admin123                                           ║"
echo "║  （首次启动会提示设置，按提示操作即可）                     ║"
echo "║                                                             ║"
echo "║  【本地 Qwen 模型】                                         ║"
echo "║  如果宿主机已有 vLLM 服务运行在端口 8000，                  ║"
echo "║  系统将自动添加 Qwen 模型供应商。                           ║"
echo "║  在「智能体管理 → 模型供应商」中即可使用。                 ║"
echo "║                                                             ║"
echo "║  【常用命令】                                               ║"
echo "║  启动: bash deploy.sh                                       ║"
echo "║  停止: $COMPOSE_CMD down                                     ║"
echo "║  日志: $COMPOSE_CMD logs -f xiaozhi-api                      ║"
echo "║  重启: $COMPOSE_CMD restart xiaozhi-api                      ║"
echo "║  查看状态: $COMPOSE_CMD ps                                   ║"
echo "║                                                             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
