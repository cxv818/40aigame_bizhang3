# v36.0 (2026-10-05) — 36aigame
# 版本: v20.0 (2025-10-03)
#!/usr/bin/env bash
# ============ 11aigame 一键停止 ============
# 版本: v20.0 (2025-10-03)
# pkill 模式带 [x] 字符类,防止匹配到本 shell 自杀(踩坑#2)
set -u
pkill -f "llama-serve[r].*port 808[0-3]" 2>/dev/null && echo "llama-server ×4 已停" || echo "无 llama-server"
pkill -f "laya serv[e]" 2>/dev/null && echo "laya 已停" || echo "无 laya"
pkill -f "python3 .*[o]c_pilot.py" 2>/dev/null && echo "pilot 已停" || echo "无 pilot"
pkill -f "python3 .*[j]ihuo_monitor.py" 2>/dev/null && echo "监控已停" || echo "无监控"
pkill -9 -f "python3 [t]ank_battle_deluxe.py" 2>/dev/null && echo "游戏已停(kill -9)" || echo "无游戏"
exit 0
