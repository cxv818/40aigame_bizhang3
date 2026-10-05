# v36.0 (2026-10-05) — 36aigame
#!/usr/bin/env python3
# 军师服务 - 简化版
import json
import math
import os
import time
import urllib.request
import re

URL = "http://127.0.0.1:8083/v1/chat/completions"
STATUS_FILE = "/tmp/tank_battle_status.json"
OUTPUT_FILE = "/tmp/advisor_state.json"

# 军师进化存档
ADVISOR_EVO_FILE = "/home/ibm/桌面/24aigame/data/advisor_evolution.json"

def load_advisor_evolution():
    """加载军师进化存档"""
    if os.path.exists(ADVISOR_EVO_FILE):
        try:
            with open(ADVISOR_EVO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"generation": 0, "lessons": [], "battle_count": 0, "win_count": 0}

def save_advisor_evolution(evo):
    """保存军师进化存档"""
    os.makedirs(os.path.dirname(ADVISOR_EVO_FILE), exist_ok=True)
    with open(ADVISOR_EVO_FILE, 'w', encoding='utf-8') as f:
        json.dump(evo, f, ensure_ascii=False, indent=2)

def add_advisor_lesson(result, hp_ratio, wave, enemies_killed):
    """添加军师教训"""
    evo = load_advisor_evolution()
    evo["battle_count"] += 1
    
    if result == "win":
        evo["win_count"] += 1
        lesson = f"第{evo['battle_count']}局胜利: HP比例{hp_ratio:.1%}, 歼敌{enemies_killed}, 波次{wave}. 策略有效!"
    else:
        lesson = f"第{evo['battle_count']}局失败: HP比例{hp_ratio:.1%}, 歼敌{enemies_killed}, 波次{wave}. 需改进策略."
    
    evo["lessons"].append(lesson)
    evo["lessons"] = evo["lessons"][-8:]  # 保留最近8条
    
    # 每3局进化一代（比曹操AI更快，因为军师需要快速学习）
    if evo["battle_count"] % 3 == 0:
        evo["generation"] += 1
        log(f"🎉 军师进化到第{evo['generation']}代!")
    
    save_advisor_evolution(evo)
    return evo

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def read_status():
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except:
        return None

def save_state(state):
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(state, f)


def validate_advice(advice, game_state):
    """校验建议合理性，拦截明显错误的建议"""
    # 获取敌人数量
    enemies = game_state.get('enemies', [])
    enemy_count = len(enemies) if isinstance(enemies, list) else game_state.get('enemies_onfield', 0)
    
    # 满血时不建议回血
    if game_state.get('player_hp', 500) > 400 and advice.get('target') == 'home_heal':
        advice['target'] = 'enemies'
        advice['style'] = 'aggressive'
    
    # 波次<=3时不建议攻营
    if game_state.get('wave', 1) <= 3 and advice.get('target') == 'camp':
        advice['target'] = 'enemies'
    
    # 敌人<5时不建议游击
    if enemy_count < 5 and advice.get('style') == 'kite':
        advice['style'] = 'aggressive'
    
    # 低血量(<200)强制游击+回血
    if game_state.get('player_hp', 500) < 200 and advice.get('style') != 'kite':
        advice['style'] = 'kite'
        advice['target'] = 'home_heal'
    
    # 敌人>20时强制游击
    if enemy_count > 20 and advice.get('style') != 'kite':
        advice['style'] = 'kite'
    
    return advice


