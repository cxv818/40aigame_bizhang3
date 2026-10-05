# -*- coding: utf-8 -*-
"""
坦克大战 3D 版 — 方案 A 集成入口

运行方式：
    cd ~/桌面/40aigame_bizhang
    source venv/bin/activate
    python src/tank_battle_3d.py

说明：
- 本文件是原 tank_battle_deluxe.py 的 3D 包装器
- 游戏逻辑完全复用原文件（2D 坐标、碰撞、AI 等）
- 只添加 3D 渲染同步层
- 如果 Panda3D 不可用，自动回退到 2D Pygame
"""

import os
import sys
import threading
import time

# 添加 src 目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 尝试导入 Panda3D
try:
    from panda3d_renderer import TankBattle3D, GameAdapter, to_3d
    HAS_PANDA3D = True
    print("[3D] Panda3D 渲染层已加载")
except ImportError as e:
    HAS_PANDA3D = False
    print(f"[3D] Panda3D 不可用 ({e})，将回退到 2D Pygame")

# 导入原始游戏（复用所有逻辑）
# 注意：我们需要一种方式让原游戏在 3D 模式下不自己创建 Pygame 窗口
# 这里采用 monkey-patch 方式

import tank_battle_deluxe as game


class Game3DBridge:
    """
    3D 桥接器：在原游戏和 Panda3D 之间同步状态
    """

    def __init__(self):
        self.app = None
        self.adapter = None
        self.running = False
        self.sync_thread = None

        # ID 映射表
        self.tank_ids = {}      # game_tank -> 3d_id
        self.bullet_ids = {}    # game_bullet -> 3d_id
        self.barricade_ids = {} # game_barricade -> 3d_id

        # 计数器用于生成唯一 ID
        self._id_counter = 0

    def _next_id(self, prefix):
        self._id_counter += 1
        return f"{prefix}_{self._id_counter}"

    def start(self):
        """启动 3D 渲染"""
        if not HAS_PANDA3D:
            print("[3D] Panda3D 不可用，跳过 3D 启动")
            return False

        self.app = TankBattle3D()
        self.adapter = self.app.adapter
        self.running = True

        # 在后台线程运行 Panda3D（非阻塞）
        self.sync_thread = threading.Thread(target=self._panda_loop, daemon=True)
        self.sync_thread.start()

        print("[3D] 3D 渲染已启动")
        return True

    def _panda_loop(self):
        """Panda3D 主循环（在独立线程运行）"""
        # Panda3D 需要在主线程运行，这里用 taskMgr 方式
        # 实际游戏中，我们在游戏循环中手动调用 step()
        pass

    def step(self):
        """手动推进一帧（在游戏主循环中调用）"""
        if self.app and self.running:
            self.app.taskMgr.step()

    def sync_from_game(self, game_state):
        """
        从游戏状态同步到 3D 场景

        game_state 格式：
        {
            'tanks': [
                {'id': ..., 'x': ..., 'y': ..., 'angle': ..., 'turret_angle': ...,
                 'color': (r,g,b,a), 'is_player': bool, 'hp': ..., 'max_hp': ...},
                ...
            ],
            'bullets': [
                {'id': ..., 'x': ..., 'y': ..., 'angle': ..., 'color': (r,g,b,a)},
                ...
            ],
            'barricades': [
                {'id': ..., 'x': ..., 'y': ..., 'radius': ...},
                ...
            ]
        }
        """
        if not self.adapter:
            return

        # 同步坦克
        current_tank_ids = set()
        for tank in game_state.get('tanks', []):
            tid = tank['id']
            current_tank_ids.add(tid)

            self.adapter.sync_tank(
                tank_id=tid,
                x=tank['x'],
                y=tank['y'],
                angle=tank.get('angle', 0),
                turret_angle=tank.get('turret_angle', 0),
                color=tank.get('color', (0.5, 0.5, 0.5, 1)),
                is_player=tank.get('is_player', False),
                hp=tank.get('hp', 100),
                max_hp=tank.get('max_hp', 100)
            )

        # 清理已消失的坦克
        for tid in list(self.adapter.tanks.keys()):
            if tid not in current_tank_ids:
                self.adapter.remove_tank(tid)

        # 同步子弹
        current_bullet_ids = set()
        for bullet in game_state.get('bullets', []):
            bid = bullet['id']
            current_bullet_ids.add(bid)

            self.adapter.sync_bullet(
                bullet_id=bid,
                x=bullet['x'],
                y=bullet['y'],
                angle=bullet.get('angle', 0),
                color=bullet.get('color', (1, 0.5, 0, 1))
            )

        # 清理已消失的子弹
        for bid in list(self.adapter.bullets.keys()):
            if bid not in current_bullet_ids:
                self.adapter.remove_bullet(bid)

        # 同步烈璧障
        current_barricade_ids = set()
        for bar in game_state.get('barricades', []):
            bid = bar['id']
            current_barricade_ids.add(bid)

            self.adapter.add_barricade(
                barricade_id=bid,
                x=bar['x'],
                y=bar['y'],
                radius=bar.get('radius', 50)
            )

        # 清理已消失的烈璧障
        for bid in list(self.adapter.barricades.keys()):
            if bid not in current_barricade_ids:
                self.adapter.remove_barricade(bid)

    def stop(self):
        """停止 3D 渲染"""
        self.running = False
        if self.app:
            self.app.userExit()
        print("[3D] 3D 渲染已停止")


