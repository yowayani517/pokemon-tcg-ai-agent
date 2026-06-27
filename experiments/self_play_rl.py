"""自己対戦モンテカルロ価値学習でコンボを実行できるAIを育てる.

各決定で選んだ手の特徴を記録し、その試合の勝敗(1/0)でラベル付け。
モデル f(盤面,選択肢)->勝率 を学習し、それで貪欲に指す(=方策改善)。
ε-greedyで探索しつつ反復(方策反復)。デッキはPraxel(コンボ=学習価値が高い)。
"""
import importlib.util, os, glob, sys, numpy as np, random
import lightgbm as lgb
from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
bi = importlib.util.spec_from_file_location("bi", os.path.join(HERE, "build_imitation.py"))
BI = importlib.util.module_from_spec(bi); bi.loader.exec_module(BI)

# 現メタ実ラダー1位の Mega Starmie ex (水) デッキを RL で操縦学習。学習相手は現メタ。
DECK_FILE = os.path.join(HERE, "meta_now", "00_starmie_top1.csv")
PRAXEL = [int(x) for x in open(DECK_FILE) if x.strip()]
# 本物のアタッカー -> 必要エネ。メガスターミーex(1031)=ネビュラビーム3エネ210・壁貫通が主軸
ATTACKERS = {1031: 3, 1030: 1, 666: 1}   # MegaStarmie ex / Staryu / Cinderace
FK = ["sel_type", "n_opt", "maxcount", "turn", "energy_attached", "supporter_played",
      "my_act_hp", "my_act_en", "my_bench", "my_hand", "my_prize",
      "op_act_hp", "op_act_en", "op_bench", "op_hand", "op_prize",
      "o_type", "o_area", "o_inplay_active", "o_index_pos", "o_own", "o_target_hp",
      "o_is_attacker", "o_atk_need_gap"]


def feat_vec(o, obs, bf):
    d = {**bf, **BI.opt_feats(o, obs, 0)}
    v = [d.get(k, -1) if isinstance(d.get(k, -1), (int, float)) else -1 for k in FK[:-2]]
    # コンボ用の追加特徴: この選択肢が本物アタッカーの育成か
    is_atk = atk_gap = 0
    try:
        if o.get("type") == 8:
            poke = _poke(obs, o.get("inPlayArea"), o.get("inPlayIndex", 0))
            if poke and poke.get("id") in ATTACKERS:
                is_atk = 1
                atk_gap = ATTACKERS[poke["id"]] - len(poke.get("energies", []) or [])
    except Exception:
        pass
    return v + [is_atk, atk_gap]


def _poke(obs, area, idx):
    try:
        cur = obs["current"]; me = cur["yourIndex"]; p = cur["players"][me]
        arr = (p.get("active") if area == 4 else p.get("bench")) or []
        return arr[idx] if 0 <= idx < len(arr) and isinstance(arr[idx], dict) else None
    except Exception:
        return None


def make_logging_agent(model, epsilon, log):
    """現方策(model)でε-greedyに指し、選んだ手の特徴を log に記録するエージェント."""
    def agent(obs):
        sel = obs["select"]
        if sel is None:
            return PRAXEL
        opts = sel["option"]
        if not opts:
            return []
        need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
        bf = BI.board_feats(obs)
        feats = [feat_vec(o, obs, bf) for o in opts]
        if model is None or random.random() < epsilon:
            order = random.sample(range(len(opts)), len(opts))
        else:
            sc = model.predict(np.array(feats))
            order = list(np.argsort(-sc))
        chosen = order[:need]
        for i in chosen:
            log.append(feat_vec(opts[i], obs, bf))   # 記録(後で勝敗ラベル)
        log_marks.append(len(chosen))                 # この決定の手数
        return [int(i) for i in chosen]
    return agent


log_marks = []


def load(p): return [int(x) for x in open(p) if x.strip()]
FIELD = {os.path.basename(p)[:-4]: load(p) for p in sorted(glob.glob(os.path.join(HERE, "meta_now", "*.csv")))}
FIELD_DECKS = list(FIELD.values())


def selfplay_collect(model, n, epsilon):
    X, Y = [], []
    for g in range(n):
        log = []; log_marks.clear()
        ag = make_logging_agent(model, epsilon, log)
        opp = FIELD_DECKS[g % len(FIELD_DECKS)]
        def opp_ag(o): return opp if o["select"] is None else m.agent(o)
        env = make("cabt")
        start = len(X)
        if g % 2 == 0:
            env.run([ag, opp_ag]); r = env.steps[-1][0].reward or 0
        else:
            env.run([opp_ag, ag]); r = env.steps[-1][1].reward or 0
        y = 1.0 if r > 0 else 0.0
        for v in log:
            X.append(v); Y.append(y)
    return np.array(X, float), np.array(Y, float)


def eval_policy(model, n=14):
    def ag(o):
        sel = o["select"]
        if sel is None: return PRAXEL
        opts = sel["option"]
        if not opts: return []
        bf = BI.board_feats(o)
        sc = model.predict(np.array([feat_vec(x, o, bf) for x in opts]))
        need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
        return [int(i) for i in np.argsort(-sc)[:need]]
    tw = tot = 0
    for dn, dk in FIELD.items():
        if dn == "praxel_now": continue
        w = l = 0
        for g in range(n):
            def opp_ag(o): return dk if o["select"] is None else m.agent(o)
            e = make("cabt")
            if g % 2 == 0: e.run([ag, opp_ag]); r = e.steps[-1][0].reward or 0
            else: e.run([opp_ag, ag]); r = e.steps[-1][1].reward or 0
            w += r > 0; l += r < 0
        tw += w; tot += w + l
        print(f"    vs {dn[3:][:9]:9s}: {w}/{w+l}")
    return tw / tot


def main():
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    games = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    model = None
    Xall = np.zeros((0, len(FK))); Yall = np.zeros(0)
    for it in range(iters):
        eps = max(0.15, 0.6 - 0.15 * it)
        X, Y = selfplay_collect(model, games, eps)
        Xall = np.vstack([Xall, X]); Yall = np.concatenate([Yall, Y])
        model = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
                                  min_child_samples=40, random_state=it, n_jobs=-1, verbose=-1)
        model.fit(Xall, Yall)
        print(f"[iter {it}] eps={eps:.2f} data={len(Yall)} 勝率(全データ平均)={Yall.mean():.2f}")
        wr = eval_policy(model)
        print(f"  => [iter {it}] 学習方策 vs メタ 総合勝率 {wr:.0%}", flush=True)
        import joblib
        joblib.dump(model, os.path.join(HERE, "rl_model.pkl"))
        np.save(os.path.join(HERE, "rl_X.npy"), Xall); np.save(os.path.join(HERE, "rl_Y.npy"), Yall)


if __name__ == "__main__":
    main()
