"""攻撃ダメージ/きぜつ判定 + KO狙いBoss を v2(+search) と A/B."""
import importlib.util, sys
spec = importlib.util.spec_from_file_location("main", "agent/main.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
DECK, PRI, DEF = m.DECK, m.PRIORITY, m.DEFAULT_PRIORITY

CRUSTLE, DWEBBLE, GRASS, BOSS = 345, 344, 1, 1182
# 自分の攻撃ダメージ（アクティブのカードIDで判定）。うちのデッキはイワパレス120のみ。
ATTACK_DAMAGE = {CRUSTLE: 120, DWEBBLE: 0}


def _cid(o, obs):
    try:
        area, idx, pi = o.get("area"), o.get("index"), o.get("playerIndex", 0)
        if area == 1:
            c = obs["select"]["deck"][idx]; return c.get("id") if isinstance(c, dict) else c
        cur = obs.get("current")
        if not cur: return None
        p = cur["players"][pi]
        arr = {2: p.get("hand"), 4: p.get("active"), 5: p.get("bench")}.get(area)
        if arr and idx < len(arr) and isinstance(arr[idx], dict): return arr[idx].get("id")
    except Exception:
        return None
    return None


def make_agent(search=True, koboss=True):
    def my_damage(obs):
        try:
            cur = obs["current"]; me = cur["yourIndex"]
            a = cur["players"][me].get("active")
            return ATTACK_DAMAGE.get(a[0].get("id"), 0) if a else 0
        except Exception:
            return 0

    def opp_ko_targets(obs):
        """相手ベンチで、こちらの火力で倒せる(hp<=dmg)ポケの (benchIndex, hp) 一覧."""
        out = []
        try:
            cur = obs["current"]; me = cur["yourIndex"]; dmg = my_damage(obs)
            if dmg <= 0: return out
            for i, p in enumerate(cur["players"][1 - me].get("bench") or []):
                hp = p.get("hp", 999)
                if hp <= dmg: out.append((i, hp))
        except Exception:
            pass
        return out

    def score(o, obs):
        t = o.get("type"); s = PRI.get(t, DEF) * 100
        if t in (8, 9) and o.get("inPlayArea") == 4: s += 30
        try:
            me = obs["current"]["yourIndex"] if obs.get("current") else 0
        except Exception:
            me = 0
        # search: 山札サーチでイワパレス優先
        if search and t == 3 and o.get("area") == 1:
            s += {CRUSTLE: 8, DWEBBLE: 4, GRASS: 1}.get(_cid(o, obs), 0)
        # KO-Boss: Bossを撃つのは倒せる相手がいる時だけ
        if koboss and t == 7:  # PLAY
            if _cid(o, obs) == BOSS:
                s += 25 if opp_ko_targets(obs) else -250  # 不発なら強く抑制
        # Boss対象選択(相手ベンチCARD): 倒せる中で最大HP=最大価値を優先
        if koboss and t == 3 and o.get("area") in (4, 5):
            pi = o.get("playerIndex", 0)
            if pi != me:
                try:
                    arr = obs["current"]["players"][pi].get("bench" if o.get("area") == 5 else "active")
                    hp = arr[o.get("index")].get("hp", 999)
                    dmg = my_damage(obs)
                    s += (10 + hp / 20) if hp <= dmg else -5  # 倒せる相手を優先、無理筋は回避
                except Exception:
                    pass
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


def duel(A, B, n=200):
    w = l = d = 0
    for g in range(n):
        env = make("cabt")
        if g % 2 == 0: env.run([A, B]); r = env.steps[-1][0].reward or 0
        else: env.run([B, A]); r = env.steps[-1][1].reward or 0
        if r > 0: w += 1
        elif r < 0: l += 1
        else: d += 1
    return w, l, d


v2 = m.agent
A = make_agent(search=True, koboss=False)   # v2+search
B = make_agent(search=True, koboss=True)    # v2+search+KOボス
w, l, d = duel(B, A); print(f"[KOボス+search] vs [search]      : 勝{w} 負{l} 分{d}  勝率 {w/(w+l+d):.1%}")
w, l, d = duel(B, v2); print(f"[KOボス+search] vs v2(現行)      : 勝{w} 負{l} 分{d}  勝率 {w/(w+l+d):.1%}")