def monkey_patch_game_for_3d():
    """
    Monkey-patch 原游戏，使其支持 3D 模式

    主要修改：
    1. 禁用 Pygame 显示初始化（保留事件和声音）
    2. 在游戏主循环中插入 3D 同步调用
    3. 捕获游戏状态并转发到 3D 场景
    """

    # 保存原始函数
    original_init = game.pygame.init
    original_display_set_mode = game.pygame.display.set_mode
    original_display_flip = game.pygame.display.flip
    original_display_update = game.pygame.display.update

    # 标记是否处于 3D 模式
    game._3d_mode = True
    game._3d_bridge = Game3DBridge()

    # 重写 pygame.display.set_mode - 3D 模式下创建小窗口或隐藏窗口
    def patched_set_mode(size, flags=0, depth=0):
        if game._3d_mode:
            # 3D 模式下创建一个小的控制窗口，或者隐藏窗口
            # 保留 pygame 事件循环
            print("[3D] Pygame 显示已重定向到 Panda3D")
            # 返回一个虚拟的 Surface
            return game.pygame.Surface((1, 1))
        return original_display_set_mode(size, flags, depth)

    # 重写 display.flip/update - 3D 模式下不做任何事
    def patched_flip():
        if not game._3d_mode:
            original_display_flip()

    def patched_update(*args, **kwargs):
        if not game._3d_mode:
            original_display_update(*args, **kwargs)

    game.pygame.display.set_mode = patched_set_mode
    game.pygame.display.flip = patched_flip
    game.pygame.display.update = patched_update

    print("[3D] 游戏已 monkey-patch 为 3D 模式")


def run_3d_game():
    """
    运行 3D 版游戏

    这是主入口函数
    """
    if not HAS_PANDA3D:
        print("[3D] Panda3D 未安装，运行 2D 版本")
        print("安装命令: pip install panda3d")
        # 直接运行原游戏
        import tank_battle_deluxe
        return

    # Monkey-patch 游戏
    monkey_patch_game_for_3d()

    # 启动 3D 桥接器
    bridge = game._3d_bridge
    bridge.start()

    # 启动游戏（在后台线程）
    game_thread = threading.Thread(target=game.main, daemon=True)
    game_thread.start()

    # 主线程运行 Panda3D
    print("[3D] 游戏已启动，3D 渲染运行中...")
    print("[3D] 按 ESC 退出")

    try:
        while bridge.running and game_thread.is_alive():
            # 从游戏中提取状态并同步到 3D
            # 这里需要一个钩子来获取游戏状态
            # 暂时用简单方式：定期同步

            # 实际实现需要在游戏主循环中插入 sync 调用
            # 见下面的 integrate_into_main_loop 函数

            time.sleep(0.016)  # ~60fps
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()


def integrate_into_main_loop(game_module):
    """
    将 3D 同步集成到游戏主循环中

    在游戏主循环的每帧末尾调用：

        if hasattr(game, '_3d_bridge') and game._3d_bridge:
            game_state = extract_game_state()
            game._3d_bridge.sync_from_game(game_state)
            game._3d_bridge.step()

    这个函数提供 extract_game_state 的参考实现
    """

    def extract_game_state():
        """从游戏状态提取 3D 同步数据"""
        state = {
            'tanks': [],
            'bullets': [],
            'barricades': []
        }

        # 提取玩家坦克
        if hasattr(game_module, 'player'):
            p = game_module.player
            state['tanks'].append({
                'id': 'player',
                'x': p.rect.centerx,
                'y': p.rect.centery,
                'angle': getattr(p, 'angle', 0),
                'turret_angle': getattr(p, 'turret_angle', 0),
                'color': (0.2, 0.6, 0.2, 1),
                'is_player': True,
                'hp': getattr(p, 'hp', 100),
                'max_hp': getattr(p, 'max_hp', 100)
            })

        # 提取敌人坦克
        if hasattr(game_module, 'enemies'):
            for i, e in enumerate(game_module.enemies):
                state['tanks'].append({
                    'id': f'enemy_{i}',
                    'x': e.rect.centerx,
                    'y': e.rect.centery,
                    'angle': getattr(e, 'angle', 0),
                    'color': (0.7, 0.2, 0.2, 1),
                    'is_player': False,
                    'hp': getattr(e, 'hp', 100),
                    'max_hp': getattr(e, 'max_hp', 100)
                })

        # 提取子弹
        if hasattr(game_module, 'bullets'):
            for i, b in enumerate(game_module.bullets):
                state['bullets'].append({
                    'id': f'bullet_{i}',
                    'x': b.rect.centerx,
                    'y': b.rect.centery,
                    'angle': getattr(b, 'angle', 0),
                    'color': (1, 0.8, 0, 1)
                })

        # 提取烈璧障
        if hasattr(game_module, 'barricades'):
            for i, bar in enumerate(game_module.barricades):
                state['barricades'].append({
                    'id': f'barricade_{i}',
                    'x': bar.x,
                    'y': bar.y,
                    'radius': getattr(bar, 'radius', 50)
                })

        return state

    return extract_game_state


if __name__ == "__main__":
    # 先运行独立演示
    if HAS_PANDA3D and len(sys.argv) > 1 and sys.argv[1] == "--demo":
        from panda3d_renderer import demo
        demo()
    else:
        run_3d_game()
