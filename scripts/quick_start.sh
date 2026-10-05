# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 快速启动脚本
# 一键启动所有服务

set -e

echo "=== 坦克大战AI集群作战系统 快速启动 ==="
echo ""

# 检查配置
if [ ! -f "config/env.sh" ]; then
    echo "错误: 未找到 config/env.sh"
    echo "请先运行 ./scripts/deploy.sh 进行部署配置"
    exit 1
fi

# 加载配置
source config/env.sh

# 检查模型
if [ ! -f "$TANK_MODEL" ]; then
    echo "错误: 未找到模型文件: $TANK_MODEL"
    echo "请下载模型或修改 config/env.sh 中的路径"
    exit 1
fi

echo "1. 启动LLM服务..."
./scripts/start_all.sh

echo ""
echo "2. 等待服务启动..."
sleep 10

# 检查服务状态
echo ""
echo "3. 检查服务状态..."
ALL_OK=true
for port in 8080 8081 8082 8083; do
    if curl -s -m 2 http://127.0.0.1:$port/health > /dev/null 2>&1; then
        echo "   端口 $port: ✅ 在线"
    else
        echo "   端口 $port: ❌ 离线"
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    echo ""
    echo "警告: 部分服务未启动"
    echo "查看日志排查问题"
    exit 1
fi

echo ""
echo "4. 启动游戏..."
cd src
python3 tank_battle_deluxe.py &
GAME_PID=$!
cd ..

echo ""
echo "5. 启动Pilot..."
cd src
python3 oc_pilot.py &
PILOT_PID=$!
cd ..

echo ""
echo "=== 启动完成 ==="
echo ""
echo "游戏PID: $GAME_PID"
echo "PilotPID: $PILOT_PID"
echo ""
echo "访问:"
echo "  游戏: 本地窗口"
echo "  状态: cat /tmp/tank_battle_status.json"
echo ""
echo "监控:"
echo "  ./scripts/monitor.sh"
echo ""
echo "停止:"
echo "  ./scripts/stop_all.sh"
echo "  kill $GAME_PID"
echo "  kill $PILOT_PID"
