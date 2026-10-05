# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 编译llama.cpp脚本
# 支持ROCm和CUDA

set -e

echo "=== 编译llama.cpp ==="
echo ""

# 检测GPU类型
if command -v rocm-smi &> /dev/null; then
    GPU_TYPE="rocm"
    echo "检测到AMD ROCm"
elif command -v nvidia-smi &> /dev/null; then
    GPU_TYPE="cuda"
    echo "检测到NVIDIA CUDA"
else
    echo "未检测到GPU，将编译CPU版本"
    GPU_TYPE="cpu"
fi

# 克隆仓库
if [ ! -d "llama.cpp" ]; then
    echo "克隆llama.cpp..."
    git clone https://github.com/ggerganov/llama.cpp.git
fi

cd llama.cpp

# 更新到最新版本
echo "更新代码..."
git pull

# 编译
if [ "$GPU_TYPE" = "rocm" ]; then
    echo "编译ROCm版本..."
    mkdir -p build-hip
    cd build-hip
    cmake .. -DGGML_HIPBLAS=ON \
             -DCMAKE_BUILD_TYPE=Release \
             -DLLAMA_BUILD_SERVER=ON
    make -j$(nproc)
    
    # 创建符号链接
    ln -sf build-hip/bin/llama-server ../llama-server
    
elif [ "$GPU_TYPE" = "cuda" ]; then
    echo "编译CUDA版本..."
    mkdir -p build
    cd build
    cmake .. -DGGML_CUDA=ON \
             -DCMAKE_BUILD_TYPE=Release \
             -DLLAMA_BUILD_SERVER=ON
    make -j$(nproc)
    
    # 创建符号链接
    ln -sf build/bin/llama-server ../llama-server
    
else
    echo "编译CPU版本..."
    mkdir -p build
    cd build
    cmake .. -DCMAKE_BUILD_TYPE=Release \
             -DLLAMA_BUILD_SERVER=ON
    make -j$(nproc)
    
    # 创建符号链接
    ln -sf build/bin/llama-server ../llama-server
fi

echo ""
echo "=== 编译完成 ==="
echo "llama-server路径: $(pwd)/llama-server"
echo ""
echo "测试: ./llama-server --help"
