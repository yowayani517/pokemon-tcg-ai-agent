"""候補デッキを『上位10デッキの実メタ』にぶつけて勝率を測る（全て自前AIで操縦）."""
import importlib.util, os, glob, sys
from kaggle_environments import make
from kaggle_environments.envs.cabt.cg.game import battle_start, battle_finish

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def load(p):
    return [int(x) for x in open(p) if x.strip()]


FIELD = {os.path.basename(p)[:-4]: load(p)
         for p in sorted(glob.glob(os.path.join(HERE, "gauntlet_top", "*.csv")))}


def agent_with(deck):
    def f(o):
        return deck if o["select"] is None else m.agent(o)
    return f


def legal(deck):
    try:
        battle_start(deck, deck); battle_finish(); return True
    except Exception:
        return False


def winrate(cand_deck, field_deck, n):
    A, B = agent_with(cand_deck), agent_with(field_deck)
    w = l = 0
    for g in range(n):
        env = make("cabt")
        if g % 2 == 0:
            env.run([A, B]); r = env.steps[-1][0].reward or 0
        else:
            env.run([B, A]); r = env.steps[-1][1].reward or 0
        w += r > 0; l += r < 0
    return w, l


def evaluate(name, deck, n):
    if not legal(deck):
        print(f"{name}: ILLEGAL deck, skip"); return
    tot_w = tot = 0; parts = []
    for fname, fdeck in FIELD.items():
        w, l = winrate(deck, fdeck, n); tot_w += w; tot += w + l
        parts.append(f"{fname[3:][:6]}={w}/{w+l}")
    print(f"{name:16s} 総合 {tot_w}/{tot}={tot_w/tot:.0%}  | " + " ".join(parts))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    cands = sys.argv[2:] if len(sys.argv) > 2 else ["01_Shun", "03_mm-1989", "04_persn"]
    print(f"=== 候補デッキ vs 上位10デッキ(各{n}戦) — 全て自前AI操縦 ===")
    for c in cands:
        evaluate(c, FIELD[c], n)
