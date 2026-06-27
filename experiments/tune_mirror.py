"""ミラー強化候補を gauntlet(実ラダー・アーキタイプ) で評価."""
import importlib.util, os, glob, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
DECK, PRI, DEF = m.DECK, m.PRIORITY, m.DEFAULT_PRIORITY
CRUSTLE, DWEBBLE, GRASS, BOSS = 345, 344, 1, 1182
ATTACK_DAMAGE = {CRUSTLE: 120, DWEBBLE: 0}


def _cid(o, obs):
    try:
        area, idx, pi = o.get("area"), o.get("index"), o.get("playerIndex", 0)
        if area == 1:
            c = obs["select"]["deck"][idx]; return c.get("id") if isinstance(c, dict) else c
        cur = obs.get("current");  p = cur["players"][pi]
        arr = {2: p.get("hand"), 4: p.get("active"), 5: p.get("bench")}.get(area)
        if arr and idx < len(arr) and isinstance(arr[idx], dict): return arr[idx].get("id")
    except Exception: return None
    return None


def make_agent(search=False, promote=False, koboss=False):
    def my_dmg(obs):
        try:
            cur = obs["current"]; a = cur["players"][cur["yourIndex"]].get("active")
            return ATTACK_DAMAGE.get(a[0].get("id"), 0) if a else 0
        except Exception: return 0

    def ko_targets(obs):
        try:
            cur = obs["current"]; me = cur["yourIndex"]; dmg = my_dmg(obs)
            return [1 for p in (cur["players"][1-me].get("bench") or []) if p.get("hp", 999) <= dmg] if dmg > 0 else []
        except Exception: return []

    def score(o, obs):
        t = o.get("type"); s = PRI.get(t, DEF) * 100
        if t in (8, 9) and o.get("inPlayArea") == 4: s += 30
        try: me = obs["current"]["yourIndex"]
        except Exception: me = 0
        if search and t == 3 and o.get("area") == 1:
            s += {CRUSTLE: 8, DWEBBLE: 4, GRASS: 1}.get(_cid(o, obs), 0)
        if promote and t == 3 and o.get("playerIndex", 0) == me and o.get("area") in (4, 5):
            s += {CRUSTLE: 8, DWEBBLE: 3}.get(_cid(o, obs), 0)
        if koboss and t == 7 and _cid(o, obs) == BOSS:
            s += 25 if ko_targets(obs) else -250
        if koboss and t == 3 and o.get("area") in (4, 5) and o.get("playerIndex", 0) != me:
            try:
                arr = obs["current"]["players"][o["playerIndex"]].get("bench" if o["area"] == 5 else "active")
                hp = arr[o["index"]].get("hp", 999)
                s += (10 + hp / 20) if hp <= my_dmg(obs) else -5
            except Exception: pass
        return s

    def agent(obs):
        sel = obs["select"]
        if sel is None: return DECK
        opts = sel["option"]
        if not opts: return []
        order = sorted(range(len(opts)), key=lambda i: score(opts[i], obs), reverse=True)
        need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
        return order[:need]
    return agent


from kaggle_environments import make
def opp_with(deck):
    def opp(obs): return deck if obs["select"] is None else m.agent(obs)
    return opp
def load(p): return [int(x) for x in open(p) if x.strip()]
def wr(A, opp, n):
    w = l = 0
    for g in range(n):
        env = make("cabt")
        if g % 2 == 0: env.run([A, opp]); r = env.steps[-1][0].reward or 0
        else: env.run([opp, A]); r = env.steps[-1][1].reward or 0
        if r > 0: w += 1
        elif r < 0: l += 1
    return w, l

decks = {os.path.splitext(os.path.basename(p))[0]: load(p) for p in sorted(glob.glob(os.path.join(HERE, "gauntlet", "*.csv")))}
cands = {
    "base(v2)": m.agent,
    "mirror+(koboss+promote+search)": make_agent(search=True, promote=True, koboss=True),
}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
for cname, ag in cands.items():
    tot_w = tot = 0; line = []
    for dname, dk in decks.items():
        w, l = wr(ag, opp_with(dk), N); tot_w += w; tot += w + l
        line.append(f"{dname[:8]}={w/(w+l):.0%}")
    print(f"{cname:34s}  " + "  ".join(line) + f"  | 総合 {tot_w/tot:.1%}")
