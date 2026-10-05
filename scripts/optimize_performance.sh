# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 性能优化脚本
# 解决游戏卡顿问题

echo "=== 坦克大战性能优化 ==="
echo ""

# 1. 清理数据库缓存
echo "1. 清理数据库缓存..."
mv /tmp/hsdb_battle.json /tmp/hsdb_battle.json.bak 2>/dev/null
echo "{}" > /tmp/hsdb_battle.json
echo "   ✅ 数据库已清理"

# 2. 更新代码
echo ""
echo "2. 更新优化代码..."
cp /home/ibm/15aigame/src/highspeed_db.py /home/ibm/12aigame/src/highspeed_db.py
cp /home/ibm/15aigame/src/battle_recorder.py /home/ibm/12aigame/src/battle_recorder.py
echo "   ✅ 代码已更新"

# 3. 显示优化内容
echo ""
echo "3. 优化内容:"
echo "   - 数据库同步间隔: 10秒 → 30秒"
echo "   - 战场记录间隔: 1秒 → 2秒"
echo "   - 增量同步: 只同步变更数据"
echo "   - 数据库清理: 28MB → 空"

# 4. 检查游戏状态
echo ""
echo "4. 游戏状态:"
GAME_PID=$(pgrep -f "tank_battle_deluxe.py" | head -1)
if [ -n "$GAME_PID" ]; then
    echo "   游戏PID: $GAME_PID"
    echo "   游戏运行中，需要重启才能生效"
    echo ""
    echo "选项:"
    echo "  1) 重启游戏 (会中断当前游戏)"
    echo "  2) 只应用数据库清理 (部分缓解)"
    echo "  3) 取消"
    
    read -p "选择 (1/2/3): " choice
    
    case $choice in
        1)
            echo "重启游戏..."
            kill $GAME_PID 2>/dev/null
            sleep 2
            cd /home/ibm/12aigame/src
            python3 tank_battle_deluxe.py &
            echo "游戏已重启"
            ;;
        2)
            echo "数据库清理已应用，游戏继续运行"
            echo "注意: 代码优化需要重启才能完全生效"
            ;;
        *)
            echo "取消操作"
            ;;
    esac
else
    echo "   游戏未运行"
    echo "   启动游戏..."
    cd /home/ibm/12aigame/src
    python3 tank_battle_deluxe.py &
fi

echo ""
echo "优化完成！"
