"""1試合だけ実行して結果を1行で出す(プロセス隔離用)。
usage: python run_one_game.py <oppspec> <seat>
  oppspec = 'wall' | path/to/deck.csv
  seat    = 0(planが先攻) | 1(planが後攻)
出力: WIN / LOSE / DRAW  (planから見た結果)
"""
import sys, os, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)


def load(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


PLAN = load(os.path.join(ROOT, "agent", "main_plan.py"), "main_plan")
WALL = load(os.path.join(ROOT, "agent", "main.py"), "wall")

def _safe(o, raw):
    """相手の返す手を必ず合法範囲にクランプ(INVALID没収による偽引分を防ぐ)。"""
    sel = o.get("select")
    if sel is None:
        return raw
    n = len(sel.get("option") or [])
    if n == 0:
        return []
    lo = sel.get("minCount") or 0; hi = sel.get("maxCount") or 1
    idx = [i for i in (raw or []) if isinstance(i, int) and 0 <= i < n]
    seen = []
    for i in idx:
        if i not in seen:
            seen.append(i)
    k = max(0, min(max(lo, 1), hi, n))
    if len(seen) < k:
        for i in range(n):
            if i not in seen:
                seen.append(i)
            if len(seen) >= k:
                break
    return seen[:max(k, lo)]


oppspec = sys.argv[1]; seat = int(sys.argv[2])
if oppspec == "wall":
    opp = WALL.agent
else:
    dk = [int(x) for x in open(oppspec) if x.strip()]
    # 注意: cabtは agent(obs, config) の2引数で呼ぶ。デフォルト引数で deck を
    # 捕捉すると config に上書きされるので、必ず単一引数+外側スコープ参照にする。
    def opp(o): return dk if o["select"] is None else WALL.agent(o)

import random
seed = int.from_bytes(os.urandom(4), "little")
try:
    env = make("cabt", configuration={"seed": seed})
except Exception:
    random.seed(seed)
    env = make("cabt")
if seat == 0:
    env.run([PLAN.agent, opp]); r = env.steps[-1][0].reward
else:
    env.run([opp, PLAN.agent]); r = env.steps[-1][1].reward
r = r or 0
print("WIN" if r > 0 else "LOSE" if r < 0 else "DRAW")
