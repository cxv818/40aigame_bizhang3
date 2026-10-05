# v36.0
# 军师LLM排错调试记录

## 版本: v20.0
## 日期: 2025-10-03
## 问题: 军师LLM从未激活，参数一直是默认值

---

## 问题描述

游戏运行中，军师LLM（8083端口，35B模型）从未真正参与战术决策。
`advisor_get()` 返回的一直是默认值：

```json
{
  "ts": 0.0,
  "ideal_dist": 190.0,
  "style": "balanced",
  "threat": 1.0,
  "target": "auto"
}
```

`ts=0.0` 说明状态**从未被更新过**。

---

## 排查过程（按时间顺序）

### 第1步：检查环境变量 ❌

```bash
echo $TANK_ADVISOR_URL
# 输出: 空
```

**发现**: `ADVISOR_URL = os.environ.get("TANK_ADVISOR_URL", "")` 返回空字符串。
`main()` 中 `if ADVISOR_URL:` 判断为 False，**军师线程从未启动**。

**结论**: 这是最根本的原因。环境变量未设置 → 线程不启动 → 无决策。

### 第2步：硬编码URL重试 ❌

```bash
sed -i 's|ADVISOR_URL = os.environ.get(...)|ADVISOR_URL = "http://127.0.0.1:8083/v1/chat/completions"|' oc_pilot.py
```

重启Pilot后，线程数仍然是1（应该有2个）。

**发现**: Pilot进程只有1个线程，说明 `advisor_loop` 线程还是没启动或立刻崩溃。

### 第3步：验证LLM服务本身 ✅

```bash
curl -s http://127.0.0.1:8083/health
# {"status":"ok"}

# 直接调用测试
curl -s http://127.0.0.1:8083/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"测试"}],"max_tokens":10}'
# 正常返回
```

**结论**: LLM服务正常，问题在客户端代码。

### 第4步：检查游戏状态文件 ✅

```python
from oc_pilot import read_status
st = read_status()
print(st.get('state'))
# 'play'
```

**结论**: 游戏状态正常，条件满足。

### 第5步：独立测试advisor_loop ⚠️

手动启动线程测试，发现线程能启动，但**状态仍未更新**。

进一步测试LLM调用，发现响应内容：

```
"I need to be honest with you: I don't have enough context to..."
```

**发现**: LLM返回的是**解释性文本**，不是JSON！

### 第6步：发现提示词问题 🎯

测试不同提示词格式：

| 提示词 | LLM响应 | 结果 |
|--------|---------|------|
| `输出JSON:{"dist":200,...}` | "I can only see the JSON string..." | ❌ 模型困惑 |
| `玩家HP500/500,敌人10个。输出JSON:...` | "I need to understand..." | ❌ 模型困惑 |
| 完整规则+格式说明+system角色 | `{"dist": 250, "style": "kite", ...}` | ✅ 正常输出 |

**结论**: 35B模型需要：
1. **system角色**明确任务
2. **完整规则**说明JSON格式
3. **字段范围**说明
4. **"只输出JSON"** 强调

### 第7步：sed批量修改破坏代码 ❌

多次使用 `sed` 修改代码导致：
- `IndentationError: expected an indented block`
- 代码重复插入
- while循环体丢失

**教训**: 复杂Python代码不要用sed修改，用Python脚本或edit工具精确修改。

### 第8步：后台进程被SIGTERM杀掉 ❌

```bash
python3 advisor_simple.py &
# 等待期间命令被 SIGTERM/SIGKILL 中断
```

**发现**: 长时间 `sleep` 的命令会被中断，军师服务也跟着被杀。

### 第9步：最终方案 ✅ 独立进程 + 文件通信

创建独立军师服务 `advisor_simple.py`：
- 独立进程运行，不依赖Pilot线程
- 通过 `/tmp/advisor_state.json` 文件通信
- Pilot的 `advisor_get()` 改为优先读文件

**结果**: 军师LLM成功激活，每5秒更新决策！

```
[18:57:03] 响应(1.7s): {"dist":200,"style":"aggressive","threat":2,"target":"camp"}
[18:57:03] ✅ 更新: dist=200, style=aggressive
```

---

## 根本原因总结

1. **环境变量未设置** → 军师线程从未启动（主因）
2. **提示词格式不对** → 即使启动了，LLM也返回非JSON文本
3. **线程内调试困难** → 异常被 `except: pass` 吞掉，无声失败
4. **sed修改复杂代码** → 破坏缩进结构

---

## 最终解决方案

### 架构变更

```
旧方案（失败）:
Pilot进程 → 内部线程 → 直接调用LLM → 内存状态

新方案（成功）:
游戏 → 状态文件 → advisor_simple.py(独立进程) → LLM(8083)
                          ↓
                  /tmp/advisor_state.json
                          ↓
              Pilot.advisor_get() 读文件
```

### 关键代码

**1. 军师服务提示词（成功格式）**:

```python
body = json.dumps({
    "messages": [
        {"role": "system", "content": "你是一个游戏AI助手。只输出JSON格式的战术决策，不要任何解释。"},
        {"role": "user", "content": "HP500/500,敌人10个.回复JSON:{\"dist\":200,\"style\":\"aggressive\",\"threat\":2,\"target\":\"camp\"}"}
    ],
    "max_tokens": 100,
    "temperature": 0.1,
    "chat_template_kwargs": {"enable_thinking": False},
})
```

**2. Pilot读取文件**:

