"""RL方策(LightGBM)をnumpyだけで動くmain_rl.pyに変換(sandbox依存ゼロのデプロイ)."""
import joblib, json, os, base64, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
model = joblib.load(os.path.join(HERE, "rl_model.pkl"))
dump = model.booster_.dump_model()
DECK = [int(x) for x in open(os.path.join(HERE, "meta_now", "01_Praxel.csv")) if x.strip()]

# --- 木をフラットな配列に変換 ---
feat = []; thr = []; left = []; right = []; leaf = []; defleft = []; roots = []


def flatten(node):
    """node を配列に追加し、そのindexを返す。"""
    idx = len(feat)
    feat.append(0); thr.append(0.0); left.append(-1); right.append(-1); leaf.append(0.0); defleft.append(1)
    if "leaf_value" in node:
        feat[idx] = -1; leaf[idx] = float(node["leaf_value"])
        return idx
    feat[idx] = int(node["split_feature"])
    thr[idx] = float(node["threshold"])
    defleft[idx] = 1 if node.get("default_left", True) else 0
    li = flatten(node["left_child"]); ri = flatten(node["right_child"])
    left[idx] = li; right[idx] = ri
    return idx


for t in dump["tree_info"]:
    roots.append(flatten(t["tree_structure"]))

A = lambda x, d: base64.b64encode(np.asarray(x, dtype=d).tobytes()).decode()
arrays = {
    "feat": A(feat, np.int32), "thr": A(thr, np.float32),
    "left": A(left, np.int32), "right": A(right, np.int32),
    "leaf": A(leaf, np.float32), "defleft": A(defleft, np.int8),
    "roots": A(roots, np.int32),
}
print(f"trees={len(roots)} nodes={len(feat)}")

# --- 特徴量関数とエージェント本体(自己完結) ---
FK = ["sel_type", "n_opt", "maxcount", "turn", "energy_attached", "supporter_played",
      "my_act_hp", "my_act_en", "my_bench", "my_hand", "my_prize",
      "op_act_hp", "op_act_en", "op_bench", "op_hand", "op_prize",
      "o_type", "o_area", "o_inplay_active", "o_index_pos", "o_own", "o_target_hp",
      "o_is_attacker", "o_atk_need_gap"]

TEMPLATE = '''"""PTCG AI - 自己対戦RLで学習した純センチスコーチ操縦AI (numpy推論, 依存ゼロ)."""
import base64
import numpy as np

DECK = {deck}
ATTACKERS = {attackers}
FK = {fk}
_B = {arrays}


def _dec(k, d):
    return np.frombuffer(base64.b64decode(_B[k]), dtype=d)


FEAT = _dec("feat", np.int32); THR = _dec("thr", np.float32)
LEFT = _dec("left", np.int32); RIGHT = _dec("right", np.int32)
LEAF = _dec("leaf", np.float32); DEFLEFT = _dec("defleft", np.int8)
ROOTS = _dec("roots", np.int32)


def _predict(X):
    """X: (n, F) -> 各行の予測値(全木のleaf合計)."""
    n = X.shape[0]; out = np.zeros(n)
    for r in ROOTS:
        node = np.full(n, r, dtype=np.int64)
        active = np.ones(n, dtype=bool)
        for _ in range(64):
            leaf_mask = active & (FEAT[node] < 0)
            if leaf_mask.any():
                out[leaf_mask] += LEAF[node[leaf_mask]]
                active = active & ~leaf_mask
            if not active.any():
                break
            f = FEAT[node]; t = THR[node]
            xv = X[np.arange(n), np.where(f >= 0, f, 0)]
            goleft = xv <= t
            nan = np.isnan(xv)
            goleft = np.where(nan, DEFLEFT[node] == 1, goleft)
            nxt = np.where(goleft, LEFT[node], RIGHT[node])
            node = np.where(active, nxt, node)
        # 残り(深さ超過)はleafとして加算
        rem = active & (FEAT[node] < 0)
        out[rem] += LEAF[node[rem]]
    return out


def _poke(obs, area, idx):
    try:
        cur = obs["current"]; me = cur["yourIndex"]; p = cur["players"][me]
        arr = (p.get("active") if area == 4 else p.get("bench")) or []
        return arr[idx] if 0 <= idx < len(arr) and isinstance(arr[idx], dict) else None
    except Exception:
        return None


def _board(obs):
    cur = obs.get("current"); sel = obs["select"]
    f = {{"sel_type": sel.get("type", -1), "n_opt": len(sel["option"]),
          "maxcount": sel.get("maxCount", 1)}}
    if not cur:
        return f
    me = cur.get("yourIndex", 0)
    f["turn"] = cur.get("turn", 0)
    f["energy_attached"] = int(bool(cur.get("energyAttached")))
    f["supporter_played"] = int(bool(cur.get("supporterPlayed")))
    for who, pi in (("my", me), ("op", 1 - me)):
        p = cur["players"][pi]; a = p.get("active") or []
        a0 = a[0] if (a and isinstance(a[0], dict)) else None
        f[who + "_act_hp"] = a0.get("hp", 0) if a0 else 0
        f[who + "_act_en"] = len(a0.get("energies", [])) if a0 else 0
        f[who + "_bench"] = len(p.get("bench") or [])
        f[who + "_hand"] = p.get("handCount", len(p.get("hand") or []))
        f[who + "_prize"] = len(p.get("prize") or [])
    return f


def _opt(o, obs):
    cur = obs.get("current"); me = cur.get("yourIndex", 0) if cur else 0
    f = {{"o_type": o.get("type", -1), "o_area": o.get("area", -1),
          "o_inplay_active": int(o.get("inPlayArea") == 4),
          "o_index_pos": 0, "o_own": int(o.get("playerIndex", me) == me)}}
    hp = -1
    try:
        if cur and o.get("area") in (4, 5):
            arr = cur["players"][o.get("playerIndex", 0)].get("bench" if o["area"] == 5 else "active")
            c = arr[o["index"]] if arr and o["index"] < len(arr) else None
            hp = c.get("hp", -1) if isinstance(c, dict) else -1
    except Exception:
        pass
    f["o_target_hp"] = hp
    is_atk = gap = 0
    try:
        if o.get("type") == 8:
            pk = _poke(obs, o.get("inPlayArea"), o.get("inPlayIndex", 0))
            if pk and pk.get("id") in ATTACKERS:
                is_atk = 1; gap = ATTACKERS[pk["id"]] - len(pk.get("energies", []) or [])
    except Exception:
        pass
    f["o_is_attacker"] = is_atk; f["o_atk_need_gap"] = gap
    return f


def _vec(o, obs, bf):
    d = dict(bf); d.update(_opt(o, obs))
    return [d.get(k, -1) if isinstance(d.get(k, -1), (int, float)) else -1 for k in FK]


def agent(obs):
    sel = obs["select"]
    if sel is None:
        return DECK
    opts = sel["option"]
    if not opts:
        return []
    need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
    try:
        bf = _board(obs)
        X = np.array([_vec(o, obs, bf) for o in opts], dtype=float)
        sc = _predict(X)
        return [int(i) for i in np.argsort(-sc)[:need]]
    except Exception:
        return list(range(need))
'''

out = TEMPLATE.format(deck=DECK, attackers={678: 2, 674: 3, 677: 2, 673: 3, 676: 1}, fk=FK, arrays=json.dumps(arrays))
path = os.path.join(ROOT, "agent", "main_rl2.py")
open(path, "w", encoding="utf-8").write(out)
print("wrote", path, f"({os.path.getsize(path)} bytes)")
