# v36.0 (2026-10-05) — 36aigame
# 版本: v16.0 (2025-10-03)
#!/usr/bin/env python3
# OpenClaw 接管玩家坦克 v16.0
# 版本: v16.0 (2025-10-03)
# 更新: 配合高级集群作战调度系统
# 功能: 推挤场 + 墙壁排斥 + 绕桩走位,防叠顶钉死
import json, math, socket, time, sys
import os, re, threading
import urllib.request  # v36.0: 提升到模块级,修复 laya_ask_skill 运行时 NameError

UDP_HOST = os.environ.get("TANK_UDP_HOST", "127.0.0.1")
UDP_PORT = int(os.environ.get("TANK_UDP_PORT", 8089))
_RUNTIME = os.environ.get("TANK_RUNTIME_DIR", "/tmp")
FAST_FILE = os.path.join(_RUNTIME, "tank_fast.json")            # 快遥测(0.2s): 方阵/玩家坐标/敌坐标
SLOW_FILE = os.path.join(_RUNTIME, "tank_battle_status.json")  # 慢遥测(2s): 波次/HP/AI状态

UDP = (UDP_HOST, UDP_PORT)
BOSS_LAST = [None, None]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

W, H = 900, 640
BULLET_SPEED = 9.0  # 玩家弹速 px/帧

# 上帧敌坦位置(提前量差分用): id -> (x, y)
_prev_pos = {}
_prev_ts = [None]

def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

def read_status():
    """慢遥测兜底,快遥测优先(坐标/方阵新鲜,其余字段从慢遥测补)。"""
    slow = read_json(SLOW_FILE)
    fast = read_json(FAST_FILE)
    if fast and slow and fast.get("ts"):
        st = dict(slow)
        st["player_x"] = fast.get("player_x", slow.get("player_x"))
        st["player_y"] = fast.get("player_y", slow.get("player_y"))
        st["enemies"] = fast.get("enemies", slow.get("enemies"))
        st["phalanx"] = fast.get("phalanx", [])
        st["boss_walls"] = fast.get("boss_walls", [])
        st["ts_fast"] = fast["ts"]
        return st
    return slow

def lead_aim(t, px, py):
    """提前量瞄准: 弹飞时间 = dist/弹速, 敌速由两帧差分估计。
    返回瞄准点(mx,my)。测不到速度(首帧/瞬移)则直瞄。"""
    ex, ey = t["x"], t["y"]
    ts = t.get("ts_fast") or _prev_ts[0]
    key = t.get("id")
    vx, vy = 0.0, 0.0
    if key is not None and key in _prev_pos and ts and _prev_ts[0] \
            and ts != _prev_ts[0]:
        ox, oy = _prev_pos[key]
        dt = max(0.05, ts - _prev_ts[0])
        vx = (ex - ox) / dt
        vy = (ey - oy) / dt
        # 限幅: 遥测毛刺(瞬移)不当作速度
        spd = math.hypot(vx, vy)
        if spd > 200:
            vx = vy = 0.0
    if key is not None:
        _prev_pos[key] = (ex, ey)
    if ts:
        _prev_ts[0] = ts
    dist = math.hypot(ex - px, ey - py)
    t_fly = dist / BULLET_SPEED
    return ex + vx * t_fly * 0.85, ey + vy * t_fly * 0.85  # 0.85 防过冲

def _norm(dx, dy):
    m = math.hypot(dx, dy)
    if m < 1e-6:
        return 0.0, 0.0
    return dx / m, dy / m

