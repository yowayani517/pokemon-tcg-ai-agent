"""v3候補（複数の強化トグル）を現行v2とA/B対戦して効果を測る."""
import sys, importlib.util
sys.path.insert(0, "experiments")
spec = importlib.util.spec_from_file_location("main", "agent/main.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
DECK, PRI, DEF = m.DECK, m.PRIORITY, m.DEFAULT_PRIORITY

CRUSTLE, DWEBBLE, GRASS = 345, 344, 1


def make_agent(promote=False, search=False, boss=False):
    def _cid(o, obs):
        try:
            area, idx = o.get("area"), o.get("index")
            pi = o.get("playerIndex", 0)
            if area == 1:
                c = obs["select"]["deck"][idx]
                return c.get("id") if isinstance(c, dict) else c
            cur = obs.get("current")
            if not cur:
                return None
            p = cur["players"][pi]
            arr = {2: p.get("hand"), 4: p.get("active"), 5: p.get("bench")}.get(area)
            if arr and idx < len(arr) and isinstance(arr[idx], dict):
                return arr[idx].get("id")
        except Exception:
            return None
        return None

    def score(o, obs):
        t = o.get("type")
        s = PRI.get(t, DEF) * 100
        if t in (8, 9) and o.get("inPlayArea") == 4:  # active focus (v2)
            s += 30
        if t == 3:
            try:
                me = obs["current"]["yourIndex"] if obs.get("current") else 0
                pi = o.get("playerIndex", 0)
                area = o.get("area")
                cid = _cid(o, obs)
                if search and area == 1:  # 山札サーチ=得るので好み可
                    s += {CRUSTLE: 8, DWEBBLE: 4, GRASS: 1}.get(cid, 0)
                if promote and pi == me and area in (4, 5):  # 自分の場=イワパレス優先
                    s += {CRUSTLE: 8, DWEBBLE: 3}.get(cid, 0)
                if boss and pi != me and area in (4, 5):  # 相手呼び出し=低HP優先
                    arr = obs["current"]["players"][pi].get("bench" if area == 5 else "active")
                    hp = arr[o.get("index")].get("hp", 999)
                    s += max(0, 20 - hp / 10)
            except Exception:
                pass
        return s

    def agent(obs):
        sel = obs["select"]
        if sel is None:
            return DECK
        opts = sel["option"]
        if not opts:
            return []
        order = sorted(range(len(opts)), key=lambda i: score(opts[i], obs), reverse=True)
        need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
        return order[:need]
    return agent


from kaggle_environments import make


def duel(A, B, n=160):
    w = l = d = 0
    for g in range(n):
        env = make("cabt")
        if g % 2 == 0:
            env.run([A, B]); r = env.steps[-1][0].reward or 0
        else:
            env.run([B, A]); r = env.steps[-1][1].reward or 0
        if r > 0: w += 1
        elif r < 0: l += 1
        else: d += 1
    return w, l, d


v2 = m.agent
tests = {
    "v3-all(promote+search+boss)": make_agent(True, True, True),
    "promote-only": make_agent(promote=True),
    "search-only": make_agent(search=True),
    "boss-only": make_agent(boss=True),
}
for name, a in tests.items():
    w, l, d = duel(a, v2)
    print(f"{name:32s} vs v2: 勝{w} 負{l} 分{d}  勝率 {w/(w+l+d):.1%}")
