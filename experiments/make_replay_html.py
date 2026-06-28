"""対戦を回して、ブラウザで開ける本格リプレイビューア(replay.html)を生成。
両者の盤面(バトル場/ベンチ/サイド/手札/トラッシュ)、タイプ色のカード描画、
クリックで技・効果パネル、再生バー、EN/JA切替。自己完結の1ファイル。
usage: python make_replay_html.py [opp] [seat]
"""
import sys, os, json, csv, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cg import api
from kaggle_environments import make
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

CARDS = {c.cardId: c for c in api.all_card_data()}
ATK = {a.attackId: a for a in api.all_attack()}
JP = {}
try:
    for row in csv.DictReader(open(os.path.join(ROOT, "data", "JP_Card_Data.csv"), encoding="utf-8-sig")):
        JP[int(row["Card ID"])] = row.get("Card Name", "")
except Exception:
    pass


def load(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


ARCH = load(os.path.join(ROOT, "agent", "main_arch.py"), "main_arch")
oppname = sys.argv[1] if len(sys.argv) > 1 else "starmie"
seat = int(sys.argv[2]) if len(sys.argv) > 2 else 0
if oppname == "starmie":
    opp = load(os.path.join(ROOT, "agent", "main_plan.py"), "main_plan").agent; OPP = "Mega Starmie ex"
elif oppname == "wall":
    opp = load(os.path.join(ROOT, "agent", "main.py"), "wall").agent; OPP = "Crustle Wall"
else:
    dk = [int(x) for x in open(oppname) if x.strip()]
    WALL = load(os.path.join(ROOT, "agent", "main.py"), "wall")
    def opp(o): return dk if o["select"] is None else WALL.agent(o)
    OPP = "Opponent"

env = make("cabt")
order = [ARCH.agent, opp] if seat == 0 else [opp, ARCH.agent]
env.run(order)
me = seat
result = env.steps[-1][me].reward or 0
RES = "WIN" if result > 0 else "LOSE" if result < 0 else "DRAW"
vis = env.steps[0][0].get("visualize") or []

ETYPE = {0: ["C", "#9b9b94"], 1: ["G", "#639922"], 2: ["R", "#D85A30"], 3: ["W", "#378ADD"],
         4: ["L", "#EF9F27"], 5: ["P", "#7F77DD"], 6: ["F", "#993C1D"], 7: ["D", "#444441"],
         8: ["M", "#5F5E5A"], 9: ["N", "#BA7517"], 10: ["A", "#888780"], 11: ["TR", "#72243E"]}


def cardmeta(cid):
    c = CARDS.get(cid)
    if not c:
        return None
    atks = []
    for aid in c.attacks:
        a = ATK.get(aid)
        if a:
            atks.append({"n": a.name, "c": [int(e) for e in a.energies], "d": a.damage, "t": a.text})
    abil = [{"n": s.name, "t": s.text} for s in c.skills]
    stage = "Mega ex" if c.megaEx else "ex" if c.ex else "2進化" if c.stage2 else "1進化" if c.stage1 else "たね" if c.basic else "-"
    typ = int(c.energyType) if c.cardType == 0 else -1
    prize = 3 if c.megaEx else 2 if c.ex else 1
    return {"en": c.name, "jp": JP.get(cid, c.name), "hp": c.hp, "type": typ,
            "stage": stage, "prize": prize, "cat": int(c.cardType), "atk": atks, "abil": abil}


def pk(p):
    if not isinstance(p, dict):
        return None
    return {"id": p["id"], "hp": p.get("hp", 0), "max": p.get("maxHp", 0),
            "en": [int(e) for e in p.get("energies", []) or []],
            "tools": [t.get("id") for t in (p.get("tools", []) or [])]}


def side(pl):
    act = pl.get("active") or []
    return {"active": pk(act[0]) if act and isinstance(act[0], dict) else None,
            "bench": [pk(b) for b in (pl.get("bench") or []) if isinstance(b, dict)],
            "hand": pl.get("handCount", 0), "deck": pl.get("deckCount", 0),
            "prize": len(pl.get("prize") or []), "discard": len(pl.get("discard") or []),
            "cond": [k for k in ("poisoned", "burned", "asleep", "paralyzed", "confused") if pl.get(k)]}


def describe(f):
    sel = f.get("select"); act = f.get("action")
    if not sel or not act:
        return ""
    opts = sel.get("option") or []
    who = (f.get("current") or {}).get("yourIndex", 0)
    idxs = act[who] if isinstance(act, list) and len(act) > who else None
    if not idxs:
        return ""
    T = {0: "数選択", 1: "Yes", 2: "No", 3: "選択", 4: "道具選択", 5: "エネ選択", 6: "エネ選択",
         7: "出す", 8: "エネルギー付け", 9: "進化", 10: "特性", 12: "にげる", 13: "こうげき", 14: "ターン終了"}
    o = opts[idxs[0]] if idxs and idxs[0] < len(opts) else None
    if not o:
        return ""
    txt = T.get(o.get("type"), "")
    return txt


used = set()
frames = []
for f in vis:
    cur = f.get("current")
    if not cur:
        continue
    p0, p1 = cur["players"][0], cur["players"][1]
    s0, s1 = side(p0), side(p1)
    for s in (s0, s1):
        if s["active"]:
            used.add(s["active"]["id"])
            for t in s["active"]["tools"]:
                used.add(t)
        for b in s["bench"]:
            used.add(b["id"])
            for t in b["tools"]:
                used.add(t)
    frames.append({"turn": cur.get("turn", 0), "me": (s0 if me == 0 else s1),
                   "opp": (s1 if me == 0 else s0), "act": describe(f)})

# 連続重複フレームを間引く
clean = []
prev = None
for fr in frames:
    sig = json.dumps([fr["me"], fr["opp"], fr["act"]], ensure_ascii=False)
    if sig != prev:
        clean.append(fr); prev = sig
db = {cid: cardmeta(cid) for cid in used if cardmeta(cid)}
DATA = {"result": RES, "opp": OPP, "etype": ETYPE, "db": db, "frames": clean}

html = open(os.path.join(HERE, "replay_template.html"), encoding="utf-8").read()
html = html.replace("/*DATA*/", json.dumps(DATA, ensure_ascii=False, separators=(",", ":")))
out = os.path.join(HERE, "replay.html")
open(out, "w", encoding="utf-8").write(html)
print(f"{RES} vs {OPP} | frames {len(clean)} | -> {out}  ({len(html)} bytes)")