def decide(st):
    px, py = st["player_x"], st["player_y"]
    enemies = st.get("enemies") or []

    # ---------- 曹操·赤壁屏障回避: 目标方向若穿紫墙→加切向绕行 ----------
    _walls = st.get("boss_walls") or []

    # ---------- 无敌人 ----------
    if not enemies:
        if st.get("boss"):
            bx, by = BOSS_LAST[0], BOSS_LAST[1]
            if bx is None:
                bx, by = W // 2, 70
            dist = math.hypot(bx - px, by - py)
            if dist > 380:
                ax, ay = bx - px, by - py
                dx, dy = _norm(ax * 0.85 - ay * 0.5, ay * 0.85 + ax * 0.5)
            else:
                dirx = 1 if (int(time.time() * 0.5) % 2 == 0) else -1
                dx, dy = dirx * 0.9, (0.25 if py < H * 0.55 else -0.15)
            return {"dx": round(dx, 3), "dy": round(dy, 3), "fire": True,
                    "mx": px + dx * 100, "my": py + dy * 100}
        # v32.4: 待机时停留在当前位置，不要移动到左下角
        # 待机: 保持当前位置，轻微随机移动
        dx = 0.1 if px < W // 2 else (-0.1 if px > W // 2 else 0)
        dy = 0.1 if py < H // 2 else (-0.1 if py > H // 2 else 0)
        return {"dx": dx, "dy": dy, "fire": False}

    # ---------- boss 坐标同步(快遥测含 kind=boss 条目) ----------
    for e in enemies:
        if e.get("kind") == "boss" or e.get("id") == 0:
            BOSS_LAST[0], BOSS_LAST[1] = e["x"], e["y"]

    n = len(enemies)

    # ---------- 统一计算真实距离(快遥测无 dist 字段) ----------
    for e in enemies:
        e["dist"] = round(math.hypot(px - e["x"], py - e["y"]), 1)

    # ---------- 近身推挤场(150px 内敌往外推) ----------
    pushx, pushy = 0.0, 0.0
    for e in enemies:
        ax, ay = px - e["x"], py - e["y"]
        d = math.hypot(ax, ay)
        if d < 150:
            w = (150 - d) / 150.0
            d = max(d, 8.0)
            pushx += (ax / d) * w
            pushy += (ay / d) * w

    # ---------- 墙壁排斥 ----------
    # v32.4: 减弱墙壁排斥，避免躲在角落
    if px < 100: pushx += 0.3
    if px > W - 100: pushx -= 0.3
    if py < 100: pushy += 0.3
    if py > H - 100: pushy -= 0.3

    pm = math.hypot(pushx, pushy)

    # ---------- 瞄准目标: 优先杀敌，不管是否在方阵 ----------
    # v32.4: 修改逻辑，优先攻击最近敌人，不管是否在方阵
    ph = st.get("phalanx", []) if isinstance(st, dict) else []
    _outside = [e for e in enemies if e["dist"] >= 25 and e["id"] not in ph]
    _inside = [e for e in enemies if e["dist"] >= 25 and e["id"] in ph]
    # 全场皆盾: 仍然开火，优先打最近的
    _all_shield = False  # 改为False，总是开火
    
    # 检查军师指令: 是否攻击大营/回家回血
    _enemy_camp = st.get("enemy_camp")
    _player_camp = st.get("player_camp")
    _target_camp = False
    _go_home = False
    _advisor = advisor_get()
    _adv_target = str(_advisor.get("target", "auto"))

    # 军师下令回家回血(全盾保命/HP低) → 朝我方大营移动(大营范围内自动+2HP/帧)
    if _adv_target == "home_heal" and _player_camp and _player_camp.get("alive"):
        _go_home = True
    # 军师下令攻大营 或 敌人少时主动攻大营
    # 攻营决策（换家/牵制逻辑，替代旧的"敌人≤8才攻营"）:
    # 触发条件（满足其一）:
    #   A. 军师明说 target=camp（脑的主决策）
    #   B. 换家对拆: 我营血量比敌营低很多(差距>50%)且敌营可攻 → 不硬拼换家
    #   C. 牵制拆火: 我营被围攻(HP<70%)且附近敌人多(≥8) → 拉走仇恨攻敌营
    #   D. 顺风推塔: 可打敌人极少(≤3)且不是回家回血状态 → 顺手拆营
    _camp_swap = False
    _ec_hp = _enemy_camp.get("hp", 0) if _enemy_camp else 0
    _pc_hp = _player_camp.get("hp", 888) if _player_camp else 888
    _wave_now = 1
    try:
        with open("/tmp/tank_battle_status.json") as _f:
            _wave_now = int(json.load(_f).get("wave", 1))
    except Exception:
        _wave_now = 1
    _camp_ok = _enemy_camp and _enemy_camp.get("alive") and _wave_now > 3
    if _camp_ok:
        _hp_gap = (_ec_hp - _pc_hp) / 888.0          # 换家缺口: 敌营比我营血多越多,换家越值(>0.5触发)
        _near_my_camp = sum(1 for e in enemies
                            if math.hypot(e["x"] - (_player_camp["x"] if _player_camp else 450),
                                          e["y"] - (_player_camp["y"] if _player_camp else 540)) < 200)
        _hittable = n - len(ph)
        _cond_b = _hp_gap > 0.5                      # 换家: 我营比敌营血少50%以上
        _cond_c = _pc_hp < 0.7 * 888 and _near_my_camp >= 8   # 牵制: 我营被围攻
        _cond_d = _hittable <= 3 and not _go_home    # 顺风: 几乎没可打敌人
        if (_adv_target == "camp" or _cond_b or _cond_c or _cond_d) and not _go_home:
            camp_dist = math.hypot(_enemy_camp["x"] - px, _enemy_camp["y"] - py)
            t = {"x": _enemy_camp["x"], "y": _enemy_camp["y"], "dist": camp_dist, "id": -1, "kind": "camp"}
            dist = camp_dist
            mx, my = _enemy_camp["x"], _enemy_camp["y"]
            _target_camp = True
            _all_shield = False   # 敌营不是方阵盾,不受免伤,攻营必须开火
    
    if _go_home:
        # 回营模式: 朝我方大营移动(不恋战,优先脱离接触)
        hx, hy = _player_camp["x"], _player_camp["y"]
        home_dist = math.hypot(hx - px, hy - py)
        ax_, ay_ = hx - px, hy - py
        mx, my = hx, hy   # 瞄准大营方向(默认值,防UnboundLocalError)
        if home_dist > 60:
            dx0, dy0 = _norm(ax_, ay_)
        else:
            dx0, dy0 = 0.0, 0.0   # 已在营内,站桩回血
        # 全盾时不开火(打不着),有可打目标才开火
        _can_fire = not _all_shield and (len(_outside) > 0)
        return {"dx": round(dx0, 3), "dy": round(dy0, 3),
                "fire": _can_fire,
                "mx": px + dx0 * 100 if dx0 or dy0 else mx, "my": py + dy0 * 100 if dx0 or dy0 else my,
                "skill": False}
    
    if not _target_camp:
        aimable = _outside or _inside or enemies
        t = min(aimable, key=lambda e: e["dist"])
        dist = t["dist"]
        mx, my = lead_aim(t, px, py)
        if mx == px and my == py:
            mx, my = px + 1, py

    # ---------- 移动 ----------
    if _target_camp:
        # 攻击大营模式: 直接朝大营移动,保持适当距离
        ax, ay = t["x"] - px, t["y"] - py
        camp_dist = math.hypot(ax, ay)
        if camp_dist > 300:
            # 距离太远,直接朝大营走
            dx, dy = _norm(ax, ay)
        elif camp_dist < 150:
            # 太近,后退一点
            dx, dy = _norm(-ax, -ay)
        else:
            # 理想距离,左右移动保持火力
            side = 1.0 if (int(time.time() * 0.7) % 2 == 0) else -1.0
            dx, dy = _norm(-ay * side, ax * side)
    elif pm > 0.25:
        # 推挤主导 + 以目标为轴的切向绕桩(方向周期切换,防绕死)
        dx, dy = pushx / pm, pushy / pm
        ax, ay = t["x"] - px, t["y"] - py
        tx_, ty_ = _norm(ax, ay)
        side = 1.0 if (int(time.time() * 0.7) % 2 == 0) else -1.0
        dx, dy = _norm(dx - ty_ * side * 0.45, dy + tx_ * side * 0.45)
    else:
        ideal = advisor_get()["ideal_dist"]   # 军师动态调参(默认190)
        ax, ay = t["x"] - px, t["y"] - py
        tx_, ty_ = _norm(ax, ay)
        side = 1.0 if (int(time.time() * 0.7) % 2 == 0) else -1.0
        _threat = advisor_get()["threat"]
        if n >= 10 and dist < 280:
            # 集火警戒: 远离最近敌+切向(军师威胁高时撤离更果断)
            _w = 0.9 + 0.3 * (_threat - 1.0)
            dx, dy = _norm(-tx_ * _w - ty_ * side * 0.6,
                           -ty_ * _w + tx_ * side * 0.6)
        elif dist > ideal + 50:
            dx, dy = _norm(tx_ * 0.85 - ty_ * 0.4, ty_ * 0.85 + tx_ * 0.4)
        elif dist < ideal - 70:
            dx, dy = _norm(-tx_ * 0.8 - ty_ * 0.5, -ty_ * 0.8 + tx_ * 0.5)
        else:
            dx, dy = _norm(-ty_ * side, tx_ * side)

    # v32.4: 总是开火，优先杀敌
    # ---- 吕布·烈璧障策略: 被围(近敌≥3且最近<90)或集火高压(≥10台且<280)且CD好 → 放 ----
    skill = False
    _cd = st.get("barricade_cd_s", 0)
    if _cd == 0:
        _near_cnt = sum(1 for e in enemies if e["dist"] < 90)
        if _near_cnt >= 3 or (n >= 10 and dist < 280):
            skill = True
    # ---- 曹操·赤壁屏障回避: 移动矢量若穿紫墙→旋转70°切向绕行 ----
    if _walls and (dx or dy):
        _nx = px + dx * 30
        _ny = py + dy * 30
        _blocked = any((_nx - w["x"]) ** 2 + (_ny - w["y"]) ** 2 < (w["r"] + 14) ** 2
                       for w in _walls)
        if _blocked:
            _a = math.atan2(dy, dx) + math.radians(70)
            dx, dy = _norm(math.cos(_a), math.sin(_a))
    # v32.4: 总是开火，只要距离小于600
    return {"dx": round(dx, 3), "dy": round(dy, 3),
            "fire": dist < 600, "mx": mx, "my": my,
            "skill": skill}

