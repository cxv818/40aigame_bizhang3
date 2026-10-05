# -*- coding: utf-8 -*-
"""
Panda3D 3D 渲染层 — 方案 A：3D 视觉 + 2D 逻辑

设计原则：
- 本文件只负责渲染，不碰游戏逻辑
- 游戏逻辑继续在 tank_battle_deluxe.py 中运行（2D 坐标系）
- 通过 GameAdapter 把 2D 状态同步到 3D 场景

坐标映射：
- 2D 逻辑坐标: (x, y) 单位像素，范围 [0, WIDTH] x [0, HEIGHT]
- 3D 场景坐标: (x, 0, y) 单位米，Y轴向上（Panda3D 标准）
- 摄像机俯视，带轻微倾斜增加 3D 感
"""

import os
import sys
import math

# Panda3D 导入
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    Point3, Vec3, Vec4, PointLight, AmbientLight,
    Texture, Geom, GeomNode, GeomVertexFormat, GeomVertexData,
    GeomVertexWriter, GeomTriangles, GeomTristrips,
    CardMaker, TextNode, TransparencyAttrib,
    CollisionTraverser, CollisionHandlerPusher, CollisionNode,
    CollisionSphere, CollisionBox, BitMask32,
    loadPrcFileData, WindowProperties, ClockObject
)
from direct.task import Task
from direct.gui.OnscreenText import OnscreenText

# 游戏常量（从 tank_battle_deluxe.py 同步）
WIDTH, HEIGHT = 1600, 1000
MAP_WIDTH = 1600
MAP_HEIGHT = 1000

# 3D 场景缩放：多少像素 = 1 米
SCALE_2D_TO_3D = 0.05  # 20像素 = 1米，地图变成 80m x 50m


def to_3d(x, y, z=0):
    """2D 逻辑坐标 → 3D 场景坐标"""
    return Point3(
        (x - MAP_WIDTH / 2) * SCALE_2D_TO_3D,
        z,
        -(y - MAP_HEIGHT / 2) * SCALE_2D_TO_3D  # Panda3D Z 轴向后
    )


def to_2d(pos3d):
    """3D 场景坐标 → 2D 逻辑坐标"""
    return (
        pos3d.x / SCALE_2D_TO_3D + MAP_WIDTH / 2,
        -pos3d.z / SCALE_2D_TO_3D + MAP_HEIGHT / 2
    )


