# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 恢复脚本
# 版本: v20.0

if [ -z "$1" ]; then
    echo "用法: $0 <备份文件.tar.gz>"
    echo ""
    echo "可用备份:"
    ls -lh backups/*.tar.gz 2>/dev/null || echo "无备份文件"
    exit 1
fi

BACKUP_FILE="$1"

echo "=== 恢复存档 ==="
echo "备份文件: $BACKUP_FILE"

# 解压
TMP_DIR="/tmp/16aigame_restore_$$"
mkdir -p "$TMP_DIR"
tar xzvf "$BACKUP_FILE" -C "$TMP_DIR"

# 找到解压后的目录
RESTORE_DIR=$(find "$TMP_DIR" -maxdepth 1 -type d | tail -1)

echo ""
echo "恢复内容:"
ls -la "$RESTORE_DIR"

echo ""
read -p "确认恢复? [y/N]: " CONFIRM

if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
    # 恢复存档
    echo "1. 恢复进化存档..."
    cp "$RESTORE_DIR"/*evo*.json assets/ 2>/dev/null || true
    
    # 恢复数据库
    echo "2. 恢复数据库..."
    cp "$RESTORE_DIR"/hsdb_*.json /tmp/ 2>/dev/null || true
    
    # 恢复配置
    echo "3. 恢复配置..."
    cp "$RESTORE_DIR"/env.sh config/ 2>/dev/null || true
    
    echo ""
    echo "恢复完成！"
else
    echo "取消恢复"
fi

# 清理
rm -rf "$TMP_DIR"
