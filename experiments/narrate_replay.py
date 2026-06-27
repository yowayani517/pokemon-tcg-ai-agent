"""上位プレイヤーのリプレイを『一手ずつ文章』に変換してプレイングを分析する.

各決定点で「盤面状況」と「選んだ手(カード名・対象つき)」を人間可読に出力。
"""
import json, glob, os, csv, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = {r["Card ID"]: r for r in csv.DictReader(open(os.path.join(HERE, "..", "data", "EN_Card_Data.csv"), encoding="utf-8"))}


def nm(cid):
    return ROWS.get(str(cid), {}).get("Card Name", f"#{cid}")


OPT = {0: "数", 1: "はい", 2: "いいえ", 3: "カード", 4: "道具", 5: "エネ札", 6: "エネ",
       7: "出す", 8: "エネ付け", 9: "進化", 10: "特性", 11: "トラッシュ", 12: "にげる",
       13: "ワザ", 14: "ターン終了", 15: "スキル", 16: "特殊状態"}
AREA = {1: "山", 2: "手札", 3: "トラッシュ", 4: "アクティブ", 5: "ベンチ", 6: "サイド"}


def deck_of(steps, pi):
    for st in steps:
        a = st[pi].get("action")
        if isinstance(a, list) and len(a) >= 40 and all(isinstance(x, int) for x in a):
            return a
    return []


def poke_str(p):
    if not isinstance(p, dict):
        return "?"
    e = len(p.get("energies", []) or [])
    return f"{nm(p.get('id'))}(HP{p.get('hp')}/エネ{e})"


def resolve(o, obs, me):
    """選択肢を文章化(対象カード名つき)。"""
    t = o.get("type"); base = OPT.get(t, str(t))
    cur = obs.get("current")
    try:
        if t in (7,) and cur:  # 手札から出す
            hand = cur["players"][me].get("hand") or []
            i = o.get("index", -1)
            return f"{base}:{nm(hand[i].get('id'))}" if 0 <= i < len(hand) else base
        if t == 3 and o.get("area") == 1 and obs["select"].get("deck"):  # 山サーチ
            c = obs["select"]["deck"][o["index"]]
            return f"サーチ:{nm(c.get('id') if isinstance(c,dict) else c)}"
        if t in (8, 9):  # エネ付け/進化 -> 対象
            tgt = "アクティブ" if o.get("inPlayArea") == 4 else "ベンチ"
            return f"{base}->{tgt}"
        if t == 3 and o.get("area") in (4, 5):  # 場のポケ選択
            pi = o.get("playerIndex", me)
            arr = cur["players"][pi].get("active" if o["area"] == 4 else "bench") if cur else None
            who = "自分" if pi == me else "相手"
            poke = arr[o["index"]] if arr and o["index"] < len(arr) else None
            return f"{base}({who}{AREA.get(o['area'])}):{poke_str(poke)}"
    except Exception:
        pass
    return base


def board_summary(obs, me):
    cur = obs.get("current")
    if not cur:
        return ""
    my = cur["players"][me]; op = cur["players"][1 - me]
    ma = (my.get("active") or [None])[0]; oa = (op.get("active") or [None])[0]
    return (f"[T{cur.get('turn')}] 自分:{poke_str(ma)} ベンチ{len(my.get('bench') or [])} | "
            f"相手:{poke_str(oa)} ベンチ{len(op.get('bench') or [])}")


def narrate(replay_path, signature, max_decisions=60):
    d = json.load(open(replay_path, encoding="utf-8"))
    steps = d["steps"]; rew = d.get("rewards", [0, 0])
    me = 0 if tuple(sorted(deck_of(steps, 0))) == signature else 1
    res = "勝ち" if (rew[me] or 0) > (rew[1 - me] or 0) else "負け"
    print(f"\n===== {os.path.basename(replay_path)}  Praxel=P{me} 結果={res} =====")
    cnt = 0
    for st in steps:
        ps = st[me]; obs = ps.get("observation"); act = ps.get("action")
        if not isinstance(obs, dict) or not obs.get("select") or not isinstance(act, list):
            continue
        if len(act) >= 40:
            continue
        opts = obs["select"]["option"]
        chosen = [resolve(opts[i], obs, me) for i in act if i < len(opts)]
        chosen = [c for c in chosen if c and c not in ("ターン終了", "いいえ", "はい")]
        if not chosen:
            continue
        print(f"  {board_summary(obs, me)}  =>  {' / '.join(chosen)}")
        cnt += 1
        if cnt >= max_decisions:
            break


if __name__ == "__main__":
    sig = tuple(sorted(int(x) for x in open(os.path.join(HERE, "gauntlet_top", "praxel_now.csv")) if x.strip()))
    files = sorted(glob.glob(os.path.join(HERE, "replays_praxel", "*replay*.json")))
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for f in files[:n]:
        narrate(f, sig)
