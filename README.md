# 40aigame_bizhang — 烈璧障优化版 + 3D 渲染

> **v40.1** = 烈璧障优化 + 可选 Panda3D 3D 渲染

## 新特性：3D 渲染（v40.1）

### 启用方式
```bash
cd ~/桌面/40aigame_bizhang
source venv/bin/activate
TANK_3D=1 python src/tank_battle_deluxe.py
```

### 3D 特性
- **坦克 3D 模型**：车身、炮塔、炮管、履带
- **子弹 3D 模型**：发光球体
- **烈璧障 3D 模型**：环形墙 + 地面标记
- **3D 地形**：军绿色地面、半透明边界墙
- **灯光系统**：环境光 + 方向光
- **俯视摄像机**：带透视效果

### 技术架构
- **方案 A**：Panda3D 做 3D 渲染，保留 2D 游戏逻辑
- 游戏逻辑完全不变（AI 导演、军师系统、进化系统）
- 3D 渲染失败时自动回退到 2D

## 烈璧障特性（v40.0）

### 设计
- **完整圆形物理墙（360°无死角）**
- **放置后位置固定**
- **朝向=玩家炮塔方向（仅影响视觉，不影响物理阻挡）**

### 阻挡规则
1. ✅ **敌军子弹** - 不能穿过（触环即毁）
2. ✅ **敌军身体** - 完全不能穿过环带和内侧（360°无死角，像一堵真正的墙）
3. ✅ **敌军无法从任何角度绕过**（完整物理墙，必须破坏或等待消散）

### 使用策略
- 放置位置决定防御区域，朝向仅影响视觉呈现
- 可以放置多个烈璧障形成交叉火力
- 军师会自动触发烈璧障（当敌军接近时）
- 敌军遇墙会尝试沿墙切向滑动，无法穿透

## 快速启动

### 2D 模式（默认）
```bash
cd ~/桌面/40aigame_bizhang
bash scripts/start_all.sh
```

### 3D 模式
```bash
cd ~/桌面/40aigame_bizhang
source venv/bin/activate
TANK_3D=1 python src/tank_battle_deluxe.py
```

## 版本历史

- v40.1 - 3D 渲染支持（Panda3D）
- v40.0_bizhang - 烈璧障优化版
- v39.0 - 军师控制优化版
- v36.0 - 架构重构版

## 文件变更

### v40.1 新增
- `src/panda3d_integration.py` - Panda3D 3D 渲染集成层
- `src/panda3d_renderer.py` - 独立 3D 渲染演示
- `tests/test_3d_integration.py` - 3D 集成测试

### 修改
- `src/tank_battle_deluxe.py` - 添加 3D 同步调用
- `requirements.txt` - 添加 panda3d 依赖

### v40.0 修改
- `src/tank_battle_deluxe.py` - 烈璧障机制优化
  - Barricade.blocks_point() - 检测内侧+环带
  - Barricade.blocks_line() - 子弹路径检测
  - 敌军移动逻辑 - 完全阻挡，尝试绕路

### 新增
- 军师自动触发烈璧障（当敌军接近时）
- 调试信息输出

## 遥测数据

- `/tmp/tank_fast.json` - 快遥测（0.5秒）
- `/tmp/tank_battle_status.json` - 慢遥测（15秒）

## 相关文档

- `docs/PANDA3D_INTEGRATION.md` - 3D 渲染集成指南
- `docs/v39.0_军师控制优化详解.md`
- `docs/v39.0_部署指南.md`
- `docs/v39.0_游戏逻辑详解.md`

## 3D 截图

MEDIA:/tmp/tank3d_integration_test.png