class TankModel:
    """坦克 3D 模型封装"""

    def __init__(self, render_np, color, is_player=False):
        self.root = render_np.attachNewNode("tank")
        self.color = color
        self.is_player = is_player

        # 车身（长方体）
        self._create_body()
        # 炮塔（圆柱体近似）
        self._create_turret()
        # 炮管
        self._create_barrel()
        # 履带（左右两条）
        self._create_tracks()

        # 玩家特殊标记
        if is_player:
            self._create_player_marker()

        self.root.setColor(*color)

    def _create_box(self, w, h, d, color=None):
        """创建简单立方体几何体"""
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("box", format, Geom.UHStatic)

        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color_writer = GeomVertexWriter(vdata, "color")

        # 8 个顶点
        vertices = [
            (-w/2, -h/2, -d/2), (w/2, -h/2, -d/2),
            (w/2, h/2, -d/2), (-w/2, h/2, -d/2),
            (-w/2, -h/2, d/2), (w/2, -h/2, d/2),
            (w/2, h/2, d/2), (-w/2, h/2, d/2),
        ]

        for v in vertices:
            vertex.addData3(*v)
            # 简化法线
            nx = 1 if v[0] > 0 else -1
            ny = 1 if v[1] > 0 else -1
            nz = 1 if v[2] > 0 else -1
            normal.addData3(nx, ny, nz)
            if color:
                color_writer.addData4(*color)
            else:
                color_writer.addData4(1, 1, 1, 1)

        # 12 个三角形（6 个面）
        indices = [
            0, 1, 2, 0, 2, 3,  # 底面
            4, 6, 5, 4, 7, 6,  # 顶面
            0, 4, 5, 0, 5, 1,  # 前面
            2, 6, 7, 2, 7, 3,  # 后面
            0, 3, 7, 0, 7, 4,  # 左面
            1, 5, 6, 1, 6, 2,  # 右面
        ]

        prim = GeomTriangles(Geom.UHStatic)
        for i in range(0, len(indices), 3):
            prim.addVertices(indices[i], indices[i+1], indices[i+2])

        geom = Geom(vdata)
        geom.addPrimitive(prim)

        node = GeomNode("box")
        node.addGeom(geom)
        return node

    def _create_body(self):
        """坦克车身"""
        body = self.root.attachNewNode(self._create_box(2.0, 0.6, 1.4))
        body.setPos(0, 0.3, 0)
        body.setColor(0.3, 0.3, 0.3, 1)

    def _create_turret(self):
        """炮塔"""
        turret = self.root.attachNewNode(self._create_box(1.2, 0.4, 1.0))
        turret.setPos(0, 0.7, 0)
        turret.setColor(0.4, 0.4, 0.4, 1)
        self.turret = turret

    def _create_barrel(self):
        """炮管"""
        barrel = self.root.attachNewNode(self._create_box(0.15, 0.15, 1.2))
        barrel.setPos(0, 0.7, 0.8)
        barrel.setColor(0.2, 0.2, 0.2, 1)
        self.barrel = barrel

    def _create_tracks(self):
        """履带"""
        for offset in [-0.9, 0.9]:
            track = self.root.attachNewNode(self._create_box(0.3, 0.4, 1.5))
            track.setPos(offset, 0.2, 0)
            track.setColor(0.15, 0.15, 0.15, 1)

    def _create_player_marker(self):
        """玩家标记 - 头顶发光"""
        # 创建一个发光的球体在头顶
        marker = self.root.attachNewNode(self._create_box(0.3, 0.3, 0.3))
        marker.setPos(0, 1.2, 0)
        marker.setColor(1, 1, 0, 1)
        # 添加点光源
        pl = PointLight("player_light")
        pl.setColor(Vec4(1, 1, 0.5, 1))
        pl.setAttenuation((1, 0, 0.1))
        plnp = marker.attachNewNode(pl)
        self.root.setLight(plnp)

    def set_pos(self, x, y):
        """设置 2D 逻辑位置"""
        pos = to_3d(x, y)
        self.root.setPos(pos)

    def set_rotation(self, angle_deg):
        """设置朝向（角度，0=右，90=下）"""
        # Panda3D H 是水平旋转，0=朝屏幕内（北），顺时针
        # 2D: 0=右，90=下，180=左，270=上
        # 3D: 需要映射
        h = -angle_deg + 90  # 粗略映射
        self.root.setH(h)

    def set_turret_angle(self, angle_deg):
        """设置炮塔角度"""
        if hasattr(self, 'turret'):
            h = -angle_deg + 90
            self.turret.setH(h)
            if hasattr(self, 'barrel'):
                self.barrel.setH(h)

    def remove(self):
        self.root.removeNode()


class BulletModel:
    """子弹 3D 模型"""

    def __init__(self, render_np, color):
        self.root = render_np.attachNewNode("bullet")

        # 子弹 - 小圆柱体
        bullet = self.root.attachNewNode(self._create_cylinder(0.08, 0.3))
        bullet.setColor(*color)

    def _create_cylinder(self, radius, height):
        """创建圆柱体"""
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("cylinder", format, Geom.UHStatic)

        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")

        segments = 8
        # 顶部和底部圆
        for y in [height/2, -height/2]:
            for i in range(segments):
                angle = 2 * math.pi * i / segments
                x = radius * math.cos(angle)
                z = radius * math.sin(angle)
                vertex.addData3(x, y, z)
                normal.addData3(math.cos(angle), 0, math.sin(angle))
                color.addData4(1, 1, 1, 1)

        prim = GeomTriangles(Geom.UHStatic)
        # 侧面
        for i in range(segments):
            i0 = i
            i1 = (i + 1) % segments
            i2 = i + segments
            i3 = (i + 1) % segments + segments
            prim.addVertices(i0, i2, i1)
            prim.addVertices(i1, i2, i3)

        geom = Geom(vdata)
        geom.addPrimitive(prim)

        node = GeomNode("cylinder")
        node.addGeom(geom)
        return node

    def set_pos(self, x, y):
        pos = to_3d(x, y, 0.5)
        self.root.setPos(pos)

    def set_rotation(self, angle_deg):
        h = -angle_deg + 90
        self.root.setH(h)

    def remove(self):
        self.root.removeNode()


