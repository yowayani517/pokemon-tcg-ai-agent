"""ハイブリッド(現m.DECK)を固める: vs純壁 直接対戦 + vs全10デッキ."""
import importlib.util, os, glob, sys
from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def load(p): return [int(x) for x in open(p) if x.strip()]
FIELD = {os.path.basename(p)[:-4]: load(p)
         for p in sorted(glob.glob(os.path.join(HERE, "gauntlet_top", "*.csv")))}
WALL = load(os.path.join(HERE, "gauntlet_top", "04_persn.csv"))


def da(deck):
    def f(o): return deck if o["select"] is None else m.agent(o)
    return f


def duel(deckA, deckB, n):
    A, B = da(deckA), da(deckB); w = l = 0
    for g in range(n):
        env = make("cabt")
        if g % 2 == 0:
            env.run([A, B]); r = env.steps[-1][0].reward or 0
        else:
            env.run([B, A]); r = env.steps[-1][1].reward or 0
        w += r > 0; l += r < 0
    return w, l


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    print("=== ハイブリッド vs 純壁(persn) 直接対戦 (30戦) ===")
    w, l = duel(m.DECK, WALL, 30)
    print(f"  ハイブリッド {w}-{l}  勝率 {w/(w+l):.0%}  (>50%ならハイブリッドが強い)")
    print(f"=== ハイブリッド vs 全10デッキ 各{n}戦 ===")
    tw = tot = 0
    for dn, dk in FIELD.items():
        if dn == "kuritan_now":
            continue
        w, l = duel(m.DECK, dk, n); tw += w; tot += w + l
        print(f"  vs {dn[:14]:14s}: {w}-{l}  {w/(w+l):.0%}")
    print(f"  === 総合 {tw}/{tot} = {tw/tot:.0%} ===  (純壁ルールAIは約74%)")


if __name__ == "__main__":
    main()
