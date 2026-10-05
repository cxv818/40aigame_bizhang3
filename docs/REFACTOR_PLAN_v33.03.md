# 重构执行方案（详细施工图）

> 日期: 2026-10-05
> 前置: 《ARCHITECTURE_DEBATE_v33.md》论辩裁决
> 本文 = 6个交付项的逐文件施工图，含代码级改动说明、验证步骤、回滚预案
> 总工时: 3天 | 每项独立交付 | 每日收尾跑标准冒烟流程

---

## 全局约定

- **工作目录**: `~/桌面/33aigame`（每日收尾同步到 `~/桌面/35aigame`）
- **标准验证流程**（每项交付前必跑）:
  ```bash
  cd ~/桌面/33aigame
  python3 -m py_compile src/*.py                 # 语法
  python3 tests/test_highspeed_db.py             # 三测试
  python3 tests/test_tactics_evolution.py
  python3 tests/test_diversity.py
  # 无头冒烟3遍(见下方脚本)
  ```
- **无头冒烟脚本** `/tmp/smoke.sh`:
  ```bash
  #!/bin/bash
  cd ~/桌面/33aigame/src
  for i in 1 2 3; do
    rm -f /tmp/hsdb_smoke*.json
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy timeout 25 \
      python3 -u -c "import tank_battle_deluxe as t; t.main()" \
      > /tmp/smoke_$i.log 2>&1
    ERR=$(grep -cE "Traceback|NameError|AttributeError|TypeError|KeyError" /tmp/smoke_$i.log)
    echo "第${i}遍: 异常=$ERR 行数=$(wc -l < /tmp/smoke_$i.log)"
    [ "$ERR" != "0" ] && echo "❌ FAIL" && tail -20 /tmp/smoke_$i.log && exit 1
  done
  echo "✅ 冒烟通过"
  ```
- **回滚预案**: 每天开工前 `git init`（若无）+ commit；每交付一项 commit 一次。出问题 `git checkout -- src/` 秒回滚

---

## 第1天上午 · 交付项①②③（合计约2小时）

### ① R重开进程重生（5行，30分钟含验证）

**文件**: `src/tank_battle_deluxe.py` 约3190行

**改前**:
```python
if state in ("gameover", "win") and event.key == pygame.K_r:
    main()
    return
```

**改后**:
```python
if state in ("gameover", "win") and event.key == pygame.K_r:
    # v36.0: 进程重生替代递归——内核兜底清零线程/内存/socket,不可能漏清状态
    # (旧递归每次泄漏3×AIDirector+11线程; os.execv 物理消灭该问题)
    pygame.quit()
    os.execv(sys.executable, [sys.executable] + [os.path.abspath(__file__)])
```

**验证**: 无头模式模拟 gameover 后按键 R（用 pygame.event.post 注入），确认新进程 PID 变化、UDP 端口重绑成功、进化存档保留。
**回滚**: git revert 单文件。

### ② 吞异常留痕（1小时）

**文件**: 新增 `src/swallow.py`；改动 `tank_battle_deluxe.py` 8处

**新增** `src/swallow.py`:
```python
# v36.0: 静默异常限流留痕——每个标签每小时只记1条,防刷屏
import time

_last = {}

def swallow(tag, exc, rate=3600):
    now = time.time()
    if now - _last.get(tag, 0) < rate:
        return
    _last[tag] = now
    print(f"[SWALLOWED] {tag}: {type(exc).__name__}: {exc}", flush=True)
```

**8处关键位清单**（只改这些，其余13处纯防御性 pass 保持原样）:

| # | 位置(约) | tag | 现状 |
|---|---------|-----|------|
| 1 | 4265 战术进化每12帧 | `evo_tick` | except: pass |
| 2 | 4257+ 战场记录record_frame | `battle_record` | except: pass |
| 3 | 进化复盘 _worker 内层 | `evo_review` | print DEBUG |
| 4 | 选计器 _announce | `strat_announce` | print失败 |
| 5 | 遥测写盘 _save_slow | `telem_slow` | except: pass |
| 6 | 遥测写盘 fast 30s段 | `telem_fast` | except: pass |
| 7 | hsdb._sync_to_disk | `hsdb_sync` | 已print,统一格式 |
| 8 | 36计注入 _stratagem_block | `strat_inject` | except: "" |

**改法模板**:
```python
from swallow import swallow
except Exception as e:
    swallow("battle_record", e)
```

**验证**: 人为断开8080跑冒烟，确认 `[SWALLOWED]` 出现且1小时内同标签只1条。
**回滚**: git revert；swallow.py 是纯新增无依赖风险。

