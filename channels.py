# v36.0 (2026-10-05) — 36aigame
# 职责: 游戏内三套对话系统的类定义。实例由 main() 装配, COMM 通过构造注入。
import json
import math
import random
import re
import threading
import time
import urllib.request

import pygame  # v36.0: SquadComm.say 用 pygame.time.get_ticks

# 运行时上下文(由 main() 通过 set_communicator 注入; 保留模块级兜底读取)
_COMM = None
_DIRECTOR = None

def set_communicator(comm, director=None):
    """main() 创建 SquadComm / AIDirector 后调用, 供类方法内部使用"""
    global _COMM, _DIRECTOR
    _COMM = comm
    if director is not None:
        _DIRECTOR = director

# 默认军师端口(可在 env.sh 覆盖, 与主文件一致)
ADVISOR_PORT = 8083


class SquadComm:
    """敌坦之间共享玩家位置、分配围杀角色,并留下通讯记录。"""

    def __init__(self):
        self.roles = {}          # id(enemy) -> 角色名
        self.log = []            # [(秒, 说话人, 内容)]
        self._next = 0
        self._last_assign = -10.0  # 允许游戏一开始立即分配
        self.known_player = None  # 最新共享的玩家坐标

    def next_num(self):
        self._next += 1
        return self._next

    def say(self, who, msg):
        t = pygame.time.get_ticks() / 1000
        self.log.append((t, who, msg))
        if len(self.log) > 60:
            self.log.pop(0)
        # 同时输出到控制台，确保能看到通讯记录
        print(f"[{t:.1f}s] {who}: {msg}")

    def share_player(self, player):
        pos = (player.rect.centerx, player.rect.centery)
        if pos != self.known_player:
            self.known_player = pos
            self.say("频道", f"玩家位置更新 ({pos[0]},{pos[1]})")

    def assign(self, enemies, player):
        """每 5s 分配一次围杀角色:最近的直攻,其余两翼包抄,狙击风筝,残血后撤。"""
        now = pygame.time.get_ticks() / 1000
        if now - self._last_assign < 5.0:
            return
        self._last_assign = now
        self.share_player(player)
        px, py = player.rect.centerx, player.rect.centery
        liv = sorted(enemies,
                     key=lambda e: math.hypot(px - e.rect.centerx,
                                              py - e.rect.centery))
        flank = 0
        for i, e in enumerate(liv):
            # AI 指挥官接管的不参与规则分配
            if _DIRECTOR is not None and _DIRECTOR.get_order(e.num) is not None:
                continue
            if e.kind == "sniper":
                role = "风筝压制"
            elif e.hp <= max(1, e.max_hp // 3):
                role = "拉开距离"
            elif i == 0:
                role = "直攻"
            elif flank == 0:
                role = "左翼包抄"
                flank = 1
            else:
                role = "右翼包抄"
            if self.roles.get(id(e)) != role:
                self.roles[id(e)] = role
                self.say(f"{e.kind}#{e.num}", f"收到 → {role}")


# ============ 高级集群作战调度系统 ============

class WeiCommandChannel:
    """魏军指挥频道: 曹操→副将专用通讯"""
    
    def __init__(self):
        self.messages = []  # [(timestamp, sender, receiver, content)]
        self.last_coordination = 0
        self.COORD_INTERVAL = 12.0  # 协调间隔(秒)
        # v36.0: 类属性持最新实例,供 stratagem_llm 反向调用(避免循环导入)
        WeiCommandChannel.latest = self
        
    def send(self, sender, receiver, content):
        """发送命令到指定副将"""
        t = pygame.time.get_ticks() / 1000
        self.messages.append((t, sender, receiver, content))
        if len(self.messages) > 30:
            self.messages.pop(0)
        # 显示在魏军频道
        if _COMM:
            _COMM.say(f"【魏军】{sender}→{receiver}", content)
    
    def broadcast(self, sender, content):
        """曹操向所有副将广播命令"""
        for receiver in ["夏侯惇", "夏侯渊"]:
            if receiver != sender:
                self.send(sender, receiver, content)
    
    def should_coordinate(self):
        now = pygame.time.get_ticks() / 1000
        if now - self.last_coordination >= self.COORD_INTERVAL:
            self.last_coordination = now
            return True
        return False
    
    def coordinate_attack(self, directors):
        """曹操协调三帅攻击"""
        if not self.should_coordinate():
            return
        
        # 分析玩家状态
        player_weak = False
        for d in directors:
            if d and hasattr(d, 'battle_memory'):
                behavior = d.battle_memory.analyze_player_behavior()
                if behavior.get('aggression_level', 0.5) > 0.7:
                    player_weak = True
                    break
        
        # 根据战场态势选择不同的指令（使用36计和孙子兵法）
        import random
        
        # 获取当前战场信息
        import sys as _sys
        _main = _sys.modules.get('tank_battle_deluxe')
        wave = getattr(_main, '_cached_wave', 1)
        enemy_count = len([e for e in (getattr(_main, '_enemies', []) or []) if getattr(e, 'alive', False)])
        
        if player_weak:
            # 玩家势弱时 - 使用36计中的进攻计
            strategies = [
                "【36计·趁火打劫】敌已疲惫,全军突击,一举歼灭!",
                "【36计·声东击西】左翼佯攻,右翼包抄,中路突破!",
                "【36计·围魏救赵】分兵攻营,逼敌回防,半路截杀!",
                "【孙子兵法·兵势篇】全军集结,如转圆石于千仞之山,总攻!",
                "【36计·擒贼擒王】集火吕布,斩首行动,群龙无首!"
            ]
        else:
            # 玩家势强时 - 使用36计中的谋略计
            strategies = [
                "【36计·以逸待劳】全军固守,待敌疲惫,后发制人!",
                "【36计·借刀杀人】诱敌深入,借地形之险,以少胜多!",
                "【36计·暗度陈仓】明修栈道,暗度陈仓,奇兵突袭!",
                "【孙子兵法·虚实篇】攻其必救,围点打援,调动敌军!",
                "【36计·笑里藏刀】佯装败退,诱敌深入,伏兵四起!",
                "【孙子兵法·军争篇】以迂为直,以患为利,后发先至!",
                "【36计·调虎离山】佯攻大营,调虎离山,半路截杀!",
                "【36计·欲擒故纵】佯装败退,诱敌追击,反包围!"
            ]
        
        # 根据波次和战况添加特殊指令（使用36计和孙子兵法）
        if wave > 3 and enemy_count > 15:
            strategies.append("【36计·连环计】多计并用,环环相扣,使敌疲于应付!")
        
        if wave > 5:
            strategies.extend([
                "【36计·走为上】波次已深,暂避锋芒,保存实力,待时而动!",
                "【孙子兵法·九地篇】深入敌境,置之死地而后生,全力攻营!"
            ])
        
        if wave > 8:
            strategies.extend([
                "【孙子兵法·火攻篇】决战时刻,如火发上风,不可向迩,全军突击!",
                "【36计·苦肉计】诈降诱敌,里应外合,一举破敌!"
            ])
        
        if enemy_count < 10:
            strategies.append("【36计·美人计】示敌以弱,诱敌轻进,反戈一击!")
        
        # 随机选择一条指令
        self.broadcast("曹操", random.choice(strategies))



class AdvisorChannel:
    """军师频道: 军师↔吕布专用对话(接入真LLM)"""
    
    def __init__(self):
        self.messages = []  # [(timestamp, sender, content)]
        self.last_advice = 0
        self.ADVICE_INTERVAL = 8.0  # 建议间隔(秒)
        self.player_input_active = False  # 玩家输入状态
        self.player_input_text = ""  # 玩家输入内容
        self.llm_pending = False  # LLM请求中
        self.llm_reply_buffer = ""  # LLM回复缓冲
        self.use_llm = True  # 是否使用LLM(失败自动回退关键词)
        self.conversation_history = []  # 对话历史(给LLM上下文)
        
        # --- 军师进化系统(v36.0) ---
        self.generation = 0  # 进化代数
        self.lessons = []    # 教训库
        self.plan_stats = {  # 建议效果统计
            "进攻": {"issued": 0, "followed": 0, "success": 0},
            "防守": {"issued": 0, "followed": 0, "success": 0},
            "游击": {"issued": 0, "followed": 0, "success": 0},
            "集火预警": {"issued": 0, "followed": 0, "success": 0},
            "方阵预警": {"issued": 0, "followed": 0, "success": 0},
            "山地预警": {"issued": 0, "followed": 0, "success": 0},
        }
        self.last_plans = []  # 最近使用的建议类型
        self.stats = {"deaths": 0, "hits": 0, "orders": 0}  # 战果统计
        self.review_pending = False
        self.REVIEW_COOLDOWN = 120  # 进化冷却: 2分钟
        self._last_review = 0
        self.lock = threading.Lock()
        self.enabled = True
        
        # 启动时读取进化存档
        self._load_evolution()
        
    def say(self, sender, content):
        """军师或吕布发言"""
        t = pygame.time.get_ticks() / 1000
        self.messages.append((t, sender, content))
        if len(self.messages) > 20:
            self.messages.pop(0)
        # 显示在军师频道
        if _COMM:
            _COMM.say(f"【军师】{sender}", content)
    
    def _post_process_cmd(self, cmd, game_state):
        """v36.04: 后处理修正 - 边界检测和智能修正(增强版)"""
        if not game_state:
            return cmd
        
        player = game_state.get("player", {})
        px = player.get("x", 800)
        py = player.get("y", 500)
        
        dx = cmd.get("dx", 0)
        dy = cmd.get("dy", 0)
        
        # v36.04: 边界修正 - 如果靠近边界，强制离开边界
        MARGIN = 150  # 边界余量(增大到150)
        WIDTH = 1600
        HEIGHT = 1000
        
        # v36.05: 调试信息
        if px < MARGIN or px > WIDTH - MARGIN or py < MARGIN or py > HEIGHT - MARGIN:
            print(f"[DEBUG] 边界检测: 主公在({px},{py})，修正前指令: dx={dx}, dy={dy}")
        
        # X轴边界检测 - 如果贴边，强制向中心移动
        if px < MARGIN:
            dx = 0.8  # 强制向右
            print(f"[DEBUG] 边界修正: 主公在左侧(x={px})，强制向右 dx=0.8")
        elif px > WIDTH - MARGIN:
            dx = -0.8  # 强制向左
            print(f"[DEBUG] 边界修正: 主公在右侧(x={px})，强制向左 dx=-0.8")
        
        # Y轴边界检测 - 如果贴边，强制向中心移动
        if py < MARGIN:
            dy = 0.8  # 强制向下
            print(f"[DEBUG] 边界修正: 主公在上侧(y={py})，强制向下 dy=0.8")
        elif py > HEIGHT - MARGIN:
            dy = -0.8  # 强制向上
            print(f"[DEBUG] 边界修正: 主公在下侧(y={py})，强制向上 dy=-0.8")
        
        # v36.04: 如果同时在角落，优先向中心对角线移动
        if px < MARGIN and py < MARGIN:
            dx, dy = 0.7, 0.7  # 右下
            print(f"[DEBUG] 边界修正: 主公在左上角，强制向右下")
        elif px > WIDTH - MARGIN and py < MARGIN:
            dx, dy = -0.7, 0.7  # 左下
            print(f"[DEBUG] 边界修正: 主公在右上角，强制向左下")
        elif px < MARGIN and py > HEIGHT - MARGIN:
            dx, dy = 0.7, -0.7  # 右上
            print(f"[DEBUG] 边界修正: 主公在左下角，强制向右上")
        elif px > WIDTH - MARGIN and py > HEIGHT - MARGIN:
            dx, dy = -0.7, -0.7  # 左上
            print(f"[DEBUG] 边界修正: 主公在右下角，强制向左上")
        
        # 大营守护逻辑: 如果大营受威胁，强制回防
        player_camp = game_state.get("player_camp", {})
        if player_camp.get("alive"):
            camp_hp = player_camp.get("hp", 888)
            camp_x = player_camp.get("x", 800)
            camp_y = player_camp.get("y", 900)
            
            # v36.04: 降低触发阈值到50%，更积极回防
            if camp_hp < 450:
                dx_to_camp = camp_x - px
                dy_to_camp = camp_y - py
                dist = math.hypot(dx_to_camp, dy_to_camp)
                if dist > 0:
                    dx = dx_to_camp / dist
                    dy = dy_to_camp / dist
        
        # 更新cmd
        cmd["dx"] = round(dx, 2)
        cmd["dy"] = round(dy, 2)
        
        return cmd
    
    def should_advice(self):
        # v36.02: 每5秒读一次（原2s仍太频繁，军师建议权重低）
        # 降低频率 → 提高单条建议权重，让吕布有足够时间执行
        # 修复: 使用time.time()而非pygame.time.get_ticks()，避免初始值为0的问题
        import time as _time
        now = _time.time()
        # 首次调用或间隔超过5秒
        if self.last_advice == 0 or now - self.last_advice >= 5.0:
            self.last_advice = now
            return True
        return False
    
    def give_advice(self, player_hp, player_max, enemy_plan="", game_state=None):
        """军师给吕布提供战术建议(v36.0: 使用LLM生成控制指令)"""
        if not self.should_advice():
            return
        
        # v36.0: 从实时数据库读取完整战场态势
        if game_state is None:
            game_state = self._read_realtime_state()
        
        # 保存玩家位置用于回退逻辑
        if game_state and "player" in game_state:
            self._last_player_x = game_state["player"].get("x", 800)
            self._last_player_y = game_state["player"].get("y", 500)
        
        # 使用LLM生成建议（异步，不阻塞）
        if self.use_llm and not self.llm_pending:
            self._generate_llm_advice(player_hp, player_max, enemy_plan, game_state)
        else:
            # LLM不可用时的回退方案
            self._fallback_advice(player_hp, player_max, enemy_plan)
    
    def _read_realtime_state(self):
        """从HSDB读取战场态势(v36.0: 多线程异步读取)"""
        # 如果缓存数据在10秒内，直接返回缓存
        if hasattr(self, '_cached_game_state') and hasattr(self, '_cache_time'):
            if time.time() - self._cache_time < 10:  # 10秒缓存
                return self._cached_game_state
        
        # 启动后台线程读取HSDB
        def _read_hsdb_async():
            try:
                import json
                # v36.01: 改读小文件而不是30MB全量hsdb — 每次全量json.load是IO/CPU黑洞
                # 优先读慢遥测(含player/enemies/camps)，退而读快遥测
                import os
                data = None
                # v37.0: 运行时目录改为环境变量优先，兼容多副本部署(36/37aigame)
                import os as _env_os
                _rt = _env_os.environ.get("TANK_RUNTIME_DIR", "/tmp")
                for path in (f"{_rt}/tank_battle_status.json",
                             f"{_rt}/tank_fast.json"):
                    try:
                        with open(path, "r") as f:
                            raw = f.read()
                        if raw.startswith("#"):
                            nl = raw.find("\n")
                            raw = raw[nl+1:] if nl >= 0 else raw
                        data = json.loads(raw)
                        break
                    except (FileNotFoundError, json.JSONDecodeError, OSError):
                        continue
                if data:
                    self._cached_game_state = {
                        "player": {"x": data.get("player_x", 800), "y": data.get("player_y", 500),
                                   "hp": data.get("player_hp", 500), "max_hp": data.get("player_max_hp", 888)},
                        "enemies": data.get("enemies", []),
                        "bullets": [],
                        "camps": {"enemy": data.get("enemy_camp"), "player": data.get("player_camp")},
                        "events": [],
                        "frame": data.get("ts", 0),
                        "game_time": data.get("ts", 0),
                    }
                    self._cache_time = time.time()
            except Exception as e:
                print(f"[DEBUG] 异步读取HSDB失败: {e}")
        
        # 启动线程
        threading.Thread(target=_read_hsdb_async, daemon=True).start()
        
        # 立即返回快速状态（不阻塞）
        try:
            import json, os as _os2
            _rt2 = _os2.environ.get("TANK_RUNTIME_DIR", "/tmp")
            with open(f"{_rt2}/tank_fast.json", "r") as f:
                fast_data = json.load(f)
            with open(f"{_rt2}/tank_battle_status.json", "r") as f:
                status_data = json.load(f)
            
            return {
                "player": {
                    "x": fast_data.get("player_x", 0),
                    "y": fast_data.get("player_y", 0),
                    "hp": status_data.get("player_hp", 0),
                    "max_hp": status_data.get("player_max_hp", 0),
                },
                "enemies": fast_data.get("enemies", []),
                "player_camp": fast_data.get("player_camp", {}),
                "enemy_camp": fast_data.get("enemy_camp", {}),
                "wave": status_data.get("wave", 0),
                "killed": status_data.get("killed", 0),
                "score": status_data.get("score", 0),
            }
        except Exception as e:
            print(f"[DEBUG] 读取快速状态失败: {e}")
        return None
    
    def _generate_llm_advice(self, player_hp, player_max, enemy_plan, game_state=None):
        """使用LLM生成控制指令（v36.02: 军师直接控制吕布，绕过Pilot）"""
        # v36.02: 防止llm_pending卡住，设置超时保护
        if self.llm_pending:
            # 检查上次请求是否超过30秒，如果是则重置
            if hasattr(self, '_llm_start_time') and time.time() - self._llm_start_time > 30:
                print("[DEBUG] 军师LLM请求超时，强制重置")
                self.llm_pending = False
            else:
                return  # 已有请求在处理中，跳过
        
        self.llm_pending = True
        self._llm_start_time = time.time()
        
        def worker():
            try:
                hp_ratio = player_hp / player_max
                
                # v36.0: 构建完整战场态势
                situation = []
                if hp_ratio < 0.25:
                    situation.append("主公血量危急（<25%）")
                elif hp_ratio < 0.5:
                    situation.append("主公血量偏低（<50%）")
                elif hp_ratio > 0.8:
                    situation.append("主公血量充沛（>80%）")
                
                if "集火" in enemy_plan:
                    situation.append("敌军正在集火")
                elif "方阵" in enemy_plan:
                    situation.append("敌军结方阵推进")
                elif "山地" in enemy_plan:
                    situation.append("敌军欲占高地")
                elif "游击" in enemy_plan:
                    situation.append("敌军游击袭扰")
                
                # 添加实时战场信息
                if game_state:
                    player_pos = game_state.get("player", {})
                    enemies = game_state.get("enemies", [])
                    player_camp = game_state.get("player_camp", {})
                    enemy_camp = game_state.get("enemy_camp", {})
                    
                    situation.append(f"主公位置({player_pos.get('x',0)},{player_pos.get('y',0)})")
                    situation.append(f"敌军{len(enemies)}台")
                    
                    if player_camp.get("alive"):
                        situation.append(f"我方大营HP{player_camp.get('hp',0)}")
                    if enemy_camp.get("alive"):
                        situation.append(f"敌方大营HP{enemy_camp.get('hp',0)}")
                    
                    # 添加最近敌人信息
                    if enemies:
                        nearest = min(enemies, key=lambda e: math.hypot(
                            e.get("x",0) - player_pos.get("x",0),
                            e.get("y",0) - player_pos.get("y",0)
                        ))
                        situation.append(f"最近敌人在({nearest.get('x',0)},{nearest.get('y',0)})")
                
                situation_text = "；".join(situation) if situation else "战况平稳"
                
                # v36.02: 军师直接控制吕布，绕过Pilot决策
                # 关键改进: 军师输出的是【强制命令】，不是建议
                system_prompt = (
                    "你是吕布的军师，三国时期的顶级谋士。你直接控制吕布的战斗行动。"
                    "【重要】你的指令是强制命令，吕布必须严格执行！"
                    "\n【控制指令格式】"
                    "\n{"
                    "\n  \"dx\": 0.0,  // X方向移动: -1.0(左) 到 1.0(右)"
                    "\n  \"dy\": 0.0,  // Y方向移动: -1.0(上) 到 1.0(下)"
                    "\n  \"fire\": true,  // 是否开火: true/false"
                    "\n  \"mx\": 800,  // 瞄准X坐标(必须设置，指向敌人位置)"
                    "\n  \"my\": 400,  // 瞄准Y坐标(必须设置，指向敌人位置)"
                    "\n  \"skill\": false  // 是否释放烈璧障: true/false (CD 30秒，同屏最多3个)"
                    "\n}"
                    "\n【坐标系说明 - 必须严格遵守】"
                    "\n- 游戏画面: 1600x1000像素"
                    "\n- 左上角: (0,0)，右下角: (1600,1000)"
                    "\n- X轴: 0=最左, 1600=最右"
                    "\n- Y轴: 0=最上, 1000=最下"
                    "\n- 我方大本营: (800,900) 在底部中间"
                    "\n- 敌方大本营: (800,100) 在顶部中间"
                    "\n- 玩家出生: (800,940) 在底部"
                    "\n- 敌人出生: y=60~500 在上半部分"
                    "\n【瞄准规则 - 必须遵守】"
                    "\n1. mx,my必须设置为最近敌人的坐标"
                    "\n2. 敌人在上方(y<500)，my应该小于500"
                    "\n3. 敌人在下方(y>500)，my应该大于500"
                    "\n4. 敌人在左边(x<800)，mx应该小于800"
                    "\n5. 敌人在右边(x>800)，mx应该大于800"
                    "\n【战略目标 - 优先级从高到低】"
                    "\n1. 【最高优先】守护我方大本营(800,900)！绝不能让敌人攻破！"
                    "\n2. 【第二优先】寻找机会打击敌人大本营(800,100)！"
                    "\n3. 【第三优先】保全自己的性命，血量低时撤退回大本营(800,900)回血"
                    "\n4. 【第四优先】打击敌人，但不要浪费子弹"
                    "\n5. 【第五优先】节约用弹，精准射击，不要无脑开火"
                    "\n【具体目标】"
                    "\n- 目标1: 我方大本营位置(800,900)在底部中间，必须守护"
                    "\n- 目标2: 敌方大本营位置(800,100)在顶部中间，寻找机会攻击"
                    "\n- 目标3: 自己当前位置，血量低时必须回(800,900)附近回血(靠近大本营自动+2HP/帧)"
                    "\n- 目标4: 最近敌人位置，精准打击"
                    "\n- 目标5: 子弹数量控制，不要浪费弹药"
                    "\n【烈璧障使用规则】"
                    "\n- 烈璧障是半圆环屏障，可以阻挡敌军和敌弹"
                    "\n- 当敌军接近主公(<200px)或主公被围攻时，必须释放烈璧障！"
                    "\n- 当主公HP低于50%时，建议释放烈璧障保护"
                    "\n- 烈璧障CD 30秒，同屏最多3个，合理使用"
                    "\n- 释放烈璧障时，将skill设为true"
                    "\n【战斗原则】"
                    "\n- 绝对不要躲在角落！要主动进攻！"
                    "\n- 不瞄准不射击，每发子弹都要有目标"
                    "\n- 优先保护大本营，其次才是击杀敌人"
                    "\n- 血量低于30%必须撤退到大本营(800,900)附近回血(靠近自动+2HP/帧)"
                    "\n- 敌人少时进攻，敌人多时游击"
                    "\n- 大本营受到威胁时，立即回防(800,900)"
                    "\n- 有机会时偷袭敌人大本营(800,100)"
                    "\n- 主动进攻，击杀敌人，不要躲藏"
                    "\n【强制命令规则】"
                    "\n- 你的指令是强制性的，吕布必须执行"
                    "\n- 不要给出矛盾指令，一次只执行一个明确目标"
                    "\n- 指令必须精确，dx/dy值要足够大(至少0.5)才能产生明显移动"
                    "\n- 紧急情况下必须释放烈璧障(skill: true)"
                    "\n只输出JSON，不要其他文字。"
                )
                
                # v36.04: 增强提示词，明确告诉LLM当前精确位置和边界情况
                player = game_state.get("player", {}) if game_state else {}
                px = player.get("x", 800)
                py = player.get("y", 500)
                
                boundary_info = []
                if px < 150:
                    boundary_info.append(f"紧急：主公已在地图最左侧(x={px})，必须立即向右移动！dx必须是正数！")
                elif px > 1450:
                    boundary_info.append(f"紧急：主公已在地图最右侧(x={px})，必须立即向左移动！dx必须是负数！")
                
                if py < 150:
                    boundary_info.append(f"紧急：主公已在地图最上方(y={py})，必须立即向下移动！dy必须是正数！")
                elif py > 850:
                    boundary_info.append(f"紧急：主公已在地图最下方(y={py})，必须立即向上移动！dy必须是负数！")
                
                # v36.04: 添加中心区域引导
                center_info = ""
                if 400 < px < 1200 and 300 < py < 700:
                    center_info = "主公在中心区域，这是最佳战斗位置，保持在此区域游击。"
                else:
                    center_info = "建议向中心区域(800,500)移动，不要靠近边界。"
                
                boundary_text = "\n".join(boundary_info) if boundary_info else center_info
                
                # v39.0: 检查是否需要烈璧障
                need_barricade = False
                if game_state:
                    enemies_list = game_state.get("enemies", [])
                    for e in enemies_list:
                        ex, ey = e.get("x", 0), e.get("y", 0)
                        if math.hypot(ex - px, ey - py) < 200:
                            need_barricade = True
                            break
                
                barricade_hint = ""
                if need_barricade:
                    barricade_hint = "【紧急】敌军接近主公！必须释放烈璧障(skill: true)！"
                elif hp_ratio < 0.5:
                    barricade_hint = "【建议】主公血量偏低，建议释放烈璧障(skill: true)保护。"
                
                user_prompt = (
                    f"当前战场态势：{situation_text}。\n"
                    f"主公精确位置：({px}, {py})\n"
                    f"{boundary_text}\n"
                    f"{barricade_hint}\n"
                    f"【重要规则】\n"
                    f"1. 绝对不要靠近地图边界！保持与边界至少150像素距离！\n"
                    f"2. 最佳战斗位置是中心区域(800,500)附近\n"
                    f"3. 如果靠近边界，必须立即向中心移动！\n"
                    f"4. 敌军接近时，必须释放烈璧障(skill: true)！\n"
                    f"请根据以上信息给出控制指令。"
                )
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
                
                body = json.dumps({
                    "messages": messages,
                    "max_tokens": 64,  # v36.02: 减少token数，加快响应
                    "temperature": 0.3,  # v36.02: 降低随机性，提高确定性
                    "chat_template_kwargs": {"enable_thinking": False},
                }).encode("utf-8")
                
                req = urllib.request.Request(
                    "http://127.0.0.1:8083/v1/chat/completions",
                    data=body, headers={"Content-Type": "application/json"})
                
                with urllib.request.urlopen(req, timeout=20) as resp:  # v36.02: 延长超时到20秒
                    data = json.loads(resp.read().decode("utf-8"))
                
                msg = data["choices"][0]["message"]
                text = msg.get("content", "").strip()
                
                # 解析JSON控制指令 (v36.0: 支持Markdown代码块)
                import re
                # 先尝试提取Markdown代码块
                markdown_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
                if markdown_match:
                    json_text = markdown_match.group(1)
                else:
                    # 回退到普通JSON匹配
                    json_match = re.search(r'\{.*\}', text, re.DOTALL)
                    if json_match:
                        json_text = json_match.group(0)
                    else:
                        json_text = None
                
                if json_text:
                    try:
                        cmd = json.loads(json_text)
                        print(f"[DEBUG] 军师LLM返回: {cmd}")
                        # 确保cmd是字典
                        if isinstance(cmd, dict):
                            # v36.03: 后处理修正 - 边界检测和智能修正
                            cmd = self._post_process_cmd(cmd, game_state)
                            self.last_cmd = cmd  # 保存控制指令
                            # 显示军师建议
                            skill_str = " 烈璧障!" if cmd.get('skill') else ""
                            advice = f"移动({cmd.get('dx',0):.1f},{cmd.get('dy',0):.1f}) 开火:{cmd.get('fire',False)}{skill_str}"
                            self.say("军师", advice)
                            self.record_advice("智能控制")
                        else:
                            print(f"[DEBUG] 军师LLM返回的不是字典: {type(cmd)}")
                            self._fallback_advice(player_hp, player_max, enemy_plan)
                    except Exception as e:
                        print(f"[DEBUG] 军师LLM JSON解析失败: {e}")
                        self._fallback_advice(player_hp, player_max, enemy_plan)
                else:
                    print(f"[DEBUG] 军师LLM没有返回JSON: {text[:50]}")
                    self._fallback_advice(player_hp, player_max, enemy_plan)
                    
            except Exception as e:
                print(f"[DEBUG] 军师LLM控制生成失败: {e}")
                # v36.02: LLM失败时不调用fallback，保持上次的有效指令
                # 避免fallback覆盖好的指令
                if not hasattr(self, 'last_cmd') or self.last_cmd is None:
                    self._fallback_advice(player_hp, player_max, enemy_plan)
            finally:
                self.llm_pending = False
                self._llm_start_time = 0
        
        threading.Thread(target=worker, daemon=True).start()
    
    def _fallback_advice(self, player_hp, player_max, enemy_plan):
        """LLM失败时的回退建议（硬编码规则）v36.05: 添加边界修正"""
        hp_ratio = player_hp / player_max
        advice_type = ""
        advice_text = ""
        
        # v36.0: 根据血量状态生成控制指令，计算回大本营方向
        # 获取当前位置（从游戏状态）
        player_x = getattr(self, '_last_player_x', 800)
        player_y = getattr(self, '_last_player_y', 500)
        
        # 计算回大本营(800,900)的方向
        dx_to_camp = 800 - player_x
        dy_to_camp = 900 - player_y
        dist = math.hypot(dx_to_camp, dy_to_camp)
        
        if dist > 0:
            dx = dx_to_camp / dist  # 归一化
            dy = dy_to_camp / dist
        else:
            dx, dy = 0, 0
        
        if hp_ratio < 0.25:
            advice_type = "防守"
            advice_text = "主公! 血量危急,速回大本营(800,900)回血!"
            # 直接向大本营移动
            self.last_cmd = {"dx": dx, "dy": dy, "fire": False, "mx": 800, "my": 900}
        elif hp_ratio < 0.5:
            advice_type = "游击"
            advice_text = "主公, 建议向大本营方向游击!"
            # 向大本营方向移动，同时攻击
            self.last_cmd = {"dx": dx * 0.5, "dy": dy * 0.5, "fire": True, "mx": 800, "my": 500}
        else:
            advice_type = "进攻"
            advice_text = "主公神勇! 主动出击!"
            # 向上进攻（敌人通常在上方）
            self.last_cmd = {"dx": 0, "dy": -0.5, "fire": True, "mx": 800, "my": 300}
        
        # v36.05: fallback也进行边界修正
        self.last_cmd = self._post_process_cmd(self.last_cmd, {
            "player": {"x": player_x, "y": player_y}
        })
        
        if advice_text:
            self.say("军师", advice_text)
            self.record_advice(advice_type)
        
        # 分析敌军动向
        if "集火" in enemy_plan:
            self.say("军师", "报! 侦测到敌军集火意图,主公请分散走位,不可停留!")
            self.record_advice("集火预警")
        elif "方阵" in enemy_plan:
            self.say("军师", "报! 敌军结方阵而进,主公可从侧翼迂回,避其锋芒!")
            self.record_advice("方阵预警")
        elif "山地" in enemy_plan:
            self.say("军师", "报! 敌军欲占山为营,主公宜速夺高地,不可让其得逞!")
            self.record_advice("山地预警")
        
        # v32.4: 添加击杀提示和奖励
        if hp_ratio > 0.8 and enemy_plan == "":
            self.say("军师", "主公威武! 可趁势追击,扩大战果!击杀有奖励!")
            self.record_advice("追击")
        
        # 击杀奖励：鼓励主动进攻
        if hp_ratio > 0.5:
            self.say("军师", "主公，主动进攻可获积分奖励！不要躲在角落！")
            self.record_advice("进攻奖励")
    
    def player_response(self, action):
        """吕布回应军师"""
        responses = {
            "attack": "吕布: 军师放心,某去去就回!",
            "retreat": "吕布: 哼,暂且退避,待某恢复再战!",
            "hold": "吕布: 某自有分寸,军师不必多言!",
        }
        if action in responses:
            self.say("吕布", responses[action])
    
    def player_chat(self, text):
        """玩家输入文字与军师对话"""
        if not text.strip():
            return
        self.say("吕布", text)
        # 记录到对话历史
        self.conversation_history.append({"role": "user", "content": text})
        if len(self.conversation_history) > 10:
            self.conversation_history.pop(0)
        
        # 军师回复: 优先LLM,异步不阻塞
        if self.use_llm and not self.llm_pending:
            self._ask_llm(text)
        else:
            # LLM忙或禁用: 回退关键词
            reply = self._keyword_reply(text)
            if reply:
                self.say("军师", reply)
    
    def _keyword_reply(self, player_text):
        """关键词回退回复(LLM失败时用)"""
        text = player_text.lower()
        if any(k in text for k in ["攻", "打", "冲", "杀"]):
            return "主公勇猛! 但需留意敌军阵型,不可孤军深入!"
        elif any(k in text for k in ["退", "跑", "逃", "撤"]):
            return "主公明智! 留得青山在,不怕没柴烧!"
        elif any(k in text for k in ["血", "伤", "死", "活"]):
            return "主公保重! 某已备好伤药,随时可补给!"
        elif any(k in text for k in ["曹", "敌", "军", "兵"]):
            return "曹操老贼诡计多端,主公需防其埋伏!"
        elif any(k in text for k in ["计", "策", "谋", "略"]):
            return "某有一计: 待敌军集结时,主公可绕后突袭!"
        elif any(k in text for k in ["谢", "好", "恩", "妙"]):
            return "为主公效力,某之荣幸!"
        elif any(k in text for k in ["?", "？", "吗", "何"]):
            return "主公所问,某正在思量..."
        else:
            return "主公所言极是,某谨记在心!"
    
    # --- 军师进化系统方法(v36.0) ---
    def _load_evolution(self):
        """加载军师进化存档"""
        try:
            import os
            path = "/tmp/advisor_evolution.json"
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.generation = data.get("generation", 0)
                self.lessons = data.get("lessons", [])
                self.plan_stats = data.get("plan_stats", self.plan_stats)
                print(f"[军师] 加载进化存档: 第{self.generation}代, {len(self.lessons)}条教训")
        except Exception as e:
            print(f"[军师] 加载进化存档失败: {e}")
    
    def _save_evolution(self):
        """保存军师进化存档"""
        try:
            data = {
                "generation": self.generation,
                "lessons": self.lessons,
                "plan_stats": self.plan_stats,
                "timestamp": time.time()
            }
            with open("/tmp/advisor_evolution.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[军师] 保存进化存档失败: {e}")
    
    def record_advice(self, advice_type, player_followed=False, success=False):
        """记录建议效果"""
        if advice_type in self.plan_stats:
            self.plan_stats[advice_type]["issued"] += 1
            if player_followed:
                self.plan_stats[advice_type]["followed"] += 1
            if success:
                self.plan_stats[advice_type]["success"] += 1
        self.last_plans.append(advice_type)
        if len(self.last_plans) > 10:
            self.last_plans.pop(0)
        self.stats["orders"] += 1
    
    def record_hit(self):
        """记录玩家受击"""
        self.stats["hits"] += 1
    
    def record_death(self):
        """记录玩家死亡"""
        self.stats["deaths"] += 1
    
    def request_review_async(self, wave, player_hp, player_max):
        """波次结束进化: 保留有效教训, 剔除无效战术"""
        if not self.enabled or self.review_pending:
            return
        if time.time() - self._last_review < self.REVIEW_COOLDOWN:
            return
        with self.lock:
            if self.stats["deaths"] == 0 and self.stats["hits"] == 0:
                return
            st = dict(self.stats)
            plans = list(self.last_plans)
            lessons = list(self.lessons)
            gen = self.generation
            genealogy = {k: dict(v) for k, v in self.plan_stats.items()}
            self.stats = {"deaths": 0, "hits": 0, "orders": 0}
            self.last_plans = []
        self.review_pending = True
        
        def worker():
            try:
                old = "\n".join(f"{i+1}) {l}" for i, l in enumerate(lessons)) or "（无，初创代）"
                pl = " → ".join(plans) if plans else "（未发出建议）"
                gene = "\n".join(
                    f"- {name}: 建议{ps['issued']}次, 玩家听从{ps['followed']}次, 成功{ps['success']}次"
                    for name, ps in genealogy.items() if ps['issued'] > 0) or "（无）"
                
                prompt = (
                    f"你是军师AI，正在进化你的战术建议体系(当前第{gen}代)。\n"
                    f"第{wave}波建议序列: {pl}\n"
                    f"本波: 玩家死亡{st['deaths']}次, 受击{st['hits']}次, 建议{st['orders']}次\n"
                    f"玩家余HP{player_hp}/{player_max}\n"
                    f"建议谱系(跨波累积):\n{gene}\n"
                    f"\n现役教训(第{gen}代):\n{old}\n"
                    "进化规则: 被战果验证有效的教训保留(可精炼原文);"
                    "无效的改写或剔除; 针对暴露的漏洞补充新教训。"
                    "最多5条。只输出JSON: {\"lessons\":[\"教训1\",...]}"
                )
                body = json.dumps({
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800, "temperature": 0.5,
                    "chat_template_kwargs": {"enable_thinking": False},
                }).encode("utf-8")
                req = urllib.request.Request(
                    "http://127.0.0.1:8083/v1/chat/completions",
                    data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                msg = data["choices"][0]["message"]
                text = msg.get("content", "") or msg.get("reasoning_content", "") or ""
                new_lessons = []
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    try:
                        obj = json.loads(m.group(0))
                        for l in obj.get("lessons", []):
                            l = str(l).strip()[:60]
                            if l:
                                new_lessons.append(l)
                    except Exception:
                        pass
                
                with self.lock:
                    if new_lessons:
                        self.lessons = new_lessons[:5]
                        self.generation += 1
                        self._save_evolution()
                        print(f"🎉 军师进化到第{self.generation}代!")
                        for lesson in self.lessons:
                            print(f"  📜 {lesson}")
                    else:
                        print("[DEBUG] 军师进化失败, 维持现役教训")
            except Exception as e:
                print(f"[DEBUG] 军师进化失败: {e}")
            finally:
                self.review_pending = False
                self._last_review = time.time()
        
        threading.Thread(target=worker, daemon=True).start()
    
    def _ask_llm(self, player_text):
        """异步调用LLM生成军师回复"""
        self.llm_pending = True
        
        def worker():
            try:
                # 构建prompt: 军师角色设定 + 对话历史 + 当前输入
                system_prompt = (
                    "你是吕布的军师，三国时期的谋士。你正在一个坦克大战游戏中为吕布提供战术建议。"
                    "吕布是玩家，你是他的AI军师。请用古风中文回复，语气要恭敬但要有谋略。"
                    "回复要简短(30字以内)，适合游戏内快速阅读。"
                )
                messages = [{"role": "system", "content": system_prompt}]
                # 加最近对话历史
                for msg in self.conversation_history[-6:]:
                    messages.append(msg)
                
                body = json.dumps({
                    "messages": messages,
                    "max_tokens": 64,
                    "temperature": 0.8,
                    "chat_template_kwargs": {"enable_thinking": False},
                }).encode("utf-8")
                
                req = urllib.request.Request(
                    f"http://127.0.0.1:{ADVISOR_PORT}/v1/chat/completions",
                    data=body, headers={"Content-Type": "application/json"}
                )
                
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                
                msg = data["choices"][0]["message"]
                reply = msg.get("content", "") or msg.get("reasoning_content", "")
                reply = reply.strip().replace("\n", " ")[:40]  # 限制长度
                
                if reply:
                    self.llm_reply_buffer = reply
                    self.conversation_history.append({"role": "assistant", "content": reply})
                else:
                    self.llm_reply_buffer = self._keyword_reply(player_text)
                    
            except Exception as e:
                # LLM失败: 回退关键词,标记不用LLM(下次再试)
                self.llm_reply_buffer = self._keyword_reply(player_text)
                self.use_llm = False  # 临时禁用,下次再试
            finally:
                self.llm_pending = False
        
        threading.Thread(target=worker, daemon=True).start()
    
    def update(self):
        """每帧调用: 检查LLM回复是否就绪"""
        if self.llm_reply_buffer:
            self.say("军师", self.llm_reply_buffer)
            self.llm_reply_buffer = ""
            # LLM成功过一次,恢复使用
            self.use_llm = True
    
    def toggle_input(self):
        """切换输入状态"""
        self.player_input_active = not self.player_input_active
        if not self.player_input_active:
            self.player_input_text = ""
        return self.player_input_active


