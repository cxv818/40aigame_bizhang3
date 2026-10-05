# 数据库文件使用分析 v36.0

## 概述
本文档分析23aigame项目中数据库文件是否被LLM合理使用。

## 一、数据库文件清单

| 文件路径 | 大小 | 用途 | 是否被LLM使用 |
|---------|------|------|-------------|
| `data/hsdb_backup/hsdb_battle.json` | 35.6 MB | 战斗记录 | ⚠️ 部分使用 |
| `data/hsdb_backup/hsdb_tactics.json` | 10 bytes | 战术统计 | ❌ 未使用 |
| `data/hsdb_backup/hsdb_evolution.json` | 10 bytes | 进化数据 | ❌ 未使用 |
| `data/hsdb_backup/hsdb_game_state.json` | 10 bytes | 游戏状态 | ❌ 未使用 |
| `data/runtime_state/tank_battle_status.json` | 2.9 KB | 运行时状态 | ✅ 外部读取 |
| `data/runtime_state/tank_fast.json` | 2.1 KB | 快速状态 | ✅ 外部读取 |
| `config/evolution.json` | 4 KB | 曹操进化存档 | ✅ 直接使用 |
| `config/evolution_dun.json` | 4 KB | 夏侯惇进化存档 | ✅ 直接使用 |
| `config/evolution_yuan.json` | 4 KB | 夏侯渊进化存档 | ✅ 直接使用 |

## 二、LLM使用数据库的方式

### 2.1 直接使用（✅）

#### 进化存档
```python
# 直接读取JSON文件
with open(self._evo_path, encoding="utf-8") as f:
    evo = json.load(f)
self.generation = int(evo.get("generation", 0))
self.lessons = list(evo.get("lessons", []))[:8]
self.plan_stats = evo.get("plan_stats", {})
```

**使用方式**：启动时加载，用于继承代数和教训。

#### 战术数据库（Python模块）
```python
from tactics_db import TACTICS_DB, get_valid_tactics
valid_tactics = get_valid_tactics()
tactics_stats = "\n📈战术效果统计:\n"
for name, data in TACTICS_DB.items():
    if data['used'] > 0 and shown < 5:
        tactics_stats += f"- {name}: 使用{data['used']}次, 效果{data['effectiveness']:.2f}\n"
```

**使用方式**：直接导入Python模块，嵌入LLM提示词。

### 2.2 间接使用（⚠️）

#### 战场分析缓存
```python
from battle_recorder import get_cached_analysis
battle_analysis = get_cached_analysis()
```

**问题**：缓存超过5秒未更新时返回空字符串，导致LLM无法获取最新分析。

### 2.3 未使用（❌）

#### 高速数据库备份文件
- `hsdb_tactics.json` - 10 bytes（空文件）
- `hsdb_evolution.json` - 10 bytes（空文件）
- `hsdb_game_state.json` - 10 bytes（空文件）

**问题**：这些文件虽然被创建，但内容为空，未被LLM实际使用。

## 三、数据库使用效率分析

### 3.1 战斗记录数据库（35.6 MB）

**记录数量**：3971条战斗记录

**记录结构**：
```json
{
  "battle_1791023038_frame_1": {
    "battle_id": "battle_1791023038",
    "frame": 1,
    "timestamp": 1791023038.316624,
    "game_time": 0.37,
    "player": {"x": 450, "y": 580, "hp": 500, ...},
    "enemies": [{"id": 1, "x": 239, "y": 58, "hp": 100, ...}],
    "events": [{"type": "enemy_killed", "data": {...}}]
  }
}
```

**LLM使用情况**：
- ✅ 记录详细，包含玩家位置、敌人状态、事件
- ⚠️ 但LLM提示词中未直接引用这些记录
- ⚠️ 战场分析缓存经常为空

### 3.2 战术数据库（Python模块）

**当前状态**：
```python
TACTICS_DB = {
    "右翼包抄": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "左翼包抄": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "佯退拉扯": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "方阵推进": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "集火攻击": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "直攻": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "压制": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
}
```

**问题**：
- ❌ 所有战术使用次数为0
- ❌ 效果评估未实际计算
- ❌ 状态未根据实战更新

## 四、问题诊断

### 4.1 数据库未充分利用的原因

1. **缓存机制问题**
   - 战场分析缓存5秒过期
   - 记录线程未正确更新缓存

2. **战术统计未更新**
   - `record_tactic()` 函数未被正确调用
   - 战术效果未根据实战结果更新

3. **数据孤岛**
   - 战斗记录存储在hsdb_backup，但LLM提示词使用tactics_db模块
   - 两个数据源未同步

### 4.2 建议改进

1. **修复缓存更新机制**
   ```python
   # 确保记录线程正确更新缓存
   def record_event(event_type, data):
       recorder.add_event(event_type, data)
       update_analysis_cache(generate_analysis())  # 立即更新缓存
   ```

2. **同步战术统计**
   ```python
   # 在战斗结束后同步到tactics_db
   def sync_tactics_stats():
       for tactic in battle_records:
           TACTICS_DB[tactic]["used"] += 1
           TACTICS_DB[tactic]["effectiveness"] = calculate_effectiveness(tactic)
   ```

3. **直接使用战斗记录**
   ```python
   # 在LLM提示词中直接引用最近战斗记录
   recent_battles = get_recent_battles(limit=10)
   prompt += f"\n最近战斗记录: {recent_battles}"
   ```

## 五、总结

### 5.1 当前状态

| 数据库 | 是否被LLM使用 | 使用效率 | 问题 |
|--------|-------------|---------|------|
| 进化存档 | ✅ 是 | 高 | 正常 |
| 战术数据库 | ✅ 是 | 低 | 数据未更新 |
| 战斗记录 | ⚠️ 部分 | 低 | 缓存经常为空 |
| 高速数据库 | ❌ 否 | 无 | 文件为空 |

### 5.2 改进优先级

1. **高优先级**：修复战术数据库更新机制
2. **中优先级**：优化战场分析缓存
3. **低优先级**：清理未使用的高速数据库文件

---

**文档版本**: v23.0（v36.0包内归档）
**更新日期**: 2026-10-04
**分析结论**: 数据库文件部分被LLM使用，但存在更新不及时、数据未同步的问题。
