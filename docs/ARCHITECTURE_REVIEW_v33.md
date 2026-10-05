# 33aigame 架构评审与重构规划 v1.0

> 日期: 2026-10-05
> 范围: 全项目 7890 行 Python / 7 进程 / 11+ 线程 / 6 路并发 LLM
> 结论先行: **功能设计优秀，工程结构欠债明显**。建议"数据总线统一 + 主循环拆分 + 进化系统合并"三步走，不做推倒重写。

---

## 一、现状全景

### 1.1 模块清单（按行数）

| 文件 | 行数 | 职责 | 评价 |
|------|------|------|------|
| tank_battle_deluxe.py | **4494** | 游戏引擎+20个类+main() | ⚠️ 巨石文件，一切问题的根源 |
| oc_pilot.py | 547 | 玩家坦克AI(20Hz) | ✅ 独立清晰 |
| self_check.py | 447 | 自检系统 | ✅ 可用 |
| battle_recorder.py | 315 | 战场记录 | ✅ 职责单一 |
| tactics_evolution.py | 265 | 战术进化 | ⚠️ 与tactics_db重复 |
| advisor_simple.py | 256 | 军师服务进程 | ⚠️ 与游戏内AdvisorChannel重复 |
| stratagem_llm.py | 243 | 36计选计(新) | ✅ 独立清晰 |
| highspeed_db.py | 229 | SQLite内存库 | ✅ 修复后健康 |
| battle_analyzer.py | 198 | 战报分析 | ⚠️ 依赖recorder但少被用 |
| tactics_db.py | 101 | 战术效果库 | ⚠️ 与tactics_evolution重复 |
| 其余(generals等) | ~500 | 已清理/死代码 | — |

### 1.2 运行时拓扑

```
进程层(7):
  游戏(pygame, 11线程) ── UDP:8089 ── pilot
       │ HTTP:8080-8083 ── 4×llama-server(35B, GPU0/1/2)
       │ HTTP:8091 ── laya哨兵
       └ advisor_simple(独立进程, 读/tmp状态→调8083→写/tmp)

数据总线(/tmp文件, 无锁裸读写):
  tank_battle_status.json (2s慢遥测)
  tank_fast.json          (0.2s快遥测)
  hsdb_battle.json        (1s同步SQLite落盘)
  advisor_state.json      (军师参数包)
```

### 1.3 好的部分（值得保留的设计）

1. **LLM分层决策架构** — 三帅(战术)+军师(谋略)+Laya(本能)三层大脑，频控清晰(1.5s/5s/1s)，异步pending防阻塞，reasoning_content兜底解析。这套设计是项目灵魂，**不要动**
2. **进化闭环** — 方案谱系跨波累积→冷却限速复盘→教训代际继承→按武将分档存档。第283代实战数据证明有效
3. **高速数据库设计** — 内存SQLite+1s增量落盘+原子替换，修复后写入18万ops/s
4. **强制多样化双保险** — 提示词约束(LLM自觉)+代码强制(执行兜底)，被实战验证必要
5. **遥测永不阻塞游戏** — 所有LLM/IO均daemon线程+except兜底，主循环零等待

---

## 二、问题清单（按危害排序）

### 🔴 P1: 巨石主文件（4494行，main()独占1500行）

**症状**: 20个类挤在一个文件；游戏引擎/AI导演/频道系统/武将系统/遥测系统混杂；改一处要理解全局。

**实害**（本次排错实证）:
- 变量遮蔽：`COMM` 在main()里 `global` 赋值，类方法读模块级变量——36计喊话静默失败排查了40分钟
- 双重定义风险：两个 `_stratagem_block` 定义相邻(528/534行)，后者覆盖前者，静默
- 死代码滋生：`highspeed_db_old.py`、旧版generals.py这类尸体没人敢删

### 🔴 P2: R重开 = main()递归（资源泄漏）

```python
if state in ("gameover", "win") and event.key == pygame.K_r:
    main()   # 递归!
    return
```
每重开一层：新建SquadComm/3×AIDirector/11个daemon线程/UDP socket。注释说"死亡/R重开走main()递归,若每次重建socket+线程"——**意识到了但只解决了socket**。长局多开必内存上涨、线程堆积。

### 🟠 P3: 战术数据四套并存（同一概念4处存储）

| 存储 | 位置 | 写者 | 读者 |
|------|------|------|------|
| tactics_db.json | data/ | 游戏内LLM效果记录 | 提示词统计、进化过滤 |
| hsdb_tactics_evolution | /tmp | tactics_evolution.py | 几乎没人读 |
| plan_stats(内存) | AIDirector | 三帅 | 进化复盘 |
| evolution*.json | config/ | 进化存档 | 跨局继承 |

同一战术的"使用/命中/阵亡"在3处各记各的，数字对不上（本次实锤：tactics_db说山地占领112次发令，plan_stats谱系里是另一套数）。**进化系统吃的统计与给LLM看的统计不是同一份**。

### 🟠 P4: 文件轮询当IPC（脆弱的总线）

pilot↔游戏 既有UDP又有`/tmp/*.json`轮询；advisor_simple靠轮询status文件。JSON裸读写无锁——本次`tank_fast.json` FileNotFound报错就是时序竞争。虽然"自愈"，但每秒几十次无效轮询+偶发脏读。

### 🟡 P5: 21处 `except Exception: pass`

