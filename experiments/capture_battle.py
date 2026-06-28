"""main_arch(我々のAI=P0)の1試合を回し、各決定の盤面+選んだ手を battle_log.json に記録。
バトルビューア用。usage: python capture_battle.py [opp] [seat]"""
import sys, os, json, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cg import api
from kaggle_environments import make
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CARD = {c.cardId: c for c in api.all_card_data()}


def load(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


ARCH = load(os.path.join(ROOT, "agent", "main_arch.py"), "main_arch")
oppname = sys.argv[1] if len(sys.argv) > 1 else "starmie"
seat = int(sys.argv[2]) if len(sys.argv) > 2 else 0
if oppname == "starmie":
    opp = load(os.path.join(ROOT, "agent", "main_plan.py"), "main_plan").agent
    opp_label = "Mega Starmie ex"
elif oppname == "wall":
    opp = load(os.path.join(ROOT, "agent", "main.py"), "wall").agent
    opp_label = "Crustle Wall"
else:
    dk = [int(x) for x in open(oppname) if x.strip()]
    WALL = load(os.path.join(ROOT, "agent", "main.py"), "wall")
    def opp(o): return dk if o["select"] is None else WALL.agent(o)
    opp_label = "opponent"

env = make("cabt")
if seat == 0:
    env.run([ARCH.agent, opp]); me = 0
else:
    env.run([opp, ARCH.agent]); me = 1
final = env.steps[-1]
my_reward = final[me].reward or 0
result = "WIN" if my_reward > 0 else "LOSE" if my_reward < 0 else "DRAW"


def nm(cid):
    c = CARD.get(cid); return c.name if c else f"#{cid}"


def pk_info(pk):
    if not isinstance(pk, dict):
        return None
    return {"name": nm(pk.get("id")), "id": pk.get("id"),
            "hp": pk.get("hp", 0), "maxHp": pk.get("maxHp", 0),
            "energy": len(pk.get("energies", []) or []),
            "tools": [nm(t.get("id")) for t in (pk.get("tools", []) or [])]}


def board(player):
    act = (player.get("active") or [])
    a = pk_info(act[0]) if act and isinstance(act[0], dict) else None
    bench = [pk_info(b) for b in (player.get("bench") or []) if isinstance(b, dict)]
    return {"active": a, "bench": bench,
            "hand": player.get("handCount", len(player.get("hand") or [])),
            "prize": len(player.get("prize") or []), "deck": player.get("deckCount", 0)}


def describe(opt):
    t = opt.get("type")
    T = {0: "数選択", 1: "Yes", 2: "No", 3: "選択", 7: "出す", 8: "エネ付け",
         9: "進化", 10: "特性", 12: "にげる", 13: "こうげき", 14: "ターン終了"}.get(t, f"type{t}")
    return T


frames = []
prev_sig = None
for st in env.steps:
    cell = st[me]
    obs = cell.observation
    if not isinstance(obs, dict):
        continue
    sel = obs.get("select"); cur = obs.get("current")
    if sel is None or cur is None:
        continue
    if sel.get("context") != 0:   # MAIN局面だけ(見やすさ優先)
        continue
    opts = sel.get("option") or []
    act = cell.action
    chosen_txt = None
    try:
        if isinstance(act, list) and act and 0 <= act[0] < len(opts):
            o = opts[act[0]]; chosen_txt = describe(o)
            if o.get("type") == 13:
                chosen_txt = "こうげき"
            elif o.get("type") == 7:
                c = (cur["players"][me].get("hand") or [])
                if o.get("index") is not None and o["index"] < len(c):
                    chosen_txt = "出す: " + nm(c[o["index"]].get("id"))
            elif o.get("type") == 9:
                chosen_txt = "進化"
            elif o.get("type") == 8:
                chosen_txt = "エネ付け"
            elif o.get("type") == 12:
                chosen_txt = "にげる"
    except Exception:
        pass
    if not chosen_txt or chosen_txt == "選択":
        continue   # 不明/サーチ選択などはスキップ
    meb = board(cur["players"][me]); opb = board(cur["players"][1 - me])
    sig = (str(meb), str(opb), chosen_txt)
    if sig == prev_sig:
        continue   # 直前と同一盤面・同一手は省く
    prev_sig = sig
    frames.append({"turn": cur.get("turn", 0), "me": meb, "opp": opb, "action": chosen_txt})

out = {"result": result, "opp_label": opp_label, "n_decisions": len(frames),
       "frames": frames}
json.dump(out, open(os.path.join(HERE, "battle_log.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"{result} vs {opp_label} | 記録した決定数 {len(frames)} | battle_log.json")
