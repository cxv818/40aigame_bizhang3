# v36.0
# 吕布军师进化系统 v36.0

## 概述
本文档说明吕布军师AI的进化系统，与曹操AI类似，军师也会学习和进化。

## 一、当前状态

### 1.1 军师服务架构
- **文件**: `src/advisor_simple.py`
- **运行方式**: 独立进程，通过HTTP与主游戏通信
- **当前功能**: 根据战况给出战术建议（JSON格式）

### 1.2 与曹操AI的区别
| 功能 | 曹操AI | 吕布军师 |
|------|--------|---------|
| 进化存档 | ✅ 有 | ⚠️ 新增 |
| 历史教训 | ✅ 有 | ⚠️ 新增 |
| 代数显示 | ✅ 有 | ⚠️ 新增 |
| 持久化 | ✅ 有 | ⚠️ 新增 |

## 二、新增进化功能

### 2.1 进化存档
```python
# 军师进化存档
ADVISOR_EVO_FILE = "/home/ibm/桌面/24aigame/data/advisor_evolution.json"

# 存档内容
{
    "generation": 0,      # 进化代数
    "lessons": [],        # 历史教训
    "battle_count": 0,    # 总战斗次数
    "win_count": 0        # 胜利次数
}
```

### 2.2 加载机制
启动时自动加载：
```python
evo = load_advisor_evolution()
log(f"继承存档: 第{evo['generation']}代, {len(evo['lessons'])}条教训")
```

### 2.3 保存机制
每局结束保存：
```python
def add_advisor_lesson(result, hp_ratio, wave, enemies_killed):
    evo["battle_count"] += 1
    if result == "win":
        evo["win_count"] += 1
    # 每10局进化一代
    if evo["battle_count"] % 10 == 0:
        evo["generation"] += 1
    save_advisor_evolution(evo)
```

### 2.4 LLM提示词增强
```python
prompt = (
    f"你吕布军师(第{evo['generation']}代),根据战况输出战术决策。\n"
    + lessons_text +  # 历史教训
    f"战况:HP{hp}/{max_hp}..."
)
```

## 三、使用方式

### 3.1 启动军师服务
```bash
cd /home/ibm/桌面/24aigame/src
python3 advisor_simple.py
```

### 3.2 查看进化状态
```bash
cat /home/ibm/桌面/24aigame/data/advisor_evolution.json
```

### 3.3 重置进化
```bash
rm /home/ibm/桌面/24aigame/data/advisor_evolution.json
```

## 四、与主游戏集成

### 4.1 主游戏调用
在 `tank_battle_deluxe.py` 游戏结束时：
```python
# 记录军师进化
from advisor_simple import record_battle_result
record_battle_result("win" if state == "win" else "lose", 
                     player.hp / player.max_hp, 
                     wave, 
                     killed)
```

### 4.2 显示军师代数
在AI状态面板添加：
```python
# 军师LLM单独检测
_ai_st = "吕布军师·待命"
if ADV_CHANNEL and hasattr(ADV_CHANNEL, 'advisor_gen'):
    _ai_st = f"吕布军师·第{ADV_CHANNEL.advisor_gen}代"
```

## 五、待完善

### 5.1 当前限制
1. **独立进程**: 军师服务是独立进程，与主游戏通信有限
2. **无实时反馈**: 军师建议的效果难以实时评估
3. **简单统计**: 只有胜负统计，没有详细的战术效果分析

### 5.2 未来优化
1. **详细评估**: 记录每次建议的效果（玩家HP变化、歼敌数等）
2. **战术分类**: 区分不同建议类型（攻击、防御、撤退等）
3. **玩家反馈**: 记录玩家是否采纳建议及结果

## 六、总结

### 6.1 已完成
- ✅ 军师进化存档机制
- ✅ 加载/保存功能
- ✅ LLM提示词增强

### 6.2 待完成
- ⚠️ 主游戏集成（记录战斗结果）
- ⚠️ 军师代数显示
- ⚠️ 详细效果评估

---

**文档版本**: v24.0（v36.0包内归档）
**更新日期**: 2026-10-04
**状态**: 基础框架已完成，需主游戏集成
