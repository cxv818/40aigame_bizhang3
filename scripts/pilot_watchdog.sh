# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# Pilot看门狗 - 检测Pilot死亡自动拉起
# 用法: 加入crontab每分钟执行
# * * * * * /home/ibm/17aigame/scripts/pilot_watchdog.sh

LOG="/tmp/watchdog.log"
SRC_DIR="/home/ibm/12aigame/src"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 1. 检查游戏是否在跑（游戏没跑则Pilot无需拉起）
if ! pgrep -f "tank_battle_deluxe.py" > /dev/null; then
    exit 0
fi

# 2. 检查Pilot是否存活
if pgrep -f "oc_pilot.py" > /dev/null; then
    exit 0   # 活着，无事
fi

# 3. Pilot死了，检查是否频繁重启（防疯狂拉起：2分钟内重启超过3次就告警等待）
RESTART_COUNT_FILE="/tmp/pilot_restart_count"
NOW=$(date +%s)
RESET_SEC=120

COUNT_LINE=$(cat "$RESTART_COUNT_FILE" 2>/dev/null || echo "0 0")
LAST_COUNT=$(echo "$COUNT_LINE" | awk '{print $1}')
LAST_TS=$(echo "$COUNT_LINE" | awk '{print $2}')

if [ $((NOW - LAST_TS)) -gt $RESET_SEC ]; then
    LAST_COUNT=0
fi
NEW_COUNT=$((LAST_COUNT + 1))
echo "$NEW_COUNT $NOW" > "$RESTART_COUNT_FILE"

if [ "$NEW_COUNT" -gt 3 ]; then
    echo "[$ts] ⚠️ Pilot 2分钟内重启${NEW_COUNT}次，疑似崩溃循环，暂停拉起" >> "$LOG"
    exit 1
fi

# 4. 拉起Pilot
cd "$SRC_DIR"
nohup python3 oc_pilot.py > /tmp/pilot_v2.log 2>&1 &
echo "[$ts] 🔄 检测到Pilot死亡，已重启 (PID $!, 第${NEW_COUNT}次/2分钟内)" >> "$LOG"
