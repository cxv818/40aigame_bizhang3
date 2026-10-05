# v36.0
# 配置运行指南

## 环境要求

### 硬件
- **GPU**：AMD ROCm 或 NVIDIA CUDA
- **显存**：每实例 24GB+（35B 模型 Q4 量化）
- **内存**：32GB+
- **存储**：50GB+（模型文件）

### 软件
- **OS**：Linux (Ubuntu 22.04+)
- **Python**：3.10+
- **Pygame**：2.5+
- **llama.cpp**：最新版

## 安装步骤

### 1. 克隆仓库
```bash
git clone https://github.com/yourname/12aigame.git
cd 12aigame
```

### 2. 安装依赖
```bash
pip install pygame numpy pillow
```

### 3. 编译 llama.cpp
```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
mkdir build && cd build
cmake .. -DLLAMA_HIPBLAS=ON  # AMD GPU
cmake .. -DLLAMA_CUDA=ON     # NVIDIA GPU
make -j$(nproc)
```

### 4. 下载模型
```bash
# 下载 Ornith-1.5-35B-Q4_K_M.gguf
# 放置到 /media/ibm/软件/models/
```

## 配置文件

### config/env.sh
```bash
#!/bin/bash
# 游戏配置
export TANK_RUNTIME_DIR="/tmp"
export TANK_LOG_LEVEL="INFO"

# LLM 模型路径
export TANK_MODEL="/media/ibm/软件/models/Ornith-1.5-35B-Q4_K_M.gguf"
export LLAMA_SERVER_BIN="/home/ibm/llama.cpp/build-hip/bin/llama-server"

# GPU 分配
export TANK_GPU_1="0"
export TANK_GPU_2="1"
export TANK_GPU_3="2"
export TANK_ADVISOR_GPU="0"

# 端口配置
export TANK_AI_PORT_1="8080"      # 曹操
export TANK_AI_PORT_2="8081"      # 夏侯惇
export TANK_AI_PORT_3="8082"      # 夏侯渊
export TANK_ADVISOR_PORT="8083"   # 军师
export TANK_UDP_PORT="8089"       # Pilot 通讯

# LLM 参数
export TANK_NGL="999"
export TANK_CTX="16384"
export TANK_ADVISOR_CTX="8192"

# Pilot 配置
export TANK_ADVISOR_URL="http://127.0.0.1:8083/v1/chat/completions"
export TANK_UDP_HOST="127.0.0.1"
```

## 启动方式

### 方式一：一键启动
```bash
./scripts/start_all.sh
```

### 方式二：手动启动
```bash
# 1. 加载配置
source config/env.sh

# 2. 启动游戏
cd src
python3 tank_battle_deluxe.py &

# 3. 启动 Pilot
python3 oc_pilot.py &
```

### 方式三：分步启动 LLM
```bash
# 启动曹操 LLM
HIP_VISIBLE_DEVICES=0 llama-server \
  -m $TANK_MODEL --host 127.0.0.1 --port 8080 \
  -ngl 999 -c 16384 --parallel 1 &

# 启动夏侯惇 LLM
HIP_VISIBLE_DEVICES=1 llama-server \
  -m $TANK_MODEL --host 127.0.0.1 --port 8081 \
  -ngl 999 -c 16384 --parallel 1 &

# 启动夏侯渊 LLM
HIP_VISIBLE_DEVICES=2 llama-server \
  -m $TANK_MODEL --host 127.0.0.1 --port 8082 \
  -ngl 999 -c 16384 --parallel 1 &

# 启动军师 LLM
HIP_VISIBLE_DEVICES=0 llama-server \
  -m $TANK_MODEL --host 127.0.0.1 --port 8083 \
  -ngl 999 -c 8192 --parallel 1 &
```

## 查看状态

### 游戏状态
```bash
cat /tmp/tank_battle_status.json | python3 -m json.tool
```

### 进程状态
```bash
./scripts/status.sh
```

### GPU 状态
```bash
nvidia-smi  # NVIDIA
rocm-smi    # AMD
```

## 调试技巧

### 查看日志
```bash
# 游戏日志
tail -f /tmp/tank_game.log

# Pilot 日志
tail -f /tmp/oc_pilot.log

# LLM 日志
tail -f /tmp/llama_8080.log
tail -f /tmp/llama_8081.log
tail -f /tmp/llama_8082.log
tail -f /tmp/llama_8083.log
```

### 测试 LLM
```bash
# 测试军师 LLM
curl http://127.0.0.1:8083/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}'
```

### 测试 Pilot
```bash
# 手动发送 UDP 指令
python3 -c "
import socket, json
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = {'dx': 0.5, 'dy': 0.0, 'fire': True, 'mx': 450, 'my': 100}
s.sendto(json.dumps(cmd).encode(), ('127.0.0.1', 8089))
"
```

## 常见问题

### Q: 游戏窗口不显示
A: 检查 DISPLAY 环境变量
```bash
export DISPLAY=:0
export XAUTHORITY=/run/user/$(id -u)/.mutter-Xwaylandauth.*
```

### Q: LLM 启动失败
A: 检查模型路径和 GPU 可用性
```bash
ls -la $TANK_MODEL
rocm-smi  # 或 nvidia-smi
```

### Q: Pilot 不连接
A: 检查 UDP 端口和状态文件
```bash
ls -la /tmp/tank_battle_status.json
netstat -tulpn | grep 8089
```

### Q: 进化不触发
A: 检查击杀数和波次
```bash
cat /tmp/tank_battle_status.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'击杀: {d.get(\"killed\")}, 波次: {d.get(\"wave\")}')
"
```

## 性能优化

### 降低 GPU 占用
```bash
# 减少层数
export TANK_NGL="50"

# 减少上下文
export TANK_CTX="8192"
```

### 提高帧率
```bash
# 关闭 AI 指挥官（测试用）
export TANK_AI_ENABLED="false"
```

### 减少日志
```bash
export TANK_LOG_LEVEL="ERROR"
```

## 备份与恢复

### 备份进化存档
```bash
cp assets/*_evo.json backup/
```

### 恢复进化存档
```bash
cp backup/*_evo.json assets/
```

### 重置进化
```bash
rm assets/*_evo.json
```
