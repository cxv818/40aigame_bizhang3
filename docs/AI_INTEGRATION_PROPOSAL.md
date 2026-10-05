# v36.0
# AI服务整合优化方案 v1.0

> **制定日期**: 2024-10-04 | **适用版本**: v22.0+

---

## 当前架构问题

```
【现有流程 - 问题重重】
军师LLM(8083) → 生成建议(2-6s) → 写入文件 → Pilot读取 → 执行
                    ↓
              延迟高、建议有时不合理、缺少技能决策
```

### 具体问题

1. **军师延迟高**: 2-6秒才更新一次建议
2. **建议质量不稳定**: LLM有时给出不合理建议（满血建议回血）
3. **技能释放粗糙**: 仅靠硬编码规则，无AI辅助
4. **资源浪费**: 4个LLM服务同时运行，GPU压力大

---

## 优化方案: 三层AI架构

```
┌─────────────────────────────────────────────────────────────┐
│                    第一层: 战略层 (军师)                      │
│                   频率: 每5秒 | 端口: 8083                   │
│              职责: 全局战术建议、威胁评估、目标选择              │
└──────────────────────┬──────────────────────────────────────┘
                       │ JSON建议
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    第二层: 战术层 (Pilot)                     │
│                   频率: 20Hz | 端口: 8089                    │
│              职责: 实时执行、路径规划、躲避算法                  │
└──────────────────────┬──────────────────────────────────────┘
                       │ 状态数据
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    第三层: 技能层 (Laya)                      │
│                   频率: 1Hz | 端口: 8091                     │
│              职责: 精细技能决策、神经打分、风险评估              │
└─────────────────────────────────────────────────────────────┘
```

---

## 详细设计

### 第一层: 战略层优化

**当前问题**:
- 提示词太长，LLM理解困难
- 返回格式不稳定
- 建议过于笼统

**优化方案**:

```python
# 1. 精简提示词
PROMPT_TEMPLATE = """
你是吕布的军师。当前战况:
- 玩家HP: {hp}/{max_hp}
- 敌人数量: {enemy_count}
- 波次: {wave}
- 大营可攻击: {camp_attackable}

快速判断(只输出JSON):
{{
  "style": "aggressive|balanced|kite",
  "target": "camp|enemies|heal",
  "priority": "focus_fire|survive|push"
}}
"""

# 2. 增加规则校验
def validate_advice(advice, game_state):
    """校验建议是否合理"""
    # 满血时不建议回血
    if game_state['player_hp'] > 400 and advice['target'] == 'heal':
        advice['target'] = 'enemies'
    
    # 波次<=3时不建议攻营
    if game_state['wave'] <= 3 and advice['target'] == 'camp':
        advice['target'] = 'enemies'
    
    # 敌人<5时不建议kite
    if game_state['enemies'] < 5 and advice['style'] == 'kite':
        advice['style'] = 'aggressive'
    
    return advice
```

### 第二层: 战术层优化

**当前问题**:
- 距离控制不精确
- 躲避算法简单
- 不考虑地形

**优化方案**:

```python
# 1. 改进距离控制
def calculate_position(player, enemies, advisor_dist, style):
    """计算理想位置"""
    if not enemies:
        return player.x, player.y
    
    # 找到威胁最大的敌人
    threats = []
    for e in enemies:
        dist = distance(player, e)
        threat = e['dmg'] / max(dist, 1)  # 伤害/距离
        threats.append((threat, e))
    
    threats.sort(reverse=True)
    main_threat = threats[0][1]
    
    # 根据风格调整距离
    if style == 'aggressive':
        target_dist = advisor_dist * 0.7  # 更近
    elif style == 'kite':
        target_dist = advisor_dist * 1.3  # 更远
    else:
        target_dist = advisor_dist
    
    # 计算理想位置
    to_enemy = normalize(main_threat.x - player.x, main_threat.y - player.y)
    ideal_x = main_threat.x - to_enemy[0] * target_dist
    ideal_y = main_threat.y - to_enemy[1] * target_dist
    
    return ideal_x, ideal_y

# 2. 增加躲避算法
def avoid_bullets(player, bullets, safe_zone):
    """躲避子弹"""
    danger = [b for b in bullets if distance(player, b) < safe_zone]
    if not danger:
        return 0, 0
    
    # 计算躲避方向
    avoid_x, avoid_y = 0, 0
    for b in danger:
        dx = player.x - b.x
        dy = player.y - b.y
        dist = max(math.hypot(dx, dy), 1)
        avoid_x += dx / dist * (safe_zone - dist)
        avoid_y += dy / dist * (safe_zone - dist)
    
    return avoid_x, avoid_y
```

