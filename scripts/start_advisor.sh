# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 启动军师服务
# 版本: v20.0

echo "=== 启动军师服务 ==="

# 检查游戏是否运行
if ! pgrep -f "tank_battle_deluxe.py" > /dev/null; then
    echo "错误: 游戏未运行"
    echo "请先启动游戏: python3 src/tank_battle_deluxe.py"
    exit 1
fi

# 检查LLM服务
if ! curl -s http://127.0.0.1:8083/health > /dev/null 2>&1; then
    echo "错误: 军师LLM(8083)未响应"
    exit 1
fi

# 停止旧服务
pkill -f "advisor_simple.py" 2>/dev/null
sleep 1

# 启动新服务
cd "$(dirname $0)/../src"
python3 advisor_simple.py > /tmp/advisor.log 2>&1 &
PID=$!
echo "军师服务PID: $PID"

# 等待启动
sleep 5

# 验证
if ps -p $PID > /dev/null 2>&1; then
    echo "✅ 军师服务已启动"
    echo "日志: tail -f /tmp/advisor.log"
    echo "状态: cat /tmp/advisor_state.json"
else
    echo "❌ 启动失败"
    exit 1
fi
