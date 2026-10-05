# v36.0
# API 参考

## 版本: v20.0

## 高速数据库 API

### HighSpeedDB

```python
from src.highspeed_db import HighSpeedDB

# 创建数据库
db = HighSpeedDB(
    name="mydb",
    disk_path="/tmp/mydb.json",
    max_memory_size=1000
)

# 基本操作
db.set("key", {"data": "value"})  # 写入
value = db.get("key")              # 读取
value = db.get("key", default={})  # 带默认值

# 同步
db.sync()  # 手动同步到硬盘

# 统计
stats = db.get_stats()
# {
#     "name": "mydb",
#     "memory_items": 100,
#     "memory_hits": 95,
#     "disk_hits": 5,
#     "misses": 0,
#     "hit_rate": "99.0%",
#     "writes": 100,
#     "syncs": 10
# }

# 关闭
db.close()
```

### 便捷函数

```python
from src.game_db import (
    save_game_state,
    load_game_state,
    record_tactic_effect,
    get_tactic_stats,
    save_evolution_data,
    get_evolution_history,
    get_db_stats
)

# 游戏状态
save_game_state({"player_x": 450, "player_y": 580})
state = load_game_state()

# 战术效果
record_tactic_effect("直攻", hit=True, death=False)
stats = get_tactic_stats("直攻")
# {"used": 10, "hits": 5, "deaths": 2, "effectiveness": 0.3}

# 进化数据
save_evolution_data("曹操", 25, ["集火有效", "方阵保命"])
history = get_evolution_history("曹操")

# 所有数据库统计
all_stats = get_db_stats()
```

## 战场记录 API

### BattleRecorder

```python
from src.battle_recorder import (
    get_recorder,
    record_frame,
    record_event
)

# 获取记录器
recorder = get_recorder()

# 记录一帧
record_frame({
    "player_x": 450,
    "player_y": 580,
    "player_hp": 500,
    "enemies": [...],
    "bullets": [...]
})

# 记录事件
record_event("enemy_killed", {
    "enemy_id": 1,
    "player_hp": 500
})

# 获取摘要
summary = recorder.get_battle_summary()
# {
#     "battle_id": "battle_1234567890",
#     "total_frames": 100,
#     "duration": 100,
#     "start_time": "1234567890"
# }

# 获取帧范围
frames = recorder.get_frame_range(1, 10)
```

## 战术进化 API

### TacticsEvolution

```python
from src.tactics_evolution import (
    get_evolution,
    record_tactic,
    record_effect,
    get_recommendations,
    get_diversity_info
)

# 记录战术使用
record_tactic("直攻", enemy_id=1)

# 记录效果
record_effect("直攻", hit=True, death=False, damage_dealt=10)

# 获取推荐
recommendations = get_recommendations()
# [
#     {"tactic": "集火", "score": 0.35, "reason": "效果0.35,使用20次"},
#     {"tactic": "直攻", "score": 0.28, "reason": "效果0.28,使用15次"}
# ]

# 获取多样性信息
diversity = get_diversity_info()
# {
#     "diversity": 1.45,
#     "dominant_tactic": "直攻",
#     "dominant_ratio": 0.35,
#     "tactic_count": 5
# }
```

## 战术多样性强制执行 API

### TacticsDiversityEnforcer

```python
from src.tactics_diversity_enforcer import (
    get_enforcer,
    assign_diverse_tactics,
    get_diversity_report,
    reset_diversity
)

# 分配多样化战术
assignments = assign_diverse_tactics(
    enemy_count=10,
    current_orders={0: {"plan": "直攻"}}
)
# {0: "直攻", 1: "集火", 2: "方阵", ...}

# 获取多样性报告
report = get_diversity_report()
# {
#     "total_usage": 100,
#     "tactic_count": 4,
#     "max_ratio": 0.30,
#     "max_tactic": "直攻",
#     "status": "良好",
#     "ratios": {"直攻": 0.30, "集火": 0.25, ...}
# }

# 重置统计
reset_diversity()
```