本次修复的bug一半拜它所赐（SQLite跨线程、urllib NameError全被吞）。完全去掉不现实（游戏确实不能停），但**连日志都不留**等于埋雷。

### 🟡 P6: 测试覆盖3/15

只有3个测试文件且都是数据层。游戏逻辑（碰撞/波次/技能/计策约束注入）零测试——本次36计的计策-战术联动全靠人眼看日志。

### 🟡 P7: GPU资源刚性绑定

4×35B实例固定绑3张卡(24GB/卡已用~70%)。军师用exps=CPU挤在第3卡。想加第5个AI服务或换更大模型，得手动改env.sh+重启全部。

---

## 三、重构规划（三步走，每步可独立交付）

### 第一步：止血（1天，零风险）

**目标：不再产生新债务，不改变任何行为**

1. **吞异常留痕**：21处 `except Exception: pass` 统一改为 `except Exception as e: _swallow(e, "位置说明")`，新logger写 `/tmp/tank_swallow.log`，每位置每小时只记首条（防刷屏）
2. **删死代码**：highspeed_db_old.py、注释掉的旧generals、第一个`_stratagem_block`定义
3. **R重开改软复位**：`main()` 拆出 `_reset_world()`，重开只清空实体/计数器/频道，不重建线程和socket
4. **补test**：给 `_enforce_tactic_diversity`、`stratagem_llm.prompt_block`、`_parse_orders` 各补最小用例（本次三个bug都在这三处附近）

### 第二步：正骨（3-4天，中风险，逐文件迁移）

**目标：拆巨石，统一数据，不改功能**

```
src/
├── engine/           # 纯pygame: entities.py(Bullet/Tank/Player/Enemy/General/Boss)
│                     #           world.py(碰撞/波次/大营/山地/道具), render.py
├── ai/
│   ├── director.py   # AIDirector+ClusterPlanner+BattleMemory+FormationManager
│   ├── channels.py   # WeiCommandChannel+AdvisorChannel+SquadComm
│   ├── stratagem.py  # 36计(已有,挪进来)
│   └── evolution.py  # ★合并三套战术存储为一套(见下)
├── infra/
│   ├── hsdb.py       # highspeed_db(已稳定)
│   ├── telemetry.py  # 快慢遥测统一出口
│   └── llm_client.py # ★统一LLM调用: 重试/超时/降级/用量统计一处管
└── main.py           # 目标<300行: 只做装配+主循环时序
```

**进化数据统一方案**（解P3）：
- 唯一事实源 = hsdb `tactics` 表（已有1s落盘）
- `tactics_db.py`、`tactics_evolution.py`、`AIDirector.plan_stats` 全部改为读写同一张表的不同视图
- evolution*.json 只存"教训"（LLM产出的文本），统计数字一律查库
- 好处：给LLM看的统计=进化吃的统计，复盘数字可信

**统一LLM客户端**（解P7的一部分）：
- 现在散落5处的 `urllib.request+timeout+chat_template_kwargs+reasoning_content兜底` 收敛为一个 `llm_client.ask(port, prompt, max_tokens, temperature)`
- 自带：失败计数/自动降级、调用耗时统计（给self_check暴露LLM健康度）、未来换模型只改一处

### 第三步：进化（按需，1-2周）

**目标：架构红利变现**

1. **总线升级**：/tmp JSON轮询 → 本地WebSocket或Unix socket推送（pilot/advisor订阅制，消灭轮询和脏读）。UDP保留给20Hz控制流（它就该用UDP）
2. **AI服务池**：llama-server前置一个轻量路由(哪怕50行nginx)，三帅/军师/选计共享实例池按负载调度——同模型本就不用4份显存，可省一张卡给更大ctx或第4帅
3. **回放系统**：battle_recorder已有完整帧数据，补一个`replay.py`即可用LLM做赛后深度复盘（现在只复盘波次摘要）
4. **对局自评**：每局结束用回放数据让三帅+军师互相评分（吕布侧+魏军侧各一份战报），喂进化系统——从"波次学习"升级到"整局学习"

---

## 四、不建议做的事

- ❌ **换游戏框架/上ECS**： pygame单文件跑30fps毫无压力，重构收益为零
- ❌ **推倒重写**： 进化系统283代数据是真实资产，新架构必须兼容旧evolution.json
- ❌ **一次性大迁移**： 巨石文件拆分必须逐类搬+每搬一个跑一遍无头冒烟，一次全拆必炸
- ❌ **微服务化游戏进程**： 7进程已经够多，游戏本体必须保持单进程（sprite组共享内存）

---

## 五、优先级速查

| 做 | 何时 | 收益 |
|----|------|------|
| 吞异常留痕+删死代码 | 立即 | 下次排错省40分钟 |
| R重开软复位 | 立即 | 消除线程/内存泄漏 |
| 进化数据四合一 | 第二步 | 复盘统计可信 |
| 拆main() | 第二步 | 改功能不再提心吊胆 |
| 统一LLM客户端 | 第二步 | 降级/监控/换模型一处搞定 |
| 总线升级WebSocket | 第三步 | 消灭轮询脏读 |
| LLM实例池 | 第三步 | 省一张卡 |

**一句话总结**：这个项目最值钱的是"LLM分层决策+代际进化"的设计和283代的实战数据，最欠债的是4494行巨石和四套并存的战术存储。先止血（留痕+软复位），再正骨（拆文件+统一数据），别重写。
