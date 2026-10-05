# 39aigame — 坦克大战AI集群作战系统 v39.0

> **吕布(玩家/OpenClaw pilot) vs 曹操(AI集群)** — Pygame 实时AI对抗
>
> v39.0 = 军师控制优化版：修复边界问题 + 增强提示词 + 后处理修正

---

## ⚡ 快速启动

```bash
cd ~/桌面/39aigame
bash scripts/start_all.sh          # 一键启动全部服务
bash scripts/stop_all.sh           # 一键停止
```

## 📁 项目结构

```
39aigame/
├── src/                    # 源码目录
│   ├── tank_battle_deluxe.py   # 游戏主程序
│   ├── channels.py              # 通讯系统（军师优化）
│   ├── directors.py             # AI导演
│   ├── oc_pilot.py              # Pilot控制
│   └── ...
├── config/                 # 配置文件
│   └── env.sh                   # 环境变量
├── scripts/                # 启动脚本
│   ├── start_all.sh             # 一键启动
│   ├── stop_all.sh              # 一键停止
│   └── ...
├── docs/                   # 文档目录
│   ├── v39.0_军师控制优化详解.md
│   ├── v39.0_部署指南.md
│   ├── v39.0_游戏逻辑详解.md
│   └── ...
├── data/                   # 数据目录
├── tests/                  # 测试目录
├── 启动说明.md             # 详细启动说明
├── CHANGELOG.md            # 更新日志
└── VERSION                 # 版本号
```

## 🧠 核心特性

### 军师控制优化 (v39.0)
- ✅ 修复军师不工作问题
- ✅ 修复边界卡住问题
- ✅ 修复指令stuck问题
- ✅ 增强提示词，添加边界警告
- ✅ 后处理修正，强制离开边界
- ✅ 调试信息输出

### AI集群作战
- 曹操(8080) + 夏侯惇(8081) + 夏侯渊(8082)
- 每1.5秒LLM决策，36计选计
- 战术进化，跨局继承

### 实时对抗
- Pygame 30fps渲染
- 20Hz UDP控制流
- 实时遥测数据

## 📚 文档

- [启动说明](启动说明.md) — 详细启动和配置说明
- [军师控制优化详解](docs/v39.0_军师控制优化详解.md) — v39.0优化详解
- [部署指南](docs/v39.0_部署指南.md) — 部署和配置指南
- [游戏逻辑详解](docs/v39.0_游戏逻辑详解.md) — 游戏逻辑和架构
- [更新日志](CHANGELOG.md) — 版本更新记录

## 🎯 系统要求

- OS: Linux (Ubuntu 22.04+)
- GPU: AMD GPU (ROCm/HIP)
- Python: 3.10+
- 内存: 32GB+

## 📊 项目统计

- Python源码: 23个文件
- 文档: 28个Markdown文件
- 脚本: 20个Shell脚本

## 🔗 相关项目

- 37aigame — 基础版本
- 39aigame — 军师优化版本（当前）

---

*39aigame v39.0 — 让军师真正掌控战场*
