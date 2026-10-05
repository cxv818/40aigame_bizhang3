# -*- coding: utf-8 -*-
"""
Panda3D 集成模块 - 最小侵入式

使用方式：
    在 tank_battle_deluxe.py 顶部导入：
        from panda3d_integration import init_3d, sync_frame, cleanup_3d

    在 main() 函数开始处初始化：
        init_3d()

    在游戏主循环每帧调用：
        sync_frame(player, enemies, bullets, barricades, generals, camps)

    在退出时清理：
        cleanup_3d()

设计原则：
- 不修改原游戏逻辑
- 3D 渲染失败时静默回退到 2D
- 性能开销最小化
"""

import os
import sys
import math

# 尝试导入 Panda3D
try:
    from direct.showbase.ShowBase import ShowBase
    from panda3d.core import (
        Point3, Vec3, Vec4, PointLight, AmbientLight,
        Geom, GeomNode, GeomVertexFormat, GeomVertexData,
        GeomVertexWriter, GeomTriangles, GeomTristrips,
        CardMaker, TransparencyAttrib,
        loadPrcFileData, ClockObject
    )
    from direct.task import Task
    HAS_PANDA3D = True
except ImportError:
    HAS_PANDA3D = False
    print("[3D] Panda3D 未安装，3D 渲染已禁用")
    print("[3D] 安装: pip install panda3d")

# 游戏常量
WIDTH, HEIGHT = 1600, 1000
SCALE_2D_TO_3D = 0.05


def to_3d(x, y, z=0):
    """2D 逻辑坐标 → 3D 场景坐标"""
    return Point3(
        (x - WIDTH / 2) * SCALE_2D_TO_3D,
        z,
        -(y - HEIGHT / 2) * SCALE_2D_TO_3D
    )


class SimpleModel:
    """简单 3D 模型基类"""

    def __init__(self, render_np):
        self.root = render_np.attachNewNode("model")

    def set_pos(self, x, y, z=0):
        self.root.setPos(to_3d(x, y, z))

    def set_h(self, angle_deg):
        """设置水平旋转"""
        self.root.setH(-angle_deg + 90)

    def set_color(self, r, g, b, a=1):
        self.root.setColor(r, g, b, a)

    def remove(self):
        self.root.removeNode()


