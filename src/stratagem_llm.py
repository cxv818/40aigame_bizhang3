# v36.0 (2026-10-05) — 36aigame
# 曹操·36计 LLM选计系统
# 版本: v36.0
# 功能: 用LLM真选计策(替代随机模板), 并把选中计策转为战术约束注入三帅提示词

import json
import re
import threading
import time
import urllib.request

# 36计计策库: 计名 → (含义, {战术约束})
# 约束字段: forced_plans=必须包含的战术, max_phalanx=方阵上限比, attack_camp_ratio=攻营兵力比
STRATAGEMS = {
    # --- 胜战计 ---
    "瞒天过海": ("备周则意怠,常见则不疑。用日常小骚扰麻痹吕布,积蓄致命一击", {"forced_plans": ["游击"], "note": "先用游击麻痹,再寻机集火"}),
    "围魏救赵": ("攻其所必救。分兵攻吕布大营,逼其回防,半路截杀", {"attack_camp_ratio": 0.5, "forced_plans": ["直攻"], "note": "≥50%兵力target=pcamp攻营"}),
    "借刀杀人": ("借地形之险消耗敌军。诱吕布入山地,山上射速x2火力压制", {"forced_plans": ["游击"], "note": "把吕布诱向山地,山上单位火力全开"}),
    "以逸待劳": ("困敌之势。方阵壁垒固守,待吕布进攻受挫再反击", {"forced_plans": ["方阵"], "note": "方阵消耗为主,fire克制,等吕布撞墙"}),
    "趁火打劫": ("敌之害也。吕布残血或被围时全军突击,一举歼灭", {"forced_plans": ["直攻", "集火"], "note": "吕布HP<40%时全线压上,不给喘息"}),
    "声东击西": ("示敌以东,击敌以西。左翼佯攻吸引,右翼主力包抄", {"forced_plans": ["游击", "直攻"], "note": "30%兵力佯攻吸引注意,70%从另一侧包抄"}),
    # --- 敌战计 ---
    "无中生有": ("诳也。虚张声势多路佯动,让吕布判断不了主攻方向", {"forced_plans": ["游击"], "note": "多路分散游走,虚虚实实"}),
    "暗度陈仓": ("明修栈道,暗度陈仓。正面示弱牵制,奇兵绕后攻大营", {"attack_camp_ratio": 0.4, "forced_plans": ["直攻"], "note": "正面牵制,≥40%奇兵target=pcamp"}),
    "笑里藏刀": ("近而示之恭。佯装败退示弱,诱吕布深入,伏兵四起", {"forced_plans": ["游击", "集火"], "note": "前排后撤诱敌,后排集火架好等他进来"}),
    # --- 攻战计 ---
    "调虎离山": ("待天以困之。佯攻大营调吕布离山/离掩体,半路截杀", {"attack_camp_ratio": 0.4, "forced_plans": ["直攻", "集火"], "note": "攻营逼吕布移动,移动中集火截杀"}),
    "欲擒故纵": ("逼则反兵,走则减势。佯装败退,诱敌追击,反包围", {"forced_plans": ["游击"], "note": "先集体后撤拉开距离,吕布追击时两翼合围"}),
    # --- 并战计 ---
    "擒贼擒王": ("摧毁其首脑。全军集火吕布本体,斩首行动", {"forced_plans": ["集火"], "note": "所有集火单位同角度锁定吕布,充能合火必杀"}),
    # --- 败战计 ---
    "走为上": ("全师避敌。波次已深保存实力,暂避锋芒待时而动", {"forced_plans": ["方阵", "游击"], "note": "残血单位后撤回营,方阵掩护,避免决战"}),
    "苦肉计": ("人不自害,受假之真。诈降诱敌,里应外合", {"forced_plans": ["游击"], "note": "少量单位示弱送头诱敌,主力埋伏"}),
    "连环计": ("多计并用,环环相扣。方阵消耗+集火收割交替,使敌疲于应付", {"forced_plans": ["方阵", "集火"], "note": "方阵耗他子弹,散开瞬间集火,循环往复"}),
}

FALLBACK_ORDER = ["以逸待劳", "直攻消耗"]  # LLM失败时兜底(纯文本计)