### 第三层: 技能层 (启用Laya)

**当前状态**: 未启用

**启用方案**:

```bash
# 1. 部署Laya服务
# Laya是一个轻量级神经网络服务，专门做二分类决策

# 2. 配置环境变量
export LAYA_URL="http://127.0.0.1:8091/v1/systemone"

# 3. 重启Pilot
pkill -f oc_pilot.py
python3 src/oc_pilot.py
```

**Laya输入输出**:

```python
# 输入
{
  "state": "tank battle: 15 enemies, 3 within 120px, HP 320/500, skill ready",
  "questions": {
    "skill": {
      "type": "choice",
      "instructions": "Should deploy protective wall?",
      "criteria": {
        "hold": "situation manageable",
        "deploy": "crowded or dangerous"
      }
    }
  }
}

# 输出
{
  "answers": {
    "skill": {
      "choice": "deploy",
      "confidence": 0.85,
      "probabilities": {
        "deploy": 0.85,
        "hold": 0.15
      }
    }
  }
}
```

---

## 整合优势

### 1. 延迟优化

| 层级 | 当前延迟 | 优化后 | 优化方式 |
|------|----------|--------|----------|
| 战略层 | 2-6s | 1-2s | 精简提示词、缓存 |
| 战术层 | 50ms | 50ms | 已优化 |
| 技能层 | 无 | 200ms | 启用Laya |

### 2. 决策质量

| 场景 | 当前 | 优化后 |
|------|------|--------|
| 满血建议回血 | ❌ 不合理 | ✅ 规则校验拦截 |
| 敌人贴身释放技能 | ⚠️ 硬编码 | ✅ Laya智能判断 |
| 波次<=3攻营 | ❌ 无效 | ✅ 规则校验拦截 |
| 低血量游击 | ⚠️ 有时失效 | ✅ 状态机自动切换 |

### 3. 资源利用

| 服务 | 当前 | 优化后 |
|------|------|--------|
| LLM数量 | 4个 | 4个 (但军师负载降低) |
| GPU显存 | 高 | 中 (Laya轻量) |
| CPU占用 | 中 | 低 (缓存优化) |

---

## 实施步骤

### 阶段1: 军师优化 (1天)

```bash
# 1. 精简提示词
# 编辑 advisor_simple.py

# 2. 增加规则校验
# 添加 validate_advice() 函数

# 3. 测试
python3 src/advisor_simple.py
```

### 阶段2: Pilot优化 (2天)

```bash
# 1. 改进距离控制
# 编辑 oc_pilot.py

# 2. 增加躲避算法
# 添加 avoid_bullets() 函数

# 3. 测试
python3 src/oc_pilot.py
```

### 阶段3: 启用Laya (3天)

```bash
# 1. 部署Laya服务
# 需要单独安装和配置

# 2. 配置环境变量
export LAYA_URL="http://127.0.0.1:8091/v1/systemone"

# 3. 测试
python3 src/oc_pilot.py
```

---

## 预期效果

### 玩家体验

| 指标 | 当前 | 优化后 |
|------|------|--------|
| 生存时间 | 中等 | 提升30% |
| 技能释放时机 | 一般 | 精准 |
| 战术切换流畅度 | 有卡顿 | 流畅 |

### AI表现

| 指标 | 当前 | 优化后 |
|------|------|--------|
| 建议合理性 | 70% | 90% |
| 响应延迟 | 2-6s | 1-2s |
| 技能命中率 | 60% | 85% |

---

## 风险评估

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Laya服务不稳定 | 中 | 技能释放回退到原规则 | 完善回退机制 |
| 规则校验过于严格 | 低 | AI过于保守 | 动态调整阈值 |
| 性能下降 | 低 | 延迟增加 | 优化算法 |

---

## 总结

**整合后的优势**:

1. **三层协同**: 战略+战术+技能，各司其职
2. **延迟优化**: 从2-6s降低到1-2s
3. **决策精准**: 规则校验+Laya神经打分
4. **体验提升**: 生存时间+30%，技能释放更精准

**建议实施顺序**:
1. 🔴 先优化军师提示词和规则校验 (立即见效)
2. 🟡 再改进Pilot距离控制 (提升体验)
3. 🟢 最后启用Laya (锦上添花)

---

> **制定**: AI Assistant | **日期**: 2024-10-04
