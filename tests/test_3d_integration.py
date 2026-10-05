# -*- coding: utf-8 -*-
"""
3D 集成测试
"""

import sys
import os
import time

# 添加 src 目录
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# 设置 3D 模式
os.environ['TANK_3D'] = '1'

from panda3d_integration import init_3d, sync_frame, cleanup_3d, is_3d_enabled


def test_3d_basic():
    """测试基本 3D 功能"""
    print("[TEST] 测试 3D 初始化...")

    # 初始化
    result = init_3d()
    print(f"[TEST] 初始化结果: {result}")

    if not result:
        print("[TEST] 3D 不可用，跳过测试")
        return

    # 创建模拟游戏对象
    class MockRect:
        def __init__(self, x, y):
            self.centerx = x
            self.centery = y

    class MockPlayer:
        def __init__(self):
            self.rect = MockRect(800, 500)
            self.angle = 0
            self.turret_angle = 45
            self.hp = 80
            self.max_hp = 100

    class MockEnemy:
        def __init__(self, num, x, y):
            self.num = num
            self.rect = MockRect(x, y)
            self.angle = num * 30
            self.hp = 100
            self.max_hp = 100

    class MockBullet:
        def __init__(self, x, y, angle):
            self.rect = MockRect(x, y)
            self.angle = angle

    player = MockPlayer()
    enemies = [MockEnemy(i, 200 + i*200, 200 + (i%2)*400) for i in range(5)]
    bullets = [MockBullet(600 + i*100, 400, i*20) for i in range(3)]

    # 同步多帧
    print("[TEST] 同步 30 帧...")
    for i in range(30):
        # 更新位置模拟运动
        player.rect.centerx = 800 + int(50 * (i / 30))
        for e in enemies:
            e.rect.centerx += 1

        sync_frame(
            player=player,
            enemies=enemies,
            bullets=bullets,
            barricades=[],
            generals=[]
        )
        time.sleep(0.05)

    # 截图
    from panda3d_integration import _3d_app
    if _3d_app:
        screenshot_path = '/tmp/tank3d_integration_test.png'
        _3d_app.win.saveScreenshot(screenshot_path)
        print(f"[TEST] 截图已保存: {screenshot_path}")

    # 清理
    cleanup_3d()
    print("[TEST] 测试完成")


if __name__ == "__main__":
    test_3d_basic()
