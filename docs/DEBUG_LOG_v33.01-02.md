# v33.01/v33.02 排错修复记录（v36.0包内归档）

> 日期: 2026-10-04 深夜 ~ 2026-10-05 凌晨
> 范围: 33aigame v33.0 → v33.01(bug修复) → v33.02(36计LLM选计)
> 成果: 7个bug修复 + 1个新功能, 无头3遍验证0异常, 桌面已存最新副本 `35aigame/`

---

## 一、排错方法论（专家式层层验证）

1. **静态层**: `py_compile` 全量语法检查 + `pyflakes` 找未定义名/未用导入
2. **导入层**: 逐模块 `__import__` 验证import链（当场炸出4个模块瘫痪）
3. **单元层**: 跑 `tests/` 三个测试套件，抓API不匹配
4. **集成层**: dummy SDL 无头模式跑 `main()`，抓运行时崩溃
5. **数据层**: 检查落盘文件（`/tmp/hsdb_*.json`）是否真在写——**这步抓到了最深的bug**
6. **探针层**: 日志静默处加临时探针定位死分支（36计喊话无声问题）

**关键教训**: 错误被 `except: pass` 吞掉时表面一切正常，必须用"数据落盘了吗"来反向验证。

---

## 二、v33.01 修复清单（7个bug）

### 🔴 1. highspeed_db.py 新旧API断裂（系统瘫痪级）
- **现象**: `game_db/battle_recorder/tactics_evolution/battle_analyzer` 四模块 import 即炸
- **根因**: v33.0 把高速数据库重写为SQLite版，删了 `set()/sync()/get_db()/close_all()/get(key,default)`，但所有调用方还是旧API
- **修复**: 补齐兼容层——`set()`=put别名、`sync()`、模块级 `_DBS` 注册表+`get_db()`工厂、`get` 支持default、`get_stats` 补 `memory_items/hit_rate` 字段
- **验证**: 4模块import OK，三测试套件全过

### 🔴 2. SQLite 跨线程崩溃（数据静默丢失）
- **现象**: 游戏跑25秒，`/tmp/hsdb_battle.json` 一个字节都没落盘
- **根因**: `sqlite3.connect(':memory:')` 默认 `check_same_thread=True`，游戏主循环线程与同步线程共享连接时抛 `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`，被上游 `except: pass` 吞掉
- **定位过程**: 猴子补丁 `BattleRecorder.record` 确认被调452次→单测直连DB正常→跨线程访问才炸→锁定connect参数
- **修复**: `check_same_thread=False`（线程安全由 `self.lock` 保证）
- **验证**: writes=24, syncs=11, 磁盘落盘✅

### 🔴 3. oc_pilot.py urllib NameError
- **现象**: Laya哨兵技能判断每次调用必崩（被try吞）
- **根因**: `urllib.request` 只在 `main()` 里局部import，`laya_ask_skill()` 在模块级函数里用不到
- **修复**: 提升到模块级 `import urllib.request`

### 🟠 4. 战术多样化强制器形同虚设
- **现象**: `test_diversity.py` 抓到——LLM输出单一战术"山地占领"（不在受控名单），10台坦克原样放行
- **根因**: 保留条件只查 `current_tactic not in overused`，名单外战术直接放行
- **修复**: 只有「在受控池 + 不超占比 + 非全场单一」的指令才可保留
- **验证**: 10个敌人→4种战术均衡分布，测试过

### 🟠 5. tactics_db.py 路径跨项目污染
- **现象**: 战术数据写到了旧项目 `/home/ibm/桌面/23aigame/data/`
- **修复**: 改为基于 `__file__` 的项目内路径 `<root>/data/tactics_db.json`

### 🟠 6. generals.py 死文件且必崩
- **现象**: 单独import即 `NameError: Tank`（25处未定义名）
- **核实**: 主程序用的是内联 `General` 类（tank_battle_deluxe.py 2697行），此文件从未被任何代码引用
- **处置**: 移除（新版35aigame已不含）

### 🟡 7. self_check.py 自检路径失效
- **现象**: 检查的文件路径写死 `/home/ibm/桌面/26aigame/`（不存在的旧目录）
- **修复**: 改为基于 `__file__` 的项目相对路径

