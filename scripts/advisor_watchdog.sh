# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 军师服务看门狗 - 检测军师死亡自动拉起
# 用法: 加入crontab每分钟执行
# * * * * * /home/ibm/17aigame/scripts/advisor_watchdog.sh

LOG="/tmp/watchdog.log"
SRC_DIR="/home/ibm/12aigame/src"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 1. 游戏没跑则不需要军师
if ! pgrep -f "tank_battle_deluxe.py" > /dev/null; then
    exit 0
fi

# 2. 军师活着？
if pgrep -f "advisor_simple.py" > /dev/null; then
    exit 0
fi

# 3. 防疯狂重启（2分钟内>3次暂停）
RESTART_COUNT_FILE="/tmp/advisor_restart_count"
NOW=$(date +%s)
COUNT_LINE=$(cat "$RESTART_COUNT_FILE" 2>/dev/null || echo "0 0")
LAST_COUNT=$(echo "$COUNT_LINE" | awk '{print $1}')
LAST_TS=$(echo "$COUNT_LINE" | awk '{print $2}')
if [ $((NOW - LAST_TS)) -gt 120 ]; then LAST_COUNT=0; fi
NEW_COUNT=$((LAST_COUNT + 1))
echo "$NEW_COUNT $NOW" > "$RESTART_COUNT_FILE"
if [ "$NEW_COUNT" -gt 3 ]; then
    echo "[$ts] ⚠️ 军师2分钟内重启${NEW_COUNT}次，暂停拉起" >> "$LOG"
    exit 1
fi

# 4. 拉起
cd "$SRC_DIR"
nohup python3 advisor_simple.py > /tmp/advisor.log 2>&1 &
echo "[$ts] 🔄 检测到军师死亡，已重启 (PID $!)" >> "$LOG"
