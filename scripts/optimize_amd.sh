# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# AMD GPU优化脚本
# 版本: v20.0
# 功能: 优化llama-server配置，减少游戏卡顿

echo "=== AMD Radeon AI PRO R9700 优化 ==="

# 1. 降低LLM并发数（从4个减少到3个）
# 2. 减少GPU层数（从999减少到80）
# 3. 降低上下文长度（从16384减少到8192）
# 4. 增加推理间隔

echo "优化策略:"
echo "1. 减少GPU层数 (-ngl 80 代替 -ngl 999)"
echo "2. 降低上下文 (-c 8192 代替 -c 16384)"
echo "3. 增加批处理大小提高效率"
echo "4. 启用动态批处理"

# 停止现有服务
echo ""
echo "停止现有服务..."
pkill -f "llama-server.*port 808[012]" 2>/dev/null
sleep 2

# 获取模型路径
MODEL="${TANK_MODEL:-/media/ibm/软件/models/Ornith-1.5-35B-Q4_K_M.gguf}"
LLAMA_BIN="${LLAMA_SERVER_BIN:-/home/ibm/llama.cpp/build-hip/bin/llama-server}"

# 优化后的启动命令
echo ""
echo "启动优化后的LLM服务..."

# 曹操 (8080) - 主帅，保留完整性能
HIP_VISIBLE_DEVICES=0 $LLAMA_BIN \
  -m $MODEL --host 127.0.0.1 --port 8080 \
  -ngl 80 -c 8192 --parallel 2 \
  --batch-size 512 --ubatch-size 128 \
  --timeout 300 &
echo "曹操(8080): GPU0, 80层, 8K上下文"

# 夏侯惇 (8081) - 副将，降低配置
HIP_VISIBLE_DEVICES=1 $LLAMA_BIN \
  -m $MODEL --host 127.0.0.1 --port 8081 \
  -ngl 60 -c 4096 --parallel 2 \
  --batch-size 256 --ubatch-size 64 \
  --timeout 300 &
echo "夏侯惇(8081): GPU1, 60层, 4K上下文"

# 夏侯渊 (8082) - 副将，降低配置
HIP_VISIBLE_DEVICES=2 $LLAMA_BIN \
  -m $MODEL --host 127.0.0.1 --port 8082 \
  -ngl 60 -c 4096 --parallel 2 \
  --batch-size 256 --ubatch-size 64 \
  --timeout 300 &
echo "夏侯渊(8082): GPU2, 60层, 4K上下文"

# 军师 (8083) - 使用CPU+GPU混合
# 保留现有配置或降低
# 暂时不重启，避免中断

echo ""
echo "等待服务启动..."
sleep 5

# 检查状态
echo ""
echo "服务状态:"
for port in 8080 8081 8082; do
    status=$(curl -s -m 2 http://127.0.0.1:$port/health 2>/dev/null || echo "离线")
    echo "  端口 $port: $status"
done

echo ""
echo "优化完成！"
echo "提示: 如果仍然卡顿，可以进一步降低-ngl到40或启用--cpu-range"
