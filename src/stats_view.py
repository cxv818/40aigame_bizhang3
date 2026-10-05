# v36.0 (2026-10-05) — 36aigame
#
# 口径A (data/tactics_hit_account.json, 原tactics_db.json):
#   命中视角。used=该战术在场时敌子弹命中玩家的记账次数。deaths恒0是正常的
#   (命中事件不含死亡信息)。
# 口径B (AIDirector.plan_stats, 随evolution.json持久化):
#   发令视角。issued=发令次数, hits=执行期间玩家受击, deaths=执行期间我方阵亡。
#
# 两口径不可混算! 本模块唯一职责: 把它们并排换算后输出给LLM一份自洽视图。
import json
import os

HIT_ACCOUNT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "tactics_hit_account.json")

# 旧文件名自动迁移(v33.03一次性的): tactics_db.json → tactics_hit_account.json
_OLD = os.path.join(os.path.dirname(HIT_ACCOUNT), "tactics_db.json")


def _migrate_old():
    if os.path.exists(_OLD) and not os.path.exists(HIT_ACCOUNT):
        try:
            os.replace(_OLD, HIT_ACCOUNT)
            print(f"[stats_view] 历史数据迁移: tactics_db.json → tactics_hit_account.json",
                  flush=True)
        except Exception:
            pass


def _load_hit_account():
    _migrate_old()
    try:
        with open(HIT_ACCOUNT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_merged_report(plan_stats=None, top=5):
    """双口径合并报告。

    plan_stats: AIDirector.plan_stats dict; 不传则只出口径A。
    返回给LLM提示词的自洽文本: 每个数字只来自一个口径, 并标注口径。
    效果分 = 0.6*命中率 + 0.4*存活率 (均基于口径B; 无口径B时显示口径A原始值)
    """
    a = _load_hit_account()
    ps = plan_stats or {}
    lines = ["📈战术统计([发令]视角=发令记账, [命中记]视角=命中记账):"]
    names = list(dict.fromkeys(list(a.keys()) + list(ps.keys())))
    scored = []
    for n in names:
        ha = a.get(n, {})
        p = ps.get(n, {})
        issued = p.get("issued", 0)
        eff = None
        if issued > 0:
            eff = (0.6 * min(1.0, p.get("hits", 0) / issued)
                   + 0.4 * max(0.0, 1.0 - p.get("deaths", 0) / issued))
        scored.append((n, issued, ha.get("used", 0), ha.get("hits", 0), eff))
    scored.sort(key=lambda x: (-x[1], -x[2]))
    if not scored:
        return "📈战术统计: 暂无数据, 多尝试不同战术以积累"
    for n, issued, hit_used, hit_hits, eff in scored[:top]:
        if eff is not None:
            lines.append(f"- {n}: [发令]{issued}次 [命中记]{hit_used}次 综合效果{eff:.2f}")
        else:
            lines.append(f"- {n}: [命中记]{hit_used}次 命中{hit_hits}次 (发令数据待积累)")
    return "\n".join(lines)


if __name__ == "__main__":
    # 离线自测: 模拟两口径数据
    demo_plan = {"直攻": {"issued": 2084, "hits": 2533, "deaths": 137},
                 "集火": {"issued": 2047, "hits": 2644, "deaths": 92}}
    print(get_merged_report(demo_plan))