### 附加优化
- 惰性commit：纯内存库攒批提交，写性能 9.7万→18.2万 ops/s
- `PRAGMA journal_mode=MEMORY + synchronous=OFF`（内存库无崩溃恢复需求）
- `tactics_evolution.py` 补 `reset()`（测试依赖）

---

## 三、v36.0 新功能：曹操·36计LLM真选计

### 背景
原 `coordinate_attack()` 每12秒从预写模板**随机抽**一条36计喊话——纯氛围，与实际战术分配零联动。

### 实现（`src/stratagem_llm.py`）
- 16条精选计策库，每条含：含义 + 战术约束（forced_plans/attack_camp_ratio/note）
- 每45秒把战场态势（波次/双方HP/大营血量/当前部署）发给曹操LLM(8080)
- LLM输出 `{"stratagem":"计名","reason":"≤20字军令"}`，模糊匹配计名容错
- **计策→战术硬联动**: 选中计策经 `prompt_block()` 注入三帅 `_build_prompt`（基础调度+高级调度双路径）
- LLM失败2次自动降级随机模板（保持联动），游戏永不阻塞
- 频道注入: 主循环 `attach_channel(channel=WEI_CHANNEL, comm=COMM)` 避免循环导入

### 踩坑记录（重要！）
1. **喊话静默失败**: `_announce` 最初试图 `from tank_battle_deluxe import WEI_CHANNEL` —— 但 `WEI_CHANNEL` 是 `main()` 局部变量（虽有 `global` 声明），循环导入拿到的是半初始化模块 → 改为 `attach_channel()` 由主循环显式注入实例
2. **日志假死**: 重定向到文件后 stdout 缓冲区不满就不写，看起来像进程卡死 → 用 `python3 -u` 无缓冲 + 遥测文件时间戳判断真实心跳
3. **GL context BadAccess**: 多个pygame实例/锁屏状态抢GL → 无头验证用 `SDL_VIDEODRIVER=dummy`，带窗口启动前确保旧实例清干净

### 实战验证
```
[0.6s]  【魏军】曹操→夏侯渊: 【36计·瞒天过海】敌军未察，趁虚而入，暗藏杀机
[45.9s] 【魏军】曹操→夏侯惇: 【36计·无中生有】虚张声势，先造声势诱敌暴露
[90.9s] 【魏军】曹操→夏侯渊: 【36计·苦肉计】不宜硬拼，示弱诱敌，待机反击
[127.6s] 曹操: 13号 → 右翼游击-远程袭   ← 苦肉计生效，全军转游击！
```
计策各不相同、贴合战局，战术分配真实响应计策约束。

---

## 四、验证记录汇总

| 验证项 | 结果 |
|--------|------|
| pyflakes 未定义名 | 修复前26处 → 修复后 0（主链路） |
| 模块import链(9模块) | 修复前4失败 → 修复后全OK |
| tests/test_highspeed_db.py | ✅ 全过（写18.2万/读29.1万 ops/s） |
| tests/test_tactics_evolution.py | ✅ 全过 |
| tests/test_diversity.py | ✅ 全过 |
| 无头运行3遍×25s | 0代码级异常 |
| hsdb落盘 | writes=24, syncs=11 ✅ |
| 36计LLM选计 | 计策-战术联动实盘生效 ✅ |
| 三帅进化 | 第283代持续累积 ✅ |
| 带窗口启动 | 稳定运行, pilot接管, 36计开局即选 ✅ |

---

## 五、遗留观察项（非bug）

1. `run1.log` 里 `[DEBUG] 读取快速状态失败: tank_fast.json` —— pilot与游戏启动时序竞争，pilot先起时读不到文件，游戏起来后自愈。可在pilot侧重试逻辑优化
2. `advisor_simple.py` 与游戏内军师频道（8083）是两条独立链路，重启游戏后记得检查 advisor 进程是否连的是活着的8083（本次踩过：旧advisor进程连着已死的旧端口静默报错）
3. 玩家残血 (<100) 时提示词有"全力收割"标记——敌方LLM会围杀，pilot残血时注意走位
