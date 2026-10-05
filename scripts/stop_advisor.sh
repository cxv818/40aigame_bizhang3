# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 停止军师服务

echo "=== 停止军师服务 ==="
pkill -f "advisor_simple.py" 2>/dev/null
echo "✅ 军师服务已停止"
