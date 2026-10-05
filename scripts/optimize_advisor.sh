# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
echo "=========================================="
echo "  军师服务优化 v22.0"
echo "=========================================="

# 备份
cp src/advisor_simple.py src/advisor_simple.py.bak.$(date +%Y%m%d_%H%M%S)

echo ""
echo "[1/2] 优化提示词和响应速度..."

# 使用sed进行简单替换
sed -i 's/"你是一个游戏AI助手。只输出JSON格式的战术决策，不要任何解释。"/"游戏AI。只输出JSON，无解释。"/g' src/advisor_simple.py
sed -i 's/"max_tokens": 100,/"max_tokens": 60,/g' src/advisor_simple.py

echo "✓ 提示词精简完成"
echo "✓ max_tokens从100降到60"

echo ""
echo "[2/2] 重启军师服务..."
pkill -f advisor_simple.py 2>/dev/null
sleep 1
nohup python3 src/advisor_simple.py > /tmp/advisor.log 2>&1 &
echo "✓ 军师服务已重启 (PID: $!)"

echo ""
echo "=========================================="
echo "  优化完成!"
echo "=========================================="