### ③ 删死文件（10分钟）

```bash
git rm src/advisor_service.py        # 无人引用(已验证grep零引用)
git rm src/highspeed_db_old.py       # 旧版尸体
# generals.py 已在v33.01清掉
```
删前 `grep -rn "advisor_service\|highspeed_db_old" src/ tests/ scripts/` 最后确认零引用。

---

## 第1天下午 · 交付项④ stats_view.py（半天）

**目标**: 双口径战术账合并出口——LLM提示词只喂一份自洽视图。

**背景口径定义**（写死在文件头）:
- `tactics_db.json`（改名 `tactics_hit_account.json`）= **命中视角**: 子弹命中时, 该敌当时挂的战术记账。deaths 恒为0是正常的（命中事件里不含死亡信息）
- `AIDirector.plan_stats`（内存+evolution.json）= **发令视角**: 发令时记账, hits=该战术执行期间玩家受击, deaths=执行期间该方阵亡

**新增** `src/stats_view.py`:
```python
# v36.0: 战术统计唯一出口——双口径合并视图
# 口径A(tactics_hit_account.json): 命中视角。used=该战术在场时敌子弹命中玩家的次数
# 口径B(plan_stats/evolution.json): 发令视角。issued=发令次数, hits/deaths=执行期间结果
import json, os

HIT_ACCOUNT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "tactics_hit_account.json")

def _load_hit_account():
    try:
        with open(HIT_ACCOUNT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_merged_report(plan_stats=None, top=5):
    """双口径合并报告。plan_stats 传 AIDirector 实例的 dict; 不传则只出口径A。
    输出给LLM的每一行都自洽: 一个数字只来自一个口径。"""
    a = _load_hit_account()
    lines = ["📈战术统计(双口径: [发令]/[命中] 视角):"]
    names = list(dict.fromkeys(list(a.keys()) + list((plan_stats or {}).keys())))
    scored = []
    for n in names:
        ha = a.get(n, {})
        ps = (plan_stats or {}).get(n, {})
        issued = ps.get("issued", 0)
        # 效果分 = 0.6*命中率(口径B: hits/issued) + 0.4*存活率(口径B)
        eff = 0.0
        if issued > 0:
            eff = 0.6 * min(1.0, ps.get("hits", 0)/issued) + \
                  0.4 * max(0.0, 1.0 - ps.get("deaths", 0)/issued)
        scored.append((n, issued, ha.get("used", 0), eff))
    scored.sort(key=lambda x: -x[1])
    for n, issued, hit_used, eff in scored[:top]:
        lines.append(f"- {n}: [发令]{issued}次 [命中记]{hit_used}次 综合{eff:.2f}")
    return "\n".join(lines)
```

**接线**（2处）:
1. `_build_prompt` 里 `tactics_stats` 段替换:
   ```python
   from stats_view import get_merged_report
   tactics_stats = "\n" + get_merged_report(self.plan_stats) + "\n"
   ```
2. `tactics_db.py` 文件名迁移: 首次运行时若旧 `tactics_db.json` 存在则改名（保留历史数据），DB_FILE 指向新名:
   ```python
   OLD = os.path.join(_DATA, "tactics_db.json")
   if os.path.exists(OLD) and not os.path.exists(DB_FILE):
       os.replace(OLD, DB_FILE)
   ```

**验证**: 无头跑2分钟 → diff 新旧提示词统计段（临时print），确认数字与 plan_stats 实时一致且带双口径标注。
**回滚**: stats_view.py 是纯新增；接线处 git revert 两个 hunk。

---

## 第2天 · 交付项⑤ 拆 channels.py + world_api.py（1天）

### ⑤a world_api.py（上午，纯函数零风险）

**搬走**（tank_battle_deluxe.py 74-147行 + 相关helper）:
- `barricade_blocks / boss_wall_blocks / barricade_slide / separate_enemies`
- 依赖检查: 只用 math/random + 模块级常量（WIDTH/HEIGHT 改为函数参数或从 config 常量文件 import——**用参数，避免引入新全局**）

**搬后主文件**:
```python
from world_api import barricade_blocks, boss_wall_blocks, barricade_slide, separate_enemies
```
注意: `barricade_blocks` 在 General/Boss 类方法里被调用（模块级引用），类也一起搬或保留原文件皆可——**类不动，函数搬**，类里调用改为 import 名。

### ⑤b channels.py（下午，三个通讯类）

**搬走**:
- `SquadComm`(278-338) / `WeiCommandChannel`(538-635) / `AdvisorChannel`(637-1247)

