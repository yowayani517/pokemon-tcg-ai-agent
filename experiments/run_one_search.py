"""search版を1試合実行(計測/評価用)。usage: python run_one_search.py <oppspec> <seat>"""
import sys, os, importlib.util, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)                 # cg
sys.path.insert(0, os.path.join(ROOT, "agent"))  # import main_plan / main_search
from kaggle_environments import make
import main_search as SEARCH
import main as _wallmod  # agent/main.py = wall

oppspec = sys.argv[1]; seat = int(sys.argv[2])
if oppspec == "wall":
    opp = _wallmod.agent
else:
    dk = [int(x) for x in open(oppspec) if x.strip()]
    def opp(o): return dk if o["select"] is None else _wallmod.agent(o)

t0 = time.time()
env = make("cabt")
if seat == 0:
    env.run([SEARCH.agent, opp]); r = env.steps[-1][0].reward
else:
    env.run([opp, SEARCH.agent]); r = env.steps[-1][1].reward
r = r or 0
dt = time.time() - t0
res = "WIN" if r > 0 else "LOSE" if r < 0 else "DRAW"
print(f"{res} {dt:.1f}s steps={len(env.steps)}")
