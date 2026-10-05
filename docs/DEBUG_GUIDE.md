# v36.0
# 调试指南

## 版本: v20.0

## 快速诊断

### 1. 检查所有服务状态

```bash
./scripts/status.sh
```

### 2. 检查LLM服务器

```bash
# 测试所有LLM端口
for port in 8080 8081 8082 8083; do
    echo "Port $port: $(curl -s -m 2 http://127.0.0.1:$port/health)"
done
```

### 3. 检查游戏进程

```bash
ps aux | grep -E "tank_battle|oc_pilot|llama-server" | grep -v grep
```

## 常见问题排查

### Q1: 战术仍然单一（山地占领99%）

**症状**: 数据库中所有敌人都使用"山地占领"

**排查步骤**:

1. 检查强制多样化代码是否执行
```bash
grep "DEBUG" /tmp/tank_game_debug.log | head -10
```

2. 检查 `_enforce_tactic_diversity` 是否被调用
```bash
grep "_enforce_tactic_diversity" /home/ibm/15aigame/src/tank_battle_deluxe.py
```

3. 检查敌人对象是否有current_plan属性
```bash
grep "current_plan" /home/ibm/15aigame/src/tank_battle_deluxe.py
```

**解决方案**:
- 确认代码已正确插入到 `_parse_orders` 方法中
- 确认数据库记录使用 `e.current_plan` 而不是 `DIRECTOR.get_order`
- 重启游戏服务

### Q2: 数据库无记录

**症状**: `/tmp/hsdb_*.json` 文件为空或不存在

**排查步骤**:

1. 检查数据库文件
```bash
ls -la /tmp/hsdb_*.json
```

2. 检查记录代码是否执行
```bash
grep "record_frame" /home/ibm/15aigame/src/tank_battle_deluxe.py
```

3. 手动测试记录
```python
from src.battle_recorder import record_frame
record_frame({"player_x": 450, "player_y": 580, "enemies": []})
```

**解决方案**:
- 确认 `battle_recorder.py` 已正确导入
- 确认记录代码在游戏主循环中
- 检查文件权限

### Q3: LLM不响应或响应慢

**症状**: AI状态显示"离线"或延迟>10秒

**排查步骤**:

1. 测试LLM健康状态
```bash
curl -s -m 5 http://127.0.0.1:8080/health
```

2. 测试LLM推理
```bash
curl -s -m 10 http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}],"max_tokens":10}'
```

3. 检查GPU使用率
```bash
rocm-smi  # AMD
nvidia-smi  # NVIDIA
```

**解决方案**:
- 重启llama-server
- 检查GPU显存是否不足
- 降低并发请求数

### Q4: Pilot不连接

**症状**: 玩家坦克不动或乱动

**排查步骤**:

1. 检查Pilot进程
```bash
ps aux | grep oc_pilot | grep -v grep
```

2. 检查Pilot日志
```bash
tail -20 /tmp/oc_pilot.log
```

3. 测试UDP连接
```python
import socket, json
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = {"dx": 0.5, "dy": 0.0, "fire": True, "mx": 450, "my": 100}
s.sendto(json.dumps(cmd).encode(), ("127.0.0.1", 8089))
```

**解决方案**:
- 重启Pilot
- 检查UDP端口是否被占用
- 确认游戏状态文件存在

### Q5: 游戏卡顿或崩溃

**症状**: 帧率下降或游戏退出

**排查步骤**:

1. 检查系统资源
```bash
free -h
df -h /tmp
```

2. 检查Python错误
```bash
tail -50 /tmp/tank_game.log
```

3. 检查数据库大小
```bash
ls -lh /tmp/hsdb_*.json
```

**解决方案**:
- 清理临时文件
- 增加内存或交换空间
- 降低记录频率

## 性能优化

### 数据库优化

```python
# 调整同步间隔
HighSpeedDB.sync_interval = 30  # 默认10秒

# 调整内存上限
HighSpeedDB.max_memory_size = 5000  # 默认1000
```

### LLM优化

```bash
# 减少上下文长度
export TANK_CTX=8192  # 默认16384

# 减少GPU层数
export TANK_NGL=50  # 默认999
```

### 游戏优化

```python
# 降低记录频率
BattleRecorder.record_interval = 2.0  # 默认1.0秒

# 降低敌人数量
MAX_ONFIELD = 12  # 默认16
```

## 日志分析

### 游戏日志

```bash
# 实时查看
tail -f /tmp/tank_game.log

# 搜索特定内容
grep "ERROR" /tmp/tank_game.log
grep "强制多样化" /tmp/tank_game_debug.log
```

### Pilot日志

```bash
# 查看最后100行
tail -100 /tmp/oc_pilot.log

# 搜索决策记录
grep "军师回复" /tmp/oc_pilot.log
```

### LLM日志

```bash
# 查看各端口日志
tail -f /tmp/llama_8080.log
tail -f /tmp/llama_8081.log
tail -f /tmp/llama_8082.log
tail -f /tmp/llama_8083.log
```

## 数据验证

### 验证战术多样化

```python
import json

with open('/tmp/hsdb_battle.json', 'r') as f:
    data = json.load(f)

# 获取最新帧
latest = max(k for k in data.keys() if '_latest' in k)
frame = data[latest]

# 统计战术
tactics = {}
for e in frame['enemies']:
    plan = e.get('plan', '')
    tactics[plan] = tactics.get(plan, 0) + 1

print("战术分布:")
for tactic, count in sorted(tactics.items(), key=lambda x: -x[1]):
    print(f"  {tactic}: {count}")

# 检查多样性
max_ratio = max(tactics.values()) / sum(tactics.values())
print(f"\n最大占比: {max_ratio:.1%}")
print(f"战术种类: {len(tactics)}")

if max_ratio > 0.5:
    print("⚠️ 战术单一，需要强制多样化")
else:
    print("✅ 战术多样化良好")
```

### 验证数据库性能

```python
from src.highspeed_db import HighSpeedDB
import time

db = HighSpeedDB('test', max_memory_size=10000)

# 写入测试
start = time.time()
for i in range(10000):
    db.set(f'key_{i}', {'data': i})
write_time = time.time() - start

# 读取测试
start = time.time()
for i in range(10000):
    db.get(f'key_{i}')
read_time = time.time() - start

print(f"写入: {10000/write_time:.0f} ops/s")
print(f"读取: {10000/read_time:.0f} ops/s")
print(f"统计: {db.get_stats()}")
```

## 联系支持

如有问题，请提供以下信息：
1. 游戏版本号
2. 操作系统和GPU型号
3. 错误日志片段
4. 复现步骤