**关键改造点**（本次踩坑处，集中解决）:
1. 三类的 `COMM` 引用问题统一: 类初始化不再依赖全局 COMM，改为构造注入:
   ```python
   # channels.py
   class WeiCommandChannel:
       def __init__(self, comm=None):
           self.comm = comm          # main() 里: WeiCommandChannel(comm=COMM)
   ```
2. `AdvisorChannel` 依赖较多（llm调用/进化存档）——它是最重的一个，搬时连带 `_load_evolution/_save_evolution/request_review_async` 全套方法平移，**不改任何语句逻辑，只改 import 和 COMM 引用方式**
3. `stratagem_llm.attach_channel` 不变（它拿的是实例，与文件位置无关）

**主文件只剩**:
```python
from channels import SquadComm, WeiCommandChannel, AdvisorChannel
```

**验证**: 全天收尾跑标准冒烟 + 额外检查:
- 魏军频道36计喊话出现在日志（`grep 36计`）
- 军师建议照常（`grep 军师`）
- R重生后频道仍工作（交付项①联测）

---

## 第3天 · 交付项⑥⑦ directors.py + llm_client.py + 埋点（1天）

### ⑥ directors.py（上午）

**搬走**: `ClusterPlanner`(339) / `BattleMemory`(1339) / `FormationManager`(431) / `AIDirector`(1421-2329，最大的一块)

**搬迁红线**:
- AIDirector 内部语句顺序**一字不改**（进化复盘时序是实战验证过的）
- `global DIRECTOR...` 模式保留（main 里照旧 global 赋值——争议点一裁决: 不改全局风格，只搬位置）
- `request_review_async`（三帅版2107行）与军师版(1102)在 AdvisorChannel 内的，随⑤b已走；确认无重复定义

### ⑦ llm_client.py（下午前半）

**新增** `src/llm_client.py`:
```python
# v36.0: LLM调用唯一出口——重试/超时/降级/耗时统计
import json, time, threading, urllib.request

_stats = {}          # port -> {calls, fails, total_ms, last_fail}
_lock = threading.Lock()

def ask(port, prompt, max_tokens=800, temperature=0.7, timeout=25,
        retries=0, tag=""):
    """调用 llama-server OpenAI 兼容接口。返回 (text, latency_s)。
    失败重试 retries 次; enable_thinking=false + reasoning_content 兜底 已内置。"""
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    last_exc = None
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            msg = data["choices"][0]["message"]
            text = msg.get("content", "") or msg.get("reasoning_content", "") or ""
            _record(port, time.time() - t0, ok=True)
            return text, time.time() - t0
        except Exception as e:
            last_exc = e
            _record(port, time.time() - t0, ok=False)
    raise last_exc

def _record(port, ms, ok):
    with _lock:
        s = _stats.setdefault(port, {"calls": 0, "fails": 0, "total_ms": 0})
        s["calls"] += 1
        s["total_ms"] += ms
        if not ok: s["fails"] += 1

def health():
    """给 self_check 用: {port: {calls, fails, fail_rate, avg_ms}}"""
    with _lock:
        return {p: {**s, "avg_ms": round(s["total_ms"]/max(1, s["calls"])),
                    "fail_rate": round(s["fails"]/max(1, s["calls"]), 2)}
                for p, s in _stats.items()}
```

**替换5个调用点**（逐个替换，每换一个跑一次冒烟）:
| 调用点 | 替换后策略 |
|--------|-----------|
| AIDirector._query(1623) | retries=1（三帅可重试一次） |
| _send_enhanced_request(1640) | retries=1 |
| 军师 _ask_llm(1191) | retries=0（有fallback关键词） |
| 选计器 _worker | retries=0, timeout=12（短prompt，失败立刻降级模板——争议点五裁决） |
| 进化复盘 worker(2164) | retries=0, timeout=25 |

**self_check 接入**: `_check_llm_servers` 末尾追加 `llm_client.health()` 输出。

### ⑧ 关键时刻时间线埋点（下午后半，3小时）

**改造**: `battle_recorder.record_event` 已存在，补6个埋点调用:

| 埋点 | 位置 | 事件名 |
|------|------|--------|
| 敌将出场/阵亡 | generals 生成/移除处(3199/3206) | `general_spawn` / `general_down` |
| 方阵成阵/被破 | phalanx 状态切换处(搜 `in_phalanx`) | `phalanx_form` / `phalanx_break` |
| 集火充能完成/失败 | 集火计数处(搜 `合火`) | `focus_ready` / `focus_fail` |
| 大营受击 | camps update 处 | `camp_hit` |
| 计策切换 | stratagem_llm._worker 成功后 | `stratagem_change` |

