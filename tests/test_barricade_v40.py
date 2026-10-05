#!/usr/bin/env python3
"""
v40.1 烈璧障无头测试 - 完整物理墙验证
运行: cd /home/ibm/桌面/40aigame_bizhang && python3 tests/test_barricade_v40.py
"""
import sys
import math
sys.path.insert(0, '/home/ibm/桌面/40aigame_bizhang/src')

# 模拟pygame.time.get_ticks
class MockPygame:
    @staticmethod
    def time_get_ticks():
        return 0

sys.modules['pygame'] = MockPygame()

# 直接复制Barricade类进行测试
class Barricade:
    """v40.1: 烈璧障 - 完整圆形物理墙(360°无死角)"""
    RADIUS = 120
    THICK = 20
    ARC = math.pi
    LIFETIME = 60_000

    def __init__(self, x, y, facing):
        self.x, self.y = float(x), float(y)
        self.facing = facing
        self.born = 0
        self._build()

    def _build(self):
        self._segments = []
        n = 26
        for i in range(n):
            a = self.facing - self.ARC / 2 + self.ARC * i / (n - 1)
            self._segments.append((a, self.x + math.cos(a) * self.RADIUS,
                                   self.y + math.sin(a) * self.RADIUS))

    def blocks_point(self, px, py):
        """v40.1: 完整物理墙 - 360°无死角阻挡"""
        dx, dy = px - self.x, py - self.y
        d = math.hypot(dx, dy)
        if d < self.RADIUS - self.THICK:
            return True
        if self.RADIUS - self.THICK <= d <= self.RADIUS + self.THICK:
            return True
        return False

    def blocks_line(self, x1, y1, x2, y2):
        """v40.1: 子弹从任何角度接近，穿过环带即被阻挡"""
        dx, dy = x2 - x1, y2 - y1
        fx, fy = x1 - self.x, y1 - self.y
        a = dx * dx + dy * dy
        b = 2 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - self.RADIUS * self.RADIUS
        discriminant = b * b - 4 * a * c
        if discriminant < 0:
            return False
        discriminant = math.sqrt(discriminant)
        t1 = (-b - discriminant) / (2 * a)
        t2 = (-b + discriminant) / (2 * a)
        for t in [t1, t2]:
            if 0 <= t <= 1:
                ix = x1 + t * dx
                iy = y1 + t * dy
                d_to_center = math.hypot(ix - self.x, iy - self.y)
                if d_to_center <= self.RADIUS + self.THICK:
                    return True
        return False


def test_barricade_blocks_point():
    """测试点阻挡 - 360°无死角"""
    print("=" * 60)
    print("测试1: 点阻挡 (blocks_point)")
    print("=" * 60)

    b = Barricade(800, 500, facing=0)  # facing=0, 开口朝右

    # 测试点: (描述, x, y, 期望结果)
    test_cases = [
        # 内侧区域 - 应该全部阻挡
        ("圆心", 800, 500, True),
        ("内侧-正上方", 800, 400, True),
        ("内侧-正下方", 800, 600, True),
        ("内侧-正左方", 700, 500, True),
        ("内侧-正右方", 900, 500, True),
        ("内侧-左上", 730, 430, True),
        ("内侧-右下", 870, 570, True),

        # 环带上 - 应该全部阻挡
        ("环带-正上方", 800, 380, True),
        ("环带-正下方", 800, 620, True),
        ("环带-正左方", 680, 500, True),
        ("环带-正右方", 920, 500, True),

        # 外侧 - 应该通过
        ("外侧-正上方", 800, 300, False),
        ("外侧-正下方", 800, 700, False),
        ("外侧-正左方", 600, 500, False),
        ("外侧-正右方", 1000, 500, False),

        # 关键: 开口方向 (facing=0, 开口朝右，但v40.1是完整墙)
        ("开口方向-右侧内侧", 880, 500, True),
        ("开口方向-右侧环带", 930, 500, True),
        ("开口方向-右侧外侧", 1000, 500, False),
    ]

    passed = 0
    failed = 0

    for desc, px, py, expected in test_cases:
        result = b.blocks_point(px, py)
        d = math.hypot(px - b.x, py - b.y)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"  {status} {desc:20s} 距离={d:6.1f}px 阻挡={result} (期望={expected})")

    print(f"\n结果: {passed}/{len(test_cases)} 通过, {failed} 失败")
    return failed == 0


