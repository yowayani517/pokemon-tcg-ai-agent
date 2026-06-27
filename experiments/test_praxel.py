"""Praxel(#1) のデッキ＋プレイ手順をAIに落とし込んでgauntletで壁と比較."""
import importlib.util, os, glob, sys
from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("main", os.path.join(ROOT, "agent", "main.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

PRAXEL = [int(x) for x in open(os.path.join(HERE, "gauntlet_top", "praxel_now.csv")) if x.strip()]
# 本物のアタッカー -> 必要エネ数。ここにエネを集中させる(Solrock/Lunatoneには貯めない)
ATTACKERS = {678: 2, 674: 3, 677: 2, 673: 3}   # Lucario/Hariyama/Riolu/Makuhita
PPP = 1141                                       # Premium Power Pro (殴る前に連打)


def _poke(obs, area, idx):
    try:
        cur = obs["current"]; me = cur["yourIndex"]; p = cur["players"][me]
        arr = p.get("active") if area == 4 else p.get("bench")
        arr = arr or []
        return arr[idx] if 0 <= idx < len(arr) and isinstance(arr[idx], dict) else None
    except Exception:
        return None


def praxel_score(o, obs):
    t = o.get("type")
    s = m.PRIORITY.get(t, m.DEFAULT_PRIORITY) * 100   # items(7)が高い=PPP/Gongを攻撃前に自動連打
    if t == 8:                                         # エネ付け: 本物のアタッカーに集中
        poke = _poke(obs, o.get("inPlayArea"), o.get("inPlayIndex", 0))
        if poke is not None:
            cid = poke.get("id"); ne = len(poke.get("energies", []) or [])
            need = ATTACKERS.get(cid)
            if need is not None and ne < need:
                # 育成中アタッカー。アクティブで瀕死なら見切り
                hp = poke.get("hp", 999); mhp = poke.get("maxHp", hp) or hp or 1
                if o.get("inPlayArea") == 4 and hp <= 0.3 * mhp:
                    s -= 120
                else:
                    s += 70 - ne * 5     # 少ない方から埋める
            elif need is not None:
                s -= 300                  # もう足りてる -> 付けない
            else:
                s += 5                    # Solrock等: ほぼ付けない(1個まで)
    elif t == 9 and o.get("inPlayArea") == 4:
        s += 30
    elif t == 3 and o.get("area") in (4, 5):           # Boss対象: 脅威スナイプ流用
        s += m._boss_target_score(o, obs)
    return s


def praxel_agent(obs):
    sel = obs["select"]
    if sel is None:
        return PRAXEL
    opts = sel["option"]
    if not opts:
        return []
    order = sorted(range(len(opts)), key=lambda i: praxel_score(opts[i], obs), reverse=True)
    need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
    return order[:need]


def load(p): return [int(x) for x in open(p) if x.strip()]
FIELD = {os.path.basename(p)[:-4]: load(p) for p in sorted(glob.glob(os.path.join(HERE, "gauntlet_top", "*.csv")))}


def da(deck, ag):
    def f(o): return deck if o["select"] is None else ag(o)
    return f


def wr(my_deck, my_ag, opp_deck, n):
    A, B = da(my_deck, my_ag), da(opp_deck, m.agent); w = l = 0
    for g in range(n):
        e = make("cabt")
        if g % 2 == 0:
            e.run([A, B]); r = e.steps[-1][0].reward or 0
        else:
            e.run([B, A]); r = e.steps[-1][1].reward or 0
        w += r > 0; l += r < 0
    return w, l


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    reps = ["04_persn", "01_Shun", "03_mm-1989", "02_Shun_PI", "09_pokemaster", "praxel_now"]
    print(f"=== Praxelデッキ+手順AI vs メタ 各{n}戦 ===")
    tw = tot = 0
    for dn in reps:
        if dn == "praxel_now":
            continue
        w, l = wr(PRAXEL, praxel_agent, FIELD[dn], n); tw += w; tot += w + l
        print(f"  vs {dn[3:][:9]:9s}: {w}-{l} {w/(w+l):.0%}")
    print(f"  総合 {tw}/{tot}={tw/tot:.0%}")
    # 直接対決: Praxel手順 vs 我々の壁
    w, l = wr(PRAXEL, praxel_agent, m.DECK, 30)
    print(f"  Praxel手順 vs 我々の壁(直接30戦): {w}-{l} {w/(w+l):.0%}")
