"""模倣AI(上位の手を学習) vs ルールベースAI を、実メタ相手に最小比較."""
import importlib.util, os, glob, sys, numpy as np, pandas as pd
import lightgbm as lgb
from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
bi = importlib.util.spec_from_file_location("bi", os.path.join(HERE, "build_imitation.py"))
BI = importlib.util.module_from_spec(bi); bi.loader.exec_module(BI)

# --- 模倣モデルを学習（ほのお側=Centiskorch934を含む側、両ディレクトリから） ---
CENTI = 934
r1, y1, g1 = BI.collect(os.path.join(HERE, "replays_top"), marker=CENTI)
r2, y2, g2 = BI.collect(os.path.join(HERE, "replays_fire"), marker=CENTI)
g2 = (g2 + (g1.max() + 1)) if len(g1) else g2
rows = r1 + r2
y = np.concatenate([y1, y2]); groups = np.concatenate([g1, g2])
X = pd.DataFrame(rows).fillna(-1)
COLS = list(X.columns)
MODEL = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                           min_child_samples=30, random_state=0, n_jobs=-1, verbose=-1)
MODEL.fit(X, y)
print(f"imitation model trained on {len(X)} rows / {groups.max()+1} decisions")


def imitation_agent(obs):
    sel = obs["select"]
    if sel is None:
        return m.DECK
    opts = sel["option"]
    if not opts:
        return []
    try:
        bf = BI.board_feats(obs)
        rs = [{**bf, **BI.opt_feats(o, obs, i)} for i, o in enumerate(opts)]
        Xi = pd.DataFrame(rs).reindex(columns=COLS).fillna(-1)
        score = MODEL.predict_proba(Xi)[:, 1]
        need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
        return [int(i) for i in np.argsort(-score)[:need]]
    except Exception:
        return m.agent(obs)   # 失敗時はルールベースに退避


def load(p):
    return [int(x) for x in open(p) if x.strip()]


FIELD = {os.path.basename(p)[:-4]: load(p)
         for p in sorted(glob.glob(os.path.join(HERE, "gauntlet_top", "*.csv")))}
MYDECK = m.DECK


def agent_with(deck, ag):
    def f(o):
        return deck if o["select"] is None else ag(o)
    return f


def winrate(my_ag, field_deck, n):
    A = agent_with(MYDECK, my_ag); B = agent_with(field_deck, m.agent)
    w = l = 0
    for g in range(n):
        env = make("cabt")
        if g % 2 == 0:
            env.run([A, B]); r = env.steps[-1][0].reward or 0
        else:
            env.run([B, A]); r = env.steps[-1][1].reward or 0
        w += r > 0; l += r < 0
    return w, l


def evaluate(label, ag, decks, n):
    tw = tot = 0; parts = []
    for dn in decks:
        w, l = winrate(ag, FIELD[dn], n); tw += w; tot += w + l
        parts.append(f"{dn[3:][:6]}={w}/{w+l}")
    print(f"{label:12s} 総合 {tw}/{tot}={tw/tot:.0%}  | " + " ".join(parts))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    # 代表4デッキ: 壁/ほのお/ドラパルト/メガルカリオ
    reps = ["04_persn", "01_Shun", "02_Shun_PI", "09_pokemaster"]
    print(f"=== 自デッキ(persn壁)で 模倣AI vs ルールAI、代表メタ各{n}戦 ===")
    evaluate("rule-base", m.agent, reps, n)
    evaluate("imitation", imitation_agent, reps, n)
