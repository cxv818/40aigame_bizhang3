# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 部署脚本
# 版本: v20.0
# 功能: 自动检测环境并选择最佳部署方式

set -e

echo "=== 坦克大战AI集群作战系统 部署脚本 ==="
echo "版本: v20.0"
echo ""

# 检测环境
echo "1. 检测环境..."

# Python
PYTHON_VERSION=$(python3 --version 2>/dev/null | awk '{print $2}' || echo "未安装")
echo "   Python: $PYTHON_VERSION"

# GPU
if command -v rocm-smi &> /dev/null; then
    GPU_TYPE="rocm"
    GPU_COUNT=$(rocm-smi --showproductname 2>/dev/null | grep "Card Series" | wc -l)
    echo "   GPU: AMD ROCm ($GPU_COUNT 个)"
elif command -v nvidia-smi &> /dev/null; then
    GPU_TYPE="cuda"
    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l)
    echo "   GPU: NVIDIA CUDA ($GPU_COUNT 个)"
else
    GPU_TYPE="cpu"
    GPU_COUNT=0
    echo "   GPU: 无（将使用CPU）"
fi

# 内存
MEM_TOTAL=$(free -g | awk '/^Mem:/{print $2}')
echo "   内存: ${MEM_TOTAL}GB"

# 磁盘
DISK_FREE=$(df -h . | awk 'NR==2{print $4}')
echo "   磁盘可用: $DISK_FREE"

echo ""

# 选择部署方式
echo "2. 选择部署方式..."
echo ""
echo "检测到的环境:"
echo "  - GPU类型: $GPU_TYPE"
echo "  - GPU数量: $GPU_COUNT"
echo "  - 内存: ${MEM_TOTAL}GB"
echo ""

if [ "$GPU_COUNT" -ge 3 ]; then
    echo "推荐: 多GPU部署（最佳性能）"
    DEPLOY_TYPE="multi-gpu"
elif [ "$GPU_COUNT" -ge 1 ]; then
    echo "推荐: 单GPU部署"
    DEPLOY_TYPE="single-gpu"
else
    echo "推荐: CPU部署（性能受限）"
    DEPLOY_TYPE="cpu"
fi

echo ""
read -p "选择部署方式 [multi-gpu/single-gpu/cpu/Docker/Systemd]: " USER_CHOICE
DEPLOY_TYPE=${USER_CHOICE:-$DEPLOY_TYPE}

echo ""
echo "3. 配置环境..."

# 根据部署方式生成配置
case $DEPLOY_TYPE in
    multi-gpu)
        cat > config/env.sh << EOF
export TANK_MODEL=\${TANK_MODEL:-/path/to/model.gguf}
export TANK_GPU_1=0
export TANK_GPU_2=1
export TANK_GPU_3=2
export TANK_NGL=999
export TANK_CTX=16384
export TANK_PARALLEL=1
EOF
        ;;
    single-gpu)
        cat > config/env.sh << EOF
export TANK_MODEL=\${TANK_MODEL:-/path/to/model.gguf}
export TANK_GPU_1=0
export TANK_GPU_2=0
export TANK_GPU_3=0
export TANK_NGL=80
export TANK_CTX=8192
export TANK_PARALLEL=1
EOF
        ;;
    cpu)
        cat > config/env.sh << EOF
export TANK_MODEL=\${TANK_MODEL:-/path/to/model.gguf}
export TANK_NGL=0
export TANK_CTX=4096
export TANK_THREADS=16
EOF
        ;;
    docker)
        echo "Docker部署..."
        if ! command -v docker &> /dev/null; then
            echo "安装Docker..."
            curl -fsSL https://get.docker.com | sh
            sudo usermod -aG docker $USER
        fi
        docker build -t 16aigame:latest .
        echo "Docker镜像构建完成"
        echo "运行: docker run -d --gpus all -p 8080-8083:8080-8083 -p 8089:8089/udp 16aigame:latest"
        exit 0
        ;;
    systemd)
        echo "Systemd服务部署..."
        sudo tee /etc/systemd/system/16aigame.service << EOF
[Unit]
Description=坦克大战AI集群作战系统
After=network.target

[Service]
Type=forking
User=$USER
WorkingDirectory=$PWD
ExecStart=$PWD/scripts/start_all.sh
ExecStop=$PWD/scripts/stop_all.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable 16aigame
        echo "Systemd服务已创建"
        echo "启动: sudo systemctl start 16aigame"
        exit 0
        ;;
    *)
        echo "未知部署方式: $DEPLOY_TYPE"
        exit 1
        ;;
esac

echo "   配置已生成: config/env.sh"

# 检查模型
echo ""
echo "4. 检查模型文件..."
if [ -f "models/*.gguf" ] 2>/dev/null; then
    echo "   找到模型文件"
    ls -lh models/*.gguf
else
    echo "   未找到模型文件"
    echo "   请下载模型到 models/ 目录"
    echo "   示例: wget https://huggingface.co/.../model.gguf -O models/model.gguf"
fi

# 编译llama.cpp
echo ""
echo "5. 编译llama.cpp..."
if [ ! -f "llama.cpp/llama-server" ]; then
    ./scripts/build_llama.sh
else
    echo "   llama.cpp已编译"
fi

# 运行测试
echo ""
echo "6. 运行测试..."
cd tests
python3 test_highspeed_db.py > /dev/null 2>&1 && echo "   数据库测试: 通过" || echo "   数据库测试: 失败"
cd ..

# 完成
echo ""
echo "=== 部署完成 ==="
echo ""
echo "部署方式: $DEPLOY_TYPE"
echo ""
echo "下一步:"
echo "1. 编辑 config/env.sh 配置模型路径"
echo "2. 下载模型文件到 models/ 目录"
echo "3. 运行 ./scripts/start_all.sh 启动服务"
echo "4. 运行 python3 src/tank_battle_deluxe.py 启动游戏"
echo ""
echo "查看文档:"
echo "- 部署指南: docs/DEPLOY_GUIDE.md"
echo "- 部署方法: docs/DEPLOY_METHODS.md"
echo "- 故障排查: docs/TROUBLESHOOTING.md"