## 战场分析 API

### BattleAnalyzer

```python
from src.battle_analyzer import BattleAnalyzer

# 创建分析器
analyzer = BattleAnalyzer("http://127.0.0.1:8083/v1/chat/completions")

# 分析战斗
result = analyzer.analyze_battle(frame_count=30)
# {
#     "good_tactics": ["集火", "直攻"],
#     "bad_tactics": ["右翼包抄"],
#     "analysis": "玩家倾向于...",
#     "suggestions": ["建议1", "建议2", "建议3"]
# }

# 自动分析（检查间隔）
result = analyzer.auto_analyze()
```

## UDP 控制接口

### 游戏接收指令

```python
import socket
import json

# 发送控制指令
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cmd = {
    "dx": 0.5,      # X方向移动 (-1~1)
    "dy": -0.3,     # Y方向移动 (-1~1)
    "fire": True,   # 是否开火
    "mx": 450,      # 瞄准目标X
    "my": 100,      # 瞄准目标Y
    "skill": False  # 是否释放技能
}
s.sendto(json.dumps(cmd).encode(), ("127.0.0.1", 8089))
```

### 状态文件格式

```json
{
    "state": "play",
    "wave": 5,
    "killed": 20,
    "player_x": 450,
    "player_y": 580,
    "player_hp": 400,
    "player_max_hp": 500,
    "enemies": [
        {"id": 1, "x": 400, "y": 200, "hp": 80, "plan": "直攻"}
    ],
    "ai": {
        "status": "AI在线",
        "generation": 25,
        "lessons": ["集火有效"]
    }
}
```

## LLM 提示词接口

### 军师 LLM 输入格式

```json
{
    "messages": [
        {
            "role": "user",
            "content": "你是吕布的军师...\n当前战况:\n- 我方坦克位置: (450,580)\n- 我方HP: 400/500\n- 敌人数量: 16个\n- 敌军大营: (450,100)HP888\n\n📊敌军最近动态:\n- 敌军数量:16个\n- 敌军战术:{\"直攻\":5, \"集火\":3}\n\n输出JSON格式: {...}"
        }
    ],
    "max_tokens": 100,
    "temperature": 0.3,
    "chat_template_kwargs": {"enable_thinking": false}
}
```

### 敌军 LLM 输入格式

```json
{
    "messages": [
        {
            "role": "user",
            "content": "你是魏军曹操...\n【强制规则】\n1. 必须分配至少3种不同战术！\n2. 每种战术最多只能给40%的坦克！\n\n输出JSON数组: [{\"ids\":[1,2],\"plan\":\"直攻\",\"dir\":0,\"fire\":1,\"strafe\":0}]"
        }
    ],
    "max_tokens": 800,
    "temperature": 0.7
}
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| TANK_AI_PORT_1 | 8080 | 曹操 LLM 端口 |
| TANK_AI_PORT_2 | 8081 | 夏侯惇 LLM 端口 |
| TANK_AI_PORT_3 | 8082 | 夏侯渊 LLM 端口 |
| TANK_ADVISOR_PORT | 8083 | 军师 LLM 端口 |
| TANK_UDP_PORT | 8089 | Pilot 通讯端口 |
| TANK_MODEL | - | 模型路径 |
| TANK_GPU_1 | 0 | 曹操 GPU |
| TANK_GPU_2 | 1 | 夏侯惇 GPU |
| TANK_GPU_3 | 2 | 夏侯渊 GPU |
| TANK_NGL | 999 | GPU 层数 |
| TANK_CTX | 16384 | 上下文长度 |

## 错误码

| 错误 | 说明 | 解决方案 |
|------|------|---------|
| AI离线 | LLM服务器无响应 | 检查llama-server |
| AI返回无法解析 | JSON解析失败 | 检查提示词格式 |
| 同步失败 | 数据库写入失败 | 检查磁盘空间 |
| 战术单一 | 多样性不足 | 检查强制多样化代码 |
