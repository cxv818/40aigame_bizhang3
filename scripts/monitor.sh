# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 性能监控脚本
# 版本: v20.0

while true; do
    clear
    echo "=== 坦克大战性能监控 ==="
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    # CPU和内存
    echo "【游戏进程】"
    ps aux | grep tank_battle | grep -v grep | awk '{
        printf "  PID: %s | CPU: %s%% | MEM: %s%% | RSS: %.0fMB\n", 
        $2, $3, $4, $6/1024
    }'
    
    # LLM服务
    echo ""
    echo "【LLM服务】"
    for port in 8080 8081 8082 8083; do
        status=$(curl -s -m 1 http://127.0.0.1:$port/health 2>/dev/null | grep -o '"status":"ok"' || echo "离线")
        pid=$(lsof -t -i:$port 2>/dev/null || echo "-")
        echo "  端口 $port: $status (PID: $pid)"
    done
    
    # GPU
    echo ""
    echo "【GPU状态】"
    if command -v rocm-smi &> /dev/null; then
        rocm-smi -u 2>/dev/null | grep "GPU use" | while read line; do
            echo "  $line"
        done
    elif command -v nvidia-smi &> /dev/null; then
        nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader 2>/dev/null | while read line; do
            echo "  GPU $line"
        done
    else
        echo "  无法获取GPU信息"
    fi
    
    # 数据库
    echo ""
    echo "【数据库】"
    for db in /tmp/hsdb_*.json; do
        if [ -f "$db" ]; then
            size=$(ls -lh "$db" | awk '{print $5}')
            name=$(basename "$db")
            echo "  $name: $size"
        fi
    done
    
    # 游戏状态
    echo ""
    echo "【游戏状态】"
    if [ -f "/tmp/tank_battle_status.json" ]; then
        cat /tmp/tank_battle_status.json 2>/dev/null | python3 -m json.tool 2>/dev/null | grep -E "wave|killed|player_hp|state" | head -5 | sed 's/^/  /'
    else
        echo "  状态文件不存在"
    fi
    
    # 系统负载
    echo ""
    echo "【系统负载】"
    uptime | awk '{print "  " $0}'
    
    echo ""
    echo "按Ctrl+C退出"
    sleep 2
done
