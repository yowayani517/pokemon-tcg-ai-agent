"""Mega Starmie ex Planning Agent を 壁 と 現メタ全デッキ相手に評価。"""
import sys, os, glob, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # import cg (api+dll)
from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


PLAN = load(os.path.join(ROOT, "agent", "main_plan.py"), "main_plan")
WALL = load(os.path.join(ROOT, "agent", "main.py"), "wall")


def load_deck(p): return [int(x) for x in open(p) if x.strip()]
FIELD = {os.path.basename(p)[:-4]: load_deck(p) for p in sorted(glob.glob(os.path.join(HERE, "meta_now", "*.csv")))}

N = int(sys.argv[1]) if len(sys.argv) > 1 else 12


def play(p0, p1):
    e = make("cabt"); e.run([p0, p1]); return e


def vs_agent(opp_agent, n):
    """planning(自分) vs opp_agent を n 戦。先後入替。"""
    w = l = 0
    for g in range(n):
        if g % 2 == 0:
            e = play(PLAN.agent, opp_agent); r = e.steps[-1][0].reward or 0
        else:
            e = play(opp_agent, PLAN.agent); r = e.steps[-1][1].reward or 0
        w += r > 0; l += r < 0
    return w, l


def main():
    print(f"=== Mega Starmie ex Planning Agent gauntlet ({N} games each) ===", flush=True)
    # 1) vs 壁(我々の現提出)
    w, l = vs_agent(WALL.agent, N)
    print(f"vs 壁(我々の現提出)   : {w}/{w+l}  ({w/max(1,w+l):.0%})", flush=True)
    # 2) vs 現メタ各デッキ(壁ヒューリスティックが操縦)
    tw = tot = 0
    for dn, dk in FIELD.items():
        def opp(o, _dk=dk): return _dk if o["select"] is None else WALL.agent(o)
        w, l = vs_agent(opp, N)
        tw += w; tot += w + l
        print(f"vs {dn[3:][:12]:12s}: {w}/{w+l}  ({w/max(1,w+l):.0%})", flush=True)
    print(f"--- 対メタ総合: {tw}/{tot}  ({tw/max(1,tot):.0%}) ---", flush=True)


if __name__ == "__main__":
    main()
