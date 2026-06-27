"""仮想敵団(gauntlet)ベンチ: 自エージェントを実ラダーで見た各アーキタイプと対戦させ勝率を出す.

相手のAIコードは入手不可なので、相手は『同じルールベースAI + そのアーキタイプのデッキ』で代用。
→ デッキ/AI改良が"本物っぽい相手"にどう効くかを提出前に測れる。

使い方:
  python experiments/gauntlet_run.py [games_per_deck]
"""
import sys, os, glob, importlib.util
from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
main = importlib.util.module_from_spec(spec); spec.loader.exec_module(main)


def load_deck(path):
    with open(path) as f:
        return [int(x) for x in f if x.strip()]


def make_opponent(deck):
    """同じ思考ロジックで、指定デッキを使う相手."""
    def opp(obs):
        if obs["select"] is None:
            return deck
        return main.agent(obs)
    return opp


def winrate(my_agent, opp_agent, n):
    w = l = d = 0
    for g in range(n):
        env = make("cabt")
        if g % 2 == 0:
            env.run([my_agent, opp_agent]); r = env.steps[-1][0].reward or 0
        else:
            env.run([opp_agent, my_agent]); r = env.steps[-1][1].reward or 0
        if r > 0: w += 1
        elif r < 0: l += 1
        else: d += 1
    return w, l, d


def run(my_agent=None, n=60):
    my_agent = my_agent or main.agent
    decks = sorted(glob.glob(os.path.join(HERE, "gauntlet", "*.csv")))
    total_w = total = 0
    for path in decks:
        name = os.path.splitext(os.path.basename(path))[0]
        opp = make_opponent(load_deck(path))
        w, l, d = winrate(my_agent, opp, n)
        total_w += w; total += (w + l + d)
        print(f"  vs {name:18s}: 勝{w:3d} 負{l:3d} 分{d:2d}  勝率 {w/(w+l+d):.1%}")
    print(f"  === 総合: {total_w}/{total} = {total_w/total:.1%} ===")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"[gauntlet] 自エージェント(v2) vs 実ラダー・アーキタイプ  各{n}戦")
    run(n=n)
