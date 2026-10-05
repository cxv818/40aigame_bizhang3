# v36.0
# AI进化持久化说明 v36.0

## 概述
本文档说明AI学到的策略如何保存到数据库，以及下次开局时如何利用。

## 一、持久化机制

### 1.1 存档位置
| 将领 | 存档文件 | 当前代数 |
|------|---------|---------|
| 曹操（主帅） | `config/evolution.json` | 第18代 |
| 夏侯惇（左翼） | `config/evolution_dun.json` | 第18代 |
| 夏侯渊（右翼） | `config/evolution_yuan.json` | 第18代 |

### 1.2 存档内容
```json
{
    "generation": 18,  // 当前进化代数
    "lessons": [       // 学到的教训（最多保留8条）
        "集火战术零代价零受击，确认为最优进攻手段...",
        "攻战术代价高且玩家受击收益为0，累计阵亡5台...",
        ...
    ],
    "plan_stats": {    // 战术统计
        "直攻": {"issued": 194, "hits": 0, "deaths": 5},
        "集火": {"issued": 191, "hits": 0, "deaths": 0},
        "方阵": {"issued": 185, "hits": 0, "deaths": 4},
        "游击": {"issued": 156, "hits": 0, "deaths": 2}
    }
}
```

## 二、加载机制

### 2.1 启动时自动加载
在 `generals.py` 第939行：
```python
def __init__(self, ...):
    self.generation = 0       # 进化代数
    self.lessons = []         # 教训列表
    self.plan_stats = {}      # 战术统计
    self._load_evolution()    # ← 启动时自动加载
```

### 2.2 加载过程
```python
def _load_evolution(self):
    if os.path.exists(self._evo_path):
        with open(self._evo_path, encoding="utf-8") as f:
            evo = json.load(f)
        self.generation = int(evo.get("generation", 0))
        self.lessons = list(evo.get("lessons", []))[:8]
        self.plan_stats = evo.get("plan_stats", {})
        # 通知频道
        COMM.say(self.name, f"继承存档: 第{self.generation}代 {len(self.lessons)}条教训")
```

## 三、保存机制

### 3.1 何时保存
1. **玩家死亡时**（gameover）
2. **游戏退出时**（ESC）
3. **手动保存**（按S键）

### 3.2 保存内容
```python
def save_evolution(self):
    evo = {
        "generation": self.generation,
        "lessons": self.lessons[:8],  # 只保留最近8条
        "plan_stats": self.plan_stats,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(self._evo_path, "w", encoding="utf-8") as f:
        json.dump(evo, f, ensure_ascii=False, indent=2)
```

## 四、进化过程

### 4.1 如何进化
每完成一局游戏（无论胜负）：
1. **代数+1**：`self.generation += 1`
2. **生成新教训**：基于本局表现分析
3. **更新统计**：累加战术使用数据
4. **保存存档**：写入JSON文件

### 4.2 教训生成
```python
def request_review_async(self, wave, player_hp, player_max):
    # 构建提示词，包含历史教训
    prompt = "你是" + self.name + "，回顾本局战斗..."
    prompt += "历史教训:\n" + "\n".join(self.lessons)
    
    # LLM生成新教训
    new_lesson = llm_generate(prompt)
    self.lessons.append(new_lesson)
```

## 五、下次开局利用

### 5.1 继承内容
- ✅ **进化代数**：继续累加（第18代→第19代）
- ✅ **历史教训**：嵌入LLM提示词，避免重复犯错
- ✅ **战术统计**：了解哪些战术效果好

### 5.2 实际效果
曹操第18代的教训：
1. "集火战术零代价零受击，确认为最优进攻手段，作为主力高频轮换使用"
2. "攻战术代价高且玩家受击收益为0，累计阵亡5台，彻底弃用"
3. "游击单位就近协防阵外目标，或将单阵持续时长压缩至2次即轮换"
4. "采用双阵轮换交替策略：一阵维持2次即轮换，另一阵补位续盾"

### 5.3 LLM提示词示例
```
你是魏军曹操，负责指挥坦克作战。

历史教训（第18代）：
1. 集火战术零代价零受击，确认为最优进攻手段...
2. 攻战术代价高且玩家受击收益为0，累计阵亡5台...
3. 游击单位就近协防阵外目标...
4. 采用双阵轮换交替策略...

【强制规则】
1. 必须分配至少3种不同战术！
2. 每种战术最多只能给40%的坦克！
...
```

## 六、验证方法

### 6.1 检查存档
```bash
cat /home/ibm/桌面/24aigame/config/evolution.json
```

### 6.2 检查加载
启动游戏时查看频道消息：
```
【曹操】继承存档: 第18代 4条教训
【夏侯惇】继承存档: 第18代 5条教训
【夏侯渊】继承存档: 第18代 5条教训
```

### 6.3 检查进化
游戏结束时查看总结：
```
── AI学习总结 ──
曹操·第19代:
  • 新学到的教训...
  • 另一条教训...
```

## 七、注意事项

1. **存档不会丢失**：即使游戏崩溃，存档已写入文件
2. **教训上限**：最多保留8条，避免提示词过长
3. **跨设备迁移**：复制 `config/evolution*.json` 即可迁移进度
4. **重置进化**：删除 `config/evolution*.json` 可从第0代重新开始

## 八、总结

✅ **AI策略会保存**：每局结束自动保存到JSON文件
✅ **下次开局会利用**：启动时自动加载历史教训
✅ **持续进化**：每局累加代数，不断积累智慧
✅ **真实有效**：曹操已从第0代进化到第18代

---

**文档版本**: v24.0（v36.0包内归档）
**更新日期**: 2026-10-04
**结论**: AI进化系统完全支持持久化和跨会话学习
