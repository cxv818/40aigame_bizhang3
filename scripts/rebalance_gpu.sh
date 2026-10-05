# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# GPU重新平衡脚本
# 解决GPU0过载问题

echo "=== GPU重新平衡 ==="
echo ""
echo "当前问题:"
echo "  - GPU0: 8080(曹操) + 8083(军师) = 过载"
echo "  - GPU1: 8081(夏侯惇)"
echo "  - GPU2: 8082(夏侯渊)"
echo ""

# 停止8080和8083（GPU0上的两个）
echo "停止GPU0上的服务..."
kill 361391 2>/dev/null  # 8080
kill 271372 2>/dev/null  # 8083
sleep 3

# 检查是否停止
ps aux | grep "llama-server.*port 808[03]" | grep -v grep || echo "已停止"

MODEL="/media/ibm/软件/models/Ornith-1.5-35B-Q4_K_M.gguf"
LLAMA_BIN="/home/ibm/llama.cpp/build-hip/bin/llama-server"

# 重新启动，优化分配
echo ""
echo "重新启动LLM服务..."

# 曹操(8080) → GPU1（减轻GPU0负担）
HIP_VISIBLE_DEVICES=1 $LLAMA_BIN \
  -m $MODEL --host 127.0.0.1 --port 8080 \
  -ngl 80 -c 8192 --parallel 2 \
  --batch-size 512 --ubatch-size 128 &
echo "曹操(8080): GPU1, 80层"

# 军师(8083) → GPU2（减轻GPU0负担）
HIP_VISIBLE_DEVICES=2 $LLAMA_BIN \
  -m $MODEL --host 127.0.0.1 --port 8083 \
  -ngl 80 -c 8192 --parallel 1 \
  --batch-size 256 --ubatch-size 64 &
echo "军师(8083): GPU2, 80层"

# 等待启动
sleep 5

# 检查新分配
echo ""
echo "新的GPU分配:"
rocm-smi --showpidgpus | grep -E "PID|is using"

echo ""
echo "服务状态:"
for port in 8080 8081 8082 8083; do
    status=$(curl -s -m 2 http://127.0.0.1:$port/health 2>/dev/null || echo "离线")
    echo "  端口 $port: $status"
done

echo ""
echo "重新平衡完成！"
