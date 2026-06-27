"""壁デッキの操縦を自己対戦で最適化（線形ポリシーの重みをヒルクライム）.

手の選択 = 各選択肢の特徴ベクトル・重み で最大のものを選ぶ。
重み w を「メタ代表への勝率」が上がる方向へ少しずつ更新。デプロイは w を埋め込むだけ。
"""
import importlib.util, os, glob, sys, numpy as np
from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
bi = importlib.util.spec_from_file_location("bi", os.path.join(HERE, "build_imitation.py"))
BI = importlib.util.module_from_spec(bi); bi.loader.exec_module(BI)

# 選択肢ごとに異なる特徴だけが手の選択に効く（盤面共通特徴はargmaxに無関係）。
# option type を one-hot(17) + 選択肢別の文脈特徴5 = 22次元。
NTYPE = 17
EXTRA = ["o_inplay_active", "o_own", "o_target_hp_n", "o_index_pos_n", "o_area_n"]
NF = NTYPE + len(EXTRA)


def feat_matrix(obs):
    opts = obs["select"]["option"]
    M = np.zeros((len(opts), NF))
    for i, o in enumerate(opts):
        t = o.get("type", -1)
        if 0 <= t < NTYPE:
            M[i, t] = 1.0
        hp = -1
        try:
            cur = obs.get("current")
            if cur and o.get("area") in (4, 5):
                arr = cur["players"][o.get("playerIndex", 0)].get("bench" if o["area"] == 5 else "active")
                cell = arr[o["index"]] if arr and o["index"] < len(arr) else None
                hp = cell.get("hp", -1) if isinstance(cell, dict) else -1
        except Exception:
            pass
        me = (obs.get("current") or {}).get("yourIndex", 0)
        M[i, NTYPE + 0] = 1.0 if o.get("inPlayArea") == 4 else 0.0
        M[i, NTYPE + 1] = 1.0 if o.get("playerIndex", me) == me else 0.0
        M[i, NTYPE + 2] = hp / 100.0 if hp >= 0 else -1.0
        M[i, NTYPE + 3] = i / 10.0
        M[i, NTYPE + 4] = o.get("area", -1) / 10.0
    return M


def warm_start():
    """ルールベースの type優先度で初期化（= ほぼ現行AI）。"""
    w = np.zeros(NF)
    for t in range(NTYPE):
        w[t] = m.PRIORITY.get(t, m.DEFAULT_PRIORITY)
    w[NTYPE + 0] = 0.3   # active focus
    return w


def make_policy(w):
    def agent(obs):
        sel = obs["select"]
        if sel is None:
            return m.DECK
        opts = sel["option"]
        if not opts:
            return []
        try:
            score = feat_matrix(obs) @ w
            need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
            return [int(i) for i in np.argsort(-score)[:need]]
        except Exception:
            return m.agent(obs)
    return agent


def load(p):
    return [int(x) for x in open(p) if x.strip()]


FIELD = {os.path.basename(p)[:-4]: load(p)
         for p in sorted(glob.glob(os.path.join(HERE, "gauntlet_top", "*.csv")))}
REPS = ["04_persn", "01_Shun", "02_Shun_PI", "09_pokemaster"]  # 壁ミラー/ほのお/ドラパ/メガルカ


def deck_agent(deck, ag):
    def f(o):
        return deck if o["select"] is None else ag(o)
    return f


def winrate(pol, n, reps=REPS):
    A = deck_agent(m.DECK, pol)
    w = tot = 0
    for dn in reps:
        B = deck_agent(FIELD[dn], m.agent)
        for g in range(n):
            env = make("cabt")
            if g % 2 == 0:
                env.run([A, B]); r = env.steps[-1][0].reward or 0
            else:
                env.run([B, A]); r = env.steps[-1][1].reward or 0
            w += r > 0; tot += 1
    return w / tot


def main():
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    rng = np.random.default_rng(0)
    base = winrate(m.agent, n)
    print(f"rule-based 参考勝率: {base:.0%}  (各rep {n}戦)")
    # 初期重み: ルールベース優先度で温め（= 現行AI相当）
    w = warm_start()
    best = winrate(make_policy(w), n)
    print(f"init policy(warm-start=rule): {best:.0%}")
    for it in range(iters):
        cand = w + rng.normal(0, 0.4, NF)   # 一部の重みを摂動
        s = winrate(make_policy(cand), n)
        if s > best:
            w, best = cand, s
            print(f"[{it}] improved -> {best:.0%}")
        else:
            print(f"[{it}] {s:.0%} (keep {best:.0%})")
    np.save(os.path.join(HERE, "wall_policy_w.npy"), w)
    print(f"best policy winrate {best:.0%} vs rule-based {base:.0%}; saved weights")


if __name__ == "__main__":
    main()
