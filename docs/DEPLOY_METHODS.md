# v36.0
# 部署方法大全

## 版本: v20.0

## 目录

1. [本地部署](#本地部署)
2. [Docker部署](#docker部署)
3. [Systemd服务部署](#systemd服务部署)
4. [多机部署](#多机部署)
5. [云服务器部署](#云服务器部署)
6. [开发环境部署](#开发环境部署)

---

## 本地部署

### 单GPU部署

适合：单卡GPU，显存16-24GB

```bash
# 1. 克隆项目
git clone https://github.com/yourname/16aigame.git
cd 16aigame

# 2. 安装依赖
./scripts/install.sh

# 3. 配置（单GPU）
cat > config/env.sh << 'EOF'
export TANK_MODEL=/path/to/your/model.gguf
export TANK_GPU_1=0
export TANK_GPU_2=0
export TANK_GPU_3=0
export TANK_NGL=80
export TANK_CTX=8192
EOF

# 4. 启动
./scripts/start_all.sh
sleep 30

# 5. 运行游戏
cd src
python3 tank_battle_deluxe.py
```

### 多GPU部署

适合：多卡GPU，显存24GB+

```bash
# 配置（3个GPU）
cat > config/env.sh << 'EOF'
export TANK_MODEL=/path/to/your/model.gguf
export TANK_GPU_1=0
export TANK_GPU_2=1
export TANK_GPU_3=2
export TANK_NGL=999
export TANK_CTX=16384
EOF

# 启动
./scripts/start_all.sh
```

### CPU部署

适合：无GPU，纯CPU运行

```bash
# 配置（CPU）
cat > config/env.sh << 'EOF'
export TANK_MODEL=/path/to/your/model.gguf
export TANK_NGL=0
export TANK_CTX=4096
export TANK_THREADS=16
EOF

# 编译CPU版本
./scripts/build_llama.sh

# 启动
./scripts/start_all.sh
```

---

## Docker部署

### 构建镜像

```dockerfile
# Dockerfile
FROM ubuntu:22.04

# 安装依赖
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    git cmake build-essential \
    rocm-dev || true \
    && rm -rf /var/lib/apt/lists/*

# 复制项目
COPY . /app/16aigame
WORKDIR /app/16aigame

# 安装Python依赖
RUN pip3 install -r requirements.txt

# 编译llama.cpp
RUN ./scripts/build_llama.sh

# 暴露端口
EXPOSE 8080 8081 8082 8083 8089

# 启动脚本
CMD ["./scripts/start_all.sh"]
```

```bash
# 构建镜像
docker build -t 16aigame:latest .

# 运行容器
docker run -d \
  --name 16aigame \
  --gpus all \
  -p 8080:8080 \
  -p 8081:8081 \
  -p 8082:8082 \
  -p 8083:8083 \
  -p 8089:8089/udp \
  -v /path/to/models:/app/models \
  16aigame:latest
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  16aigame:
    build: .
    container_name: 16aigame
    runtime: nvidia  # 或 rocm
    ports:
      - "8080:8080"
      - "8081:8081"
      - "8082:8082"
      - "8083:8083"
      - "8089:8089/udp"
    volumes:
      - ./models:/app/models
      - ./saves:/app/saves
      - ./logs:/app/logs
    environment:
      - TANK_MODEL=/app/models/model.gguf
      - TANK_GPU_1=0
      - TANK_GPU_2=1
      - TANK_GPU_3=2
    restart: unless-stopped
```

```bash
docker-compose up -d
```

---

## Systemd服务部署

### 创建服务文件

```bash
# /etc/systemd/system/16aigame.service
sudo tee /etc/systemd/system/16aigame.service << 'EOF'
[Unit]
Description=坦克大战AI集群作战系统
After=network.target

[Service]
Type=forking
User=ibm
Group=ibm
WorkingDirectory=/home/ibm/16aigame
Environment="PATH=/home/ibm/16aigame/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="TANK_MODEL=/path/to/model.gguf"
Environment="TANK_GPU_1=0"
Environment="TANK_GPU_2=1"
Environment="TANK_GPU_3=2"
ExecStart=/home/ibm/16aigame/scripts/start_all.sh
ExecStop=/home/ibm/16aigame/scripts/stop_all.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

### 管理服务

```bash
# 重载配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start 16aigame

# 查看状态
sudo systemctl status 16aigame

# 开机自启
sudo systemctl enable 16aigame

# 查看日志
sudo journalctl -u 16aigame -f
```

---

## 多机部署

### 架构

```
机器A (游戏服务器)
  ├── 游戏引擎 (tank_battle_deluxe.py)
  ├── Pilot (oc_pilot.py)
  └── 状态文件 (/tmp/*.json)

机器B (LLM服务器1)
  ├── 曹操 LLM (8080)
  └── 夏侯惇 LLM (8081)

机器C (LLM服务器2)
  ├── 夏侯渊 LLM (8082)
  └── 军师 LLM (8083)
```

### 配置

```bash
# 机器A: 游戏服务器
cat > config/env.sh << 'EOF'
# LLM服务地址（远程）
export TANK_AI_HOST_1=192.168.1.101
export TANK_AI_HOST_2=192.168.1.101
export TANK_AI_HOST_3=192.168.1.102
export TANK_ADVISOR_HOST=192.168.1.102

# 端口
export TANK_AI_PORT_1=8080
export TANK_AI_PORT_2=8081
export TANK_AI_PORT_3=8082
export TANK_ADVISOR_PORT=8083
EOF

# 机器B: LLM服务器1
# 启动8080和8081
llama-server -m model.gguf --host 0.0.0.0 --port 8080 -ngl 999
llama-server -m model.gguf --host 0.0.0.0 --port 8081 -ngl 999

# 机器C: LLM服务器2
# 启动8082和8083
llama-server -m model.gguf --host 0.0.0.0 --port 8082 -ngl 999
llama-server -m model.gguf --host 0.0.0.0 --port 8083 -ngl 999
```

---

## 云服务器部署

### AWS EC2

```bash
# 1. 启动实例
# 推荐: g4dn.xlarge (T4 GPU) 或 g5.xlarge (A10G GPU)

# 2. 安装驱动
sudo apt update
sudo apt install -y nvidia-driver-535  # NVIDIA
# 或
sudo apt install -y rocm-dev  # AMD

# 3. 安装Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 4. 部署
git clone https://github.com/yourname/16aigame.git
cd 16aigame
./scripts/install.sh

# 5. 配置防火墙
sudo ufw allow 8080/tcp
sudo ufw allow 8081/tcp
sudo ufw allow 8082/tcp
sudo ufw allow 8083/tcp
sudo ufw allow 8089/udp

# 6. 启动
./scripts/start_all.sh
```

### 阿里云 ECS

```bash
# 1. 选择GPU实例
# 推荐: gn6i (T4) 或 gn7i (A10)

# 2. 安装驱动
# 使用阿里云提供的GPU驱动镜像

# 3. 部署
git clone https://github.com/yourname/16aigame.git
cd 16aigame
./scripts/install.sh

# 4. 配置安全组
# 开放端口: 8080-8083, 8089

# 5. 启动
./scripts/start_all.sh
```

---

## 开发环境部署

### 虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装开发依赖
pip install -r requirements.txt
pip install pytest black flake8 mypy

# 运行测试
pytest tests/

# 代码格式化
black src/

# 代码检查
flake8 src/
```

### VS Code配置

```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests"]
}
```

### 调试配置

```json
// .vscode/launch.json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "启动游戏",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/src/tank_battle_deluxe.py",
            "console": "integratedTerminal",
            "env": {
                "PYTHONPATH": "${workspaceFolder}/src"
            }
        },
        {
            "name": "启动Pilot",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/src/oc_pilot.py",
            "console": "integratedTerminal"
        }
    ]
}
```

---

## 部署检查清单

```
□ 硬件要求满足（CPU/内存/GPU）
□ 操作系统兼容（Ubuntu 22.04+）
□ Python 3.10+ 已安装
□ GPU驱动已安装（ROCm/CUDA）
□ 模型文件已下载
□ 配置文件已编辑
□ 端口未被占用（8080-8083, 8089）
□ 防火墙已开放
□ 磁盘空间充足（10GB+）
□ 测试通过
```

---

## 性能基准

| 部署方式 | 启动时间 | 内存占用 | GPU显存 | 适用场景 |
|---------|---------|---------|---------|---------|
| 本地单GPU | 30秒 | 8GB | 16GB | 个人开发 |
| 本地多GPU | 30秒 | 8GB | 48GB | 生产环境 |
| Docker | 60秒 | 8GB | 16GB | 隔离部署 |
| Systemd | 30秒 | 8GB | 16GB | 服务器 |
| 多机 | 60秒 | 4GB | 24GB | 大规模 |
| CPU | 10秒 | 16GB | 0GB | 无GPU测试 |

---

## 故障转移

### LLM服务故障

```bash
# 自动重启
while true; do
    if ! curl -s http://127.0.0.1:8080/health > /dev/null; then
        echo "曹操LLM离线，重启中..."
        ./scripts/start_all.sh
    fi
    sleep 30
done
```

### 游戏崩溃恢复

```bash
# 监控并重启
while true; do
    if ! pgrep -f tank_battle > /dev/null; then
        echo "游戏崩溃，重启中..."
        cd src && python3 tank_battle_deluxe.py &
    fi
    sleep 5
done
```

---

## 安全建议

1. **API密钥**: 生产环境设置API密钥
2. **防火墙**: 只开放必要端口
3. **用户权限**: 使用非root用户运行
4. **日志审计**: 定期检查日志
5. **备份**: 定期备份存档和配置
