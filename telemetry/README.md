# 39aigame 遥测系统 (v39.0)

## 概述

39aigame遥测系统用于实时监控游戏状态，收集战场数据，验证游戏机制（如烈璧障效果）。

## 文件说明

| 文件 | 功能 |
|------|------|
| `telemetry_viewer.py` | 实时查看游戏状态 |
| `telemetry_monitor.py` | 监控异常并报警 |
| `telemetry_collector.py` | 收集数据到SQLite数据库 |
| `telemetry_analyzer.py` | 分析遥测数据 |
| `verify_barricade.py` | 验证烈璧障效果 |

## 用法

### 实时查看游戏状态
```bash
cd ~/桌面/39aigame/telemetry
python3 telemetry_viewer.py
```

### 监控异常
```bash
python3 telemetry_monitor.py --alert --log
```

### 收集数据
```bash
python3 telemetry_collector.py --interval 5
```

### 验证烈璧障
```bash
python3 verify_barricade.py
```

## 遥测数据来源

游戏自动输出以下遥测文件：

| 文件 | 更新频率 | 内容 |
|------|---------|------|
| `/tmp/tank_fast.json` | 0.5秒 | 快遥测：玩家坐标、敌军坐标、烈璧障位置 |
| `/tmp/tank_battle_status.json` | 15秒 | 慢遥测：完整游戏状态、AI状态、统计信息 |

## 烈璧障验证

### 验证原理
1. 从遥测数据获取烈璧障位置（中心、朝向、半径）
2. 获取敌军位置
3. 检查敌军是否在烈璧障环带内
4. 检查敌军是否穿过了烈璧障

### 验证结果
- ✅ 敌军被阻挡：敌军在烈璧障环带内
- 🚨 敌军穿过：敌军绕过烈璧障到达主公附近

## 数据收集

收集的数据存储在：
- SQLite数据库：`telemetry/data/telemetry_history.db`
- CSV导出：`/tmp/telemetry_YYYYMMDD_HHMMSS.csv`
- 验证报告：`/tmp/barricade_verify_YYYYMMDD_HHMMSS.txt`

## v39.0 改进

1. **添加烈璧障位置到遥测**：快遥测和慢遥测都包含烈璧障详细信息
2. **新增验证工具**：`verify_barricade.py` 验证烈璧障效果
3. **数据库收集**：`telemetry_collector.py` 收集历史数据

## 相关文档

- [游戏逻辑详解](../docs/v39.0_游戏逻辑详解.md)
- [部署指南](../docs/v39.0_部署指南.md)
