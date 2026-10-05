# v36.0 (2026-10-05) — 36aigame
# 战场分析器
# 版本: v12.0
# 功能: 让LLM自动分析战场数据，生成战术建议

import json
import time
import urllib.request
from battle_recorder import get_recorder, battle_db

class BattleAnalyzer:
    """
    战场分析器:
    - 读取战场记录数据库
    - 让LLM分析战术效果
    - 生成改进建议
    """
    
    def __init__(self, llm_url="http://127.0.0.1:8083/v1/chat/completions"):
        self.llm_url = llm_url
        self.analysis_interval = 30  # 每30秒分析一次
        self.last_analysis_time = 0
        
    def analyze_battle(self, battle_id=None, frame_count=30):
        """
        分析最近N帧的战场数据
        
        Args:
            battle_id: 战斗ID，None则使用当前战斗
            frame_count: 分析最近多少帧
        """
        if battle_id is None:
            battle_id = get_recorder().current_battle_id
        
        # 获取最近N帧数据
        recorder = get_recorder()
        latest_frame = recorder.frame_count
        start_frame = max(1, latest_frame - frame_count)
        
        frames = recorder.get_frame_range(start_frame, latest_frame)
        
        if not frames:
            return None
        
        # 构建分析提示词
        analysis_prompt = self._build_analysis_prompt(frames)
        
        # 调用LLM分析
        try:
            result = self._call_llm(analysis_prompt)
            return result
        except Exception as e:
            print(f"[Analyzer] LLM分析失败: {e}")
            return None
    
    def _build_analysis_prompt(self, frames):
        """构建分析提示词"""
        # 统计关键指标
        total_enemies = 0
        total_bullets = 0
        player_hp_changes = []
        enemy_deaths = 0
        tactic_usage = {}
        
        for frame in frames:
            total_enemies += len(frame.get("enemies", []))
            total_bullets += len(frame.get("bullets", []))
            
            player = frame.get("player", {})
            player_hp_changes.append(player.get("hp", 0))
            
            for enemy in frame.get("enemies", []):
                if not enemy.get("alive", True):
                    enemy_deaths += 1
                plan = enemy.get("plan", "")
                if plan:
                    tactic_usage[plan] = tactic_usage.get(plan, 0) + 1
        
        # 计算变化
        hp_change = player_hp_changes[-1] - player_hp_changes[0] if len(player_hp_changes) >= 2 else 0
        avg_enemies = total_enemies / len(frames) if frames else 0
        
        prompt = f"""你是军事战术分析师，请分析以下战场数据并给出改进建议。

战场概况（最近{len(frames)}秒）:
- 平均敌人数量: {avg_enemies:.1f}台
- 玩家HP变化: {hp_change:+.0f}
- 敌人死亡: {enemy_deaths}台
- 平均子弹数: {total_bullets/len(frames):.1f}发

战术使用统计:
"""
        for tactic, count in sorted(tactic_usage.items(), key=lambda x: -x[1]):
            prompt += f"- {tactic}: {count}次\n"
        
        prompt += """
请分析:
1. 哪些战术效果好？哪些效果差？
2. 玩家HP变化说明什么？
3. 敌人死亡率低的原因是什么？
4. 给出3条具体的战术改进建议

输出JSON格式:
{
    "good_tactics": ["有效战术1", "有效战术2"],
    "bad_tactics": ["无效战术1", "无效战术2"],
    "analysis": "分析总结",
    "suggestions": [
        "建议1: 具体做法",
        "建议2: 具体做法",
        "建议3: 具体做法"
    ]
}
只输出JSON，不要解释。
"""
        return prompt
    
    def _call_llm(self, prompt):
        """调用LLM进行分析"""
        body = json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3,
            "chat_template_kwargs": {"enable_thinking": False}
        }).encode()
        
        req = urllib.request.Request(
            self.llm_url,
            data=body,
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        
        text = data["choices"][0]["message"]["content"]
        
        # 解析JSON
        import re
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return None
    
    def auto_analyze(self):
        """自动分析（检查间隔）"""
        current_time = time.time()
        if current_time - self.last_analysis_time < self.analysis_interval:
            return None
        
        self.last_analysis_time = current_time
        return self.analyze_battle()


# 全局分析器
_analyzer = None

def get_analyzer():
    """获取分析器实例"""
    global _analyzer
    if _analyzer is None:
        _analyzer = BattleAnalyzer()
    return _analyzer


# 测试
if __name__ == "__main__":
    # 模拟分析
    analyzer = BattleAnalyzer()
    
    # 先记录一些数据
    from battle_recorder import record_frame
    
    test_state = {
        "player_x": 450, "player_y": 580, "player_hp": 500,
        "player_max_hp": 500, "player_angle": 1.5,
        "killed": 10, "wave": 3, "game_time": 30.5,
        "enemies": [
            {"id": 1, "x": 400, "y": 200, "hp": 80, "max_hp": 100, "angle": 3.14, "type": "grunt", "plan": "直攻", "alive": True},
            {"id": 2, "x": 500, "y": 300, "hp": 0, "max_hp": 100, "angle": 0, "type": "fast", "plan": "包抄", "alive": False}
        ],
        "player_bullets": [{"x": 450, "y": 550, "vx": 0, "vy": -10}],
        "enemy_bullets": [{"x": 400, "y": 250, "vx": 2, "vy": 3}],
        "enemy_camp": {"x": 450, "y": 100, "hp": 888, "max_hp": 888, "alive": True},
        "player_camp": {"x": 450, "y": 540, "hp": 888, "max_hp": 888, "alive": True}
    }
    
    for i in range(5):
        record_frame(test_state)
        time.sleep(1.1)
    
    # 分析
    print("开始分析...")
    result = analyzer.analyze_battle(frame_count=5)
    if result:
        print(f"分析结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    else:
        print("分析失败")