def call_llm(prompt):
    body = json.dumps({
        "messages": [
            {"role": "system", "content": "游戏AI。只输出JSON，无解释。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 60,
        "temperature": 0.1,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"].get("content", "")

def main():
    log("军师服务启动")
    
    # 加载进化存档
    evo = load_advisor_evolution()
    log(f"继承存档: 第{evo['generation']}代, {len(evo['lessons'])}条教训, 胜率{evo['win_count']/max(1,evo['battle_count']):.1%}")
    
    state = {"ts": 0, "dist": 190, "style": "balanced", "threat": 1, "target": "camp"}
    save_state(state)
    
    while True:
        try:
            st = read_status()
            if not st or st.get("state") != "play":
                time.sleep(5)
                continue
            
            enemies = st.get("enemies") or []
            hp = st.get("player_hp", 500)
            max_hp = st.get("player_max_hp", 500)
            
            # 脑必须看到方阵态势（全场皆盾时打不到人！）
            phalanx = set(st.get("phalanx", []))
            in_shield = sum(1 for e in enemies if e.get("id") in phalanx)
            out_shield = len(enemies) - in_shield
            all_shield = out_shield == 0 and in_shield > 0
            surround_cnt = sum(1 for e in enemies
                               if math.hypot(e.get("x",0)-st.get("player_x",0),
                                             e.get("y",0)-st.get("player_y",0)) < 150)
            my_camp = st.get("player_camp")
            px, py = st.get("player_x", 0), st.get("player_y", 0)
            my_camp_dist = math.hypot(my_camp["x"]-px, my_camp["y"]-py) if my_camp else -1
            hp_low = hp < max_hp * 0.5
            
            # 双大营坐标 + 攻营时机信息
            ec = st.get("enemy_camp") or {}
            pc = st.get("player_camp") or {}
            ec_hp = ec.get("hp", 0)
            pc_hp = pc.get("hp", 0)
            wave = st.get("wave", 1)
            camp_attackable = wave > 3   # 波次>3敌营才可被攻击
            
            # 三国杀: 三将信息
            generals_info = ""
            for g in (st.get("generals") or []):
                generals_info += (
                    f"敌将{g['name']}({g['hp']}/{g['max_hp']})@({g['x']:.0f},{g['y']:.0f}) "
                )
            if generals_info:
                generals_info = "敌将:" + generals_info.strip() + "\n"
                generals_info += "斩杀夏侯惇/夏侯渊→其亲兵禁进化,斩曹操→直接胜利!\n"

            # 构建历史教训提示
            lessons_text = ""
            if evo["lessons"]:
                lessons_text = "历史教训:\n" + "\n".join([f"{i+1}. {l}" for i, l in enumerate(evo["lessons"][-4:])]) + "\n"
            
            prompt = (
                f"你吕布军师(第{evo['generation']}代),根据战况输出战术决策。\n"
                + lessons_text +
                f"战况:HP{hp}/{max_hp}{'(危险!)' if hp_low else ''},"
                f"敌{len(enemies)}个=方阵免伤盾{in_shield}个+可打{out_shield}个,"
                f"围你{surround_cnt}个,波次{wave}.\n"
                + generals_info +
                f"坐标:你({px:.0f},{py:.0f}) | 敌军大营({ec.get('x',450):.0f},{ec.get('y',100):.0f})HP{ec_hp}/888"
                f"{'[可攻]' if camp_attackable else '[波次>3才能攻]'}"
                f" | 我方大营({pc.get('x',450):.0f},{pc.get('y',540):.0f})HP{pc_hp}/888(回血区)\n"
                + (f"⚠全场皆盾!你的子弹全部无效,还在被打!\n" if all_shield else "")
                + (f"⚠我方大营可回血,靠近自动+2/帧.\n" if hp_low else "")
                + "规则:只回JSON不解释.字段:dist交战距离150-350;"
                "style:aggressive/balanced/kite;threat:1-3;"
                "target:camp(攻敌大营)/enemies(杀敌)/home_heal(回营回血).\n"
                "战术参考:全场皆盾→kite拉距或home_heal保命等散阵;"
                "HP低→home_heal;可打敌人多→enemies+aggressive;"
                "敌少且波次>3→camp直捣黄龙.\n"
                f"回复JSON:{{\"dist\":200,\"style\":\"aggressive\",\"threat\":2,\"target\":\"camp\"}}"
            )
            
            log("调用LLM...")
            t0 = time.time()
            txt = call_llm(prompt)
            lat = time.time() - t0
            
            log(f"响应({lat:.1f}s): {txt[:80]}")
            
            # 尝试多种方式解析JSON
            obj = None
            
            # 方式1: 直接解析
            try:
                obj = json.loads(txt)
            except:
                pass
            
            # 方式2: 查找JSON块
            if not obj:
                m = re.search(r"\{[^}]*\}", txt, re.DOTALL)
                if m:
                    try:
                        obj = json.loads(m.group(0))
                    except:
                        pass
            
            # 方式3: 查找代码块
            if not obj:
                m = re.search(r"```json\s*(.*?)\s*```", txt, re.DOTALL)
                if m:
                    try:
                        obj = json.loads(m.group(1))
                    except:
                        pass
            
            if obj:
                state = {
                    "ts": time.time(),
                    "dist": obj.get("dist", 190),
                    "style": obj.get("style", "balanced"),
                    "threat": obj.get("threat", 1),
                    "target": obj.get("target", "camp"),
                    "lat": lat
                }
                # 校验建议合理性
                state = validate_advice(state, st)
                save_state(state)
                log(f"✅ 更新: dist={state['dist']}, style={state['style']}")
            else:
                log("❌ 无JSON")
                
        except Exception as e:
            log(f"错误: {e}")
        
        time.sleep(5)

def record_battle_result(result, hp_ratio, wave, enemies_killed):
    """记录战斗结果（由主游戏调用）"""
    return add_advisor_lesson(result, hp_ratio, wave, enemies_killed)

if __name__ == "__main__":
    main()