# ---------- 35B 军师(可选, :8083): 每5s产出战术参数包 ----------
# 分层指挥: 军师只调参数,不碰20Hz操作。请求异步化(后台线程),主循环永不阻塞。
# 军师挂了/超时 → 沿用上次参数(初始=默认值),零风险。
ADVISOR_URL = os.environ.get("TANK_ADVISOR_URL", "")   # 例: http://127.0.0.1:8083/v1/chat/completions
_advisor_lock = __import__("threading").Lock()
_advisor_state = {                     # 军师参数包(带时间戳)
    "ts": 0.0,
    "ideal_dist": 190.0,               # 理想交战距离 px(默认)
    "style": "balanced",               # aggressive / balanced / kite
    "threat": 1.0,                     # 1~3 威胁评估
    "target": "auto",                  # enemies / camp / auto
    "target_type": "camp",             # camp / enemy / boss
    "target_x": 450.0,                 # 目标X
    "target_y": 45.0,                  # 目标Y
    "lat": 0.0,
}

def advisor_loop():
    """后台线程: 每5s问一次军师,更新参数包。"""
    import urllib.request
    while True:
        t0 = time.time()
        try:
            st = read_status()
            if st and st.get("state") == "play":
                enemies = st.get("enemies") or []
                px, py = st.get("player_x", 0), st.get("player_y", 0)
                near = sum(1 for e in enemies
                           if math.hypot(e["x"]-px, e["y"]-py) < 150)
                hp = st.get("player_hp", 500)
                hp_max = st.get("player_max_hp", 500)
                plans = {}
                for e in (st.get("enemies") or []):
                    p = e.get("plan", "")
                    if p: plans[p] = plans.get(p, 0) + 1
                focus = max(plans.values()) if plans else 0
                # 大营信息
                _ec = st.get("enemy_camp")
                _pc = st.get("player_camp")
                camp_info = ""
                if _ec and _ec.get("alive"):
                    camp_info = f" Enemy camp at ({_ec['x']},{_ec['y']}) HP={_ec['hp']}/1000."
                if _pc:
                    camp_info += f" Our camp HP={_pc['hp']}/1000."
                
                # 计算到我军大本营距离
                _my_camp_dist = float('inf')
                if _pc and _pc.get("alive"):
                    _my_camp_dist = math.hypot(_pc["x"] - px, _pc["y"] - py)
                
                # 计算被包围情况
                _surrounded = sum(1 for e in enemies if math.hypot(e["x"]-px, e["y"]-py) < 150)
                
                # 读取战场数据库分析
                battle_analysis = ""
                try:
                    from battle_recorder import battle_db
                    import json
                    
                    # 获取最近战场数据
                    with open('/tmp/hsdb_battle.json', 'r') as f:
                        all_data = json.load(f)
                    
                    # 找到最新战斗
                    battle_ids = set()
                    for key in all_data.keys():
                        if '_frame_' in key:
                            bid = key.split('_frame_')[0]
                            battle_ids.add(bid)
                    
                    if battle_ids:
                        latest_battle = max(battle_ids)
                        latest_key = f"{latest_battle}_latest"
                        if latest_key in all_data:
                            latest_frame = all_data[latest_key]
                            enemy_count = len(latest_frame.get('enemies', []))
                            bullet_count = len(latest_frame.get('bullets', []))
                            player_hp_hist = latest_frame.get('player', {}).get('hp', 0)
                            
                            # 统计敌军战术
                            enemy_tactics = {}
                            for e in latest_frame.get('enemies', []):
                                plan = e.get('plan', '')
                                if plan:
                                    enemy_tactics[plan] = enemy_tactics.get(plan, 0) + 1
                            
                            battle_analysis = f"\n📊敌军最近动态:\n"
                            battle_analysis += f"- 敌军数量:{enemy_count}个\n"
                            battle_analysis += f"- 敌军子弹:{bullet_count}发\n"
                            battle_analysis += f"- 敌军战术:{enemy_tactics}\n"
                except Exception as e:
                    battle_analysis = ""
                
                # 读取战术效果数据库
                tactics_stats = ""
                try:
                    from tactics_db import TACTICS_DB
                    tactics_stats = "\n📈我军战术效果:\n"
                    for name, data in TACTICS_DB.items():
                        if data['used'] > 0:
                            tactics_stats += f"- {name}: 使用{data['used']}次, 效果{data['effectiveness']:.2f}\n"
                except:
                    tactics_stats = ""
                
                # 构建复盘分析提示词
                prompt = (
                    "你是吕布的军师，负责战术决策和复盘分析。\n"
                    f"当前战况:\n"
                    f"- 我方坦克位置: ({px:.0f},{py:.0f})\n"
                    f"- 我方HP: {hp}/{hp_max}\n"
                    f"- 敌人数量: {len(enemies)}个\n"
                    f"- 周围150px内敌人: {_surrounded}个\n"
                    f"- 敌军大营: {camp_info}\n"
                    f"- 到我军大本营距离: {_my_camp_dist:.0f}px\n"
                    + battle_analysis
                    + tactics_stats
                    + "\n"
                    "请根据以上数据进行复盘分析:\n"
                    "1. 分析当前战局优劣\n"
                    "2. 识别敌军战术模式\n"
                    "3. 评估我军策略效果\n"
                    "4. 给出改进建议\n"
                    "\n"
                    "然后输出决策JSON:\n"
                    "{\"analysis\":\"战局分析\",\"enemy_pattern\":\"敌军模式\","
                    "\"improvement\":\"改进建议\","
                    "\"dist\":N,\"style\":\"...\",\"threat\":N,\"target\":\"...\"}\n"
                    "只输出JSON，不要解释。"
                )
                body = json.dumps({
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 48, "temperature": 0.3,
                    "chat_template_kwargs": {"enable_thinking": False},
                }).encode()
                req = urllib.request.Request(ADVISOR_URL, data=body,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    txt = json.loads(r.read().decode())["choices"][0]["message"]["content"]
                m = re.search(r"\{[^}]*\}", txt, re.DOTALL)
                if m:
                    obj = json.loads(m.group(0))
                    dist = max(150.0, min(350.0, float(obj.get("dist", 190))))
                    style = str(obj.get("style", "balanced"))[:12]
                    threat = max(1.0, min(3.0, float(obj.get("threat", 1))))
                    target = str(obj.get("target", "auto"))[:12]
                    
                    # 解析目标类型和坐标
                    target_type = "camp"
                    target_x, target_y = 450.0, 45.0
                    if target == "camp" and _ec and _ec.get("alive"):
                        target_type = "camp"
                        target_x, target_y = _ec["x"], _ec["y"]
                    elif target == "enemies" and enemies:
                        # 找最近的敌人
                        nearest = min(enemies, key=lambda e: math.hypot(e["x"]-px, e["y"]-py))
                        target_type = "enemy"
                        target_x, target_y = nearest["x"], nearest["y"]
                    
                    with _advisor_lock:
                        _advisor_state.update(ts=time.time(), ideal_dist=dist,
                                              style=style, threat=threat,
                                              target=target,
                                              target_type=target_type,
                                              target_x=target_x,
                                              target_y=target_y,
                                              lat=time.time()-t0)
        except Exception:
            pass  # 军师失联: 沿用上次参数
        time.sleep(5.0)


def advisor_get():
    """读取军师状态（优先从服务文件读取）"""
    try:
        with open("/tmp/advisor_state.json", 'r') as f:
            data = json.load(f)
        if data and data.get("ts", 0) > 0:
            # 转换格式
            return {
                "ts": data.get("ts", 0),
                "ideal_dist": data.get("dist", 190.0),
                "style": data.get("style", "balanced"),
                "threat": data.get("threat", 1.0),
                "target": data.get("target", "auto"),
                "target_type": "camp" if data.get("target") == "camp" else "enemy",
                "target_x": 450.0,
                "target_y": 45.0,
                "lat": data.get("lat", 0.0)
            }
    except:
        pass
    
    with _advisor_lock:
        return dict(_advisor_state)


# ---------- Laya System-1 战术顾问(可选): HTTP 打分,200ms/次 ----------
# 用途: 把"是否放烈璧障"从硬编码阈值升级为神经打分辅助。
# 服务未起(或超时)时静默回退原有规则,零风险。
LAYA_URL = os.environ.get("LAYA_URL", "")   # 例: http://127.0.0.1:8091/v1/systemone
_laya_cache = [0.0, None]                   # [上次询问时间, 上次结论bool]

def laya_ask_skill(st):
    """问 Laya: 当前该不该放烈璧障? 1s 内复用缓存。失败返回 None(走原规则)。"""
    if not LAYA_URL:
        return None
    now = time.time()
    if now - _laya_cache[0] < 1.0:
        return _laya_cache[1]
    _laya_cache[0] = now
    try:
        enemies = st.get("enemies") or []
        px, py = st.get("player_x", 0), st.get("player_y", 0)
        near = sum(1 for e in enemies
                   if math.hypot(e["x"] - px, e["y"] - py) < 120)
        hp = st.get("player_hp", 8)
        state = (f"tank battle: {len(enemies)} enemies on field, "
                 f"{near} within 120px of my tank, my HP {hp:.0f}/8, "
                 f"barricade wall skill ready, 20Hz control loop")
        body = json.dumps({
            "state": state,
            "questions": {"skill": {
                "type": "choice",
                "instructions": ("Enemy commander is coordinating focus fire. "
                                 "Should the tank deploy its protective arc wall right now?"),
                "criteria": {
                    "hold": "situation manageable, keep the wall for a real emergency",
                    "deploy": "crowded or dangerous, deploy the protective wall now"}}},
        }).encode()
        req = urllib.request.Request(LAYA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=0.5) as r:
            ans = json.loads(r.read().decode())["answers"]["skill"]
        use = ans["choice"] == "deploy" and ans.get("confidence", 0) > -1  # 概率差为主
        # 用概率差更稳: deploy 概率显著高于 hold 才放
        p = ans.get("probabilities", {})
        use = p.get("deploy", 0) > p.get("hold", 0)
        _laya_cache[1] = use
        return use
    except Exception:
        _laya_cache[1] = None
        return None


def main():
    if ADVISOR_URL:
        threading.Thread(target=advisor_loop, daemon=True).start()
    while True:
        st = read_status()
        if st and st.get("state") == "play":
            cmd = decide(st)
            # Laya 顾问意见: 原规则说放 or Laya 强烈建议放 → 放
            laya_says = laya_ask_skill(st)
            if laya_says and not cmd.get("skill"):
                _cd = st.get("barricade_cd_s", 0)
                _near = sum(1 for e in (st.get("enemies") or [])
                            if math.hypot(e["x"] - st["player_x"],
                                          e["y"] - st["player_y"]) < 120)
                if _cd == 0 and _near >= 1:
                    cmd["skill"] = True   # Laya 建议且条件允许(有敌近身) → 补放
            s.sendto(json.dumps(cmd).encode(), UDP)
        else:
            s.sendto(json.dumps({"dx": 0, "dy": 0, "fire": False}).encode(), UDP)
        time.sleep(0.05)  # 20Hz

if __name__ == "__main__":
    main()
