# v36.0
# 部署指南

## 版本: v20.0

## 系统要求

### 硬件
- **CPU**: 8核以上（推荐16核+）
- **内存**: 32GB以上（推荐64GB+）
- **GPU**: AMD ROCm或NVIDIA CUDA（推荐24GB+显存）
- **磁盘**: 10GB可用空间

### 软件
- **OS**: Ubuntu 22.04+ / Debian 12+ / CentOS 8+
- **Python**: 3.10+
- **Pygame**: 2.5.0+
- **llama.cpp**: b3500+（支持ROCm/CUDA）

## 快速部署

### 1. 克隆项目

```bash
git clone https://github.com/yourname/16aigame.git
cd 16aigame
```

### 2. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装Python依赖
pip install -r requirements.txt

# 安装llama.cpp（ROCm版本）
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
mkdir build-hip && cd build-hip
cmake .. -DGGML_HIPBLAS=ON
make -j$(nproc)
cd ../..
```

### 3. 下载模型

```bash
# 创建模型目录
mkdir -p models

# 下载35B模型（示例）
# 请从HuggingFace或ModelScope下载
# wget https://huggingface.co/.../Ornith-1.5-35B-Q4_K_M.gguf -O models/Ornith-1.5-35B-Q4_K_M.gguf
```

### 4. 配置环境

```bash
# 复制环境配置
cp config/env.sh.template config/env.sh

# 编辑配置
nano config/env.sh
```

关键配置项：
```bash
# 模型路径
export TANK_MODEL=/path/to/your/model.gguf

# GPU分配（3个GPU）
export TANK_GPU_1=0  # 曹操
export TANK_GPU_2=1  # 夏侯惇
export TANK_GPU_3=2  # 夏侯渊

# 上下文长度
export TANK_CTX=16384

# GPU层数（根据显存调整）
export TANK_NGL=999
```

### 5. 启动服务

```bash
# 启动所有LLM服务
./scripts/start_all.sh

# 等待服务启动（约30秒）
sleep 30

# 检查状态
./scripts/status.sh
```

### 6. 启动游戏

```bash
# 启动游戏本体
cd src
python3 tank_battle_deluxe.py

# 或者后台运行
python3 tank_battle_deluxe.py &
```

### 7. 启动Pilot（可选）

```bash
# 启动OpenClaw Pilot
python3 oc_pilot.py
```

## 性能优化

### GPU优化

```bash
# 如果卡顿，减少GPU层数
export TANK_NGL=80  # 代替999

# 或减少上下文长度
export TANK_CTX=8192  # 代替16384
```

### 数据库优化

```bash
# 清理数据库缓存
./scripts/optimize_performance.sh
```

### 系统优化

```bash
# 增加文件描述符限制
ulimit -n 65535

# 禁用CPU节能模式
sudo cpupower frequency-set -g performance
```

## 验证部署

### 检查服务状态

```bash
# LLM服务
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8081/health
curl http://127.0.0.1:8082/health
curl http://127.0.0.1:8083/health

# 游戏状态
cat /tmp/tank_battle_status.json
```

### 检查GPU状态

```bash
# AMD GPU
rocm-smi

# NVIDIA GPU
nvidia-smi
```

### 检查日志

```bash
# 游戏日志
tail -f /tmp/tank_battle.log

# LLM日志
# 查看各终端输出
```

## 常见问题

### Q: LLM服务启动失败
A: 检查模型路径是否正确，显存是否足够

### Q: 游戏卡顿
A: 运行`./scripts/optimize_performance.sh`优化

### Q: Pilot无法连接
A: 检查UDP端口8089是否被占用

### Q: 战术不变化
A: 检查LLM输出格式，查看DEBUG_GUIDE.md

## 更新升级

```bash
# 备份存档
cp -r saves saves.backup

# 拉取新版本
git pull

# 重启服务
./scripts/stop_all.sh
./scripts/start_all.sh
```

## 卸载

```bash
# 停止所有服务
./scripts/stop_all.sh

# 删除项目
rm -rf /path/to/16aigame

# 清理数据库
rm -f /tmp/hsdb_*.json
rm -f /tmp/tank_*.json
```

## 支持

- GitHub Issues: https://github.com/yourname/16aigame/issues
- 文档: https://github.com/yourname/16aigame/wiki
