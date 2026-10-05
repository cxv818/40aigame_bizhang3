# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 备份脚本
# 版本: v20.0

BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"

echo "=== 备份存档 ==="
echo "备份目录: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# 备份存档
echo "1. 备份进化存档..."
cp assets/*evo*.json "$BACKUP_DIR/" 2>/dev/null || true

# 备份数据库
echo "2. 备份数据库..."
cp /tmp/hsdb_*.json "$BACKUP_DIR/" 2>/dev/null || true

# 备份配置
echo "3. 备份配置..."
cp config/env.sh "$BACKUP_DIR/" 2>/dev/null || true

# 备份状态
echo "4. 备份游戏状态..."
cp /tmp/tank_battle_status.json "$BACKUP_DIR/" 2>/dev/null || true

# 打包
echo "5. 打包..."
tar czvf "${BACKUP_DIR}.tar.gz" -C backups "$(basename $BACKUP_DIR)"
rm -rf "$BACKUP_DIR"

echo ""
echo "备份完成: ${BACKUP_DIR}.tar.gz"
ls -lh "${BACKUP_DIR}.tar.gz"
