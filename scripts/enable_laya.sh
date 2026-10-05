# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
echo "=========================================="
echo "  Laya System-1 启用指南"
echo "=========================================="
echo ""

echo "Laya是一个可选的AI技能顾问服务，用于优化烈璧障释放时机。"
echo ""

echo "【当前状态】"
if [ -z "$LAYA_URL" ]; then
    echo "  ✗ 未启用 (LAYA_URL未设置)"
else
    echo "  ✓ 已启用: $LAYA_URL"
fi

echo ""
echo "【启用步骤】"
echo ""
echo "1. 部署Laya服务 (需要单独安装):"
echo "   git clone https://github.com/yourname/laya-systemone"
echo "   cd laya-systemone"
echo "   pip install -r requirements.txt"
echo "   python3 server.py --port 8091"
echo ""
echo "2. 设置环境变量:"
echo "   export LAYA_URL=\"http://127.0.0.1:8091/v1/systemone\""
echo ""
echo "3. 重启Pilot:"
echo "   pkill -f oc_pilot.py"
echo "   python3 src/oc_pilot.py"
echo ""

echo "【Laya作用】"
echo "  - 输入: 敌人数量、近身敌人数、玩家HP"
echo "  - 输出: deploy(释放) / hold(保留)"
echo "  - 效果: 更精准的技能释放时机"
echo ""

echo "【性能影响】"
echo "  - 请求延迟: 0.5s超时"
echo "  - 缓存时间: 1s"
echo "  - 调用频率: 约1次/秒"
echo "  - 对游戏性能影响: 极小"
echo ""

echo "【回退机制】"
echo "  - Laya未启动 → 使用原规则"
echo "  - Laya超时 → 使用原规则"
echo "  - Laya异常 → 使用原规则"
echo ""

echo "=========================================="
