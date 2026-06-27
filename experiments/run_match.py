"""ローカルで agent を対戦させ勝率を出す.

使い方:
    python experiments/run_match.py            # rule-based vs random を50戦
    python experiments/run_match.py 100 random # 相手と試合数を指定
"""
import sys, os, time, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agent"))

# agent/main.py を読み込む
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)
my_agent = main.agent

from kaggle_environments import make


def play(n_games=50, opponent="random"):
    wins = draws = losses = 0
    t0 = time.time()
    for g in range(n_games):
        env = make("cabt")
        # 先攻後攻を交互に入れ替えて公平に
        if g % 2 == 0:
            env.run([my_agent, opponent])
            r = env.steps[-1][0].reward or 0
        else:
            env.run([opponent, my_agent])
            r = env.steps[-1][1].reward or 0
        if r > 0:
            wins += 1
        elif r < 0:
            losses += 1
        else:
            draws += 1
    dt = time.time() - t0
    print(f"vs {opponent}: {n_games}戦  勝{wins} 負{losses} 分{draws}  "
          f"勝率 {wins/n_games:.1%}  ({dt:.1f}s, {dt/n_games:.2f}s/戦)")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    opp = sys.argv[2] if len(sys.argv) > 2 else "random"
    play(n, opp)
