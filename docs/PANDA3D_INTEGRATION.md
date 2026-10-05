# Panda3D 3D 渲染集成指南

## 方案 A：3D 视觉 + 2D 逻辑

### 已完成的内容

1. **Panda3D 渲染层** (`src/panda3d_renderer.py`)
   - 坦克 3D 模型（车身、炮塔、炮管、履带）
   - 子弹 3D 模型
   - 烈璧障 3D 模型（环形墙+地面标记）
   - 3D 地形（地面+网格+半透明边界墙）
   - 灯光系统（环境光+方向光）
   - 摄像机系统（俯视带透视）

2. **游戏适配器** (`GameAdapter` 类)
   - 同步坦克状态（位置、朝向、炮塔角度、HP）
   - 同步子弹状态
   - 同步烈璧障状态
   - 自动清理已消失对象

3. **坐标转换**
   - 2D 逻辑坐标 (0,0)~(1600,1000) ↔ 3D 场景坐标
   - 缩放比例：20 像素 = 1 米

### 文件结构

```
src/
├── panda3d_renderer.py    # 3D 渲染层（独立运行）
├── tank_battle_3d.py      # 集成入口（桥接 2D 游戏和 3D 渲染）
└── tank_battle_deluxe.py  # 原游戏（逻辑不变）
```

### 运行方式

#### 1. 独立 3D 演示
```bash
cd ~/桌面/40aigame_bizhang
source venv/bin/activate
python src/panda3d_renderer.py
```

#### 2. 集成到现有游戏（需要修改游戏主循环）

在 `tank_battle_deluxe.py` 的主循环中，每帧添加：

```python
# 在文件顶部导入
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from panda3d_renderer import TankBattle3D, GameAdapter
    HAS_3D = True
except ImportError:
    HAS_3D = False

# 在游戏初始化时
if HAS_3D:
    panda_app = TankBattle3D()
    adapter = panda_app.adapter

# 在游戏主循环每帧末尾
if HAS_3D:
    # 同步所有游戏对象到 3D 场景
    adapter.sync_tank("player", player.rect.centerx, player.rect.centery,
                      angle=player.angle, color=(0.2, 0.6, 0.2, 1), is_player=True)

    for i, enemy in enumerate(enemies):
        adapter.sync_tank(f"enemy_{i}", enemy.rect.centerx, enemy.rect.centery,
                          angle=enemy.angle, color=(0.7, 0.2, 0.2, 1))

    for i, bullet in enumerate(bullets):
        adapter.sync_bullet(f"bullet_{i}", bullet.rect.centerx, bullet.rect.centery,
                           angle=bullet.angle)

    # 推进 Panda3D 一帧
    panda_app.taskMgr.step()
```

### 下一步集成工作

#### 优先级 1：最小可运行集成
- [ ] 修改 `tank_battle_deluxe.py` 主循环，添加 3D 同步调用
- [ ] 处理 Pygame 和 Panda3D 窗口共存问题
- [ ] 测试基本游戏流程

#### 优先级 2：视觉优化
- [ ] 添加坦克贴图（迷彩、金属质感）
- [ ] 添加爆炸特效
- [ ] 添加阴影
- [ ] 添加天空盒

#### 优先级 3：交互优化
- [ ] 摄像机跟随玩家
- [ ] 鼠标控制摄像机旋转/缩放
- [ ] 3D 音效定位

#### 优先级 4：高级功能
- [ ] 地形高度图
- [ ] 粒子系统（烟雾、火焰）
- [ ] 后处理效果（ bloom、景深）

### 技术细节

#### 坐标系映射
```
2D 游戏坐标          3D 场景坐标
(0, 0)      →      (-40, 0, 25)     左上
(1600, 1000) →      (40, 0, -25)    右下
(800, 500)   →      (0, 0, 0)       中心
```

#### 性能考虑
- Panda3D 和 Pygame 各自有主循环，需要协调
- 建议用 `taskMgr.step()` 手动推进 Panda3D，而不是 `app.run()`
- 对象同步频率可以与渲染帧率不同（例如游戏逻辑 30fps，渲染 60fps）

#### 已知问题
1. XFree86-DGA 警告（不影响运行）
2. 坦克模型较简单（可用 Blender 制作精细模型）
3. 没有阴影（可开启 Panda3D 阴影映射）

### 模型替换

当前使用程序生成的简单几何体。要替换为精细模型：

```python
# 加载 .egg 或 .bam 模型文件
tank_model = loader.loadModel("models/tank.bam")
tank_model.reparentTo(render)
```

模型制作工具：
- Blender（免费）+ YABEE 导出插件
- 在线模型库：Sketchfab、TurboSquid

### 参考资源

- [Panda3D 官方文档](https://docs.panda3d.org/)
- [Panda3D 论坛](https://discourse.panda3d.org/)
- [Blender](https://www.blender.org/)
