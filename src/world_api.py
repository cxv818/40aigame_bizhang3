# v36.0 (2026-10-05) — 36aigame
# 职责: 烈璧障阻挡/滑动、Boss墙阻挡、敌军互斥——只做几何计算,不做决策。
# 依赖注入: main(游戏模块对象, 提供 _barricades/_boss_walls) 与 WIDTH/HEIGHT
# 由游戏启动时 set_context() 注入, 避免循环导入。
import math

_main = None
_WIDTH, _HEIGHT = 1600, 1000


def set_context(main_module, width=1600, height=1000):
    """游戏main()启动时调用一次, 注入运行时上下文"""
    global _main, _WIDTH, _HEIGHT
    _main = main_module
    _WIDTH, _HEIGHT = width, height


# ---------- 吕布·烈璧障(完整圆形物理墙): 每30s可放,挡敌军+敌弹,玩家/玩家弹不受影响 ----------
def barricade_blocks(px, py):
    """模块级查询: 点(px,py)是否被任一烈璧障挡住(吕布的,挡敌军)。挂 main._barricades。
    v40.1: 烈璧障现在是完整圆形墙(360°无死角)，内侧区域和环带本体都完全阻挡。"""
    bl = getattr(_main, "_barricades", None)
    if not bl:
        return False
    return any(b.blocks_point(px, py) for b in bl)


def boss_wall_blocks(px, py):
    """模块级查询: 点(px,py)是否被曹操的赤壁屏障挡住(挡玩家+玩家弹)。挂 Boss 实例列表。"""
    wl = getattr(_main, "_boss_walls", None)
    if not wl:
        return False
    return any(w.blocks_point(px, py) for w in wl)


def barricade_slide(px, py, move, speed, steps=6):
    """v40.1: 敌军撞烈璧障(完整圆形墙)时的切向滑动。
    以圆心方向为准,改走沿墙切向(保留少量原方向分量)。
    烈璧障现在是360°完整物理墙，内侧区域也阻挡，所以切向滑动沿外环进行。
    返回可行方向弧度;不在任何环带作用域时原样返回 move。"""
    bl = getattr(_main, "_barricades", None)
    if not bl:
        return move
    for b in bl:
        dx, dy = px - b.x, py - b.y
        d = math.hypot(dx, dy)
        # v40.1: 检测范围扩大到内侧区域(完整物理墙)
        if d > b.RADIUS + b.THICK + speed * 2:
            continue                       # 不在这堵墙附近
        # 切向 = 连线方向 ±90°,选与原方向夹角小的那支(沿墙滑,不折返)
        to_c = math.atan2(dy, dx)          # 指向圆心
        t1, t2 = to_c + math.pi / 2, to_c - math.pi / 2
        def _angdiff(a, m):
            return abs(math.atan2(math.sin(a - m), math.cos(a - m)))
        tang = t1 if _angdiff(t1, move) <= _angdiff(t2, move) else t2
        # 保留 25% 原方向分量,形成"贴弧滑行"轨迹;混成后若仍被挡则纯切向
        cand = tang * 0.75 + move * 0.25
        nx, ny = px + math.cos(cand) * speed, py + math.sin(cand) * speed
        if not any(w.blocks_point(nx, ny) for w in bl):
            return cand
        nx, ny = px + math.cos(tang) * speed, py + math.sin(tang) * speed
        if not any(w.blocks_point(nx, ny) for w in bl):
            return tang
        return tang                        # 混合被挡也强推纯切向(下一帧自然滑出)
    return move


def separate_enemies(enemies, radius_pad=2.0, strength=0.35):
    """敌军间轻量互斥(防叠罗汉): 两两重叠时沿连线推开。
    enemies 是 pygame.sprite.Group,用 list(...) 快照遍历;推力限幅防抖;只推位置不改订单。"""
    els = list(enemies)
    n = len(els)
    if n < 2:
        return
    size = els[0].rect.width if els else 40
    min_d = size + radius_pad
    for i in range(n):
        a = els[i]
        for j in range(i + 1, n):
            b = els[j]
            dx = b.rect.centerx - a.rect.centerx
            dy = b.rect.centery - a.rect.centery
            d = math.hypot(dx, dy)
            if d < 1e-4:      # 完全重叠: 固定方向弹开
                dx, dy, d = 1.0, 0.0, 1.0
            elif d >= min_d:
                continue
            push = (min_d - d) * strength
            ux, uy = dx / d, dy / d
            a.rect.x -= ux * push; a.rect.y -= uy * push
            b.rect.x += ux * push; b.rect.y += uy * push
            a.rect.clamp_ip((0, 0, _WIDTH, _HEIGHT))
            b.rect.clamp_ip((0, 0, _WIDTH, _HEIGHT))