class TankModel3D(SimpleModel):
    """坦克 3D 模型"""

    def __init__(self, render_np, color, is_player=False):
        super().__init__(render_np)
        self.is_player = is_player

        # 车身
        body = self._create_box(2.0, 0.8, 1.4)
        body.reparentTo(self.root)
        body.setPos(0, 0.4, 0)
        body.setColor(0.3, 0.3, 0.3, 1)

        # 炮塔
        turret = self._create_box(1.2, 0.5, 1.0)
        turret.reparentTo(self.root)
        turret.setPos(0, 0.8, 0)
        turret.setColor(*color)
        self.turret = turret

        # 炮管
        barrel = self._create_box(0.15, 0.15, 1.0)
        barrel.reparentTo(self.root)
        barrel.setPos(0, 0.8, 0.7)
        barrel.setColor(0.2, 0.2, 0.2, 1)
        self.barrel = barrel

        # 履带
        for offset in [-0.9, 0.9]:
            track = self._create_box(0.3, 0.5, 1.5)
            track.reparentTo(self.root)
            track.setPos(offset, 0.3, 0)
            track.setColor(0.15, 0.15, 0.15, 1)

        # 玩家标记
        if is_player:
            marker = self._create_box(0.4, 0.4, 0.4)
            marker.reparentTo(self.root)
            marker.setPos(0, 1.3, 0)
            marker.setColor(1, 1, 0, 1)

    def _create_box(self, w, h, d):
        """创建立方体"""
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("box", format, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")

        vertices = [
            (-w/2, -h/2, -d/2), (w/2, -h/2, -d/2),
            (w/2, h/2, -d/2), (-w/2, h/2, -d/2),
            (-w/2, -h/2, d/2), (w/2, -h/2, d/2),
            (w/2, h/2, d/2), (-w/2, h/2, d/2),
        ]

        for v in vertices:
            vertex.addData3(*v)
            normal.addData3(0, 1, 0)
            color.addData4(1, 1, 1, 1)

        indices = [0,1,2,0,2,3, 4,6,5,4,7,6, 0,4,5,0,5,1,
                   2,6,7,2,7,3, 0,3,7,0,7,4, 1,5,6,1,6,2]

        prim = GeomTriangles(Geom.UHStatic)
        for i in range(0, len(indices), 3):
            prim.addVertices(indices[i], indices[i+1], indices[i+2])

        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode("box")
        node.addGeom(geom)
        return self.root.attachNewNode(node)

    def set_turret_angle(self, angle_deg):
        """设置炮塔角度"""
        h = -angle_deg + 90
        if hasattr(self, 'turret'):
            self.turret.setH(h)
        if hasattr(self, 'barrel'):
            self.barrel.setH(h)


class BulletModel3D(SimpleModel):
    """子弹 3D 模型"""

    def __init__(self, render_np, color):
        super().__init__(render_np)
        bullet = self._create_sphere(0.1)
        bullet.reparentTo(self.root)
        bullet.setColor(*color)

    def _create_sphere(self, radius):
        """创建简单球体"""
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("sphere", format, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")

        segments = 8
        for i in range(segments):
            for j in range(segments // 2 + 1):
                theta = 2 * math.pi * i / segments
                phi = math.pi * j / (segments // 2)
                x = radius * math.sin(phi) * math.cos(theta)
                y = radius * math.cos(phi)
                z = radius * math.sin(phi) * math.sin(theta)
                vertex.addData3(x, y, z)
                normal.addData3(x/radius, y/radius, z/radius)
                color.addData4(1, 1, 1, 1)

        prim = GeomTriangles(Geom.UHStatic)
        for i in range(segments):
            for j in range(segments // 2):
                i0 = i * (segments // 2 + 1) + j
                i1 = ((i + 1) % segments) * (segments // 2 + 1) + j
                i2 = i * (segments // 2 + 1) + j + 1
                i3 = ((i + 1) % segments) * (segments // 2 + 1) + j + 1
                prim.addVertices(i0, i1, i2)
                prim.addVertices(i1, i3, i2)

        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode("sphere")
        node.addGeom(geom)
        return self.root.attachNewNode(node)


class BarricadeModel3D(SimpleModel):
    """烈璧障 3D 模型"""

    def __init__(self, render_np, x, y, radius, color=(0.8, 0.3, 0.1, 0.7)):
        super().__init__(render_np)
        self.radius = radius

        # 环形墙
        segments = 16
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            bx = radius * math.cos(angle) * SCALE_2D_TO_3D
            bz = radius * math.sin(angle) * SCALE_2D_TO_3D

            block = self._create_box(0.3, 1.0, 0.3)
            block.reparentTo(self.root)
            block.setPos(bx, 0.5, bz)
            block.setColor(*color)

        # 地面标记
        ground = self._create_circle(radius * SCALE_2D_TO_3D)
        ground.reparentTo(self.root)
        ground.setPos(0, 0.02, 0)
        ground.setColor(0.8, 0.3, 0.1, 0.3)
        ground.setTransparency(TransparencyAttrib.MAlpha)

        self.set_pos(x, y)

    def _create_box(self, w, h, d):
        """创建立方体"""
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("box", format, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")

        vertices = [
            (-w/2, -h/2, -d/2), (w/2, -h/2, -d/2),
            (w/2, h/2, -d/2), (-w/2, h/2, -d/2),
            (-w/2, -h/2, d/2), (w/2, -h/2, d/2),
            (w/2, h/2, d/2), (-w/2, h/2, d/2),
        ]

        for v in vertices:
            vertex.addData3(*v)
            normal.addData3(0, 1, 0)
            color.addData4(1, 1, 1, 1)

        indices = [0,1,2,0,2,3, 4,6,5,4,7,6, 0,4,5,0,5,1,
                   2,6,7,2,7,3, 0,3,7,0,7,4, 1,5,6,1,6,2]

        prim = GeomTriangles(Geom.UHStatic)
        for i in range(0, len(indices), 3):
            prim.addVertices(indices[i], indices[i+1], indices[i+2])

        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode("box")
        node.addGeom(geom)
        return self.root.attachNewNode(node)

    def _create_circle(self, radius):
        """创建圆形地面标记"""
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("circle", format, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")

        segments = 32
        vertex.addData3(0, 0, 0)
        normal.addData3(0, 1, 0)
        color.addData4(1, 1, 1, 1)

        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            vertex.addData3(x, 0, z)
            normal.addData3(0, 1, 0)
            color.addData4(1, 1, 1, 1)

        prim = GeomTriangles(Geom.UHStatic)
        for i in range(1, segments + 1):
            i0 = i
            i1 = i + 1 if i < segments else 1
            prim.addVertices(0, i0, i1)

        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode("circle")
        node.addGeom(geom)
        return self.root.attachNewNode(node)


class Terrain3D:
    """3D 地形"""

    def __init__(self, render_np):
        self.root = render_np.attachNewNode("terrain")

        # 主地面
        w = WIDTH * SCALE_2D_TO_3D / 2
        h = HEIGHT * SCALE_2D_TO_3D / 2

        cm = CardMaker("ground")
        cm.setFrame(-w, w, -h, h)
        ground = self.root.attachNewNode(cm.generate())
        ground.setP(-90)
        ground.setColor(0.2, 0.25, 0.15, 1)

        # 边界标记（低矮的半透明墙）
        wall_height = 0.5
        walls = [
            (0, wall_height/2, -h - 0.3, w * 2, wall_height, 0.6),
            (0, wall_height/2, h + 0.3, w * 2, wall_height, 0.6),
            (-w - 0.3, wall_height/2, 0, 0.6, wall_height, h * 2),
            (w + 0.3, wall_height/2, 0, 0.6, wall_height, h * 2),
        ]

        for x, y, z, width, height, depth in walls:
            wall = self._create_box(width, height, depth)
            wall.reparentTo(self.root)
            wall.setPos(x, y, z)
            wall.setColor(0.5, 0.5, 0.5, 0.3)
            wall.setTransparency(TransparencyAttrib.MAlpha)

    def _create_box(self, w, h, d):
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("box", format, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")

        vertices = [
            (-w/2, -h/2, -d/2), (w/2, -h/2, -d/2),
            (w/2, h/2, -d/2), (-w/2, h/2, -d/2),
            (-w/2, -h/2, d/2), (w/2, -h/2, d/2),
            (w/2, h/2, d/2), (-w/2, h/2, d/2),
        ]

        for v in vertices:
            vertex.addData3(*v)
            normal.addData3(0, 1, 0)
            color.addData4(1, 1, 1, 1)

        indices = [0,1,2,0,2,3, 4,6,5,4,7,6, 0,4,5,0,5,1,
                   2,6,7,2,7,3, 0,3,7,0,7,4, 1,5,6,1,6,2]

        prim = GeomTriangles(Geom.UHStatic)
        for i in range(0, len(indices), 3):
            prim.addVertices(indices[i], indices[i+1], indices[i+2])

        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode("box")
        node.addGeom(geom)
        return self.root.attachNewNode(node)


class TankBattle3DApp(ShowBase):
    """Panda3D 应用"""

    def __init__(self):
        loadPrcFileData("", """
            win-size 1600 1000
            window-title 坦克大战 3D
            show-frame-rate-meter #t
            sync-video #f
            undecorated #t
        """)

        super().__init__()
        self.disableMouse()

        # 摄像机
        self._setup_camera()

        # 灯光
        self._setup_lights()

        # 地形
        self.terrain = Terrain3D(self.render)

        # 对象管理
        self.tanks = {}
        self.bullets = {}
        self.barricades = {}

    def _setup_camera(self):
        """设置摄像机"""
        cam_height = 70
        back_dist = 20
        self.camera.setPos(0, -back_dist, cam_height)
        self.camera.lookAt(0, 0, 0)

    def _setup_lights(self):
        """设置灯光"""
        # 环境光
        al = AmbientLight("ambient")
        al.setColor(Vec4(0.5, 0.5, 0.5, 1))
        alnp = self.render.attachNewNode(al)
        self.render.setLight(alnp)

        # 方向光
        from panda3d.core import DirectionalLight
        dl = DirectionalLight("sun")
        dl.setColor(Vec4(0.8, 0.8, 0.7, 1))
        dlnp = self.render.attachNewNode(dl)
        dlnp.setPos(20, 40, 30)
        dlnp.lookAt(0, 0, 0)
        self.render.setLight(dlnp)

    def sync_tank(self, tank_id, x, y, angle=0, turret_angle=0,
                  color=(0.5, 0.5, 0.5, 1), is_player=False, hp=100, max_hp=100):
        """同步坦克"""
        if tank_id not in self.tanks:
            self.tanks[tank_id] = TankModel3D(self.render, color, is_player)

        tank = self.tanks[tank_id]
        tank.set_pos(x, y)
        tank.set_h(angle)
        tank.set_turret_angle(turret_angle)

        # HP 可视化
        if hp < max_hp:
            ratio = hp / max_hp
            tank.root.setColor(color[0] * ratio, color[1] * ratio, color[2] * ratio, 1)

    def remove_tank(self, tank_id):
        """移除坦克"""
        if tank_id in self.tanks:
            self.tanks[tank_id].remove()
            del self.tanks[tank_id]

    def sync_bullet(self, bullet_id, x, y, angle=0, color=(1, 0.5, 0, 1)):
        """同步子弹"""
        if bullet_id not in self.bullets:
            self.bullets[bullet_id] = BulletModel3D(self.render, color)

        bullet = self.bullets[bullet_id]
        bullet.set_pos(x, y, 0.5)
        bullet.set_h(angle)

    def remove_bullet(self, bullet_id):
        """移除子弹"""
        if bullet_id in self.bullets:
            self.bullets[bullet_id].remove()
            del self.bullets[bullet_id]

    def sync_barricade(self, barricade_id, x, y, radius, color=(0.8, 0.3, 0.1, 0.7)):
        """同步烈璧障"""
        if barricade_id not in self.barricades:
            self.barricades[barricade_id] = BarricadeModel3D(
                self.render, x, y, radius, color
            )

    def remove_barricade(self, barricade_id):
        """移除烈璧障"""
        if barricade_id in self.barricades:
            self.barricades[barricade_id].remove()
            del self.barricades[barricade_id]

    def cleanup(self):
        """清理所有对象"""
        for tank in list(self.tanks.values()):
            tank.remove()
        for bullet in list(self.bullets.values()):
            bullet.remove()
        for barricade in list(self.barricades.values()):
            barricade.remove()
        self.tanks.clear()
        self.bullets.clear()
        self.barricades.clear()


# ==================== 全局状态 ====================

_3d_app = None
_3d_enabled = False


def init_3d():
    """初始化 3D 渲染"""
    global _3d_app, _3d_enabled

    if not HAS_PANDA3D:
        print("[3D] Panda3D 不可用")
        return False

    try:
        _3d_app = TankBattle3DApp()
        _3d_enabled = True
        print("[3D] 3D 渲染已初始化")
        return True
    except Exception as e:
        print(f"[3D] 初始化失败: {e}")
        _3d_enabled = False
        return False


def sync_frame(player=None, enemies=None, bullets=None, barricades=None,
               generals=None, camps=None, explosions=None):
    """
    同步一帧到 3D 场景

    参数都是可选的，传入当前游戏状态即可
    """
    global _3d_app, _3d_enabled

    if not _3d_enabled or _3d_app is None:
        return

    try:
        # 同步玩家
        if player is not None:
            _3d_app.sync_tank(
                "player",
                player.rect.centerx,
                player.rect.centery,
                angle=getattr(player, 'angle', 0),
                turret_angle=getattr(player, 'turret_angle', 0),
                color=(0.2, 0.6, 0.2, 1),
                is_player=True,
                hp=getattr(player, 'hp', 100),
                max_hp=getattr(player, 'max_hp', 100)
            )

        # 同步敌人
        current_enemy_ids = set()
        if enemies is not None:
            for i, enemy in enumerate(enemies):
                eid = f"enemy_{enemy.num if hasattr(enemy, 'num') else i}"
                current_enemy_ids.add(eid)
                _3d_app.sync_tank(
                    eid,
                    enemy.rect.centerx,
                    enemy.rect.centery,
                    angle=getattr(enemy, 'angle', 0),
                    color=(0.7, 0.2, 0.2, 1),
                    hp=getattr(enemy, 'hp', 100),
                    max_hp=getattr(enemy, 'max_hp', 100)
                )

        # 清理已消失的敌人
        for eid in list(_3d_app.tanks.keys()):
            if eid != "player" and eid not in current_enemy_ids:
                _3d_app.remove_tank(eid)

        # 同步子弹
        current_bullet_ids = set()
        if bullets is not None:
            for i, bullet in enumerate(bullets):
                bid = f"bullet_{i}"
                current_bullet_ids.add(bid)
                _3d_app.sync_bullet(
                    bid,
                    bullet.rect.centerx,
                    bullet.rect.centery,
                    angle=getattr(bullet, 'angle', 0)
                )

        # 清理已消失的子弹
        for bid in list(_3d_app.bullets.keys()):
            if bid not in current_bullet_ids:
                _3d_app.remove_bullet(bid)

        # 同步烈璧障
        current_barricade_ids = set()
        if barricades is not None:
            for i, bar in enumerate(barricades):
                bid = f"barricade_{i}"
                current_barricade_ids.add(bid)
                _3d_app.sync_barricade(
                    bid,
                    bar.x,
                    bar.y,
                    getattr(bar, 'radius', 50)
                )

        # 清理已消失的烈璧障
        for bid in list(_3d_app.barricades.keys()):
            if bid not in current_barricade_ids:
                _3d_app.remove_barricade(bid)

        # 推进 Panda3D 一帧
        _3d_app.taskMgr.step()

    except Exception as e:
        print(f"[3D] 同步失败: {e}")
        _3d_enabled = False


def cleanup_3d():
    """清理 3D 资源"""
    global _3d_app, _3d_enabled

    if _3d_app is not None:
        _3d_app.cleanup()
        _3d_app.userExit()
        _3d_app = None

    _3d_enabled = False
    print("[3D] 已清理")


def is_3d_enabled():
    """检查 3D 是否启用"""
    return _3d_enabled
