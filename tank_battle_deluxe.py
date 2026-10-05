# v36.0 (2026-10-05) — 36aigame
# -*- coding: utf-8 -*-
"""
坦克大战 2.0 — Tank Battle Deluxe（AI 总指挥版）
版本: v36.0 (2026-10-04)
更新: 显示修复 - 修复标签乱码、HUD重叠、空光环问题

操作:  WASD/方向键移动, SPACE 开火, ESC 退出
玩法:  歼灭 1000 台敌坦获胜;每歼灭 15 台进入下一波(约 67 波),
       每 5 波出一个 Boss;敌人死后原地留护甲领域(敌弹减速 30%);
       每 4 金币回 1 HP(可超上限)。

AI 总指挥 (AIDirector):
  - 后台线程每 1.5s 把战场态势发给本机 llama-server (127.0.0.1:8080),
    LLM 统一商议协同方案(钳形合围/声东击西…)后按敌坦编号下订单
  - AI 全权控制: 所有敌坦(含新兵)只听总指挥指令;订单间隙沿用旧令,
    新兵未接到首令时朝玩家推进;规则 AI 已移除,不再有站桩待机
  - 每 5s 自动自检 llama-server /health(轻量探测,不占推理槽)
  - 波次结束自动复盘: 方案谱系跨波累积战果,教训代际进化(第N代)
  - 右上角徽章: 绿=正常 / 橙=单次推理失败但服务器活着 / 红=服务器宕机

敌军战术频道 (SquadComm):
  - LLM 未接管的敌坦按距离分配角色(直攻/两翼包抄/风筝压制/拉开距离)
    (角色仅作展示与归因;运动与开火一律由总指挥指令驱动)
  - 右上面板滚动最近 8 条通讯,10 秒渐隐

依赖:  python3 + pygame; 本机 127.0.0.1:8080 有 OpenAI 兼容
       llama-server(无则自动回退规则 AI,游戏不会崩)
"""
import pygame
import random
import sys
import math
import os

# v40.1 - 3D 渲染支持（可选）
try:
    from panda3d_integration import init_3d, sync_frame, cleanup_3d, is_3d_enabled
    HAS_3D = True
except ImportError:
    HAS_3D = False
    def init_3d(): return False
    def sync_frame(**kwargs): pass
    def cleanup_3d(): pass
    def is_3d_enabled(): return False

try:
    from swallow import swallow as _swallow
except ImportError:  # swallow缺失时不阻塞游戏
    def _swallow(tag, exc, rate=3600): pass

# v36.0 - 导入日志和自检测模块
try:
    from logger import init_logger, get_logger
    from self_check import init_checker, get_checker
    HAS_LOGGER = True
except ImportError:
    HAS_LOGGER = False

# ============================ 部署配置(环境变量可覆盖) ============================
# TANK_AI_PORT_1/2/3 : 三帅 LLM 端口      TANK_UDP_PORT : pilot 指令端口
# TANK_RUNTIME_DIR   : 遥测/截图目录(默认 /tmp)
# TANK_EVO_DIR       : 进化存档目录(默认 <仓库根>/config)
_ENV = os.environ
AI_PORT_1 = int(_ENV.get("TANK_AI_PORT_1", 8080))
AI_PORT_2 = int(_ENV.get("TANK_AI_PORT_2", 8081))
AI_PORT_3 = int(_ENV.get("TANK_AI_PORT_3", 8082))
ADVISOR_PORT = int(_ENV.get("TANK_ADVISOR_PORT", 8083))
UDP_PORT  = int(_ENV.get("TANK_UDP_PORT", 8089))
RUNTIME_DIR = _ENV.get("TANK_RUNTIME_DIR", "/tmp")
EVO_DIR = _ENV.get("TANK_EVO_DIR",
                   os.path.join(os.path.dirname(os.path.dirname(
                       os.path.abspath(__file__))), "config"))
FAST_FILE = os.path.join(RUNTIME_DIR, "tank_fast.json")
SLOW_FILE = os.path.join(RUNTIME_DIR, "tank_battle_status.json")
SCREENSHOT_FILE = os.path.join(RUNTIME_DIR, "game_screenshot.png")
import json
import re
import threading
import time
import urllib.request

pygame.init()
pygame.mixer.init()

WIDTH, HEIGHT = 1600, 1000
_xiahoudun_aura_until = 0   # 三国杀: 夏侯惇铁壁光环结束时间戳(ms), 0=无光环

# ---------- 吕布·烈璧障/Boss墙/敌军互斥: 几何函数已拆至 world_api.py (v36.0) ----------
from world_api import (barricade_blocks, boss_wall_blocks, barricade_slide,
                       separate_enemies, set_context as _world_set_context)



# ---------- AI导演系统: ClusterPlanner/FormationManager/BattleMemory/AIDirector 已拆至 directors.py (v36.0) ----------
from directors import ClusterPlanner, FormationManager, BattleMemory, AIDirector
# ---------- 音效（16-bit 单声道，匹配 mixer 默认格式） ----------
def tone(freq, dur=0.08, vol=0.2, kind="square"):
    rate = 22050
    n = int(rate * dur)
    buf = bytearray()
    step = (2 * math.pi * freq) / rate
    for i in range(n):
        x = math.sin(step * i)
        if kind == "square":
            x = 1.0 if x > 0 else -1.0
        elif kind == "saw":
            x = 2 * (i / n) - 1
        elif kind == "noise":
            x = random.random() * 2 - 1
        x = max(-1.0, min(1.0, x * vol))
        buf += int(x * 32767).to_bytes(2, "little", signed=True)
    try:
        return pygame.mixer.Sound(buffer=bytes(buf))
    except Exception:
        return None


SND_FIRE = tone(660, 0.06, 0.12, "square")
SND_HIT = tone(220, 0.08, 0.16, "saw")
SND_EXP = tone(90, 0.25, 0.22, "noise")
SND_COIN = tone(880, 0.08, 0.14, "square")
SND_POW = tone(520, 0.16, 0.18, "saw")
SND_HURT = tone(150, 0.12, 0.2, "saw")


def play(snd):
    if snd:
        try:
            snd.play()
        except Exception:
            pass


# ---------- 特效 ----------
flash = []
particles = pygame.sprite.Group()
screen_shake = 0


def add_shake(v):
    global screen_shake
    screen_shake = min(screen_shake + v, 16)

