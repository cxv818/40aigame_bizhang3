# v36.0
# 故障排查手册

## 版本: v20.0

## 快速诊断流程

```
游戏卡顿？
  ├─ 检查GPU利用率 → rocm-smi / nvidia-smi
  ├─ 检查系统负载 → uptime
  ├─ 检查数据库大小 → ls -lh /tmp/hsdb_*.json
  └─ 运行优化脚本 → ./scripts/optimize_performance.sh

LLM不响应？
  ├─ 检查服务状态 → curl http://127.0.0.1:8080/health
  ├─ 检查GPU显存 → rocm-smi --showmeminfo
  └─ 重启服务 → ./scripts/start_all.sh

战术不变化？
  ├─ 检查提示词 → 查看src/tank_battle_deluxe.py
  ├─ 检查数据库 → cat /tmp/hsdb_tactics.json
  └─ 强制多样化 → 查看tactics_diversity_enforcer.py
```

## 详细问题排查

### 1. 游戏卡顿（每3秒卡顿一次）

**症状**: 游戏画面每3秒左右卡顿一次

**原因**:
- GPU 100%满载
- 数据库文件过大（28MB+）
- 系统负载过高（>8）

**解决**:
```bash
# 1. 检查GPU
rocm-smi -u

# 2. 清理数据库
mv /tmp/hsdb_battle.json /tmp/hsdb_battle.json.bak
echo "{}" > /tmp/hsdb_battle.json

# 3. 运行优化脚本
./scripts/optimize_performance.sh

# 4. 如果还卡，减少LLM并发
# 编辑config/env.sh，减少TANK_NGL或TANK_CTX
```

### 2. LLM服务离线

**症状**: 状态显示"AI离线"

**排查**:
```bash
# 检查进程
ps aux | grep llama-server

# 检查端口
netstat -tulpn | grep 808[0123]

# 检查健康
curl -m 2 http://127.0.0.1:8080/health
```

**解决**:
```bash
# 重启服务
./scripts/stop_all.sh
sleep 2
./scripts/start_all.sh
```

### 3. 战术单一（所有敌人用同一战术）

**症状**: 所有敌人都用"山地占领"或"直攻"

**原因**:
- LLM倾向于重复有效战术
- 强制多样化未生效

**解决**:
```bash
# 1. 检查强制多样化代码
grep -n "_enforce_tactic_diversity" src/tank_battle_deluxe.py

# 2. 检查数据库记录
cat /tmp/hsdb_tactics.json

# 3. 手动触发多样化
# 在游戏中按D键查看调试信息
```

### 4. 数据库无记录

**症状**: /tmp/hsdb_*.json为空或只有{}

**排查**:
```bash
# 检查文件权限
ls -la /tmp/hsdb_*.json

# 检查磁盘空间
df -h /tmp

# 检查代码是否加载
python3 -c "from src.highspeed_db import HighSpeedDB; print('OK')"
```

**解决**:
```bash
# 修复权限
chmod 666 /tmp/hsdb_*.json

# 或删除重建
rm -f /tmp/hsdb_*.json
```

### 5. Pilot不连接

**症状**: 游戏不响应Pilot控制

**排查**:
```bash
# 检查Pilot进程
ps aux | grep oc_pilot

# 检查UDP端口
ss -ulnp | grep 8089

# 测试UDP发送
python3 -c "
import socket, json
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto(json.dumps({'dx':0.5,'dy':0,'fire':True}).encode(), ('127.0.0.1', 8089))
"
```

### 6. 大营HP显示异常

**症状**: HP超过上限（如954/500）

**原因**: 回血机制未检查上限

**解决**: 已修复，确保使用最新代码

### 7. 进化不触发

**症状**: 击杀很多但AI不进化

**排查**:
```bash
# 检查击杀数
cat /tmp/tank_battle_status.json | grep killed

# 检查进化存档
ls -la assets/*evo*.json
```

**解决**:
- 每3击杀触发一次进化
- 检查游戏是否正常运行

### 8. 显存不足

**症状**: llama-server启动失败，显示"out of memory"

**解决**:
```bash
# 减少GPU层数
export TANK_NGL=60  # 代替999

# 减少上下文
export TANK_CTX=4096  # 代替16384

# 使用更小的模型
```

### 9. 游戏崩溃

**症状**: 游戏突然退出

**排查**:
```bash
# 查看日志
tail -n 50 /tmp/tank_battle.log 2>/dev/null

# 检查Python错误
python3 src/tank_battle_deluxe.py 2>&1 | tee error.log
```

**常见原因**:
- 内存不足
- Pygame版本不兼容
- 模型文件损坏

### 10. 性能下降

**症状**: 游戏越来越卡

**原因**:
- 数据库文件累积
- 内存泄漏
- 敌人数量过多

**解决**:
```bash
# 定期清理
./scripts/optimize_performance.sh

# 监控资源
watch -n 1 'rocm-smi -u && echo "---" && uptime'
```

## 性能监控脚本

```bash
#!/bin/bash
# save as: scripts/monitor.sh

while true; do
    clear
    echo "=== 坦克大战性能监控 ==="
    echo ""
    
    # CPU和内存
    echo "CPU/内存:"
    ps aux | grep tank_battle | grep -v grep | awk '{print "  PID:"$2" CPU:"$3"% MEM:"$4"%"}'
    
    # GPU
    echo ""
    echo "GPU:"
    rocm-smi -u 2>/dev/null | grep "GPU use" || nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null
    
    # 数据库
    echo ""
    echo "数据库:"
    ls -lh /tmp/hsdb_*.json 2>/dev/null | awk '{print "  "$9": "$5}'
    
    # 游戏状态
    echo ""
    echo "游戏状态:"
    cat /tmp/tank_battle_status.json 2>/dev/null | python3 -m json.tool | grep -E "wave|killed|player_hp" | head -5
    
    sleep 2
done
```

## 联系支持

如果以上方法无法解决问题：

1. 收集日志：`tar czvf logs.tar.gz /tmp/*.log /tmp/hsdb_*.json`
2. 提交Issue：附上日志和系统信息
3. 紧急联系：通过Discord/Telegram