class BarricadeModel:
    """烈璧障 3D 模型"""

    def __init__(self, render_np, x, y, radius, color=(0.8, 0.3, 0.1, 0.7)):
        self.root = render_np.attachNewNode("barricade")
        self.radius = radius

        # 创建环形墙（用多个立方体围成圆）
        segments = 16
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            bx = radius * math.cos(angle)
            bz = radius * math.sin(angle)

            block = self.root.attachNewNode(self._create_box(0.3, 1.0, 0.3))
            block.setPos(bx, 0.5, bz)
            block.setColor(*color)

        # 地面标记
        ground = self.root.attachNewNode(self._create_circle(radius))
        ground.setPos(0, 0.01, 0)
        ground.setColor(0.8, 0.3, 0.1, 0.3)

        self.set_pos(x, y)

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
        return node

    def _create_circle(self, radius):
        """创建圆形地面标记 - 用三角形扇"""
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("circle", format, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")

        segments = 32
        # 中心点
        vertex.addData3(0, 0, 0)
        normal.addData3(0, 1, 0)
        color.addData4(1, 1, 1, 1)

        # 圆周上的点
        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            vertex.addData3(x, 0, z)
            normal.addData3(0, 1, 0)
            color.addData4(1, 1, 1, 1)

        # 用三角形列表
        prim = GeomTriangles(Geom.UHStatic)
        for i in range(1, segments + 1):
            i0 = i
            i1 = i + 1 if i < segments else 1
            prim.addVertices(0, i0, i1)

        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode("circle")
        node.addGeom(geom)
        return node

    def set_pos(self, x, y):
        pos = to_3d(x, y)
        self.root.setPos(pos)

    def remove(self):
        self.root.removeNode()


class Terrain:
    """3D 地形"""

    def __init__(self, render_np):
        self.root = render_np.attachNewNode("terrain")

        # 主地面
        cm = CardMaker("ground")
        cm.setFrame(
            -MAP_WIDTH/2 * SCALE_2D_TO_3D,
            MAP_WIDTH/2 * SCALE_2D_TO_3D,
            -MAP_HEIGHT/2 * SCALE_2D_TO_3D,
            MAP_HEIGHT/2 * SCALE_2D_TO_3D
        )
        ground = self.root.attachNewNode(cm.generate())
        ground.setP(-90)  # 水平放置
        ground.setColor(0.2, 0.25, 0.15, 1)  # 军绿色地面

        # 网格线
        self._create_grid()

        # 边界墙（半透明，不挡视线）
        self._create_walls()

    def _create_grid(self):
        """创建地面网格"""
        format = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("grid", format, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        color = GeomVertexWriter(vdata, "color")

        grid_size = 50 * SCALE_2D_TO_3D
        w = MAP_WIDTH * SCALE_2D_TO_3D / 2
        h = MAP_HEIGHT * SCALE_2D_TO_3D / 2

        # 横线
        for y in range(int(-h), int(h) + 1, int(grid_size)):
            vertex.addData3(-w, 0.02, y)
            vertex.addData3(w, 0.02, y)
            color.addData4(0.3, 0.35, 0.25, 1)
            color.addData4(0.3, 0.35, 0.25, 1)

        # 竖线
        for x in range(int(-w), int(w) + 1, int(grid_size)):
            vertex.addData3(x, 0.02, -h)
            vertex.addData3(x, 0.02, h)
            color.addData4(0.3, 0.35, 0.25, 1)
            color.addData4(0.3, 0.35, 0.25, 1)

        prim = GeomTriangles(Geom.UHStatic)
        for i in range(0, vertex.getWriteRow(), 2):
            prim.addVertices(i, i + 1, i)

        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode("grid")
        node.addGeom(geom)
        grid = self.root.attachNewNode(node)

    def _create_walls(self):
        """创建边界墙"""
        w = MAP_WIDTH * SCALE_2D_TO_3D / 2
        h = MAP_HEIGHT * SCALE_2D_TO_3D / 2
        wall_height = 2.0

        walls = [
            # (x, y, z, width, height, depth)
            (0, wall_height/2, -h - 0.5, w * 2, wall_height, 1),  # 上
            (0, wall_height/2, h + 0.5, w * 2, wall_height, 1),   # 下
            (-w - 0.5, wall_height/2, 0, 1, wall_height, h * 2),  # 左
            (w + 0.5, wall_height/2, 0, 1, wall_height, h * 2),   # 右
        ]

        for x, y, z, width, height, depth in walls:
            wall = self.root.attachNewNode(self._create_box(width, height, depth))
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
        return node


class GameAdapter:
    """
    游戏适配器：桥接 2D 游戏逻辑和 3D 渲染

    用法：
        adapter = GameAdapter(panda_app)
        # 在游戏循环中：
        adapter.sync_tank(tank_id, x, y, angle, turret_angle)
        adapter.sync_bullet(bullet_id, x, y, angle)
        adapter.add_barricade(x, y, radius)
    """

    def __init__(self, panda_app):
        self.app = panda_app
        self.tanks = {}      # id -> TankModel
        self.bullets = {}    # id -> BulletModel
        self.barricades = {} # id -> BarricadeModel
        self.effects = []    # 特效列表

    def sync_tank(self, tank_id, x, y, angle=0, turret_angle=0,
                  color=(0.5, 0.5, 0.5, 1), is_player=False, hp=100, max_hp=100):
        """同步坦克状态"""
        if tank_id not in self.tanks:
            self.tanks[tank_id] = TankModel(
                self.app.render, color, is_player
            )

        tank = self.tanks[tank_id]
        tank.set_pos(x, y)
        tank.set_rotation(angle)
        tank.set_turret_angle(turret_angle)

        # HP 可视化（车身颜色变暗表示受伤）
        if hp < max_hp:
            damage_ratio = hp / max_hp
            r = color[0] * damage_ratio
            g = color[1] * damage_ratio
            b = color[2] * damage_ratio
            tank.root.setColor(r, g, b, 1)

    def remove_tank(self, tank_id):
        """移除坦克"""
        if tank_id in self.tanks:
            self.tanks[tank_id].remove()
            del self.tanks[tank_id]

    def sync_bullet(self, bullet_id, x, y, angle=0, color=(1, 0.5, 0, 1)):
        """同步子弹状态"""
        if bullet_id not in self.bullets:
            self.bullets[bullet_id] = BulletModel(
                self.app.render, color
            )

        bullet = self.bullets[bullet_id]
        bullet.set_pos(x, y)
        bullet.set_rotation(angle)

    def remove_bullet(self, bullet_id):
        """移除子弹"""
        if bullet_id in self.bullets:
            self.bullets[bullet_id].remove()
            del self.bullets[bullet_id]

    def add_barricade(self, barricade_id, x, y, radius, color=(0.8, 0.3, 0.1, 0.7)):
        """添加烈璧障"""
        if barricade_id not in self.barricades:
            self.barricades[barricade_id] = BarricadeModel(
                self.app.render, x, y, radius * SCALE_2D_TO_3D, color
            )

    def remove_barricade(self, barricade_id):
        """移除烈璧障"""
        if barricade_id in self.barricades:
            self.barricades[barricade_id].remove()
            del self.barricades[barricade_id]

    def clear_all(self):
        """清空所有对象"""
        for tank in self.tanks.values():
            tank.remove()
        for bullet in self.bullets.values():
            bullet.remove()
        for barricade in self.barricades.values():
            barricade.remove()
        self.tanks.clear()
        self.bullets.clear()
        self.barricades.clear()


class TankBattle3D(ShowBase):
    """
    Panda3D 坦克大战 3D 渲染主类

    使用方式：
        app = TankBattle3D()
        adapter = GameAdapter(app)
        # 然后在外部游戏循环中调用 adapter.sync_xxx()
        app.run()  # 或者 taskMgr.step() 用于手动控制帧率
    """

    def __init__(self):
        # 配置 Panda3D 窗口
        loadPrcFileData("", """
            win-size 1600 1000
            window-title 坦克大战 3D - Panda3D
            show-frame-rate-meter #t
            sync-video #f
        """)

        super().__init__()

        # 禁用默认鼠标控制
        self.disableMouse()

        # 设置摄像机 - 俯视带倾斜
        self._setup_camera()

        # 设置灯光
        self._setup_lights()

        # 创建地形
        self.terrain = Terrain(self.render)

        # 创建适配器
        self.adapter = GameAdapter(self)

        # 添加更新任务
        self.taskMgr.add(self._update_task, "update")

        # 帧率控制
        self.clock = ClockObject.getGlobalClock()

    def _setup_camera(self):
        """设置摄像机 - 俯视角度"""
        # 位置：地图中心上方，俯视带轻微倾斜
        # Panda3D 坐标系: X=右, Y=前(屏幕内), Z=上
        # 我们要俯视地图，所以摄像机在上方，看向中心
        cam_height = 70  # 摄像机高度
        cam_tilt = 55    # 俯视角度（从水平面往下）

        # 计算位置：在地图中心上方，稍微向后拉增加透视感
        tilt_rad = math.radians(cam_tilt)
        back_dist = cam_height * math.tan(tilt_rad) * 0.3  # 向后拉一点

        self.camera.setPos(0, -back_dist, cam_height)
        self.camera.lookAt(0, 0, 0)

        # 保存参数用于后续调整
        self.cam_height = cam_height
        self.cam_tilt = cam_tilt

    def _setup_lights(self):
        """设置灯光"""
        # 环境光
        al = AmbientLight("ambient")
        al.setColor(Vec4(0.4, 0.4, 0.4, 1))
        alnp = self.render.attachNewNode(al)
        self.render.setLight(alnp)

        # 方向光（太阳光）
        from panda3d.core import DirectionalLight
        dl = DirectionalLight("sun")
        dl.setColor(Vec4(0.8, 0.8, 0.7, 1))
        dlnp = self.render.attachNewNode(dl)
        dlnp.setPos(20, 40, 30)
        dlnp.lookAt(0, 0, 0)
        self.render.setLight(dlnp)

    def _update_task(self, task):
        """每帧更新任务"""
        # 可以在这里添加摄像机跟随玩家等逻辑
        return Task.cont

    def set_camera_target(self, x, y):
        """设置摄像机跟随目标"""
        pos = to_3d(x, y)
        self.camera.lookAt(pos)

    def zoom_camera(self, delta):
        """缩放摄像机"""
        self.cam_height = max(20, min(100, self.cam_height + delta))
        self._setup_camera()


# ==================== 演示模式 ====================

def demo():
    """独立演示：创建一些坦克和子弹看看效果"""
    app = TankBattle3D()
    adapter = app.adapter

    # 创建玩家坦克
    adapter.sync_tank("player", 800, 500, angle=0, turret_angle=45,
                      color=(0.2, 0.6, 0.2, 1), is_player=True, hp=80, max_hp=100)

    # 创建几个敌人
    for i in range(5):
        x = 200 + i * 300
        y = 200 + (i % 2) * 600
        adapter.sync_tank(f"enemy_{i}", x, y, angle=i * 45,
                          color=(0.7, 0.2, 0.2, 1), hp=100, max_hp=100)

    # 创建烈璧障
    adapter.add_barricade("bar1", 600, 400, 50)
    adapter.add_barricade("bar2", 1000, 600, 40)

    # 创建一些子弹
    for i in range(3):
        adapter.sync_bullet(f"bullet_{i}", 700 + i * 100, 450,
                           angle=i * 30, color=(1, 0.8, 0, 1))

    print("3D 演示已启动！")
    print("按 ESC 退出")
    app.run()


if __name__ == "__main__":
    demo()