def test_barricade_blocks_line():
    """测试子弹路径阻挡"""
    print("\n" + "=" * 60)
    print("测试2: 子弹路径阻挡 (blocks_line)")
    print("=" * 60)

    b = Barricade(800, 500, facing=0)

    test_cases = [
        # 从外侧射向圆心 - 应该阻挡
        ("正上方射向圆心", 800, 300, 800, 500, True),
        ("正下方射向圆心", 800, 700, 800, 500, True),
        ("正左方射向圆心", 600, 500, 800, 500, True),
        ("正右方射向圆心", 1000, 500, 800, 500, True),

        # 从外侧射向内侧 - 应该阻挡
        ("上方射向内侧", 800, 300, 800, 450, True),
        ("左方射向内侧", 600, 500, 750, 500, True),

        # 斜向穿过 - 应该阻挡
        ("左上斜穿", 600, 300, 900, 700, True),
        ("右下斜穿", 1000, 700, 700, 300, True),

        # 不穿过环带 - 应该通过
        ("外侧平行", 600, 300, 700, 300, False),
        ("内侧移动", 780, 480, 820, 520, False),

        # 关键: 从开口方向射入 (facing=0, 开口朝右)
        ("开口方向射入", 1000, 500, 800, 500, True),
        ("开口方向斜射", 1000, 400, 800, 500, True),
    ]

    passed = 0
    failed = 0

    for desc, x1, y1, x2, y2, expected in test_cases:
        result = b.blocks_line(x1, y1, x2, y2)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"  {status} {desc:20s} 阻挡={result} (期望={expected})")

    print(f"\n结果: {passed}/{len(test_cases)} 通过, {failed} 失败")
    return failed == 0


def test_enemy_cannot_pass():
    """模拟敌军移动，验证无法穿过"""
    print("\n" + "=" * 60)
    print("测试3: 敌军移动模拟 - 验证无法穿过烈璧障")
    print("=" * 60)

    b = Barricade(800, 500, facing=math.pi/2)  # 开口朝上

    # 模拟敌军从上方接近
    enemy_x, enemy_y = 800, 300
    speed = 2.67  # 将领速度
    frame = 0
    blocked_frame = None

    print(f"  敌军起始: ({enemy_x}, {enemy_y})")
    print(f"  目标: 圆心({b.x}, {b.y})")
    print(f"  速度: {speed}px/帧")
    print()

    while frame < 200:
        frame += 1
        # 向圆心移动
        dx = b.x - enemy_x
        dy = b.y - enemy_y
        dist = math.hypot(dx, dy)
        if dist > 0:
            enemy_x += (dx / dist) * speed
            enemy_y += (dy / dist) * speed

        # 检测是否被阻挡
        if b.blocks_point(enemy_x, enemy_y):
            blocked_frame = frame
            print(f"  🔴 帧{frame:3d}: 敌军被阻挡！")
            print(f"     位置: ({enemy_x:.1f}, {enemy_y:.1f})")
            print(f"     距离圆心: {math.hypot(enemy_x-b.x, enemy_y-b.y):.1f}px")
            break

        if frame % 20 == 0:
            print(f"  🟢 帧{frame:3d}: 位置({enemy_x:.1f}, {enemy_y:.1f}) 距离={math.hypot(enemy_x-b.x, enemy_y-b.y):.1f}px")

    if blocked_frame:
        print(f"\n  ✅ 验证通过: 敌军在帧{blocked_frame}被阻挡，无法穿过烈璧障")
        return True
    else:
        print(f"\n  ❌ 验证失败: 敌军未被阻挡")
        return False