```python
def advisor_get():
    """读取军师状态（优先从服务文件读取）"""
    try:
        with open("/tmp/advisor_state.json", 'r') as f:
            data = json.load(f)
        if data and data.get("ts", 0) > 0:
            return {
                "ts": data.get("ts", 0),
                "ideal_dist": data.get("dist", 190.0),
                "style": data.get("style", "balanced"),
                ...
            }
    except:
        pass
    # 回退到内存默认值
    with _advisor_lock:
        return dict(_advisor_state)
```

**3. 多层JSON解析**:

```python
# 方式1: 直接解析
try: obj = json.loads(txt)
except: pass

# 方式2: 正则查找JSON块
if not obj:
    m = re.search(r"\{[^}]*\}", txt, re.DOTALL)
    if m: obj = json.loads(m.group(0))

# 方式3: 查找markdown代码块
if not obj:
    m = re.search(r"```json\s*(.*?)\s*```", txt, re.DOTALL)
    if m: obj = json.loads(m.group(1))
```

---

## 经验教训

1. **永远不要用 `except: pass` 吞掉线程异常** — 加日志，否则无声失败无法排查
2. **后台服务用独立进程** — 线程死掉主进程不知道，进程死了能看到
3. **进程间通信用文件** — 简单可靠，可离线检查（比共享内存/队列容易调试）
4. **35B小模型需要明确的system提示** — 角色设定+格式规则+范围约束+强调"只输出"
5. **复杂代码别用sed改** — 用Python脚本read/replace/write，或精确的edit工具
6. **排查顺序**: 服务健康 → 环境变量 → 线程启动 → 代码逻辑 → 提示词内容
7. **`ts=0` 是关键线索** — 时间戳为0 = 状态从未被更新 = 找更新代码为什么没执行

---

## 验证清单

部署后按此验证：

```bash
# 1. 军师服务进程存在
ps aux | grep advisor_simple | grep -v grep

# 2. 状态文件时间戳在更新（ts > 0 且不断变化）
cat /tmp/advisor_state.json | python3 -m json.tool

# 3. Pilot能读到状态
python3 -c "
import sys; sys.path.insert(0, 'src')
from oc_pilot import advisor_get
s = advisor_get()
assert s.get('ts', 0) > 0, '军师未激活!'
print('✅ 军师已激活:', s)
"

# 4. 日志显示持续更新
tail -f /tmp/advisor.log
# 应看到 "[xx:xx:xx] ✅ 更新: dist=..., style=..."
```

---

## 相关文件

| 文件 | 作用 |
|------|------|
| `src/advisor_simple.py` | 军师服务（推荐使用） |
| `src/advisor_service.py` | 军师服务完整版（含复盘分析） |
| `src/oc_pilot.py` | Pilot（advisor_get已改为读文件） |
| `/tmp/advisor_state.json` | 军师决策状态文件 |
| `/tmp/advisor.log` | 军师服务日志 |

---

## 追加案例：吕布不杀敌人（方阵困局）19:08

### 现象
吕布被21台敌军围在右下角，HP 500→165，击杀0。

### 根因
敌军AI进化出"铁壁合围"：21台全部紧贴(≤62px)结成方阵 → **全场免伤**。
Pilot检测到`_all_shield=True`不开火（正确），但**军师的提示词里没有方阵信息**，
脑不知道"打不到人"这个态势，继续下aggressive+camp指令 → 吕布硬顶挨打。

### 关键教训（架构层面）
> **修问题别修错层：手(Pilot)有问题查手，脑(LLM)缺信息喂脑。**
> 本次不是"Pilot不杀敌"的bug，是"脑看不到战场态势"的bug。
> Pilot拒绝打免伤盾是正确行为，不能为了"多杀敌"破坏它。

### 修复（改脑不改手的原则下，手只补执行）
1. **advisor_simple.py**：提示词注入方阵态势（盾数/可打数/被围数/离家距离），新增`home_heal`目标和战术参考规则
2. **oc_pilot.py**：仅添加home_heal的**执行**代码（朝大营走/60px内站桩回血/全盾不开火），零决策逻辑

### 验证
- 全盾+HP低 → LLM输出 `{"dist":320,"style":"kite","target":"home_heal"}` ✅
- 吕布脱离包围，HP 455→491回血中 ✅
- HP回升 → 军师自动切回 `target=enemies` 继续作战 ✅

---

## 追加案例2：Pilot崩溃循环（UnboundLocalError）19:24

### 现象
吕布僵在角落不动，看门狗日志显示"重启3次/2分钟"。

### 根因
home_heal分支的return引用了`mx, my`，但当吕布**已在营内**（dx0=dy0=0站桩回血）且
没走过camp分支时，`mx,my`从未赋值 → UnboundLocalError → Pilot崩溃 →
看门狗拉起 → 再崩 → **崩溃循环**。看门狗反而变成"自动喂尸"。

### 修复
```python
mx, my = hx, hy   # 瞄准大营方向(默认值,防UnboundLocalError)
```
在分支开头先给mx,my赋默认值。

### 附带发现
崩溃循环期间看门狗拉起了**多个Pilot实例**（多个进程同时发UDP指令互相打架），
已手动清理多余进程。看门狗改进方向：拉起前先`pkill`清场。

### 教训
1. return语句里的表达式引用的变量，必须在所有路径上都有赋值
2. 看门狗掩盖了崩溃（进程"存在"但活不过1秒），要用**进程存活时长**判断健康度