class StratagemLLM:
    """曹操36计LLM选计器:
    - 每 COOLDOWN 秒把战场态势发给三帅LLM(曹操端口)
    - LLM从36计库选一计 + 简短军令理由
    - 选中计策的战术约束注入 _build_prompt(联动!)
    - LLM失败自动回退随机模板(绝不阻塞游戏)
    """

    COOLDOWN = 45.0        # 选计间隔(秒) — 计策要有持续期,不能换太快
    TIMEOUT = 8.0          # LLM超时
    PORT = 8080            # 曹操端口(三帅共用同一模型,选计走曹操)

    def __init__(self):
        self.active = None          # 当前生效计策名
        self.constraint = {}        # 当前计策的战术约束
        self.reason = ""            # LLM给的军令理由
        self.since = 0.0            # 生效时间
        self.pending = False
        self.last_ask = 0.0
        self.use_llm = True         # 失败2次后自动降级为模板
        self._fail_count = 0
        self.lock = threading.Lock()
        self._channel = None        # WeiCommandChannel实例(主循环注入)
        self._comm = None           # SquadComm实例(主循环注入)

    # ---------- 战场态势摘要(供选计) ----------
    def _build_situation(self):
        import pygame
        import __main__ as M
        sit = []
        try:
            wave = getattr(M, "_cached_wave", 1)
            sit.append(f"波次{wave}")
            st = getattr(M, "_slow_cache", {}) or {}
            p = st.get("player", {})
            if p:
                sit.append(f"吕布HP{p.get('hp', 500)}/{p.get('max_hp', 500)}")
            ec = st.get("enemy_camp")
            if ec:
                sit.append(f"我营HP{ec.get('hp', 5000)}")
            pc = st.get("player_camp")
            if pc:
                sit.append(f"吕布营HP{pc.get('hp', 5000)}")
            enemies = st.get("enemies", [])
            sit.append(f"我军在场{len(enemies)}台")
            plans = {}
            for e in enemies:
                pl = e.get("plan") or ""
                if pl:
                    plans[pl] = plans.get(pl, 0) + 1
            if plans:
                sit.append("当前部署:" + ",".join(f"{k}x{v}" for k, v in plans.items()))
        except Exception:
            pass
        return " ".join(sit) or "战场迷雾,情报有限"

    # ---------- LLM选计 ----------
    def ask(self):
        """异步发起选计(不阻塞,COOLDOWN内复用上一次结果)"""
        now = time.time()
        if now - self.last_ask < self.COOLDOWN or self.pending:
            return
        self.last_ask = now
        self.pending = True
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            if not self.use_llm:
                raise RuntimeError("LLM降级模式")
            situation = self._build_situation()
            strat_list = "、".join(STRATAGEMS.keys())
            prompt = (
                "你是魏军曹操,熟读三十六计。根据当前战场态势选用一计。\n"
                f"态势: {situation}\n"
                f"可选计策: {strat_list}\n"
                "选计原则: 计策要针对当前态势,不同时段灵活变换,不与上一计重复。\n"
                '只输出JSON: {"stratagem":"计名","reason":"≤20字军令"}'
            )
            from llm_client import ask as _llm_ask  # v36.0: 统一出口(短prompt失败即降级,不重试)
            text, _lat = _llm_ask(self.PORT, prompt=prompt, max_tokens=120,
                                  temperature=0.8, timeout=self.TIMEOUT)
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                raise ValueError("无JSON: " + text[:60])
            obj = json.loads(m.group(0))
            name = str(obj.get("stratagem", "")).strip()
            reason = str(obj.get("reason", "")).strip()[:40]
            if name not in STRATAGEMS:
                # LLM可能输出变体名,做一次模糊匹配
                hit = next((k for k in STRATAGEMS if k in name or name in k), None)
                if not hit:
                    raise ValueError("未知计名: " + name)
                name = hit
            with self.lock:
                _prev = self.active
                self.active = name
                self.constraint = STRATAGEMS[name][1]
                self.reason = reason or STRATAGEMS[name][0][:20]
                self.since = time.time()
            self._fail_count = 0
            try:
                from battle_recorder import record_event
                record_event("stratagem_change", {"prev": _prev, "new": name,
                                                  "reason": self.reason})  # v33.03埋点
            except Exception:
                pass
            self._announce()
        except Exception as e:
            self._fail_count += 1
            if self._fail_count >= 2:
                self.use_llm = False   # 连续失败,降级为模板随机
            # 回退: 随机选一计(仍保持联动)
            import random
            name = random.choice(list(STRATAGEMS.keys()))
            with self.lock:
                self.active = name
                self.constraint = STRATAGEMS[name][1]
                self.reason = STRATAGEMS[name][0][:20]
                self.since = time.time()
            if self._fail_count <= 1:
                self._announce()
        finally:
            self.pending = False

    def _announce(self):
        """喊话: 既有古风计名,又带具体军令。
        v36.0: 频道实例由游戏主循环通过 attach_channel() 注入,避免循环导入"""
        try:
            line = f"【36计·{self.active}】{self.reason}"
            ch = self._channel
            if ch is not None:
                ch.broadcast("曹操", line)
                return
            comm = self._comm
            if comm is not None:
                comm.say("曹操", line)
            else:
                print(f"[曹操·选计] {line}", flush=True)  # 釦底: 至少进日志
        except Exception as e:
            print(f"[选计喊话失败] {e}", flush=True)  # 已显式留痕(高频场景,不用swallow限流)

    def attach_channel(self, channel=None, comm=None):
        """游戏主循环启动后注入真实频道实例"""
        if channel is not None:
            self._channel = channel
        if comm is not None:
            self._comm = comm

    # ---------- 给 _build_prompt 的约束注入 ----------
    def prompt_block(self):
        """返回注入三帅战术提示词的约束文本(无计策时空串)"""
        with self.lock:
            if not self.active:
                return ""
            c = dict(self.constraint)
            name, meaning = self.active, STRATAGEMS[self.active][0]
        lines = [
            f"\n★★曹操已定计:『{name}』— {meaning}",
            f"全军必须围绕此计展开: {c.get('note', '')}",
        ]
        fp = c.get("forced_plans")
        if fp:
            lines.append(f"本计役必须包含战术: {'、'.join(fp)} (至少各一队)")
        acr = c.get("attack_camp_ratio")
        if acr:
            lines.append(f"本计要求 ≥{int(acr*100)}% 兵力 target=\"pcamp\" 攻吕布大营")
        return "\n".join(lines) + "\n"

    # ---------- 快照(遥测用) ----------
    def snapshot(self):
        with self.lock:
            if not self.active:
                return None
            return {"stratagem": self.active, "reason": self.reason,
                    "age_s": round(time.time() - self.since, 1)}


# 模块级单例
_STRAT = None

def get_stratagem():
    global _STRAT
    if _STRAT is None:
        _STRAT = StratagemLLM()
    return _STRAT


if __name__ == "__main__":
    # 离线测试(不需要游戏): 直接调LLM选3次
    s = StratagemLLM()
    for i in range(3):
        s.pending = False
        s.last_ask = 0
        s._fail_count = 0
        s.use_llm = True
        s.ask()
        time.sleep(10)
        print(f"[{i+1}] 选中: {s.active} — {s.reason}")
        print("    注入提示词块:")
        print(s.prompt_block())