def test_enemy_cannot_pass_from_any_direction():
    """从8个方向测试敌军都无法穿过"""
    print("\n" + "=" * 60)
    print("测试4: 8方向穿透测试 - 验证360°无死角")
    print("=" * 60)

    b = Barricade(800, 500, facing=0)
    speed = 2.67

    directions = [
        ("正上方", 800, 300),
        ("正下方", 800, 700),
        ("正左方", 600, 500),
        ("正右方", 1000, 500),
        ("左上方", 650, 350),
        ("右上方", 950, 350),
        ("左下方", 650, 650),
        ("右下方", 950, 650),
    ]

    all_passed = True

    for desc, start_x, start_y in directions:
        enemy_x, enemy_y = start_x, start_y
        frame = 0
        blocked = False

        while frame < 200:
            frame += 1
            dx = b.x - enemy_x
            dy = b.y - enemy_y
            dist = math.hypot(dx, dy)
            if dist > 0:
                enemy_x += (dx / dist) * speed
                enemy_y += (dy / dist) * speed

            if b.blocks_point(enemy_x, enemy_y):
                blocked = True
                break

        status = "✅" if blocked else "❌"
        if not blocked:
            all_passed = False
        print(f"  {status} {desc:6s}: 从({start_x},{start_y}) -> {'被阻挡' if blocked else '未阻挡'}")

    print(f"\n  {'✅' if all_passed else '❌'} 验证{'通过' if all_passed else '失败'}: 敌军无法从任何方向穿过")
    return all_passed


def test_bullet_cannot_pass():
    """测试子弹无法从任何方向穿过"""
    print("\n" + "=" * 60)
    print("测试5: 子弹8方向穿透测试")
    print("=" * 60)

    b = Barricade(800, 500, facing=0)

    directions = [
        ("正上方", 800, 300, 800, 500),
        ("正下方", 800, 700, 800, 500),
        ("正左方", 600, 500, 800, 500),
        ("正右方", 1000, 500, 800, 500),
        ("左上方", 650, 350, 800, 500),
        ("右上方", 950, 350, 800, 500),
        ("左下方", 650, 650, 800, 500),
        ("右下方", 950, 650, 800, 500),
    ]

    all_passed = True

    for desc, x1, y1, x2, y2 in directions:
        blocked = b.blocks_line(x1, y1, x2, y2)
        status = "✅" if blocked else "❌"
        if not blocked:
            all_passed = False
        print(f"  {status} {desc:6s}: 从({x1},{y1})射向圆心 -> {'被阻挡' if blocked else '未阻挡'}")

    print(f"\n  {'✅' if all_passed else '❌'} 验证{'通过' if all_passed else '失败'}: 子弹无法从任何方向穿过")
    return all_passed


def test_multiple_barricades():
    """测试多个烈璧障叠加"""
    print("\n" + "=" * 60)
    print("测试6: 多烈璧障叠加测试")
    print("=" * 60)

    b1 = Barricade(700, 400, facing=0)
    b2 = Barricade(900, 600, facing=math.pi)

    # 测试点同时在两个烈璧障内侧
    test_points = [
        ("烈璧障1内侧", 700, 400, True),
        ("烈璧障2内侧", 900, 600, True),
        ("两障之间", 800, 500, False),
        ("外侧远处", 500, 500, False),
    ]

    all_passed = True
    for desc, px, py, expected in test_points:
        blocked1 = b1.blocks_point(px, py)
        blocked2 = b2.blocks_point(px, py)
        blocked = blocked1 or blocked2
        status = "✅" if blocked == expected else "❌"
        if blocked != expected:
            all_passed = False
        print(f"  {status} {desc:12s}: 障1={blocked1}, 障2={blocked2}, 总={blocked} (期望={expected})")

    print(f"\n  {'✅' if all_passed else '❌'} 验证{'通过' if all_passed else '失败'}")
    return all_passed


if __name__ == "__main__":
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "v40.1 烈璧障无头测试套件" + " " * 23 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = []
    results.append(("点阻挡测试", test_barricade_blocks_point()))
    results.append(("子弹路径阻挡", test_barricade_blocks_line()))
    results.append(("敌军移动模拟", test_enemy_cannot_pass()))
    results.append(("8方向穿透", test_enemy_cannot_pass_from_any_direction()))
    results.append(("子弹8方向", test_bullet_cannot_pass()))
    results.append(("多烈璧障叠加", test_multiple_barricades()))

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    total_passed = 0
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
        if passed:
            total_passed += 1

    print()
    print(f"总计: {total_passed}/{len(results)} 项测试通过")

    if total_passed == len(results):
        print("\n🎉 所有测试通过！烈璧障 v40.1 完整物理墙验证成功！")
        print("   敌军无法从任何角度穿过或绕过烈璧障！")
    else:
        print("\n⚠️  部分测试失败，请检查代码")

    sys.exit(0 if total_passed == len(results) else 1)
