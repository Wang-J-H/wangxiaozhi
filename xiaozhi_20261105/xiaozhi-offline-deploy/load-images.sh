#!/bin/bash
# =============================================================================
# Xiaozhi - Docker 镜像导入脚本
# 在本地服务器（离线环境）上运行，导入所有必需镜像
# 运行方式: bash load-images.sh [/path/to/xiaozhi-images/]
# =============================================================================

set -e

IMAGE_DIR="${1:-./xiaozhi-images}"

if [ ! -d "$IMAGE_DIR" ]; then
  echo "❌ 错误: 找不到镜像目录: $IMAGE_DIR"
  echo "用法: bash load-images.sh /path/to/xiaozhi-images/"
  exit 1
fi

echo "=========================================="
echo " Xiaozhi Docker 镜像导入"
echo " 来源目录: $IMAGE_DIR"
echo "=========================================="

COUNT=0
# 先导入 .tar.gz 文件
for GZ_FILE in "$IMAGE_DIR"/*.tar.gz; do
  if [ -f "$GZ_FILE" ]; then
    echo ""
    echo "📦 导入(压缩): $(basename "$GZ_FILE")"
    gunzip -c "$GZ_FILE" | docker load
    COUNT=$((COUNT + 1))
  fi
done

# 再导入 .tar 文件（兼容旧格式）
for TAR_FILE in "$IMAGE_DIR"/*.tar; do
  if [ -f "$TAR_FILE" ]; then
    echo ""
    echo "📦 导入: $(basename "$TAR_FILE")"
    docker load -i "$TAR_FILE"
    COUNT=$((COUNT + 1))
  fi
done

echo ""
echo "=========================================="
echo " 导入完成！共导入 ${COUNT} 个镜像"
echo ""
echo " 现在可以运行 bash deploy.sh 启动服务了"
echo "=========================================="