**复盘提示词注入**（`request_review_async` worker 里，prompt 拼接前）:
```python
from battle_recorder import get_recent_events  # 新增: 取本波事件
timeline = "\n".join(f"{e['t']:.0f}s {e['type']} {e.get('data','')}"
                     for e in get_recent_events(wave_start_ts))
prompt += f"\n本波关键时刻时间线:\n{timeline}\n(据此分析战术失败/成功的因果)"
```
`get_recent_events` 新增于 battle_recorder: 内存保留最近200条事件，按 ts 过滤。

---

## 每日收尾清单

```bash
# 1. 标准验证
bash /tmp/smoke.sh
python3 tests/test_*.py 三个

# 2. 带窗口实测(可选, 若屏幕未锁)
#    手动开局看: 军师喊话/36计/pilot接管/R重生

# 3. 同步 + 存档
cp src/{swallow,stats_view,llm_client,channels,world_api,directors}.py ~/桌面/35aigame/src/
cp src/tank_battle_deluxe.py src/battle_recorder.py src/stratagem_llm.py ~/桌面/35aigame/src/
echo "v33.03" > ~/桌面/35aigame/VERSION

# 4. git commit + 更新本文档勾选状态
git add -A && git commit -m "v33.03-dayN: <交付项>"
```

---

## 风险与红线（重申）

1. **AIDirector 搬迁不改任何语句** —— 只动 import 和文件位置。改动即重掷进化时序的骰子
2. **evolution*.json 格式冻结** —— 283代资产，本次所有改动零触及
3. **每交付一项必须冒烟** —— 不许攒到最后一起验
4. **channels.py 的 COMM 注入** 是本次唯一的行为级改动（原来读全局，现在构造注入），冒烟时重点盯军师/魏军频道是否照常出声
5. 若第2天拆 channels 后出现任何"频道无声"，回滚顺序: 先 git revert channels → 检查 attach_channel → 不要现场修

## 完成后的架构图（3天后）

```
tank_battle_deluxe.py (约2400行: 实体类+main主循环)
├── channels.py      SquadComm / WeiCommandChannel / AdvisorChannel
├── directors.py     AIDirector / ClusterPlanner / BattleMemory / FormationManager
├── world_api.py     纯几何函数
├── stratagem_llm.py 36计(已存在)
├── llm_client.py    LLM统一出口+健康统计   ★新
├── stats_view.py    双口径战术视图         ★新
├── swallow.py       异常限流留痕           ★新
├── highspeed_db.py / battle_recorder.py(+埋点) / tactics_db.py / self_check.py
└── main() <300行增量: 装配+时序, 不含类定义
```

---

## ✅ 执行完成记录（2026-10-05 03:25~03:45 实际用时约20分钟）

| 交付项 | 状态 | commit |
|--------|------|--------|
| git init + baseline | ✅ | d0cd64e |
| ① R重开进程重生 | ✅ | 690d247 |
| ② swallow留痕8处 | ✅ 顺带抓到隐藏KeyError并修复 | 690d247 |
| ③ 删死文件 | ✅ | 690d247 |
| ④ stats_view双口径 | ✅ 含旧数据自动迁移 | 4daf153 |
| ⑤a world_api.py | ✅ 91行 | 62a4da8 |
| ⑤b channels.py | ✅ 802行 | fd9f1d4 |
| ⑥ directors.py | ✅ 1152行 | e2b6841 |
| ⑦ llm_client.py | ✅ 7处推理调用全接入 | 293892d |
| ⑧ 埋点+时间线 | ✅ 6埋点+复盘注入 | ac04899 |

### 意外收获（计划外修复）
1. swallow上线即抓到 `dominant_ratio` KeyError（隐身bug）
2. 发现day2拆channels时因行号位移**漏删旧AdvisorChannel(584行)**——旧类覆盖import的新类。经方法清单diff确认channels版完整平移后删除残留
3. directors拆分时音效/粒子全局(tone/SND_*/play/flash等48行)被误切,已切回主文件

### 最终形态
- 主文件 4494 → 2552 行（-43%）
- 新增7个内聚模块: directors(1152)/channels(802)/world_api(91)/llm_client(75)/stats_view(75)/swallow(12)
- 9个git commit, 每步可回滚
- 全程: 冒烟3遍×9轮 0异常、三测试套件全过、频道/36计/进化(319代)/军师实调全部深检确认

### 每次改动后必跑（已内化）
```bash
bash /tmp/smoke.sh   # 无头3遍
python3 tests/test_*.py
```
