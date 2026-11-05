#!/bin/bash
# =============================================================================
# Xiaozhi - Docker 镜像导出脚本（完全离线部署用）
# 在有网环境的服务器上运行，导出所有必需镜像
# 运行方式: bash save-images.sh
# =============================================================================

set -e

OUTPUT_DIR="./xiaozhi-images"
mkdir -p "$OUTPUT_DIR"

echo "=========================================="
echo " Xiaozhi Docker 镜像导出"
echo " 所有镜像将导出到: $(pwd)/${OUTPUT_DIR}/"
echo "=========================================="
echo ""

# 清理旧的导出文件
rm -f "$OUTPUT_DIR"/*.tar.gz "$OUTPUT_DIR"/*.tar

IMAGES=(
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
  "paddlex:latest"
)

TOTAL=0
SUCCESS=0
for IMG in "${IMAGES[@]}"; do
  TOTAL=$((TOTAL + 1))
  # Replace / and : with _ for filename
  SAFE_NAME=$(echo "$IMG" | sed 's/[:\/]/_/g')
  
  if docker image inspect "$IMG" >/dev/null 2>&1; then
    echo ""
    echo "[${TOTAL}/${#IMAGES[@]}] 📦 导出: $IMG"
    docker save "$IMG" | gzip > "$OUTPUT_DIR/${SAFE_NAME}.tar.gz"
    SIZE=$(du -h "$OUTPUT_DIR/${SAFE_NAME}.tar.gz" | cut -f1)
    echo "   ✅ 完成 (压缩后: ${SIZE})"
    SUCCESS=$((SUCCESS + 1))
  else
    echo ""
    echo "[${TOTAL}/${#IMAGES[@]}] ⚠️  跳过: $IMG (镜像不存在)"
  fi
done

echo ""
echo "=========================================="
echo " 导出完成！"
echo " 成功: ${SUCCESS}/${TOTAL}"
echo " 文件位置: $(pwd)/${OUTPUT_DIR}/"
echo " 总大小: $(du -sh ${OUTPUT_DIR} | cut -f1)"
echo ""
echo " 请将整个 xiaozhi-offline-deploy 文件夹"
echo " 复制到 U 盘/移动硬盘，传输到本地服务器。"
echo "=========================================="
