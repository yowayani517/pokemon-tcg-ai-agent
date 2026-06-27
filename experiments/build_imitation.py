"""模倣学習: 上位リプレイの勝者の手を学習し、的中率を検証する.

各決定点を (盤面特徴 + 各選択肢特徴) の行群に展開し、選ばれた選択肢=1 で
LightGBMランカーを学習。グループCVで top-1 的中率(モデルのargmaxが実際の手と一致)を測る。
"""
import json, glob, os, numpy as np
import lightgbm as lgb
from sklearn.model_selection import GroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
REP = os.path.join(HERE, "replays_top")


def board_feats(obs):
    cur = obs.get("current")
    sel = obs["select"]
    f = {"sel_type": sel.get("type", -1), "n_opt": len(sel["option"]),
         "maxcount": sel.get("maxCount", 1), "mincount": sel.get("minCount", 0) or 0}
    if not cur:
        return f
    me = cur.get("yourIndex", 0)
    f["turn"] = cur.get("turn", 0)
    f["energy_attached"] = int(bool(cur.get("energyAttached")))
    f["supporter_played"] = int(bool(cur.get("supporterPlayed")))
    for who, pi in (("my", me), ("op", 1 - me)):
        p = cur["players"][pi]
        a = p.get("active") or []
        a0 = a[0] if (a and isinstance(a[0], dict)) else None
        f[f"{who}_act_hp"] = a0.get("hp", 0) if a0 else 0
        f[f"{who}_act_en"] = len(a0.get("energies", [])) if a0 else 0
        f[f"{who}_bench"] = len(p.get("bench") or [])
        f[f"{who}_hand"] = p.get("handCount", len(p.get("hand") or []))
        f[f"{who}_prize"] = len(p.get("prize") or [])
        f[f"{who}_discard"] = len(p.get("discard") or [])
    return f


def opt_feats(o, obs, i):
    cur = obs.get("current")
    me = cur.get("yourIndex", 0) if cur else 0
    f = {"o_type": o.get("type", -1), "o_area": o.get("area", -1),
         "o_inplay_active": int(o.get("inPlayArea") == 4),
         "o_index_pos": i, "o_own": int(o.get("playerIndex", me) == me)}
    # 対象ポケモンのHP（あれば）
    hp = -1
    try:
        if cur and o.get("area") in (4, 5):
            arr = cur["players"][o.get("playerIndex", 0)].get("bench" if o["area"] == 5 else "active")
            cell = arr[o["index"]] if arr and o["index"] < len(arr) else None
            hp = cell.get("hp", -1) if isinstance(cell, dict) else -1
    except Exception:
        pass
    f["o_target_hp"] = hp
    return f


def _deck_of(steps, pi):
    for st in steps:
        a = st[pi].get("action")
        if isinstance(a, list) and len(a) >= 40 and all(isinstance(x, int) for x in a):
            return a
    return []


def collect(rep_dir=None, marker=None):
    """rep_dir 内のリプレイから学習データを作る。
    marker(カードID)指定時はそのカードを含むデッキの側=学習対象（同一アーキタイプ限定）。
    未指定なら勝者側。"""
    rep_dir = rep_dir or REP
    rows, labels, groups = [], [], []
    gid = 0
    for fp in sorted(glob.glob(os.path.join(rep_dir, "*replay*.json"))):
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        rew = d.get("rewards") or [0, 0]
        if marker is not None:
            side = 0 if marker in _deck_of(d["steps"], 0) else (1 if marker in _deck_of(d["steps"], 1) else None)
            if side is None:
                continue
        else:
            side = 0 if (rew[0] or 0) > (rew[1] or 0) else 1
        for step in d["steps"]:
            ps = step[side]
            obs, act = ps.get("observation"), ps.get("action")
            if not isinstance(obs, dict) or not obs.get("select"):
                continue
            opts = obs["select"].get("option")
            if not opts or not isinstance(act, list):
                continue
            if len(act) >= 40:   # デッキ選択ステップは除外
                continue
            chosen = set(a for a in act if isinstance(a, int) and a < len(opts))
            if not chosen:
                continue
            bf = board_feats(obs)
            for i, o in enumerate(opts):
                row = {**bf, **opt_feats(o, obs, i)}
                rows.append(row); labels.append(int(i in chosen)); groups.append(gid)
            gid += 1
    return rows, np.array(labels), np.array(groups)


def main():
    rows, y, groups = collect()
    import pandas as pd
    X = pd.DataFrame(rows).fillna(-1)
    print(f"decisions: {groups.max()+1 if len(groups) else 0}  option-rows: {len(X)}  feats: {X.shape[1]}")
    print("chosen rate:", y.mean().round(3))

    gkf = GroupKFold(n_splits=5)
    # top-1 的中率: 各決定でモデルスコア最大の選択肢が実際に選ばれたか
    hit = tot = 0; base_hit = 0
    for tri, vai in gkf.split(X, y, groups):
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                               min_child_samples=30, random_state=0, n_jobs=-1, verbose=-1)
        m.fit(X.iloc[tri], y[tri])
        pv = m.predict_proba(X.iloc[vai])[:, 1]
        vg = groups[vai]
        import pandas as pd2
        df = pd.DataFrame({"g": vg, "p": pv, "y": y[vai], "type": X.iloc[vai]["o_type"].values})
        for g, sub in df.groupby("g"):
            tot += 1
            if sub.loc[sub["p"].idxmax(), "y"] == 1:
                hit += 1
            # baseline: ランダムに1つ選ぶ期待的中
            base_hit += sub["y"].sum() / len(sub)
    print(f"top-1 的中率(モデル): {hit/tot:.1%}   ランダム期待: {base_hit/tot:.1%}   (決定数 {tot})")


if __name__ == "__main__":
    main()