class Barricade:
    """v40.1: 烈璧障 - 完整圆形物理墙(360°无死角)。放置后位置固定。
    敌军坦克和子弹完全不能穿过(像一堵真正的墙)。玩家和玩家子弹完全不受影响。
    朝向=玩家炮塔方向，仅影响视觉呈现(开口方向)，不影响物理阻挡(全向)。"""
    RADIUS = 120          # 环半径
    THICK = 20            # 环带厚度
    ARC = math.pi         # 视觉覆盖弧度(π=180°半圆)，仅用于绘制
    LIFETIME = 60_000     # 存在 60s 后消散(ms)

    def __init__(self, x, y, facing):
        self.x, self.y = float(x), float(y)
        self.facing = facing      # 半圆朝向(玩家炮塔角)
        self.born = pygame.time.get_ticks()
        self._segments = None     # 惰性生成的环带碰撞段
        self._build()

    def _build(self):
        self._segments = []
        n = 26  # 弧上离散段数
        for i in range(n):
            a = self.facing - self.ARC / 2 + self.ARC * i / (n - 1)
            self._segments.append((a, self.x + math.cos(a) * self.RADIUS,
                                   self.y + math.sin(a) * self.RADIUS))

    def expired(self):
        return pygame.time.get_ticks() - self.born > self.LIFETIME

    def blocks_point(self, px, py):
        """v40.1: 烈璧障 = 完整物理墙。敌军不能穿过环带，也不能进入环带内侧。
        无论从何角度接近，内侧区域和环带本体都完全阻挡(像一堵真正的圆形墙)。"""
        dx, dy = px - self.x, py - self.y
        d = math.hypot(dx, dy)

        # v40.1: 环带内侧区域完全阻挡(像一堵圆形墙，360°无死角)
        if d < self.RADIUS - self.THICK:
            return True

        # 环带本体完全阻挡
        if self.RADIUS - self.THICK <= d <= self.RADIUS + self.THICK:
            return True

        return False

    def blocks_line(self, x1, y1, x2, y2):
        """v40.1: 检测线段(子弹轨迹)是否穿过烈璧障(完整圆环墙)。
        子弹从任何角度接近，只要穿过环带本体或内侧区域即被阻挡。"""
        # 计算线段与圆的交点
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

        # v40.1: 检查交点是否在线段内(360°全向阻挡)
        for t in [t1, t2]:
            if 0 <= t <= 1:
                ix = x1 + t * dx
                iy = y1 + t * dy
                # 只要交点落在环带厚度范围内或内侧区域就阻挡
                d_to_center = math.hypot(ix - self.x, iy - self.y)
                if d_to_center <= self.RADIUS + self.THICK:
                    return True
        return False

    def draw(self, screen):
        age = pygame.time.get_ticks() - self.born
        if age > self.LIFETIME - 3000:   # 最后3s闪烁提醒
            if (age // 250) % 2 == 0:
                return
        alpha = 255 if age < self.LIFETIME - 3000 else 160
        for a, sx, sy in self._segments:
            r, g, b = 220, 40 + int(40 * math.sin(age / 200 + a)), 50
            pygame.draw.circle(screen, (r, g, b), (int(sx), int(sy)), self.THICK // 2 + 2)
            pygame.draw.circle(screen, (255, 120, 120), (int(sx), int(sy)), 2)

# ---------- 山地地形(随机绿/黄迷彩块): 敌坦山上射速x2、沿山绕行;给AI总指挥的奖励计分用 ----------
class Hills:
    """战场山地: 若干迷彩山块(绿/黄随机),敌坦入山射速x2并沿山缘绕行;玩家不受地形影响。"""
    BONUS_SCORE_PER_TICK = 2   # AI总指挥奖励: 敌坦在山上每存活60帧 +2分(鼓励占山压制)
    KILL_PLAYER_BONUS = 500    # 击杀玩家一次性奖励(结算时计入AI积分)

    def __init__(self, n=6, seed=None):
        rng = random.Random(seed)
        self.blocks = []  # (x, y, w, h, color)
        for _ in range(n):
            w = rng.randint(90, 170)
            h = rng.randint(70, 130)
            x = rng.randint(40, WIDTH - w - 40)
            y = rng.randint(60, HEIGHT // 2)  # 敌人在上半部分出生，避开玩家出生区
            color = random.choice([(60, 120, 60), (150, 140, 50)])  # 绿或黄迷彩
            self.blocks.append([x, y, w, h, color])
        self._reward_acc = 0  # 奖励积分累加器

    def in_hill(self, x, y):
        return any(b[0] <= x <= b[0]+b[2] and b[1] <= y <= b[1]+b[3]
                   for b in self.blocks)

    def draw(self, screen):
        for x, y, w, h, c in self.blocks:
            pygame.draw.rect(screen, c, (x, y, w, h), border_radius=18)
            pygame.draw.rect(screen, tuple(min(255, v+40) for v in c),
                             (x, y, w, h), 3, border_radius=18)

    def update_reward(self, enemies, frames=1):
        """敌坦占山每60帧给AI +2分(奖励机制: 占山压制越久分越高)。"""
        on_hill = sum(1 for e in enemies
                      if self.in_hill(e.rect.centerx, e.rect.centery))
        self._reward_acc += on_hill * frames
        if self._reward_acc >= 60:
            gained = (self._reward_acc // 60) * self.BONUS_SCORE_PER_TICK
            self._reward_acc %= 60
            return gained
        return 0
FPS = 30
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.DOUBLEBUF)
pygame.display.set_caption("坦克大战 v36.0 — 吕布(你/OpenClaw) vs 曹操(AI)")
clock = pygame.time.Clock()

BLACK = (18, 18, 22)
DARK = (40, 40, 48)
GRAY = (130, 130, 140)
WHITE = (240, 240, 240)
YELLOW = (255, 224, 70)
RED = (220, 60, 60)
ORANGE = (240, 150, 40)
BLUE = (70, 130, 230)
CYAN = (70, 210, 210)
PURPLE = (170, 90, 220)
GREEN = (70, 170, 80)
GOLD = (255, 195, 60)
BG1 = (48, 52, 60)
BG2 = (58, 62, 72)


def _load_font(size):
    for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"):
        if p_exists(p):
            return pygame.font.Font(p, size)
    return pygame.font.SysFont("consolas", size)


def p_exists(p):
    import os
    return os.path.exists(p)


FONT = _load_font(28)
BIGFONT = _load_font(72)
FONT_SMALL = _load_font(18)

# 全局 AI 指挥官 / 战术频道（main 里创建）
DIRECTOR = None
COMM = None


# ============ 敌军战术频道（互相通讯 + 角色分配） ============
# ---------- 通讯频道: SquadComm/WeiCommandChannel/AdvisorChannel 已拆至 channels.py (v36.0) ----------
from channels import SquadComm, WeiCommandChannel, AdvisorChannel, set_communicator
class Camp:
    """大营: 敌军大营(上中)和我军大营(下中),血量1000,被攻破则输"""
    
    def __init__(self, x, y, is_enemy=True, max_hp=1000):
        self.x = x
        self.y = y
        self.is_enemy = is_enemy
        self.max_hp = max_hp
        self.hp = max_hp
        self.radius = 35
        self.alive = True
        self.flash_time = 0  # 受击闪烁
        
    def take_damage(self, dmg):
        """受到攻击"""
        if not self.alive:
            return
        self.hp -= dmg
        self.flash_time = 5  # 闪烁5帧
        # v33.03埋点: 大营受击(复盘时间线)
        try:
            from battle_recorder import record_event
            record_event("camp_hit", {"enemy_side": bool(self.is_enemy), "dmg": dmg,
                                      "hp_left": self.hp})
        except Exception:
            pass
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            
    def draw(self, screen):
        """绘制大营"""
        if not self.alive:
            return
            
        # 颜色: 敌军红色, 我军蓝色
        color = RED if self.is_enemy else BLUE
        flash_color = WHITE if self.flash_time > 0 else color
        
        # 外圈(城墙)
        pygame.draw.circle(screen, flash_color, (int(self.x), int(self.y)), self.radius, 4)
        
        # 内圈填充
        inner_surf = pygame.Surface((self.radius*2, self.radius*2), pygame.SRCALPHA)
        pygame.draw.circle(inner_surf, (*color[:3], 60), (self.radius, self.radius), self.radius)
        screen.blit(inner_surf, (self.x - self.radius, self.y - self.radius))
        
        # 营帐图标(三角形)
        points = [
            (self.x, self.y - self.radius + 8),
            (self.x - self.radius + 10, self.y + 8),
            (self.x + self.radius - 10, self.y + 8),
        ]
        pygame.draw.polygon(screen, flash_color, points)
        pygame.draw.polygon(screen, (*color[:3], 180), points)
        
        # 文字标签
        label = "魏军大营" if self.is_enemy else "我军大营"
        text = FONT_SMALL.render(label, True, flash_color)
        screen.blit(text, text.get_rect(center=(self.x, self.y - self.radius - 12)))
        
        # 血条背景
        bar_w = 80
        bar_h = 8
        bar_x = self.x - bar_w // 2
        bar_y = self.y + self.radius + 8
        pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_w, bar_h))
        
        # 血条
        hp_ratio = self.hp / self.max_hp
        hp_w = int(bar_w * hp_ratio)
        hp_color = GREEN if hp_ratio > 0.5 else (YELLOW if hp_ratio > 0.25 else RED)
        if hp_w > 0:
            pygame.draw.rect(screen, hp_color, (bar_x, bar_y, hp_w, bar_h))
        
        # 血量数字
        hp_text = FONT_SMALL.render(f"{self.hp}/{self.max_hp}", True, WHITE)
        screen.blit(hp_text, hp_text.get_rect(center=(self.x, bar_y + bar_h + 10)))
        
        # 闪烁递减
        if self.flash_time > 0:
            self.flash_time -= 1
            
    def check_bullet_hit(self, bullet):
        """检查子弹是否命中大营"""
        if not self.alive:
            return False
        dx = bullet.rect.centerx - self.x
        dy = bullet.rect.centery - self.y
        dist = math.hypot(dx, dy)
        if dist < self.radius + 5:
            # 玩家攻击大营造成5倍伤害(加速游戏节奏)
            dmg = bullet.dmg * 5 if bullet.owner == "player" else bullet.dmg
            self.take_damage(dmg)
            return True
        return False


class Particle(pygame.sprite.Sprite):
    def __init__(self, x, y, color, vx, vy, life, size=3):
        super().__init__()
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.ellipse(self.image, color, (0, 0, size, size))
        self.rect = self.image.get_rect(center=(x, y))
        self.vx, self.vy = vx, vy
        self.life = self.max_life = life

    def update(self):
        self.rect.x += self.vx
        self.rect.y += self.vy
        self.vx *= 0.94
        self.vy *= 0.94
        self.life -= 1
        if self.life <= 0:
            self.kill()


def spawn_explosion(x, y, color=ORANGE, count=18, speed=5):
    for _ in range(count):
        a = random.uniform(0, math.pi * 2)
        s = random.uniform(1, speed)
        particles.add(Particle(x, y, color,
                               math.cos(a) * s, math.sin(a) * s,
                               random.randint(15, 35), random.randint(2, 5)))
    flash.append([x, y, 12])


# ---------- 子弹 ----------
class Bullet(pygame.sprite.Sprite):
    """子弹:速度拆成 base_vx/vy(原始)与 vx/vy(当前),供护甲领域等力场改写。"""

    def __init__(self, x, y, angle, speed, owner, dmg=1, pierce=0, color=YELLOW,
                 plan=None, firer=None):
        super().__init__()
        self.image = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(self.image, color, (0, 0, 10, 10))
        pygame.draw.ellipse(self.image, WHITE, (1, 1, 4, 4))
        self.rect = self.image.get_rect(center=(x, y))
        self.base_vx = math.cos(angle) * speed
        self.base_vy = math.sin(angle) * speed
        self.vx = self.base_vx
        self.vy = self.base_vy
        self.owner = owner
        self.dmg = dmg
        self.pierce = pierce
        self.hit = set()
        self.life = 100
        self.slowed = False  # 护甲领域减速标记
        self.plan = plan     # 发射者当时执行的方案(战功真实归因)
        self.firer = firer   # 发射者编号(阵亡归因用)

    def update(self):
        self.rect.x += self.vx
        self.rect.y += self.vy
        self.life -= 1
        if (self.rect.right < 0 or self.rect.left > WIDTH or
                self.rect.bottom < 0 or self.rect.top > HEIGHT or self.life <= 0):
            self.kill()


# ---------- 坦克 ----------
class Tank(pygame.sprite.Sprite):
    """坦克基类:履带车体+炮塔绘制;玩家/敌人共用,移动逻辑分别在 Player/Enemy。"""

    def __init__(self, x, y, color, body_hp, is_player=False, size=40):
        super().__init__()
        self.color = color
        self.is_player = is_player
        self.size = size
        self.angle = -math.pi / 2 if is_player else math.pi / 2
        self.turret = -math.pi / 2  # v32.4: 初始炮塔方向向上
        # v32.1: 添加机动参数系统
        self.mobility = 10 if is_player else 5  # 机动值: 吕布10, 将领5, 士兵1
        # v32.4: 调整速度
        # 吕布: 4格/秒 = 5.33px/帧
        # 将领: 2格/秒 = 2.67px/帧
        # 士兵: 1格/秒 = 1.33px/帧
        if is_player:
            self.speed = 5.33  # 吕布: 4格/秒
        else:
            self.speed = 1.6  # 默认值，会在子类中覆盖
        self.fire_cooldown = 0
        # v36.0: 吕布发射频率改为5发/秒 (cd=6帧); 敌军 2发/s(cd=30帧)
        self.max_cooldown = 6 if is_player else 30
        self.max_hp = body_hp
        self.hp = body_hp
        self.pierce = 0
        self.rapid = 0
        self.dmg_mult = 1
        self._paint(x, y)

    def _paint(self, x, y):
        self.image = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        s = self.size
        pygame.draw.rect(self.image, DARK, (3, 4, 8, s - 8), border_radius=3)
        pygame.draw.rect(self.image, DARK, (s - 11, 4, 8, s - 8), border_radius=3)
        pygame.draw.rect(self.image, self.color, (8, 7, s - 16, s - 14), border_radius=6)
        cx, cy = s / 2, s / 2
        pygame.draw.ellipse(self.image,
                            tuple(min(255, c + 50) for c in self.color),
                            (cx - 10, cy - 10, 20, 20))
        length = s / 2 + 4
        ex = cx + math.cos(self.turret) * length
        ey = cy + math.sin(self.turret) * length
        sx = cx + math.cos(self.turret) * 8
        sy = cy + math.sin(self.turret) * 8
        pygame.draw.line(self.image, GRAY, (sx, sy), (ex, ey), 6)
        pygame.draw.line(self.image, WHITE, (sx, sy), (ex, ey), 2)
        center = self.rect.center if hasattr(self, "rect") else (x, y)
        self.rect = self.image.get_rect(center=center)

    def fire(self, group):
        if self.fire_cooldown > 0:
            return
        cd = self.max_cooldown if self.rapid <= 0 else max(5, self.max_cooldown // 2)
        # v32.4: 自动瞄准最近敌人
        if self.is_player and group:
            nearest_enemy = None
            nearest_dist = float('inf')
            for e in group:
                if hasattr(e, 'owner') and e.owner == "enemy":
                    dist = math.hypot(e.rect.centerx - self.rect.centerx, 
                                    e.rect.centery - self.rect.centery)
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest_enemy = e
            if nearest_enemy and nearest_dist < 300:  # 300px内自动瞄准
                self.turret = math.atan2(nearest_enemy.rect.centery - self.rect.centery,
                                        nearest_enemy.rect.centerx - self.rect.centerx)
        
        mx = self.rect.centerx + math.cos(self.turret) * (self.size / 2 + 4)
        my = self.rect.centery + math.sin(self.turret) * (self.size / 2 + 4)
        # v36.0: 子弹速度调整 - 吕布改为5格/秒
        # 吕布子弹: 5格/秒 = 6.67px/帧
        # 将领子弹: 5格/秒 = 6.67px/帧
        # 士兵子弹: 3格/秒 = 4px/帧
        # v32.3: 伤害调整 - 吕布5, 将领3, 士兵1
        bullet_speed = 6.67 if self.is_player else 4.0
        bullet_dmg = 5 if self.is_player else 4.0  # 吕布伤害5
        b = Bullet(mx, my, self.turret, bullet_speed, "player" if self.is_player else "enemy",
                   dmg=bullet_dmg, pierce=self.pierce,
                   color=YELLOW if self.is_player else RED)
        group.add(b)
        self.fire_cooldown = cd
        if self.is_player:
            play(SND_FIRE)
            spawn_explosion(mx, my, YELLOW, 4, 2)

    def update(self):
        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1
        if self.rapid > 0:
            self.rapid -= 1

    def take_damage(self, d):
        self.hp -= d
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            return True
        return False


# ---------- 玩家 ----------
class Player(Tank):
    """玩家(吕布):基础血 500。回血仅靠大本营驻留(+2/帧,封顶max_hp)。金币不回血(v36.0移除)。"""

    def __init__(self, x, y):
        super().__init__(x, y, GREEN, 500, is_player=True)
        self.coins = 0
        self.heal_per_coin = 0  # 金币回血积分

    def heal(self, amount):
        """统一回血出口(审计 BUG-B): 封顶 = max_hp × 3,所有回血路径必须走这里。"""
        self.hp = min(self.max_hp * 3, self.hp + amount)

    def earn_coin(self, n=1):
        """金币不再回血，只累计数量(v36.0: 移除金币回血机制)"""
        self.coins += n
        # v36.0: 移除金币回血，只保留大本营回血

    def handle_input(self, group):
        keys = pygame.key.get_pressed()
        dx = dy = 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += 1
        if dx or dy:
            a = math.atan2(dy, dx)
            h = self.speed * (0.72 if dx and dy else 1.0)
            _nx = self.rect.x + math.cos(a) * h
            _ny = self.rect.y + math.sin(a) * h
            if boss_wall_blocks(_nx + self.size/2, _ny + self.size/2):
                pass  # 曹操赤壁屏障: 键盘移动同样不可穿越
            else:
                self.rect.x, self.rect.y = _nx, _ny
            self.rect.clamp_ip((0, 0, WIDTH, HEIGHT))
            self.angle = a
            self.turret = a
            self._paint(self.rect.centerx, self.rect.centery)
        # v32.4: 修复子弹角度 - 没有移动时保持当前角度
        if keys[pygame.K_SPACE]:
            self.fire(group)


# ---------- 敌人 ----------
class Enemy(Tank):
    """四种敌坦:grunt(综合)/fast(高速)/tank(重甲)/sniper(远狙);被总指挥接管后按订单行动。"""

    # 对称平衡: 全兵种血 20 / 伤害 1(与吕布子弹一致) / cd 仅作出生首发延迟(实测射速由 max_cooldown=30 统一)
    # v32.3: 调整血量 - 士兵50, 将领500, 吕布1000
    # v32.2: 调整速度为1秒1格 (40px/30FPS = 1.33px/帧)
    TYPES = {
        "grunt": dict(color=RED, hp=50, speed=1.33, cd=30, dmg=1),
        "fast": dict(color=ORANGE, hp=50, speed=2.66, cd=30, dmg=1),
        "tank": dict(color=PURPLE, hp=50, speed=0.8, cd=30, dmg=1),
        "sniper": dict(color=BLUE, hp=50, speed=1.07, cd=30, dmg=1),
    }

    def __init__(self, kind, x, y):
        t = self.TYPES[kind]
        # 三国杀: 亲兵按归属染色 — 曹操=红 惇=橙 渊=黄(与三将主色一致,一眼识部队)
        _owner_color = None
        if COMM:
            _my_num = COMM.next_num()   # 提前取号(染色判断用,后面不再重复取)
            _owner_color = {0: RED, 2: (255, 120, 40), 1: (255, 220, 60)}.get(_my_num % 3)
        if _owner_color:
            t = dict(t)
            t["color"] = _owner_color
        super().__init__(x, y, t["color"], t["hp"], is_player=False,
                         size=40 if kind != "fast" else 32)
        self.kind = kind
        self.num = _my_num if COMM else 0   # 复用提前取的号(防双取)
        self.speed = t["speed"]
        self.mobility = 1  # v32.1: 一般士兵机动值为1
        self.max_cooldown = t["cd"]
        self.dmg_mult = t["dmg"]
        self._just_fired_angle = None  # 本帧射角(合火弹检测用)
        self._just_fired_pos = None
        self.change_dir = 0
        self.dir = random.choice([math.pi / 2, -math.pi / 2, math.pi, 0])
        self.aggro = 520 if kind == "sniper" else 380

    def snapshot(self, player):
        dx = player.rect.centerx - self.rect.centerx
        dy = player.rect.centery - self.rect.centery
        role = COMM.roles.get(id(self), "") if COMM else ""
        return {"id": self.num, "kind": self.kind, "role": role,
                "hp": self.hp, "max_hp": self.max_hp,
                "dist": math.hypot(dx, dy),
                "x": self.rect.centerx, "y": self.rect.centery}

    def ai_update(self, group, player, hills=None, player_camp=None):
        # AI 全权控制模式:所有敌坦(含新兵)都由总指挥指令驱动。
        # 订单间隙沿用上一条指令继续行动,不再站桩待机。
        # 
        # 【重要】三将是一个军事集团，由曹操主帅统一指挥：
        # - 曹操（主帅）：统一指挥所有敌人，制定全局战略
        # - 夏侯惇（左翼副将）：执行左翼包抄任务
        # - 夏侯渊（右翼副将）：执行右翼突袭任务
        # 
        # 所有敌人都由曹操主帅的AI统一指挥，确保三将协同作战
        _my_dir = DIRECTOR  # 所有敌人都由曹操（DIRECTOR）统一指挥
        
        order = _my_dir.get_order(self.num) if _my_dir else None
        
        # 保存当前plan到敌人对象（用于数据库记录）
        if order:
            self.current_plan = order.get("plan", "")
        else:
            self.current_plan = ""
        
        # 决定目标: 玩家或大营
        # 优先级: LLM指令的order_target > 20%随机(硬编码兑底,LLM未下指令时仍有攻营威胁)
        # 攻营激活条件: 波次>3(与玩家攻击敌营同规则,游戏2613行)
        _target_camp = False
        _order_target = str(order.get("target", "")) if order else ""
        # 使用模块级缓存的波次，避免每帧读取文件
        _wave_now = getattr(main, "_cached_wave", 1)
        _camp_attackable = _wave_now > 3
        if player_camp and player_camp.alive:
            _dist_to_player = math.hypot(player.rect.centerx - self.rect.centerx,
                                          player.rect.centery - self.rect.centery)
            _dist_to_camp = math.hypot(player_camp.x - self.rect.centerx,
                                       player_camp.y - self.rect.centery)
            if _order_target == "pcamp" and _camp_attackable:
                # LLM明确下令攻吕布大营(波次>3才有效)
                _target_camp = True
                dx = player_camp.x - self.rect.centerx
                dy = player_camp.y - self.rect.centery
            elif order is None and random.random() < 0.2:
                # 无订单新兵: 保留原有随机兑底
                if _dist_to_camp < _dist_to_player + 200:
                    _target_camp = True
                    dx = player_camp.x - self.rect.centerx
                    dy = player_camp.y - self.rect.centery
                else:
                    dx = player.rect.centerx - self.rect.centerx
                    dy = player.rect.centery - self.rect.centery
            else:
                dx = player.rect.centerx - self.rect.centerx
                dy = player.rect.centery - self.rect.centery
        else:
            dx = player.rect.centerx - self.rect.centerx
            dy = player.rect.centery - self.rect.centery
        
        if order is None:
            # 新兵还没接到首条订单:朝玩家推进并保持低频率开火,
            # 避免 AI 离线/首次请求间隙出现"只走不打"的空窗
            self.turret = math.atan2(dy, dx)
            self.dir = self.turret
            self.angle = self.dir
            nx = self.rect.x + math.cos(self.dir) * self.speed
            ny = self.rect.y + math.sin(self.dir) * self.speed
            if barricade_blocks(nx + self.size/2, ny + self.size/2):
                # v40.1: 烈璧障 = 完整物理墙，敌军不能穿过，只能沿墙滑动或原地待命
                # 尝试沿墙切向滑动(像撞墙一样沿墙面移动)
                moved = False
                # 先尝试切向滑动
                from world_api import barricade_slide
                slide_dir = barricade_slide(self.rect.centerx, self.rect.centery, self.dir, self.speed)
                if slide_dir != self.dir:
                    test_nx = self.rect.x + math.cos(slide_dir) * self.speed
                    test_ny = self.rect.y + math.sin(slide_dir) * self.speed
                    if not barricade_blocks(test_nx + self.size/2, test_ny + self.size/2):
                        self.rect.x, self.rect.y = test_nx, test_ny
                        self.dir = slide_dir
                        moved = True
                # 切向滑动失败则尝试其他方向
                if not moved:
                    for angle_offset in [math.pi/4, -math.pi/4, math.pi/2, -math.pi/2, 3*math.pi/4, -3*math.pi/4]:
                        test_angle = self.dir + angle_offset
                        test_nx = self.rect.x + math.cos(test_angle) * self.speed
                        test_ny = self.rect.y + math.sin(test_angle) * self.speed
                        if not barricade_blocks(test_nx + self.size/2, test_ny + self.size/2):
                            self.rect.x, self.rect.y = test_nx, test_ny
                            moved = True
                            break
                # 如果所有方向都被挡，原地待命但可以开火
            else:
                self.rect.x, self.rect.y = nx, ny
            self.rect.clamp_ip((0, 0, WIDTH, HEIGHT))
            self._paint(self.rect.centerx, self.rect.centery)
            if math.hypot(dx, dy) < self.aggro and random.random() < 0.02:
                b = Bullet(self.rect.centerx + math.cos(self.dir) * (self.size / 2 + 4),
                           self.rect.centery + math.sin(self.dir) * (self.size / 2 + 4),
                           self.dir, 4.0, "enemy", dmg=self.dmg_mult)
                group.add(b)
                play(SND_FIRE)
            return
        dist = math.hypot(dx, dy)
        aim = math.atan2(dy, dx)
        self.turret = aim
        on_hill = bool(hills and hills.in_hill(self.rect.centerx, self.rect.centery))
        # dir 是相对朝向玩家的偏移角;strafe=1 时叠加侧向分量形成环绕走位
        move = aim + order["dir"]
        if order.get("strafe"):
            side = 1 if order["dir"] >= 0 else -1
            move = aim + side * math.pi / 2 + order["dir"] * 0.3
        if on_hill:
            # 山地走法: 沿山缘绕行(切向+微朝心),不穿山心也不离山
            cx = self.rect.centerx; cy = self.rect.centery
            for b in hills.blocks:
                bx, by, bw, bh = b[0], b[1], b[2], b[3]
                if bx <= cx <= bx+bw and by <= cy <= by+bh:
                    mx_, my_ = bx+bw/2, by+bh/2
                    # 切向(绕山) + 微向山心(防出山),随移山块自转
                    to_c = math.atan2(my_-cy, mx_-cx)
                    move = to_c + math.pi/2 + 0.35 * math.sin((to_c + math.pi/2) - move) if False else (move*0.3 + (to_c + math.pi/2)*0.7)
                    break
        self.dir = move
        self.angle = move
        nx = self.rect.x + math.cos(move) * self.speed
        ny = self.rect.y + math.sin(move) * self.speed
        if barricade_blocks(nx + self.size/2, ny + self.size/2):
            # v40.1: 烈璧障 = 完整物理墙，敌军不能穿过，只能沿墙滑动或原地待命
            moved = False
            # 先尝试切向滑动
            from world_api import barricade_slide
            slide_dir = barricade_slide(self.rect.centerx, self.rect.centery, self.dir, self.speed)
            if slide_dir != self.dir:
                test_nx = self.rect.x + math.cos(slide_dir) * self.speed
                test_ny = self.rect.y + math.sin(slide_dir) * self.speed
                if not barricade_blocks(test_nx + self.size/2, test_ny + self.size/2):
                    self.rect.x, self.rect.y = test_nx, test_ny
                    self.dir = slide_dir
                    moved = True
            # 切向滑动失败则尝试其他方向
            if not moved:
                for angle_offset in [math.pi/4, -math.pi/4, math.pi/2, -math.pi/2, 3*math.pi/4, -3*math.pi/4]:
                    test_angle = self.dir + angle_offset
                    test_nx = self.rect.x + math.cos(test_angle) * self.speed
                    test_ny = self.rect.y + math.sin(test_angle) * self.speed
                    if not barricade_blocks(test_nx + self.size/2, test_ny + self.size/2):
                        self.rect.x, self.rect.y = test_nx, test_ny
                        moved = True
                        break
            # 如果所有方向都被挡，原地待命但可以开火
        else:
            self.rect.x, self.rect.y = nx, ny
        self.rect.clamp_ip((0, 0, WIDTH, HEIGHT))
        self._paint(self.rect.centerx, self.rect.centery)
        # 山地增益: 射速x2(开火概率翻倍),奖励AI总指挥积分
        fire_p = 0.06 * (2 if on_hill else 1)
        # 三国杀: 夏侯惇铁壁光环期间全军射速+50%
        if _xiahoudun_aura_until and pygame.time.get_ticks() < _xiahoudun_aura_until:
            fire_p *= 1.5
        if getattr(self, "in_phalanx", False):
            fire_p = 0.0  # 方阵壁垒成员禁火: 免伤与合火互斥,防无解组合
        if order["fire"] and dist < self.aggro * 1.2 and random.random() < fire_p:
            b = Bullet(self.rect.centerx + math.cos(aim) * (self.size / 2 + 4),
                       self.rect.centery + math.sin(aim) * (self.size / 2 + 4),
                       aim, 4.0, "enemy", dmg=self.dmg_mult,
                       plan=order.get("plan"), firer=self.num)  # 战功真实归因
            group.add(b)
            self._just_fired_angle = aim  # 记录本帧射角,供合火弹汇总
            self._just_fired_pos = (self.rect.centerx, self.rect.centery)
            play(SND_FIRE)

# ---------- Boss ----------
class General(Tank):
    """三国杀模式: 三将实体战车（夏侯惇/夏侯渊/曹操）。
    - 各有专属技能与胜利关联: 斩杀副将→其亲兵减半+禁进化; 斩曹操→直接胜利
    - 曹操复用赤壁屏障; 夏侯惇方阵强化光环; 夏侯渊急袭(速度爆发)
    """
    # 三将配置: 血量/速度/体型/颜色/专属技能CD
    # v32.4: 将领速度2格/秒 = 2.67px/帧
    CONFIG = {
        "xiahoudun": dict(name="夏侯惇", hp=250, speed=2.67, size=56, color=(255, 120, 40),
                          skill_cd_s=25, skill_name="铁壁光环"),   # 方阵强化
        "xiahouyuan": dict(name="夏侯渊", hp=250, speed=2.67, size=48, color=(255, 220, 60),
                           skill_cd_s=18, skill_name="千里急袭"),   # 速度爆发
        "caocao":    dict(name="曹操",   hp=250, speed=2.67, size=64, color=(200, 60, 200),
                          skill_cd_s=22, skill_name="赤壁屏障"),   # 复用紫墙
    }

    def __init__(self, kind, x, y):
        cfg = self.CONFIG[kind]
        super().__init__(x, y, cfg["color"], cfg["hp"], is_player=False, size=cfg["size"])
        self.kind = kind
        self.gname = cfg["name"]
        self.speed = cfg["speed"]
        self.mobility = 5  # v32.1: 将领机动值为5
        self.num = -1  # 不占COMM编号(脱离普通订单体系,自主行动)
        self.skill_cd_s = cfg["skill_cd_s"]
        self.skill_name = cfg["skill_name"]
        self._skill_ready_ms = 0
        self._spawn_ms = pygame.time.get_ticks()
        self.retreat_hp = 0.25   # HP低于25%尝试脱离(夏侯渊跑得快真的会跑)
        self.alive = True
        self.down = False        # 被斩杀
        self.escaped = 0         # 逃脱次数(战报用)

    # ---------- 专属技能 ----------
    def _try_skill(self, group, player):
        now = pygame.time.get_ticks()
        if now < self._skill_ready_ms:
            return
        self._skill_ready_ms = now + int(self.skill_cd_s * 1000)
        if self.kind == "caocao":
            # 赤壁屏障: 自带紫墙(圆心=吕布位置, 朝向=曹操→吕布方向, 与Boss同构)
            aim = math.atan2(player.rect.centery - self.rect.centery,
                             player.rect.centerx - self.rect.centerx)
            try:
                self.walls.append(Barricade(player.rect.centerx,
                                            player.rect.centery, aim))
                COMM.say("系统", f"【{self.gname}】发动『{self.skill_name}』!")
            except Exception:
                pass
        elif self.kind == "xiahoudun":
            # 铁壁光环: 光环内己方+50%射速(通过全局buff帧窗口实现)
            global _xiahoudun_aura_until
            _xiahoudun_aura_until = now + 8000
            COMM.say("系统", f"【{self.gname}】发动『铁壁光环』! 全军射速提升!")
        elif self.kind == "xiahouyuan":
            # 千里急袭: 3秒内速度×2.2 冲脸
            self._burst_until = now + 3000
            COMM.say("系统", f"【{self.gname}】发动『千里急袭』!")

    # ---------- 行动AI ----------
    def general_update(self, group, player, my_camp):
        """每帧调用。性格: 惇稳(守中军/靠山) 渊袭(绕侧冲脸) 操(中军压阵+放墙)。"""
        now = pygame.time.get_ticks()
        self._try_skill(group, player)

        # 目标选择
        if self.kind == "xiahouyuan":
            # 急袭: 直冲吕布,低血时脱离
            if self.hp < self.max_hp * self.retreat_hp and now % 8000 < 4000:
                tx, ty = my_camp.x, my_camp.y      # 撤向大营回血
            else:
                tx, ty = player.rect.centerx, player.rect.centery
        elif self.kind == "xiahoudun":
            # 稳健: 卡在吕布与我营之间的中轴线
            tx = (player.rect.centerx + my_camp.x) / 2
            ty = (player.rect.centery + my_camp.y) / 2
        else:
            # 曹操: 压向我营(攻城主将),保持中距离
            tx, ty = my_camp.x, my_camp.y - 80

        # 夏侯渊急袭burst
        spd = self.speed
        if getattr(self, "_burst_until", 0) and now < self._burst_until:
            spd = self.speed * 2.2

        dx, dy = tx - self.rect.centerx, ty - self.rect.centery
        d = math.hypot(dx, dy) or 1
        self.dir = math.atan2(dy, dx)
        self.turret = math.atan2(player.rect.centery - self.rect.centery,
                                 player.rect.centerx - self.rect.centerx)  # 炮口始终瞄吕布
        nx = self.rect.x + math.cos(self.dir) * spd
        ny = self.rect.y + math.sin(self.dir) * spd
        if not barricade_blocks(nx + self.size / 2, ny + self.size / 2):
            self.rect.x, self.rect.y = nx, ny
        self.rect.clamp_ip((0, 0, WIDTH, HEIGHT))
        self._paint(self.rect.centerx, self.rect.centery)

        # 开火(对吕布, 伤害2, 射速按类型)
        # v32.2: 将领子弹速度 = 5格/秒 = 5 * 40px / 30FPS = 6.67px/帧
        fire_cd = 40 if self.kind != "xiahouyuan" else 28
        if now - getattr(self, "_last_fire", 0) > fire_cd * 16:
            aim = self.turret
            b = Bullet(self.rect.centerx + math.cos(aim) * (self.size / 2 + 4),
                       self.rect.centery + math.sin(aim) * (self.size / 2 + 4),
                       aim, 8.0, "enemy", dmg=3)  # v32.4: 将领子弹6格/秒
            group.add(b)
            self._last_fire = now
            play(SND_FIRE)

    def _paint(self, x, y):
        """三将专属外观: 各将底色 + 将名首字(黄光环在主循环screen层画,不被sprite裁剪)。"""
        super()._paint(x, y)
        s = self.size
        cx, cy = s / 2, s / 2
        try:
            fnt = pygame.font.SysFont("notosanscjk,simhei,arial", int(s * 0.42), bold=True)
            label = fnt.render(self.gname[0], True, (255, 255, 255))
            self.image.blit(label, label.get_rect(center=(int(cx), int(cy))))
        except Exception:
            pass

    def snapshot(self, player):
        dx = player.rect.centerx - self.rect.centerx
        dy = player.rect.centery - self.rect.centery
        return {"id": -10, "kind": f"general_{self.kind}", "role": self.gname,
                "hp": self.hp, "max_hp": self.max_hp,
                "dist": math.hypot(dx, dy),
                "x": self.rect.centerx, "y": self.rect.centery}


class Boss(Tank):
    """每 5 波一个 Boss:水平追踪玩家,双阶段交替扇形/环形弹幕(伤害已衰到0.001)。"""

    WALL_CD = 22_000        # 曹操·赤壁屏障: 每22s放一次
    WALL_LIFE = 12_000      # 持续12s(比吕布的60s短,压迫节奏用)

    def __init__(self, x, y):
        super().__init__(x, y, RED, 40, is_player=False, size=72)
        self.phase = 0          # 0=扇形 1=环形,每次开火后切换
        self.cooldown = 50
        self.num = 0            # 总指挥订单用编号 0
        self.wall_cd_until = 0  # 下次可放屏障的 ms 时间戳
        self.walls = []         # 曹操放的屏障(紫色,挡玩家+玩家弹)

    def snapshot(self, player):
        dx = player.rect.centerx - self.rect.centerx
        dy = player.rect.centery - self.rect.centery
        return {"id": 0, "kind": "boss", "role": "主攻", "num_ref": True,
                "hp": self.hp, "max_hp": self.max_hp,
                "dist": math.hypot(dx, dy),
                "x": self.rect.centerx, "y": self.rect.centery}

    def boss_update(self, group, player):
        self.turret = math.atan2(player.rect.centery - self.rect.centery,
                                 player.rect.centerx - self.rect.centerx)
        dx = player.rect.centerx - self.rect.centerx
        if dx:
            self.rect.x += math.copysign(min(self.speed, abs(dx)), dx)
        self.rect.clamp_ip((0, 0, WIDTH, HEIGHT))
        self._paint(self.rect.centerx, self.rect.centery)
        # ---- 曹操·赤壁屏障: 朝吕布方向放紫色半圆环,挡玩家移动+玩家弹 ----
        _now = pygame.time.get_ticks()
        self.walls = [w for w in self.walls
                      if _now - w.born < self.WALL_LIFE]
        if _now >= self.wall_cd_until:  # 22s CD 到就放;Boss只横移,距离条件反而卡死释放
            self.walls.append(Barricade(player.rect.centerx,
                                        player.rect.centery, self.turret))
            self.wall_cd_until = _now + self.WALL_CD
            COMM.say("曹操", "赤壁屏障!看你往哪走")
        self.cooldown -= 1
        if self.cooldown <= 0:
            if self.phase == 0:
                base = self.turret
                for i in range(-2, 3):
                    group.add(Bullet(self.rect.centerx, self.rect.centery,
                                     base + i * 0.22, 4, "enemy", dmg=1))
                add_shake(8)
                self.cooldown = 50
            else:
                for i in range(12):
                    group.add(Bullet(self.rect.centerx, self.rect.centery,
                                     i * math.pi / 6, 3.5, "enemy", dmg=1))
                add_shake(12)
                self.cooldown = 75
            self.phase = 1 - self.phase
            play(SND_HIT)


# ---------- 道具 ----------
POWERUPS = {
    "rapid": (CYAN, "快速射击", "Rapid Fire"),
    "pierce": (PURPLE, "穿透弹", "Pierce"),
    "dmg": (ORANGE, "强化火力", "Big DMG"),
    "heal": (GREEN, "回血", "Heal"),
    "life": (YELLOW, "额外生命", "+1 Life"),
}


# ---------- 护甲领域（敌尸残骸装甲,减速敌弹） ----------
class ArmorZone(pygame.sprite.Sprite):
    """敌人死亡处残留的护甲力场:范围内的敌弹减速到 30%。"""

    RADIUS = 90
    SLOW = 0.30
    DURATION = 60 * 8  # 8 秒(按 60fps 计)

    def __init__(self, x, y, color):
        super().__init__()
        self.color = color
        self.life = self.DURATION
        d = self.RADIUS * 2
        self.image = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(self.image, (*color, 26), (self.RADIUS, self.RADIUS),
                           self.RADIUS)
        pygame.draw.circle(self.image, (*color, 90),
                           (self.RADIUS, self.RADIUS), self.RADIUS, 2)
        self.rect = self.image.get_rect(center=(x, y))

    def update(self):
        self.life -= 1
        if self.life <= 0:
            self.kill()


class PowerUp(pygame.sprite.Sprite):
    def __init__(self, x, y, kind):
        super().__init__()
        color, name, _ = POWERUPS[kind]
        self.kind = kind
        self.color = color
        self.t = random.randint(300, 600)
        self.image = pygame.Surface((26, 26), pygame.SRCALPHA)
        pygame.draw.ellipse(self.image, color, (0, 0, 26, 26))
        pygame.draw.ellipse(self.image, WHITE, (5, 5, 16, 16))
        self.rect = self.image.get_rect(center=(x, y))

    def update(self):
        self.t -= 1
        if self.t <= 0:
            self.kill()


# ---------- 绘制辅助 ----------
def draw_bar(x, y, w, h, frac, color):
    pygame.draw.rect(screen, DARK, (x, y, w, h), border_radius=4)
    pygame.draw.rect(screen, color, (x + 1, y + 1, max(0, (w - 2) * frac), h - 2),
                     border_radius=4)


def draw_hp(cx, cy, hp, maxhp, color):
    draw_bar(cx - 20, cy - 8, 40, 5, hp / maxhp, color)


def apply_powerup(p, player):
    k = p.kind
    color, name, _ = POWERUPS[k]
    if k == "rapid":
        player.rapid = 480
    elif k == "pierce":
        player.pierce += 1
    elif k == "dmg":
        player.dmg_mult += 1
    elif k == "heal":
        player.hp = min(player.max_hp, player.hp + 3)  # heal 药包设计上只回基础条
    elif k == "life":
        player.max_hp += 1
        player.heal(1)
    player.earn_coin(10)
    play(SND_POW)
    spawn_explosion(p.rect.centerx, p.rect.centery, color, 12, 4)


def main():
    global screen_shake, flash
    global DIRECTOR, COMM, DIRECTOR_DUN, DIRECTOR_YUAN
    DIRECTOR = AIDirector(enabled=True, name="曹操", api_port=AI_PORT_1)
    DIRECTOR_DUN = AIDirector(enabled=True, name="夏侯惇", api_port=AI_PORT_2)
    DIRECTOR_YUAN = AIDirector(enabled=True, name="夏侯渊", api_port=AI_PORT_3)
    
    # --- 初始化双频道通讯系统 ---
    WEI_CHANNEL = WeiCommandChannel()   # 魏军指挥频道(曹操→副将)
    ADV_CHANNEL = AdvisorChannel()      # 军师频道(军师↔吕布)
    DIRECTOR.wei_channel = WEI_CHANNEL
    DIRECTOR_DUN.wei_channel = WEI_CHANNEL
    DIRECTOR_YUAN.wei_channel = WEI_CHANNEL
    set_communicator_director = set_communicator  # 别名复用
    
    COMM = SquadComm()
    set_communicator(COMM, director=DIRECTOR)  # v36.0: 注入COMM+DIRECTOR上下文
    _world_set_context(sys.modules[__name__], WIDTH, HEIGHT)  # v36.0: 几何函数上下文注入
    COMM.say("频道", "战术频道已建立，各单位报数")
    player = Player(WIDTH // 2, HEIGHT - 60)

    # --- 初始化 3D 渲染（可选）---
    if HAS_3D and os.environ.get("TANK_3D", "0") == "1":
        init_3d()

    # --- 初始化大营系统 ---
    enemy_camp = Camp(WIDTH // 2, 100, is_enemy=True, max_hp=888)   # 敌军大营(上中,y=100)
    player_camp = Camp(WIDTH // 2, HEIGHT - 100, is_enemy=False, max_hp=888)  # 我军大营(下中,y=540)

    # --- OpenClaw 接管接口: UDP 127.0.0.1:8089,每帧读取最新指令 ---
    import socket as _sock
    # UDP 接口全局单例: 死亡/R 重开走 main() 递归,若每次重建 socket+线程,
    # 会堆死线程且新 bind 失败→UDP 永久失联(旧线程写旧 _ctl)。模块级复用。
    global _UDP_CTL, _UDP_SOCK
    try:
        _UDP_SOCK
    except NameError:
        _UDP_CTL = {"dx": 0.0, "dy": 0.0, "fire": False, "mx": None, "my": None,
                "skill": False}
        _UDP_SOCK = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        # 不设 SO_REUSEADDR: UDP 下保证端口独占,双实例时第二个 bind 失败走降级,
        # 避免指令被随机进程收走(审计 BUG-A)
        try:
            _UDP_SOCK.bind(("127.0.0.1", UDP_PORT))
        except OSError:
            _UDP_SOCK = None  # 端口占用时静默降级(纯键盘模式)
        if _UDP_SOCK is not None:
            _UDP_SOCK.setblocking(False)

            def _ctl_worker():
                while True:
                    try:
                        data, _ = _UDP_SOCK.recvfrom(256)
                        j = json.loads(data.decode())
                        for k in ("dx", "dy", "fire", "mx", "my", "skill"):
                            if k in j:
                                _UDP_CTL[k] = j[k]
                    except BlockingIOError:
                        pass
                    except Exception:
                        pass
                    time.sleep(0.02)

            threading.Thread(target=_ctl_worker, daemon=True).start()
    _ctl = _UDP_CTL
    _udp = _UDP_SOCK

    enemies = pygame.sprite.Group()
    player_b = pygame.sprite.Group()
    enemy_b = pygame.sprite.Group()
    all_b = pygame.sprite.Group()
    powerups = pygame.sprite.Group()
    armor_zones = pygame.sprite.Group()

    wave = 0
    score = 0
    total_to_spawn = 1000  # 全场敌人总量(不含 Boss)
    running = True

    state = "play"
    spawn_queue = []
    boss_active = None
    # 三国杀模式: 三将实体
    generals = []
    _gen_spawned = set()   # 已出场三将
    _GEN_WAVES = {"xiahoudun": 3, "xiahouyuan": 5, "caocao": 3}  # 出场波次(降低便于验证)

    def start_wave(n, allow_boss=True):
        nonlocal wave, spawn_queue, boss_active
        wave = n
        spawn_queue = []
        if allow_boss and n % 5 == 0:
            boss_active = Boss(WIDTH // 2, 70)
            return
        # 本波敌人量 = 常规波量与剩余配额的较小值
        remain = total_to_spawn - (spawned[0] + len(spawn_queue))
        if remain <= 0:
            return
        count = min(3 + n, remain)
        kinds = ["grunt"]
        if n >= 2:
            kinds += ["fast"]
        if n >= 3:
            kinds += ["tank"]
        if n >= 4:
            kinds += ["sniper"]
        for _ in range(count):
            spawn_queue.append(random.choice(kinds))

    MAX_ONFIELD = 30  # 场上同时最多 30 台敌坦
    MIN_ONFIELD = 15  # 敌人数量保底:不足 15 台自动补充
    KILLS_PER_WAVE = 3   # 每歼灭3台进入下一波(触发总指挥复盘进化)
    spawned = [0]    # 已生成总数(列表以便内嵌函数改写)
    killed = 0       # 已击杀数
    hills = Hills(n=6)              # 战场山地(绿/黄迷彩随机)
    barricades = []                 # 吕布·烈璧障(半圆环壁垒)列表
    barricade_cd = [0]              # 上次释放时间戳(ms);0=就绪
    ai_score = 0                    # AI总指挥奖励积分(占山压制得分,击杀玩家+500)
    telemetry_tick = [0]  # 遥测帧计数器(每120帧≈2s上报一次)
    fast_tick = [0]       # 快遥测帧计数器(每12帧≈0.2s,审计 PERF-2)

    def spawn_next():
        if not spawn_queue or len(enemies) >= MAX_ONFIELD:
            return
        if spawned[0] >= total_to_spawn:
            return
        k = spawn_queue.pop(0)
        e = Enemy(k, random.randint(60, WIDTH - 60), random.randint(40, 120))
        e.max_hp += wave // 4
        e.hp += wave // 4
        enemies.add(e)
        spawned[0] += 1

    start_wave(1)
    for _ in range(4):
        spawn_next()

    # v36.0 - 初始化日志和自检测
    if HAS_LOGGER:
        logger = init_logger()
        checker = init_checker()
        logger.info("SYSTEM", "游戏启动完成，日志和自检测系统已初始化")
        
        # 游戏开始时执行一次完整自检测
        checker.last_check_time = 0  # 强制立即检测
        check_results = checker.check_all()
        if check_results:
            logger.info("SELF_CHECK", "=" * 50)
            logger.info("SELF_CHECK", "游戏开始自检测完成")
            logger.info("SELF_CHECK", "=" * 50)
            
            # 记录关键组件状态
            for check_name, check_data in check_results["checks"].items():
                if isinstance(check_data, dict):
                    if "status" in check_data:
                        status = check_data["status"]
                        if status == "ok":
                            logger.info("SELF_CHECK", f"✅ {check_name}: 正常")
                        else:
                            logger.warning("SELF_CHECK", f"⚠️ {check_name}: {status}")
                    else:
                        # 处理嵌套结果（LLM服务器、数据库等）
                        ok_count = sum(1 for v in check_data.values() if isinstance(v, dict) and v.get("status") == "ok")
                        total_count = len(check_data)
                        logger.info("SELF_CHECK", f"📊 {check_name}: {ok_count}/{total_count} 正常")
                        
                        # 记录详细信息
                        for sub_name, sub_data in check_data.items():
                            if isinstance(sub_data, dict):
                                sub_status = sub_data.get("status", "unknown")
                                if sub_status == "ok":
                                    # 记录关键信息
                                    details = []
                                    for key, value in sub_data.items():
                                        if key != "status":
                                            details.append(f"{key}={value}")
                                    if details:
                                        logger.info("SELF_CHECK", f"  ✅ {sub_name}: {', '.join(details)}")
                                else:
                                    logger.warning("SELF_CHECK", f"  ⚠️ {sub_name}: {sub_status}")
            
            # 保存详细报告
            try:
                report = checker.get_detailed_report()
                with open("/tmp/game_self_check_report.txt", "w", encoding="utf-8") as f:
                    f.write(report)
                logger.info("SELF_CHECK", "详细报告已保存到 /tmp/game_self_check_report.txt")
            except Exception as e:
                logger.warning("SELF_CHECK", f"保存报告失败: {e}")
        else:
            logger.warning("SELF_CHECK", "自检测未能执行")

    while running:
        main._player_hit_this_frame = False  # 帧级玩家受击标志(方阵战果统计用)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # ESC退出时记录军师进化
                    if state == "play":
                        try:
                            from advisor_simple import record_battle_result
                            record_battle_result("quit", player.hp / player.max_hp, wave, killed)
                        except Exception as e:
                            print(f"[DEBUG] 军师进化记录失败: {e}")
                    # 清理 3D 资源
                    cleanup_3d()
                    running = False
                if state in ("gameover", "win") and event.key == pygame.K_r:
                    # v36.0: 进程重生替代递归——内核兑底清零线程/内存/socket,不可能漏清状态
                    # (旧递归每次泄漏3×AIDirector+11线程; 进化存档在磁盘,不受影响)
                    pygame.quit()
                    os.execv(sys.executable, [sys.executable] + [os.path.abspath(__file__)])
                # 回车键: 发送消息给军师
                if event.key == pygame.K_RETURN and state == "play":
                    if ADV_CHANNEL and ADV_CHANNEL.player_input_text.strip():
                        ADV_CHANNEL.player_chat(ADV_CHANNEL.player_input_text)
                        ADV_CHANNEL.player_input_text = ""
                # 退格键: 删除输入
                if event.key == pygame.K_BACKSPACE and state == "play":
                    if ADV_CHANNEL:
                        ADV_CHANNEL.player_input_text = ADV_CHANNEL.player_input_text[:-1]
                # Esc键: 清除输入
                if event.key == pygame.K_ESCAPE and state == "play":
                    if ADV_CHANNEL:
                        ADV_CHANNEL.player_input_text = ""
                # 普通字符输入(直接输入,不用按T)
                if event.unicode and event.key not in (pygame.K_RETURN, pygame.K_BACKSPACE, pygame.K_ESCAPE) and state == "play":
                    if ADV_CHANNEL:
                        if len(ADV_CHANNEL.player_input_text) < 20:
                            ADV_CHANNEL.player_input_text += event.unicode
            elif event.type == pygame.USEREVENT + 9 and state == "gameover":
                main()   # 自动重开(死亡后 3 秒),进化存档已继承
                return

        if state == "play":
            # ---- 三国杀: 三将按波次出场 ----
            for _gk, _gw in _GEN_WAVES.items():
                if wave >= _gw and _gk not in _gen_spawned:
                    _gx = WIDTH // 2 + (-120 if _gk == "xiahoudun" else 120 if _gk == "xiahouyuan" else 0)
                    generals.append(General(_gk, _gx, 60))
                    _gen_spawned.add(_gk)
                    COMM.say("系统", f"⚠ 敌将【{generals[-1].gname}】出场! (斩杀→亲兵减半+禁进化)")
                    try:
                        from battle_recorder import record_event
                        record_event("general_spawn", {"name": generals[-1].gname})  # v33.03埋点
                    except Exception:
                        pass
                    add_shake(12)

            # 三将更新+可被弹
            for _g in list(generals):
                if _g.hp <= 0 and not _g.down:
                    _g.down = True
                    generals.remove(_g)
                    spawn_explosion(_g.rect.centerx, _g.rect.centery, _g.color, 50, 10)
                    add_shake(18)
                    play(SND_EXP)
                    if _g.kind == "caocao":
                        state = "win"
                        score += 10000
                        COMM.say("系统", "🏆 斩杀曹操! 天下震动!")
                    else:
                        score += 3000
                        _halve = DIRECTOR_DUN if _g.kind == "xiahoudun" else DIRECTOR_YUAN
                        if _halve is not None:
                            _halve.enabled = True   # 保留调度但标记教训
                            try:
                                _halve.evo_disabled = True   # 禁进化标记
                            except Exception:
                                pass
                        COMM.say("系统", f"🏆 斩杀【{_g.gname}】! 亲兵威慑减半, 禁止进化!")
            
            for _g in generals:
                _g.general_update(all_b, player, player_camp)
                # 三将被玩家弹命中
                for b in list(all_b):
                    if b.owner == "player" and b.rect.colliderect(_g.rect) and id(_g) not in b.hit:
                        b.hit.add(id(_g))
                        _g.take_damage(b.dmg)
                        play(SND_HIT)
                        b.kill()
                        break

            # 补充生成:场上没满就补(每次补1台,自然限流)
            if spawn_queue and len(enemies) < MAX_ONFIELD:
                spawn_next()
            # 保底补充:场上不足 15 台且还有配额,从队列立即补足
            if (len(enemies) < MIN_ONFIELD and spawned[0] < total_to_spawn
                    and boss_active is None):
                while (len(enemies) < MIN_ONFIELD
                       and spawned[0] < total_to_spawn):
                    if not spawn_queue:
                        start_wave(wave, allow_boss=False)  # 就地续波,不重复召Boss
                        if not spawn_queue:
                            break
                    spawn_next()
            if not spawn_queue and len(enemies) == 0 and boss_active is None:
                if spawned[0] >= total_to_spawn:
                    state = "win"   # 1000 台全部清完(不等额外 Boss)
                    continue

            # ---- 吕布·烈璧障: K_LSHIFT 或 UDP skill 触发,30s CD,同屏最多3个,60s消散 ----
            _now_ms = pygame.time.get_ticks()
            if (pygame.key.get_pressed()[pygame.K_LSHIFT] or _ctl.get("skill")) \
                    and _now_ms - barricade_cd[0] >= 30_000:
                barricades.append(Barricade(player.rect.centerx, player.rect.centery,
                                            player.turret))
                if len(barricades) > 3:
                    barricades.pop(0)   # 顶掉最旧
                barricade_cd[0] = _now_ms
                COMM.say("吕布", "烈璧障!")
            _ctl["skill"] = False  # 单次触发消费

            # ---- 大本营回血: 玩家靠近我军大本营时自动回血 ----
            if player_camp and player_camp.alive:
                _dist_to_camp = math.hypot(player.rect.centerx - player_camp.x,
                                           player.rect.centery - player_camp.y)
                if _dist_to_camp < player_camp.radius + 50:  # 在大本营附近
                    if player.hp < player.max_hp:
                        player.hp = min(player.max_hp, player.hp + 2)  # 每帧回2点血
                        if random.random() < 0.05:  # 5%概率显示提示
                            COMM.say("系统", f"大本营回血中... HP:{player.hp:.0f}")
            
            # v36.0: 先处理玩家输入
            player.handle_input(player_b)
            
            # 检查是否有键盘输入
            keys = pygame.key.get_pressed()
            has_keyboard_input = (keys[pygame.K_w] or keys[pygame.K_s] or 
                                 keys[pygame.K_a] or keys[pygame.K_d] or 
                                 keys[pygame.K_UP] or keys[pygame.K_DOWN] or 
                                 keys[pygame.K_LEFT] or keys[pygame.K_RIGHT] or 
                                 keys[pygame.K_SPACE])
            
            # 只有在没有键盘输入时才使用AI控制
            if not has_keyboard_input:
                # 军师LLM控制: 优先使用军师指令
                if ADV_CHANNEL and hasattr(ADV_CHANNEL, 'last_cmd'):
                    cmd = ADV_CHANNEL.last_cmd
                    dx2, dy2 = cmd.get("dx", 0), cmd.get("dy", 0)
                    if dx2 or dy2:
                        a2 = math.atan2(dy2, dx2)
                        h2 = player.speed * (0.72 if abs(dx2) > 0.1 and abs(dy2) > 0.1 else 1.0)
                        _nx = player.rect.x + math.cos(a2) * h2
                        _ny = player.rect.y + math.sin(a2) * h2
                        
                        # v36.05: 调试边界问题
                        if player.rect.x < 150 or player.rect.x > 1450 or player.rect.y < 150 or player.rect.y > 850:
                            print(f"[DEBUG] 游戏循环: 主公在({player.rect.x},{player.rect.y}), 指令dx={dx2},dy={dy2}, 计算新位置=({_nx:.0f},{_ny:.0f})")
                        
                        if boss_wall_blocks(_nx + player.size/2, _ny + player.size/2):
                            pass
                        else:
                            player.rect.x, player.rect.y = _nx, _ny
                        player.rect.clamp_ip((0, 0, WIDTH, HEIGHT))
                        
                        # v36.05: 检查clamp后的位置
                        if player.rect.x < 150 or player.rect.x > 1450 or player.rect.y < 150 or player.rect.y > 850:
                            print(f"[DEBUG] 游戏循环: clamp后主公在({player.rect.x},{player.rect.y})")
                        
                        if cmd.get("mx") is not None:
                            player.turret = math.atan2(cmd["my"] - player.rect.centery,
                                                       cmd["mx"] - player.rect.centerx)
                        else:
                            player.turret = a2
                        player._paint(player.rect.centerx, player.rect.centery)
                    if cmd.get("fire", False):
                        player.fire(player_b)
                    
                    # v39.0: 军师触发烈璧障
                    if cmd.get("skill") and _now_ms - barricade_cd[0] >= 30_000:
                        barricades.append(Barricade(player.rect.centerx, player.rect.centery,
                                                    player.turret))
                        if len(barricades) > 3:
                            barricades.pop(0)
                        barricade_cd[0] = _now_ms
                        COMM.say("吕布", "军师令·烈璧障!")
                
                # 回退到UDP控制（oc_pilot）
                elif _udp is not None and (_ctl["dx"] or _ctl["dy"] or _ctl["fire"]):
                    dx2, dy2 = _ctl["dx"], _ctl["dy"]
                    if dx2 or dy2:
                        a2 = math.atan2(dy2, dx2)
                        h2 = player.speed * (0.72 if abs(dx2) > 0.1 and abs(dy2) > 0.1 else 1.0)
                        _nx = player.rect.x + math.cos(a2) * h2
                        _ny = player.rect.y + math.sin(a2) * h2
                        if boss_wall_blocks(_nx + player.size/2, _ny + player.size/2):
                            pass
                        else:
                            player.rect.x, player.rect.y = _nx, _ny
                        player.rect.clamp_ip((0, 0, WIDTH, HEIGHT))
                        if _ctl["mx"] is not None:
                            player.turret = math.atan2(_ctl["my"] - player.rect.centery,
                                                       _ctl["mx"] - player.rect.centerx)
                        else:
                            player.turret = a2
                        player._paint(player.rect.centerx, player.rect.centery)
                    if _ctl["fire"]:
                        player.fire(player_b)
            for e in list(enemies):
                e.ai_update(enemy_b, player, hills=hills, player_camp=player_camp)
            separate_enemies(enemies)  # 敌军互斥: 防扎堆叠罗汉
            # AI总指挥奖励: 敌坦占山压制持续加分
            ai_score += hills.update_reward(enemies)
            for e in list(enemies):
                e.update()
            player.update()
            if boss_active is not None:
                boss_active.boss_update(enemy_b, player)
                boss_active.update()

            # 敌军战术频道:角色分配 + 通讯记录
            if len(enemies) > 0:
                COMM.assign(list(enemies), player)

            # 三帅协同通讯: 每45s互相交换战术简报+给对方的建议(屏显)
            if (DIRECTOR.enabled and (enemies or boss_active is not None)
                    and pygame.time.get_ticks() - getattr(
                        main, "_coord_last", 0) > 45000):
                main._coord_last = pygame.time.get_ticks()
                _briefs = []
                for _cd in (DIRECTOR, DIRECTOR_DUN, DIRECTOR_YUAN):
                    if _cd and _cd.enabled:
                        _briefs.append(_cd.coord_brief())
                for _b in _briefs:
                    COMM.say("协同", _b)
                # 统帅拍板: 曹操根据三家简报给一句话调度令
                if _briefs:
                    COMM.say("曹操", "各镇保持协同,亲兵队压上,两翼照应!")

            # AI 指挥官：收集态势,异步请求指令(每1.5s一次)
            # 新增: 使用高级集群作战调度系统
            if (DIRECTOR.enabled or DIRECTOR_DUN.enabled or DIRECTOR_YUAN.enabled) \
                    and (len(enemies) > 0 or boss_active is not None):
                _all_snap = [e.snapshot(player) for e in enemies]
                if boss_active is not None:
                    _all_snap.append(boss_active.snapshot(player))
                _barr_snap = [{"x": round(bc.x), "y": round(bc.y),
                               "r": bc.RADIUS, "facing": round(bc.facing, 2),
                               "life_left_s": max(0, round((bc.LIFETIME -
                                (pygame.time.get_ticks() - bc.born)) / 1000))}
                              for bc in barricades]
                _snapshot_base = {"player": {"x": player.rect.centerx,
                                             "y": player.rect.centery,
                                             "hp": player.hp,
                                             "max_hp": player.max_hp},
                                  "barricades": _barr_snap,
                                  "wave": wave, "boss": boss_active is not None,
                                  "hills": {"count": len(hills.blocks),
                                            "blocks": [{"x": b[0]+b[2]//2, "y": b[1]+b[3]//2,
                                                        "w": b[2], "h": b[3],
                                                        "color": "绿" if b[4][1] > b[4][2] else "黄"}
                                                       for b in hills.blocks]}}
                
                # 更新战略阶段
                DIRECTOR.update_strategic_phase(player.hp, player.max_hp, wave)
                
                # --- 双频道通讯系统 ---
                # 1. 魏军指挥频道: 曹操→副将协调
                if WEI_CHANNEL:
                    # v36.0: 曹操LLM真选计(替代随机模板); 计策约束注入三帅提示词
                    try:
                        from stratagem_llm import get_stratagem
                        _strat = get_stratagem()
                        # 首次注入真实频道实例( COMM/WEI_CHANNEL 由global已赋值 )
                        _strat.attach_channel(channel=WEI_CHANNEL, comm=COMM)
                        _strat.ask()
                        # LLM选计成功时接管喊话(避免模板重复喊); 未就绪/降级时才走旧模板
                        if not _strat.active:
                            WEI_CHANNEL.coordinate_attack([DIRECTOR, DIRECTOR_DUN, DIRECTOR_YUAN])
                    except Exception:
                        WEI_CHANNEL.coordinate_attack([DIRECTOR, DIRECTOR_DUN, DIRECTOR_YUAN])
                
                # 2. 军师频道: 军师↔吕布对话
                if ADV_CHANNEL:
                    _enemy_plan = DIRECTOR.current_plan or ""
                    # v36.05: 传递游戏状态给军师，用于边界修正
                    _game_state = {
                        "player": {"x": player.rect.centerx, "y": player.rect.centery,
                                   "hp": player.hp, "max_hp": player.max_hp},
                        "player_camp": {"x": player_camp.x, "y": player_camp.y,
                                        "hp": player_camp.hp, "alive": player_camp.alive} if player_camp else {},
                        "enemy_camp": {"x": enemy_camp.x, "y": enemy_camp.y,
                                       "hp": enemy_camp.hp, "alive": enemy_camp.alive} if enemy_camp else {},
                    }
                    ADV_CHANNEL.give_advice(player.hp, player.max_hp, _enemy_plan, _game_state)
                    ADV_CHANNEL.update()  # 检查LLM异步回复
                
                # 三路指挥: 曹操看全场(boss+所有),夏侯惇看ID%3==2,夏侯渊看ID%3==1
                # 修复(v36.0): 统一使用%3分配，与提示词和实际归属一致
                for _dir, _filt in ((DIRECTOR, None),
                                    (DIRECTOR_DUN, lambda s: s["id"] != 0 and s["id"] % 3 == 2),
                                    (DIRECTOR_YUAN, lambda s: s["id"] != 0 and s["id"] % 3 == 1)):
                    if not _dir.enabled:
                        continue
                    _mine = ([s for s in _all_snap if _filt(s)]
                             if _filt else list(_all_snap))
                    if not _mine:
                        continue
                    _snap = dict(_snapshot_base)
                    _gsnap = [g.snapshot(player) for g in generals]
                    _snap["enemies"] = _mine + _gsnap
                    if generals:
                        _snap["generals_alive"] = [g.gname for g in generals]
                    
                    # 使用高级调度系统(曹操主帅启用)
                    if _dir.name == "曹操" and len(_mine) >= 5:
                        _dir.execute_advanced_tactics(_snap, {s["id"] for s in _mine})
                    else:
                        _dir.request_async(_snap, {s["id"] for s in _mine})

            all_b.add(player_b, enemy_b)
            all_b.update()
            armor_zones.update()
            # 护甲领域:范围内敌弹减速到 30%(离开也不恢复——被衰变过的弹保持慢速)
            for z in armor_zones:
                for b in enemy_b:
                    if not b.slowed and z.rect.collidepoint(b.rect.center):
                        b.slowed = True
                        b.vx = b.base_vx * ArmorZone.SLOW
                        b.vy = b.base_vy * ArmorZone.SLOW
            particles.update()
            powerups.update()
            for i in range(len(flash)):
                flash[i] = [flash[i][0], flash[i][1], flash[i][2] - 2]
            flash = [f for f in flash if f[2] > 0]
            if screen_shake > 0:
                screen_shake -= 1

            # 记录战术效果（只在敌人死亡时记录，避免重复计数）
            try:
                # 检查是否有敌人死亡
                for e in enemies:
                    if not e.alive():  # 敌人死亡
                        order = DIRECTOR.get_order(e.num) if DIRECTOR else None
                        if order:
                            plan = order.get("plan", "")
                            if plan:
                                # 记录阵亡（不是每次受伤都记录）
                                from tactics_db import record_tactic
                                record_tactic(plan, death=True)
                                
                # 检查玩家是否被击中（真正的"命中"）
                # 这个需要在玩家受伤时记录，不是在敌人受伤时
            except:
                pass
            
            # 玩家子弹命中
            for b in list(player_b):
                if not b.alive():
                    continue
                if boss_wall_blocks(b.rect.centerx, b.rect.centery):
                    b.kill()  # 曹操赤壁屏障挡玩家弹
                    spawn_explosion(b.rect.centerx, b.rect.centery, PURPLE, 6, 3)
                    continue
                # 检查是否命中敌军大营(大营只在波次>3时可被攻击)
                if enemy_camp.alive and wave > 3 and enemy_camp.check_bullet_hit(b):
                    b.kill()
                    spawn_explosion(b.rect.centerx, b.rect.centery, RED, 10, 4)
                    play(SND_HIT)
                    if not enemy_camp.alive:
                        state = "win"  # 攻破敌军大营,胜利!
                        score += 5000
                        
                        # 记录军师进化(v36.0: 使用新的进化系统)
                        try:
                            if ADV_CHANNEL:
                                ADV_CHANNEL.request_review_async(wave, player.hp, player.max_hp)
                        except Exception as e:
                            print(f"[DEBUG] 军师进化记录失败: {e}")
                        
                        spawn_explosion(enemy_camp.x, enemy_camp.y, RED, 60, 12)
                        add_shake(20)
                        play(SND_EXP)
                    continue
                # v32.4: 修复子弹打不到敌人 - 移除方阵免伤，让玩家子弹可以打所有敌人
                targets = [e for e in enemies
                           if b.rect.colliderect(e.rect) and id(e) not in b.hit]
                if boss_active is not None and b.rect.colliderect(boss_active.rect) \
                        and id(boss_active) not in b.hit:
                    targets.append(boss_active)
                if targets:
                    for h in targets:
                        b.hit.add(id(h))
                        h.take_damage(b.dmg)
                        play(SND_HIT)
                    b.pierce -= len(targets)
                    if b.pierce < 0:
                        b.kill()

            # --- 合火弹(集火齐射): ≥10台同角±0.05rad同帧齐射 → 合成一发万倍弹 ---
            # 集火计数持续显示(无论是否触发,只要≥2台同角就报进度)
            _fired = [e for e in enemies
                      if getattr(e, "_just_fired_angle", None) is not None]
            if len(_fired) >= 2:
                _fired.sort(key=lambda x: x._just_fired_angle)
                _max_cluster = 1; _cur = 1
                for _i in range(1, len(_fired)):
                    if abs(_fired[_i]._just_fired_angle - _fired[_i-1]._just_fired_angle) < 0.05:
                        _cur += 1
                    else:
                        _cur = 1
                    _max_cluster = max(_max_cluster, _cur)
                if _max_cluster >= 10:
                    comm_fire_text = f"集火已成! {_max_cluster}/10 → 万倍合火弹发射!"
                    try:
                        from battle_recorder import record_event
                        record_event("focus_ready", {"cluster": _max_cluster})  # v33.03埋点
                    except Exception:
                        pass
                elif _max_cluster >= 2:
                    comm_fire_text = f"集火充能中 {_max_cluster}/10 (差{10-_max_cluster}台)"
                else:
                    comm_fire_text = None
            else:
                _max_cluster = 0
                comm_fire_text = None
            if len(_fired) >= 10:
                _fired.sort(key=lambda x: x._just_fired_angle)
                _used = set()
                for _lead in _fired:
                    if id(_lead) in _used:
                        continue
                    _grp = [x for x in _fired
                            if id(x) not in _used and
                            abs(x._just_fired_angle - _lead._just_fired_angle) < 0.05]
                    if len(_grp) >= 10:
                        for _x in _grp:
                            _used.add(id(_x))
                        _ang = _lead._just_fired_angle
                        _dmg = sum(x.dmg_mult for x in _grp) * 10.0  # 集火必杀: 10台×10=100 伤害(约1/5吕布血量),保留威慑
                        _bx = _lead.rect.centerx + math.cos(_ang) * 24
                        _by = _lead.rect.centery + math.sin(_ang) * 24
                        enemy_b.add(Bullet(_bx, _by, _ang, 7, "enemy",
                                           dmg=_dmg, pierce=99, color=ORANGE))
                        screen_shake = max(screen_shake, 60)
                        spawn_explosion(_bx, _by, ORANGE, 24, 6)
                        add_shake(10)
                        COMM.say("战术频道",
                                 f"集火指令! {len(_grp)}台同角万倍合火弹!")
                        comm_fire_text = None  # 已触发,不再报充能
                # 未凑齻10台的分组: 报告进度
                if _used and comm_fire_text is None and _max_cluster < 10:
                    pass
            if comm_fire_text:
                COMM.say("战术频道", comm_fire_text)
            for _e in enemies:
                _e._just_fired_angle = None
                _e._just_fired_pos = None

            # --- 方阵壁垒: ≥5台敌互相紧贴(间距≤62px)结成互联集群,壁垒内成员免伤玩家子弹,但成员禁火 ---
            # 检测降频: 每10帧重算(坦克~3px/帧,间距变化慢),帧间复用缓存(审计 PERF-1)
            main._phalanx_frame = getattr(main, "_phalanx_frame", 0) + 1
            if main._phalanx_frame % 10 == 0 or not hasattr(main, "_phalanx_ids"):
                _adj = {id(e): [] for e in enemies}
                _el = list(enemies)
                for _i in range(len(_el)):
                    for _j in range(_i + 1, len(_el)):
                        if math.hypot(_el[_i].rect.centerx - _el[_j].rect.centerx,
                                      _el[_i].rect.centery - _el[_j].rect.centery) <= 62:
                            _adj[id(_el[_i])].append(id(_el[_j]))
                            _adj[id(_el[_j])].append(id(_el[_i]))
                _seen = set()
                _best_grp = []
                for _e in _el:
                    if id(_e) in _seen:
                        continue
                    # BFS 连通分量
                    _comp = [id(_e)]
                    _seen.add(id(_e))
                    _q = [id(_e)]
                    while _q:
                        _cur_id = _q.pop()
                        for _nid in _adj[_cur_id]:
                            if _nid not in _seen:
                                _seen.add(_nid)
                                _comp.append(_nid)
                                _q.append(_nid)
                    if len(_comp) > len(_best_grp):
                        _best_grp = _comp
                _phalanx_ids = set(_best_grp) if len(_best_grp) >= 5 else set()
                _phalanx_just_formed = bool(_phalanx_ids) and not getattr(main, "_phalanx_active", False)
                # 方阵战果统计(注入复盘: 总指挥要知道方阵战术值不值)
                if DIRECTOR is not None and hasattr(DIRECTOR, "phalanx_stats"):
                    if _phalanx_just_formed:
                        DIRECTOR.phalanx_stats["formed"] += 1
                        DIRECTOR.phalanx_feedback = ""  # 成阵成功,清掉不足回执
                    if _phalanx_ids:
                        DIRECTOR.phalanx_stats["members"] = max(
                            DIRECTOR.phalanx_stats["members"], len(_best_grp))
                        if getattr(main, "_player_hit_this_frame", False):
                            DIRECTOR.phalanx_stats["hits_during"] += 1
                main._phalanx_ids = _phalanx_ids  # 供子弹命中判定读取
                # 成员标志:壁垒成员禁火(盾举起武器放下,防无敌+合火无解组合)
                for _pe in _el:
                    _pe.in_phalanx = id(_pe) in _phalanx_ids
                main._phalanx_active = bool(_phalanx_ids)
                if _phalanx_just_formed:
                    COMM.say("战术频道", f"敌军方阵成阵! {len(_best_grp)}台壁垒免伤!")
                    try:
                        from battle_recorder import record_event
                        record_event("phalanx_form", {"units": len(_best_grp)})  # v33.03埋点
                    except Exception:
                        pass
                elif not _phalanx_ids and getattr(main, "_phalanx_was", False):
                    COMM.say("战术频道", "敌军方阵已散开")
                    try:
                        from battle_recorder import record_event
                        record_event("phalanx_break", {})  # v33.03埋点
                    except Exception:
                        pass
                main._phalanx_was = bool(_phalanx_ids)
            else:
                _phalanx_ids = getattr(main, "_phalanx_ids", set())

            # 玩家子弹对壁垒成员免伤(仅玩家子弹;若弹只碰壁垒成员则弹开销毁)
            if _phalanx_ids:
                for b in list(player_b):
                    if b.alive() and any(
                            b.rect.colliderect(e.rect)
                            for e in enemies if id(e) in _phalanx_ids):
                        _non_ph = [e for e in enemies
                                   if b.rect.colliderect(e.rect)
                                   and id(e) not in _phalanx_ids
                                   and id(e) not in b.hit]
                        if not _non_ph:
                            b.kill()

            # 敌人死亡结算: 用它最后执行的方案归因
            for e in list(enemies):
                if e.hp <= 0:
                    # 归因到该兵所属的指挥官(奇偶分兵)
                    _e_dir = DIRECTOR
                    if e.num != 0:
                        _e_dir = (DIRECTOR_DUN if e.num % 3 == 2
                                  else DIRECTOR_YUAN if e.num % 3 == 1 else DIRECTOR)
                    _last_od = _e_dir.get_order(e.num) if _e_dir else None
                    _e_dir.note_death(e.num,
                                      plan=_last_od.get("plan") if _last_od else None)
                    score += 100
                    player.earn_coin(25)
                    spawn_explosion(e.rect.centerx, e.rect.centery, e.color, 20, 7)
                    add_shake(5)
                    
                    # 记录击杀事件到战场数据库
                    try:
                        from battle_recorder import record_event
                        record_event("enemy_killed", {
                            "enemy_id": e.num,
                            "enemy_type": e.kind,
                            "enemy_plan": _last_od.get("plan") if _last_od else None,
                            "player_hp": player.hp,
                            "player_x": player.rect.centerx,
                            "player_y": player.rect.centery,
                            "score": score,
                            "wave": wave
                        })
                    except:
                        pass
                    play(SND_EXP)
                    enemies.remove(e)
                    killed += 1
                    # 每歼灭15台推进一波:总指挥复盘进化 + 换波编成
                    if (killed % KILLS_PER_WAVE == 0
                            and spawned[0] < total_to_spawn):
                        for _rd in (DIRECTOR, DIRECTOR_DUN, DIRECTOR_YUAN):
                            if _rd and _rd.enabled:
                                _rd.request_review_async(
                                    wave, player.hp, player.max_hp)
                        start_wave(wave + 1)
                    # 尸位残甲:生成护甲领域(敌弹减速至30%)
                    armor_zones.add(ArmorZone(e.rect.centerx, e.rect.centery,
                                              e.color))
                    if random.random() < 0.22:
                        powerups.add(PowerUp(e.rect.centerx, e.rect.centery,
                                             random.choice(list(POWERUPS))))
                    if random.random() < 0.10:
                        powerups.add(PowerUp(e.rect.centerx, e.rect.centery, "life"))

            # Boss 死亡
            if boss_active is not None and boss_active.hp <= 0:
                score += 1000
                player.earn_coin(300)
                spawn_explosion(boss_active.rect.centerx, boss_active.rect.centery,
                                YELLOW, 60, 12)
                add_shake(20)
                play(SND_EXP)
                boss_active = None
                if killed >= total_to_spawn:
                    state = "win"   # 清完100台+Boss才算真正通关
                continue

            # ---- 烈璧障: 同步引用/过期清理/敌弹拦截 ----
            main._barricades = barricades
            main._boss_walls = list(boss_active.walls) if boss_active is not None else []
            for _bc in list(barricades):
                if _bc.expired():
                    barricades.remove(_bc)
                    COMM.say("吕布", "烈璧障消散")
            if barricades:
                for b in list(enemy_b):
                    if not b.alive():
                        continue
                    # v39.0: 使用线段检测，更精确地拦截子弹
                    bullet_hit = False
                    for bc in barricades:
                        if bc.blocks_line(b.rect.centerx - b.vx, b.rect.centery - b.vy,
                                          b.rect.centerx, b.rect.centery):
                            bullet_hit = True
                            break
                    if bullet_hit or barricade_blocks(b.rect.centerx, b.rect.centery):
                        b.kill()
                        spawn_explosion(b.rect.centerx, b.rect.centery, RED, 6, 3)

            # 敌弹命中玩家或我军大营
            for b in list(enemy_b):
                if not b.alive():
                    continue
                # 检查是否命中我军大营
                if player_camp.alive and player_camp.check_bullet_hit(b):
                    b.kill()
                    spawn_explosion(b.rect.centerx, b.rect.centery, BLUE, 10, 4)
                    play(SND_HURT)
                    if not player_camp.alive:
                        state = "gameover"  # 我军大营被攻破,失败!
                        ai_score += Hills.KILL_PLAYER_BONUS
                        DIRECTOR.save_evolution()
                        spawn_explosion(player_camp.x, player_camp.y, BLUE, 60, 12)
                        add_shake(20)
                        play(SND_EXP)
                        pygame.time.set_timer(pygame.USEREVENT + 9, 3000, loops=1)
                    continue
                if b.rect.colliderect(player.rect):
                    b.kill()
                    play(SND_HURT)
                    main._player_hit_this_frame = True  # 方阵战果统计用
                    _h_dir = DIRECTOR
                    if getattr(b, "firer", None) is not None and b.firer != 0:
                        _h_dir = (DIRECTOR_DUN if b.firer % 3 == 2
                                  else DIRECTOR_YUAN if b.firer % 3 == 1 else DIRECTOR)
                    _h_dir.note_hit(b.plan)  # 命中归因到子弹真实方案+归属指挥官
                    
                    # 记录战术命中（玩家被击中）
                    try:
                        if getattr(b, "plan", None):
                            from tactics_db import record_tactic
                            record_tactic(b.plan, hit=True)
                    except:
                        pass
                    
                    if player.take_damage(b.dmg):
                        state = "gameover"
                        ai_score += Hills.KILL_PLAYER_BONUS  # 击杀玩家奖励500分
                        DIRECTOR.save_evolution()  # 死亡也存档,保住本局进化成果
                        
                        # 记录军师进化
                        try:
                            from advisor_simple import record_battle_result
                            record_battle_result("lose", player.hp / player.max_hp, wave, killed)
                        except Exception as e:
                            print(f"[DEBUG] 军师进化记录失败: {e}")
                        
                        spawn_explosion(player.rect.centerx, player.rect.centery,
                                        GREEN, 40, 9)
                        add_shake(16)
                        play(SND_EXP)
                        # 自动重开: 3秒后回主菜单再自动开局(继承进化存档)
                        pygame.time.set_timer(pygame.USEREVENT + 9, 3000, loops=1)

            # 碰撞道具
            for p in list(powerups):
                if p.rect.colliderect(player.rect):
                    apply_powerup(p, player)
                    p.kill()

        # ---------- 绘制 ----------
        for _bc in barricades:
            _bc.draw(screen)  # 吕布烈璧障(红) — 注: 此处在shake层,fill后重画
        ox = oy = 0
        if screen_shake > 0:
            ox = random.randint(-screen_shake, screen_shake)
            oy = random.randint(-screen_shake, screen_shake)

        screen.fill(BLACK)
        for i in range(0, WIDTH, 40):
            for j in range(0, HEIGHT, 40):
                if (i // 40 + j // 40) % 2 == 0:
                    pygame.draw.rect(screen, BG2, (i, j, 40, 40))
        hills.draw(screen)  # 山地迷彩块(绿/黄随机)
        
        # ---- 大营绘制(敌军上中,我军下中) ----
        if state == "play":
            # 大营始终显示,波次<=3时显示为不可攻击(灰色)
            if wave <= 3:
                # 绘制未激活的大营(灰色)
                _ec_color = (100, 100, 100)
                pygame.draw.circle(screen, _ec_color, (int(enemy_camp.x), int(enemy_camp.y)), enemy_camp.radius, 2)
                _txt = FONT_SMALL.render(f"魏军大营(第{3+1}波激活)", True, _ec_color)
                screen.blit(_txt, _txt.get_rect(center=(enemy_camp.x, enemy_camp.y - enemy_camp.radius - 12)))
            else:
                enemy_camp.draw(screen)
            player_camp.draw(screen)
        
        # ---- 屏障绘制(必须在 fill 后,否则被背景覆盖): 曹操紫环 + 吕布红环 ----
        if boss_active is not None:
            for _bw in boss_active.walls:
                for _a in range(0, 181, 6):  # 赤壁: 朝吕布方向的半圆弧,紫色粗环
                    _ang = _bw.facing + math.radians(_a - 90)
                    _sx = _bw.x + math.cos(_ang) * _bw.RADIUS
                    _sy = _bw.y + math.sin(_ang) * _bw.RADIUS
                    pygame.draw.circle(screen, (160, 70, 230), (int(_sx), int(_sy)), 8)
                    pygame.draw.circle(screen, (220, 160, 255), (int(_sx), int(_sy)), 3)
        for _bc2 in getattr(main, "_barricades", []) or []:
            _bc2.draw(screen)  # 烈璧障(红)第二份,确保可见
        # AI总指挥奖励积分显示(右上,黄字)
        screen.blit(FONT.render(f"AI积分 {ai_score}", True, YELLOW), (WIDTH - 130, 6))

        def blit(sp, off=(0, 0)):
            r = sp.rect.copy()
            r.x += off[0]
            r.y += off[1]
            screen.blit(sp.image, r)

        if state == "play":
            for p in powerups:
                blit(p, (ox, oy))
            # 三国杀: 三将黄色光环(直接画screen,不被sprite裁剪) + 名字牌
            # 只显示存活的三将，避免死亡后留下空光环
            for _g in generals:
                if not getattr(_g, 'alive', True) or getattr(_g, 'down', False):
                    continue  # 跳过死亡的三将
                _gcx = _g.rect.centerx + ox
                _gcy = _g.rect.centery + oy
                _gr = _g.size // 2 + 6
                # 确保三将在屏幕范围内才绘制
                if -50 < _gcx < WIDTH + 50 and -50 < _gcy < HEIGHT + 50:
                    pygame.draw.circle(screen, (255, 230, 0), (int(_gcx), int(_gcy)), _gr, 3)
                    _halo2 = pygame.Surface((_gr * 2 + 10, _gr * 2 + 10), pygame.SRCALPHA)
                    pygame.draw.circle(_halo2, (255, 230, 0, 60),
                                       (_gr + 5, _gr + 5), _gr + 4, 7)
                    screen.blit(_halo2, (_gcx - _gr - 5, _gcy - _gr - 5))
                    try:
                        _gf = pygame.font.SysFont("notosanscjk,simhei,arial", 22, bold=True)
                        # 调试：打印gname值
                        _name_to_show = _g.gname if _g.gname else "???"
                        if _name_to_show == "???":
                            print(f"[DEBUG] General gname is empty! kind={_g.kind}, gname={_g.gname}", flush=True)
                        _gl = _gf.render(_name_to_show, True, (255, 230, 0))
                        screen.blit(_gl, _gl.get_rect(midbottom=(_gcx, _gcy - _gr - 2)))
                    except Exception as _e:
                        # 字体渲染失败时显示备用文字
                        try:
                            _gf2 = pygame.font.SysFont("arial", 20, bold=True)
                            _gl2 = _gf2.render("General", True, (255, 230, 0))
                            screen.blit(_gl2, _gl2.get_rect(midbottom=(_gcx, _gcy - _gr - 2)))
                        except:
                            pass
            for e in list(enemies):
                blit(e, (ox, oy))
                # 三国杀: 亲兵归属色小三角(头顶) — 红曹操/橙惇/黄渊
                _oc = {0: (255, 80, 80), 2: (255, 150, 40), 1: (255, 220, 60)}.get(
                    getattr(e, "num", 0) % 3)
                if _oc:
                    _ex, _ey = e.rect.centerx + ox, e.rect.top + oy - 6
                    pygame.draw.polygon(screen, _oc,
                                        [(_ex - 5, _ey - 5), (_ex + 5, _ey - 5), (_ex, _ey + 2)])
                draw_hp(e.rect.centerx + ox, e.rect.centery + oy,
                        e.hp, e.max_hp, e.color)
                # 头顶标签: 简洁显示，避免重叠和乱码
                # 根据num%3判断归属，与敌人分配逻辑一致
                _pre_map = {0: "曹", 1: "渊", 2: "惇"}
                _remainder = e.num % 3 if e.num is not None else 0
                _pre = _pre_map.get(_remainder, "?")
                # 确保_pre不为空
                if _pre == "?":
                    _pre = "曹"  # 默认归属曹操
                
                # 获取该敌人的指挥官
                _own = DIRECTOR
                if e.num != 0:
                    _own = (DIRECTOR_DUN if e.num % 3 == 2
                            else DIRECTOR_YUAN if e.num % 3 == 1 else DIRECTOR)
                od = _own.get_order(e.num) if _own else None
                
                # 只显示一个标签，优先级：方阵 > 方案 > 角色
                tag = None
                if getattr(e, "in_phalanx", False):
                    _plan = od.get('plan', '方阵') if od else '方阵'
                    # 截断长文本避免重叠
                    _plan = _plan[:4] if len(_plan) > 4 else _plan
                    tag = FONT_SMALL.render(f"{_pre}盾·{_plan}", True, YELLOW)
                elif od is not None:
                    _plan = od.get('plan', '协同')
                    # 截断长文本避免重叠
                    _plan = _plan[:4] if len(_plan) > 4 else _plan
                    tag = FONT_SMALL.render(f"{_pre}·{_plan}", True, CYAN)
                else:
                    role = COMM.roles.get(id(e))
                    if role:
                        # 截断长角色名
                        role = role[:4] if len(role) > 4 else role
                        tag = FONT_SMALL.render(f"{_pre}{role}", True, e.color)
                
                # 始终显示标签（显示编号确保可见）
                if tag is None:
                    # 没有标签时显示编号
                    tag = FONT_SMALL.render(f"{_pre}{e.num}", True, e.color)
                
                if tag:
                    # 调整位置避免与HP条和三角重叠
                    _tag_y = e.rect.top + oy - 22
                    screen.blit(tag, tag.get_rect(
                        center=(e.rect.centerx + ox, _tag_y)))
            blit(player, (ox, oy))
            draw_hp(player.rect.centerx + ox, player.rect.centery + oy,
                    player.hp, player.max_hp, GREEN)
            for b in all_b:
                r = b.rect.copy()
                r.x += ox
                r.y += oy
                screen.blit(b.image, r)
            # 护甲领域(半透明,画在地砖上、子弹下;这里提前画,子弹循环在上面盖)
            for z in armor_zones:
                r = z.rect.copy()
                r.x += ox
                r.y += oy
                screen.blit(z.image, r)
            for fx, fy, rad in flash:
                s = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
                pygame.draw.ellipse(s, (255, 240, 150, 180), (0, 0, rad * 2, rad * 2))
                screen.blit(s, (fx - rad + ox, fy - rad + oy))
            for part in particles:
                r = part.rect.copy()
                r.x += ox
                r.y += oy
                s = part.image.copy()
                s.set_alpha(int(255 * part.life / part.max_life))
                screen.blit(s, r)

            # 版本号显示(左上角) - 增加行间距避免重叠
            _y_offset = 6
            screen.blit(FONT_SMALL.render("v36.0", True, GRAY), (12, _y_offset))
            _y_offset += 18
            screen.blit(FONT.render(f"波次 {wave}", True, WHITE), (12, _y_offset))
            _y_offset += 24
            screen.blit(FONT.render(f"歼敌 {killed}/{total_to_spawn}",
                                    True, ORANGE), (12, _y_offset))
            _y_offset += 24
            screen.blit(FONT.render(f"分数 {score}", True, WHITE), (12, _y_offset))
            _y_offset += 24
            screen.blit(FONT.render(f"金币 {player.coins}", True, YELLOW), (12, _y_offset))
            # 右上角状态显示 - 调整位置避免重叠
            hp_col = GREEN if player.hp <= player.max_hp else GOLD
            hp_text = f"生命 {max(1, player.hp)}/{player.max_hp}"
            if player.hp > player.max_hp:
                hp_text += f" (+{player.hp - player.max_hp})"
            hp_surf = FONT.render(hp_text, True, hp_col)
            # 放在右上角，与AI积分错开
            screen.blit(hp_surf, (WIDTH - hp_surf.get_width() - 10, 10))
            
            # 操作提示放在左下角，避免与状态信息重叠
            hint_surf = FONT_SMALL.render("WASD移动 SPACE开火 ESC退出", True, GRAY)
            screen.blit(hint_surf, (10, HEIGHT - hint_surf.get_height() - 5))
            eff = []
            if player.rapid:
                eff.append("快速")
            if player.pierce:
                eff.append(f"穿透{player.pierce}")
            if player.dmg_mult > 1:
                eff.append(f"火力x{player.dmg_mult}")
            if eff:
                screen.blit(FONT.render(" | ".join(eff), True, CYAN),
                            (WIDTH // 2 - 120, 10))
            if boss_active is not None:
                t = BIGFONT.render("⚠ BOSS ⚠", True, RED)
                screen.blit(t, t.get_rect(center=(WIDTH // 2, 22)))
                draw_bar(WIDTH // 2 - 200, 42, 400, 12,
                         boss_active.hp / boss_active.max_hp, RED)

            # AI 指挥官状态条（屏幕右侧，从顶部往下排列，避免与左上角HUD重叠）
            # 魏军三帅 (敌方AI)
            _ai_panel_y = 140  # 从y=140开始，避开左上角的HUD
            screen.blit(FONT_SMALL.render("── 魏军三帅 ──", True, RED), (WIDTH - 120, _ai_panel_y))
            _ai_panel_y += 18
            
            _wei_servers = [
                ("曹操·主帅", DIRECTOR),
                ("夏侯惇·左翼", DIRECTOR_DUN),
                ("夏侯渊·右翼", DIRECTOR_YUAN),
            ]
            for _ai_name, _ai_dir in _wei_servers:
                _ai_st = _ai_dir.status() if _ai_dir else "未初始化"
                # 获取代数信息
                _gen = "?"
                if _ai_dir and hasattr(_ai_dir, 'generation'):
                    _gen = f"第{_ai_dir.generation}代"
                
                # 自检结果优先定色
                if _ai_dir and _ai_dir.health_ok is False:
                    _ai_col, _ai_mark = RED, "● "
                elif "离线" in _ai_st or "无法解析" in _ai_st:
                    _ai_col, _ai_mark = ((255, 160, 40)), "● "
                elif "高级调度" in _ai_st or "在线" in _ai_st or "自检✓" in _ai_st:
                    _ai_col, _ai_mark = GREEN, "● "
                else:
                    _ai_col, _ai_mark = GRAY, "● "
                
                _ai_tag = _ai_mark + _ai_name + f"({_gen})"
                _ai_label = FONT_SMALL.render(_ai_tag, True, _ai_col)
                _ai_lx = WIDTH - _ai_label.get_width() - 12
                _ai_bg = pygame.Surface((_ai_label.get_width() + 12, 18), pygame.SRCALPHA)
                _ai_bg.fill((10, 12, 16, 170))
                screen.blit(_ai_bg, (_ai_lx - 6, _ai_panel_y))
                screen.blit(_ai_label, (_ai_lx, _ai_panel_y))
                _ai_panel_y += 20
            
            # 吕布军师 (我方AI,敌对)
            _ai_panel_y += 5
            screen.blit(FONT_SMALL.render("── 我方军师 ──", True, GREEN), (WIDTH - 120, _ai_panel_y))
            _ai_panel_y += 18
            
            # 军师LLM单独检测
            _ai_st = "吕布军师·待命"
            _ai_col, _ai_mark = GRAY, "● "
            try:
                import urllib.request
                with urllib.request.urlopen("http://127.0.0.1:8083/health", timeout=2) as r:
                    if r.status == 200:
                        _ai_st = "吕布军师·在线"
                        _ai_col, _ai_mark = GREEN, "● "
            except:
                _ai_st = "吕布军师·离线"
                _ai_col, _ai_mark = RED, "● "
            
            # 获取军师代数
            _adv_gen = "?"
            try:
                from advisor_simple import load_advisor_evolution
                advisor_evo = load_advisor_evolution()
                if advisor_evo:
                    _adv_gen = f"第{advisor_evo.get('generation', 0)}代"
            except:
                pass
            
            _ai_tag = _ai_mark + "吕布军师" + f"({_adv_gen})"
            _ai_label = FONT_SMALL.render(_ai_tag, True, _ai_col)
            _ai_lx = WIDTH - _ai_label.get_width() - 12
            _ai_bg = pygame.Surface((_ai_label.get_width() + 12, 18), pygame.SRCALPHA)
            _ai_bg.fill((10, 12, 16, 170))
            screen.blit(_ai_bg, (_ai_lx - 6, _ai_panel_y))
            screen.blit(_ai_label, (_ai_lx, _ai_panel_y))

            # 通讯面板: 分开显示魏军频道和军师频道
            now_t = pygame.time.get_ticks() / 1000
            
            # 1. 魏军指挥频道(左中,红色) - 下移避免与左上角HUD重叠
            wei_logs = [lr for lr in COMM.log if lr[1].startswith("【魏军】") and now_t - lr[0] < 15][-5:]
            if wei_logs:
                wei_y = 160  # 从y=160开始，避开左上角HUD
                wei_panel = pygame.Surface((260, 18 * len(wei_logs) + 22), pygame.SRCALPHA)
                wei_panel.fill((20, 10, 10, 160))
                screen.blit(wei_panel, (10, wei_y))
                screen.blit(FONT_SMALL.render("── 魏军指挥频道 ──", True, RED), (18, wei_y + 4))
                for i, (tt, who, msg) in enumerate(wei_logs):
                    age = now_t - tt
                    alpha = max(100, 255 - int(age * 12))
                    line = FONT_SMALL.render(f"{who.replace('【魏军】', '')}: {msg}", True,
                                             (255, 160, 160, alpha))
                    screen.blit(line, (18, wei_y + 24 + i * 18))
            
            # 2. 军师频道(左中,绿色) - 使用小字体避免与敌军标签重叠
            adv_logs = [lr for lr in COMM.log if lr[1].startswith("【军师】") and now_t - lr[0] < 20][-8:]
            if adv_logs:
                adv_h = 16 * len(adv_logs) + 24
                adv_y = HEIGHT - adv_h - 100  # 提高100px,避免和输入框重叠
                adv_panel = pygame.Surface((320, adv_h), pygame.SRCALPHA)
                adv_panel.fill((10, 30, 10, 180))
                screen.blit(adv_panel, (10, adv_y))
                screen.blit(FONT_SMALL.render("── 军师频道 ──", True, GREEN), (18, adv_y + 4))
                for i, (tt, who, msg) in enumerate(adv_logs):
                    age = now_t - tt
                    alpha = max(100, 255 - int(age * 10))
                    # 使用FONT_SMALL与敌军标签一致
                    line = FONT_SMALL.render(f"{who.replace('【军师】', '')}: {msg}", True,
                                             (160, 255, 160, alpha))
                    screen.blit(line, (18, adv_y + 22 + i * 16))
            
            # 军师对话输入框(始终显示) - 提高并加大
            if ADV_CHANNEL:
                input_y = HEIGHT - 75  # 提高25px
                # 输入框背景
                input_bg = pygame.Surface((350, 45), pygame.SRCALPHA)
                input_bg.fill((30, 60, 30, 220))
                screen.blit(input_bg, (10, input_y))
                # 边框
                pygame.draw.rect(screen, GREEN, (10, input_y, 350, 45), 2)
                # 输入文字（使用小字体）
                input_text = FONT_SMALL.render(f"吕布: {ADV_CHANNEL.player_input_text}_", True, GREEN)
                screen.blit(input_text, (18, input_y + 12))
                # 操作提示
                hint = FONT_SMALL.render("[Enter]发送 [Esc]清除", True, (200, 200, 200))
                screen.blit(hint, (10, input_y - 16))
            
            # 3. 敌军战术频道(右中,红色) - 上移避免与军师输入框重叠
            recent = [lr for lr in COMM.log if not lr[1].startswith("【魏军】") and not lr[1].startswith("【军师】") and now_t - lr[0] < 10][-6:]
            if recent:
                panel_h = 18 * len(recent) + 22
                panel_y = HEIGHT - panel_h - 90  # 上移90px，避开军师输入框
                panel = pygame.Surface((250, panel_h), pygame.SRCALPHA)
                panel.fill((20, 10, 10, 160))
                screen.blit(panel, (WIDTH - 260, panel_y))
                screen.blit(FONT_SMALL.render("── 敌军战术频道 ──", True, RED),
                            (WIDTH - 250, panel_y + 4))
                for i, (tt, who, msg) in enumerate(recent):
                    age = now_t - tt
                    alpha = max(80, 255 - int(age * 18))
                    line = FONT_SMALL.render(f"[{who}] {msg}", True,
                                             (255, 160, 160, alpha))
                    screen.blit(line, (WIDTH - 250, panel_y + 24 + i * 18))

        elif state == "gameover":
            ov = pygame.Surface((WIDTH, HEIGHT))
            ov.set_alpha(170)
            ov.fill(BLACK)
            screen.blit(ov, (0, 0))
            # 判断是大营被攻破还是玩家死亡
            if player_camp and not player_camp.alive:
                t = BIGFONT.render("大营失守！我军败退！", True, RED)
                screen.blit(t, t.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 70)))
                screen.blit(FONT.render(f"我军大营被攻破！最终分数 {score} 到达波次 {wave}", True, WHITE),
                            (WIDTH // 2 - 180, HEIGHT // 2 - 20))
            else:
                t = BIGFONT.render("游戏结束", True, RED)
                screen.blit(t, t.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 50)))
                screen.blit(FONT.render(f"最终分数 {score} 到达波次 {wave}", True, WHITE),
                            (WIDTH // 2 - 140, HEIGHT // 2))
            
            # 显示AI学习总结
            _y_offset = HEIGHT // 2 + 40
            screen.blit(FONT_SMALL.render("── AI学习总结 ──", True, CYAN), (WIDTH // 2 - 60, _y_offset))
            _y_offset += 20
            
            # 获取三将的进化信息
            for _ai_name, _ai_dir in [("曹操", DIRECTOR), ("夏侯惇", DIRECTOR_DUN), ("夏侯渊", DIRECTOR_YUAN)]:
                if _ai_dir and hasattr(_ai_dir, 'generation') and hasattr(_ai_dir, 'lessons'):
                    _gen = _ai_dir.generation
                    _lessons = _ai_dir.lessons[-2:] if _ai_dir.lessons else []  # 最近2条教训
                    screen.blit(FONT_SMALL.render(f"{_ai_name}·第{_gen}代:", True, YELLOW), 
                               (WIDTH // 2 - 140, _y_offset))
                    _y_offset += 16
                    for _lesson in _lessons:
                        _lesson_text = _lesson[:40] + "..." if len(_lesson) > 40 else _lesson
                        screen.blit(FONT_SMALL.render(f"  • {_lesson_text}", True, GRAY), 
                                   (WIDTH // 2 - 130, _y_offset))
                        _y_offset += 16
            
            # 显示吕布军师学习总结(v36.0: 使用新的进化系统)
            try:
                if ADV_CHANNEL and hasattr(ADV_CHANNEL, 'generation'):
                    _y_offset += 10
                    screen.blit(FONT_SMALL.render("── 吕布军师总结 ──", True, GREEN), (WIDTH // 2 - 70, _y_offset))
                    _y_offset += 16
                    _adv_gen = ADV_CHANNEL.generation
                    _adv_lessons = ADV_CHANNEL.lessons[-2:] if ADV_CHANNEL.lessons else []
                    screen.blit(FONT_SMALL.render(f"军师·第{_adv_gen}代 | 建议{ADV_CHANNEL.stats.get('orders', 0)}次", True, GREEN), 
                               (WIDTH // 2 - 140, _y_offset))
                    _y_offset += 16
                    # 显示最近2条教训
                    for _lesson in _adv_lessons:
                        _lesson_text = _lesson[:40] + "..." if len(_lesson) > 40 else _lesson
                        screen.blit(FONT_SMALL.render(f"  • {_lesson_text}", True, GRAY), 
                                   (WIDTH // 2 - 130, _y_offset))
                        _y_offset += 16
            except Exception as e:
                print(f"[DEBUG] 军师总结显示失败: {e}")
            
            screen.blit(FONT.render("按 R 重来 ESC 退出", True, GRAY),
                        (WIDTH // 2 - 95, HEIGHT - 40))

        elif state == "win":
            ov = pygame.Surface((WIDTH, HEIGHT))
            ov.set_alpha(170)
            ov.fill(BLACK)
            screen.blit(ov, (0, 0))
            # 判断是攻破大营还是清完1000台
            if enemy_camp and not enemy_camp.alive:
                t = BIGFONT.render("大营攻破！我军胜利！", True, YELLOW)
                screen.blit(t, t.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 70)))
                screen.blit(FONT.render(f"敌军大营已摧毁！最终波次 {wave} 分数 {score}", True, WHITE),
                            (WIDTH // 2 - 160, HEIGHT // 2 - 20))
            else:
                t = BIGFONT.render("胜利！歼敌1000台！", True, YELLOW)
                screen.blit(t, t.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 50)))
                screen.blit(FONT.render(f"最终波次 {wave} 分数 {score}", True, WHITE),
                            (WIDTH // 2 - 110, HEIGHT // 2))
            
            # 显示AI学习总结
            _y_offset = HEIGHT // 2 + 40
            screen.blit(FONT_SMALL.render("── AI学习总结 ──", True, CYAN), (WIDTH // 2 - 60, _y_offset))
            _y_offset += 20
            
            # 获取三将的进化信息
            for _ai_name, _ai_dir in [("曹操", DIRECTOR), ("夏侯惇", DIRECTOR_DUN), ("夏侯渊", DIRECTOR_YUAN)]:
                if _ai_dir and hasattr(_ai_dir, 'generation') and hasattr(_ai_dir, 'lessons'):
                    _gen = _ai_dir.generation
                    _lessons = _ai_dir.lessons[-2:] if _ai_dir.lessons else []  # 最近2条教训
                    screen.blit(FONT_SMALL.render(f"{_ai_name}·第{_gen}代:", True, YELLOW), 
                               (WIDTH // 2 - 140, _y_offset))
                    _y_offset += 16
                    for _lesson in _lessons:
                        _lesson_text = _lesson[:40] + "..." if len(_lesson) > 40 else _lesson
                        screen.blit(FONT_SMALL.render(f"  • {_lesson_text}", True, GRAY), 
                                   (WIDTH // 2 - 130, _y_offset))
                        _y_offset += 16
            
            # 显示吕布军师学习总结(v36.0: 使用新的进化系统)
            try:
                if ADV_CHANNEL and hasattr(ADV_CHANNEL, 'generation'):
                    _y_offset += 10
                    screen.blit(FONT_SMALL.render("── 吕布军师总结 ──", True, GREEN), (WIDTH // 2 - 70, _y_offset))
                    _y_offset += 16
                    _adv_gen = ADV_CHANNEL.generation
                    _adv_lessons = ADV_CHANNEL.lessons[-2:] if ADV_CHANNEL.lessons else []
                    screen.blit(FONT_SMALL.render(f"军师·第{_adv_gen}代 | 建议{ADV_CHANNEL.stats.get('orders', 0)}次", True, GREEN), 
                               (WIDTH // 2 - 140, _y_offset))
                    _y_offset += 16
                    # 显示最近2条教训
                    for _lesson in _adv_lessons:
                        _lesson_text = _lesson[:40] + "..." if len(_lesson) > 40 else _lesson
                        screen.blit(FONT_SMALL.render(f"  • {_lesson_text}", True, GRAY), 
                                   (WIDTH // 2 - 130, _y_offset))
                        _y_offset += 16
            except Exception as e:
                print(f"[DEBUG] 军师总结显示失败: {e}")
            
            screen.blit(FONT.render("按 R 重来 ESC 退出", True, GRAY),
                        (WIDTH // 2 - 95, HEIGHT - 40))

        # --- 3D 渲染同步 ---
        if is_3d_enabled():
            try:
                # 合并所有子弹
                all_bullets = []
                if 'player_b' in dir():
                    all_bullets.extend(list(player_b))
                if 'enemy_b' in dir():
                    all_bullets.extend(list(enemy_b))
                if 'all_b' in dir():
                    all_bullets.extend(list(all_b))

                # 获取烈璧障
                _barricades = barricades if 'barricades' in dir() else []

                sync_frame(
                    player=player,
                    enemies=list(enemies) if enemies else [],
                    bullets=all_bullets,
                    barricades=_barricades,
                    generals=generals
                )
            except Exception as e:
                print(f"[3D] 同步错误: {e}")

        pygame.display.flip()
        clock.tick(FPS)

        # --- 战术进化系统: 实时评估战术效果（每12帧约0.2s执行一次，减轻开销） ---
        try:
            if telemetry_tick[0] % 12 == 0:  # 与fast_tick对齐，避免每帧调用
                from tactics_evolution import record_tactic, record_effect, get_diversity_info
                
                # 记录每个敌人的战术使用
                for e in enemies:
                    order = DIRECTOR.get_order(e.num) if DIRECTOR else None
                    if order:
                        plan = order.get("plan", "")
                        if plan:
                            record_tactic(plan, e.num)
                
                # 获取多样性信息
                div_info = get_diversity_info()
                if div_info["dominant_ratio"] > 0.5:
                    # 如果某个战术使用超过50%，发送警告
                    if COMM and pygame.time.get_ticks() % 110000 < 100:  # 每110秒一次
                        COMM.say("战术频道", 
                                 f"警告: {div_info['dominant_tactic']}使用{div_info['dominant_ratio']:.1%}，需要多样化！")
        except Exception as e:
            _swallow("evo_tick", e)  # v33.03留痕

        # --- 战场记录: 每秒记录完整战场状态到高速数据库 ---
        try:
            from battle_recorder import record_frame
            # 缓存波次供ai_update使用，避免每帧读取文件
            main._cached_wave = wave
            
            _game_state = {
                "player_x": player.rect.centerx,
                "player_y": player.rect.centery,
                "player_hp": player.hp,
                "player_max_hp": player.max_hp,
                "player_angle": player.turret if hasattr(player, 'turret') else 0,
                "killed": killed,
                "wave": wave,
                "game_time": pygame.time.get_ticks() / 1000.0,
                "enemies": [{
                    "id": e.num,
                    "x": e.rect.centerx,
                    "y": e.rect.centery,
                    "hp": e.hp,
                    "max_hp": e.max_hp,
                    "angle": e.turret if hasattr(e, 'turret') else 0,
                    "type": e.kind,
                    "plan": getattr(e, 'current_plan', '') or (DIRECTOR.orders.get(e.num) or {}).get("plan", ""),
                    "alive": e.alive()
                } for e in enemies],
                "player_bullets": [{
                    "x": b.rect.centerx,
                    "y": b.rect.centery,
                    "vx": b.vx,
                    "vy": b.vy
                } for b in player_b],
                "enemy_bullets": [{
                    "x": b.rect.centerx,
                    "y": b.rect.centery,
                    "vx": b.vx,
                    "vy": b.vy
                } for b in enemy_b],
                "enemy_camp": {
                    "x": enemy_camp.x,
                    "y": enemy_camp.y,
                    "hp": enemy_camp.hp,
                    "max_hp": enemy_camp.max_hp,
                    "alive": enemy_camp.alive
                } if enemy_camp.alive else None,
                "player_camp": {
                    "x": player_camp.x,
                    "y": player_camp.y,
                    "hp": player_camp.hp,
                    "max_hp": player_camp.max_hp,
                    "alive": player_camp.alive
                } if player_camp.alive else None
            }
            record_frame(_game_state)
        except Exception as e:
            _swallow("battle_record", e)  # v33.03留痕(原pass导致SQLite跨线程bug隐身数月)

        # --- 快遥测: 每帧更新内存缓存, 每30秒写入硬盘 ---
        # v33.0优化: 减少硬盘IO，先写内存，30秒同步一次
        fast_tick[0] += 1
        try:
            # 每帧更新内存中的快速状态
            if not hasattr(main, '_fast_cache'):
                main._fast_cache = {}
            main._fast_cache = {
                "ts": round(time.time() % 1000, 2),
                "player_x": player.rect.centerx,
                "player_y": player.rect.centery,
                "phalanx": sorted(e.num for e in enemies
                                  if getattr(e, "in_phalanx", False)),
                "boss_walls": ([{"x": w.x, "y": w.y, "facing": round(w.facing, 2),
                                 "r": w.RADIUS}
                                for w in boss_active.walls]
                               if boss_active is not None else []),
                "barricades": [{"x": b.x, "y": b.y, "facing": round(b.facing, 2),
                                "radius": b.RADIUS, "thick": b.THICK}
                               for b in barricades],
                "enemy_camp": {"x": enemy_camp.x, "y": enemy_camp.y, "hp": enemy_camp.hp, "alive": enemy_camp.alive} if enemy_camp.alive else None,
                "player_camp": {"x": player_camp.x, "y": player_camp.y, "hp": player_camp.hp, "alive": player_camp.alive},
                "enemies": ([{"id": 0, "x": boss_active.rect.centerx,
                              "y": boss_active.rect.centery,
                              "kind": "boss", "hp": boss_active.hp}
                             ] if boss_active is not None else []) +
                           [{"id": e.num, "x": e.rect.centerx,
                             "y": e.rect.centery,
                             "kind": e.kind, "hp": e.hp}
                            for e in enemies][:30],
            }
            # 自动截屏: 赤壁在场上时每20s存一张
            if boss_active is not None and boss_active.walls:
                if pygame.time.get_ticks() - getattr(main, "_last_shot", -99999) > 20000:
                    try:
                        pygame.image.save(screen, SCREENSHOT_FILE)
                        main._last_shot = pygame.time.get_ticks()
                    except Exception:
                        pass
            # v36.01b: 0.5s高频落盘（用户要求接近原设计0.2s的实时性）
            # 原设计:每12帧(0.2s)；v33改1800帧落盘；现在文件约2KB，高频写盘无压力
            if time.time() - getattr(main, '_last_fast_save', 0) >= 0.5:
                main._last_fast_save = time.time()
                def _save_fast():
                    try:
                        _ftmp = FAST_FILE + ".tmp"
                        with open(_ftmp, "w") as _ff:
                            json.dump(main._fast_cache, _ff)
                        os.replace(_ftmp, FAST_FILE)  # v36.01: 用模块级os（原_os在fast块之后才import，NameError被吞→遥测永不落盘）
                    except Exception as _e:
                        _swallow("telem_fast", _e)  # v33.03留痕
                threading.Thread(target=_save_fast, daemon=True).start()
        except Exception:
            pass

        # --- 运行状态上报:每帧更新内存,每30秒写入硬盘 ---
        # v33.0优化: 减少硬盘IO，先写内存，30秒同步一次
        telemetry_tick[0] += 1
        
        # v36.0 - 执行自检测
        if HAS_LOGGER:
            try:
                checker = get_checker()
                checker.game = main
                check_results = checker.check_all()
                if check_results:
                    logger = get_logger()
                    for check_name, check_data in check_results["checks"].items():
                        if check_data.get("status") != "ok":
                            logger.warning("SELF_CHECK", f"{check_name}: {check_data.get('status')}")
            except Exception as e:
                pass
        
        # 运行状态上报
        try:
            import os as _os
            _snap_enemies = [{
                "id": e.num, "kind": e.kind, "hp": e.hp,
                "x": e.rect.centerx, "y": e.rect.centery,
                "dist": round(math.hypot(player.rect.centerx - e.rect.centerx,
                                         player.rect.centery - e.rect.centery)),
                "plan": (DIRECTOR.get_order(e.num) or {}).get("plan", "")
            } for e in enemies]
            if boss_active is not None:
                _snap_enemies.append({
                    "id": 0, "kind": "boss", "hp": boss_active.hp,
                    "x": boss_active.rect.centerx, "y": boss_active.rect.centery,
                    "dist": round(math.hypot(player.rect.centerx - boss_active.rect.centerx,
                                             player.rect.centery - boss_active.rect.centery)),
                    "plan": "BOSS"})
            _tele = {
                    "ts": time.strftime("%H:%M:%S"),
                    "state": state, "wave": wave, "score": score,
                    "killed": killed, "spawned": spawned[0],
                    "enemies_onfield": len(enemies), "boss": boss_active is not None,
                    "player_hp": player.hp, "player_max_hp": player.max_hp,
                    "player_x": player.rect.centerx, "player_y": player.rect.centery,
                    "pilot": bool(_udp and (_ctl["dx"] or _ctl["dy"] or _ctl["fire"])),  # OpenClaw接管中
                    "barricades": len(barricades),
                    "barricade_list": [{"x": b.x, "y": b.y, "facing": round(b.facing, 2),
                                         "radius": b.RADIUS, "thick": b.THICK}
                                        for b in barricades],
                    "barricade_cd_s": max(0, round(30 - (pygame.time.get_ticks() - barricade_cd[0]) / 1000, 1)),
                    "enemy_camp": {"x": enemy_camp.x, "y": enemy_camp.y, "hp": enemy_camp.hp, "alive": enemy_camp.alive} if enemy_camp.alive else None,
                    "player_camp": {"x": player_camp.x, "y": player_camp.y, "hp": player_camp.hp, "alive": player_camp.alive},
                    "phalanx": sorted(e.num for e in enemies if getattr(e, "in_phalanx", False)),  # 方阵壁垒成员编号
                    "generals": [{"name": g.gname, "kind": g.kind, "hp": g.hp, "max_hp": g.max_hp,
                                  "x": g.rect.centerx, "y": g.rect.centery} for g in generals],
                    "fps": round(clock.get_fps(), 1),
                    "ai": {
                        "enabled": DIRECTOR.enabled,
                        "health_ok": DIRECTOR.health_ok,
                        "health_msg": DIRECTOR.health_msg,
                        "status": DIRECTOR.status(),
                        "latency": round(DIRECTOR.last_latency, 1),
                        "pending": DIRECTOR.pending,
                        "gen": DIRECTOR.generation,
                        "lessons": len(DIRECTOR.lessons),
                        "orders": len(DIRECTOR.orders),
                        "plan_stats": {k: v for k, v in list(DIRECTOR.plan_stats.items())[:5]},
                        "lieutenants": {
                            "夏侯惇": {"gen": DIRECTOR_DUN.generation,
                                      "status": DIRECTOR_DUN.status(),
                                      "orders": len(DIRECTOR_DUN.orders),
                                      "health_ok": DIRECTOR_DUN.health_ok,
                                      "plan_stats": {k: v for k, v in list(DIRECTOR_DUN.plan_stats.items())[:4]}},
                            "夏侯渊": {"gen": DIRECTOR_YUAN.generation,
                                      "status": DIRECTOR_YUAN.status(),
                                      "orders": len(DIRECTOR_YUAN.orders),
                                      "health_ok": DIRECTOR_YUAN.health_ok,
                                      "plan_stats": {k: v for k, v in list(DIRECTOR_YUAN.plan_stats.items())[:4]}},
                        },
                    },
                    "enemies": _snap_enemies[:12],
                }
            # 每帧更新内存缓存
            if not hasattr(main, '_slow_cache'):
                main._slow_cache = {}
            main._slow_cache = _tele
            
            # v36.01: 真实时间触发(15s) — 遥测接口必须存活，不能依赖FPS
            if time.time() - getattr(main, '_last_slow_save', 0) >= 15.0:
                main._last_slow_save = time.time()
                _slow_data = dict(_tele)  # 复制数据避免竞态
                def _save_slow():
                    try:
                        _tmp = SLOW_FILE + ".tmp"
                        with open(_tmp, "w") as f:
                            json.dump(_slow_data, f, ensure_ascii=False)
                        os.replace(_tmp, SLOW_FILE)  # v36.01: 统一用模块级os
                    except Exception as _e:
                        _swallow("telem_slow", _e)  # v33.03留痕
                threading.Thread(target=_save_slow, daemon=True).start()
        except Exception:
            pass  # 遥测绝不影响游戏


if __name__ == "__main__":
    main()
