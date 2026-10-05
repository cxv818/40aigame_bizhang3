# v36.0 (2026-10-05) — 36aigame
#!/bin/bash
# 安装脚本
# 版本: v20.0

set -e

echo "=== 坦克大战AI集群作战系统 安装脚本 ==="
echo "版本: v20.0"
echo ""

# 检查系统
echo "1. 检查系统环境..."

# Python版本
PYTHON_VERSION=$(python3 --version 2>/dev/null | awk '{print $2}')
if [ -z "$PYTHON_VERSION" ]; then
    echo "错误: 未找到Python3"
    exit 1
fi
echo "   Python: $PYTHON_VERSION"

# Pygame
if python3 -c "import pygame" 2>/dev/null; then
    echo "   Pygame: 已安装"
else
    echo "   Pygame: 未安装，正在安装..."
    pip3 install pygame
fi

# ROCm/CUDA
if command -v rocm-smi &> /dev/null; then
    echo "   GPU: AMD ROCm"
    GPU_TYPE="rocm"
elif command -v nvidia-smi &> /dev/null; then
    echo "   GPU: NVIDIA CUDA"
    GPU_TYPE="cuda"
else
    echo "   GPU: 未检测到（将使用CPU）"
    GPU_TYPE="cpu"
fi

# 检查llama.cpp
if [ -f "llama.cpp/build-hip/bin/llama-server" ] || [ -f "llama.cpp/build/bin/llama-server" ]; then
    echo "   llama.cpp: 已编译"
else
    echo "   llama.cpp: 未编译"
    echo "   请运行: ./scripts/build_llama.sh"
fi

echo ""

# 创建目录
echo "2. 创建项目目录..."
mkdir -p saves logs models assets
echo "   完成"

echo ""

# 配置环境
echo "3. 配置环境..."
if [ ! -f "config/env.sh" ]; then
    cp config/env.sh.template config/env.sh
    echo "   已创建 config/env.sh（请编辑配置）"
else
    echo "   config/env.sh 已存在"
fi

echo ""

# 检查模型
echo "4. 检查模型文件..."
if [ -f "models/*.gguf" ] 2>/dev/null; then
    echo "   找到模型文件"
else
    echo "   未找到模型文件"
    echo "   请下载模型到 models/ 目录"
fi

echo ""

# 测试导入
echo "5. 测试Python模块..."
cd src
python3 -c "
import sys
sys.path.insert(0, '.')
from highspeed_db import HighSpeedDB
from battle_recorder import BattleRecorder
from tactics_evolution import TacticsEvolution
from tactics_diversity_enforcer import TacticsDiversityEnforcer
print('   所有模块导入成功')
"
cd ..

echo ""

# 运行测试
echo "6. 运行测试..."
if [ -d "tests" ]; then
    cd tests
    python3 test_highspeed_db.py > /dev/null 2>&1 && echo "   数据库测试: 通过" || echo "   数据库测试: 失败"
    python3 test_tactics_evolution.py > /dev/null 2>&1 && echo "   战术进化测试: 通过" || echo "   战术进化测试: 失败"
    python3 test_diversity.py > /dev/null 2>&1 && echo "   多样性测试: 通过" || echo "   多样性测试: 失败"
    cd ..
else
    echo "   测试目录不存在"
fi

echo ""

# 完成
echo "=== 安装完成 ==="
echo ""
echo "下一步:"
echo "1. 编辑 config/env.sh 配置模型路径和GPU"
echo "2. 下载模型文件到 models/ 目录"
echo "3. 运行 ./scripts/start_all.sh 启动服务"
echo "4. 运行 python3 src/tank_battle_deluxe.py 启动游戏"
echo ""
echo "查看文档:"
echo "- 部署指南: docs/DEPLOY_GUIDE.md"
echo "- 故障排查: docs/TROUBLESHOOTING.md"
echo "- API参考: docs/API_REFERENCE.md"
