"""ラダー対戦のリプレイを解析: 勝敗・相手デッキ・試合長を表示.

使い方:
  1) 自分の提出IDのエピソード一覧:
     python -m kaggle competitions episodes <submission_id>
  2) リプレイDL:
     python -m kaggle competitions replay <episode_id>   (このフォルダで実行)
  3) 解析:
     python experiments/analyze_replays.py
"""
import json, glob, os, csv
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "EN_Card_Data.csv")
ROWS = {r["Card ID"]: r for r in csv.DictReader(open(DATA, encoding="utf-8"))}


def nm(c):
    return ROWS.get(str(c), {}).get("Card Name", f"#{c}")


def stage(c):
    return ROWS.get(str(c), {}).get("Stage (Pokémon)/Type (Energy and Trainer)", "")


def is_ex(c):
    return "ex" in ROWS.get(str(c), {}).get("Rule", "").lower()


def deck_of(steps, pi):
    for st in steps:
        a = st[pi].get("action")
        if isinstance(a, list) and len(a) >= 40 and all(isinstance(x, int) for x in a):
            return a
    return []


def main():
    files = sorted(glob.glob(os.path.join(HERE, "replays", "*replay*.json")))
    if not files:
        print("replays/ に *replay*.json が無い。先に kaggle competitions replay <id> でDL。")
        return
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        steps, rew = d["steps"], d["rewards"]
        d0, d1 = deck_of(steps, 0), deck_of(steps, 1)
        me = 0 if 345 in d0 else 1          # 自分のデッキ=イワパレス(345)を含む側
        opp = 1 - me
        od = [d0, d1][opp]
        res = "WIN " if rew[me] > rew[opp] else ("LOSE" if rew[me] < rew[opp] else "DRAW")
        c = Counter(od)
        pokes = [(cid, n) for cid, n in c.items() if "Pokémon" in stage(cid)]
        ex_n = sum(n for cid, n in pokes if is_ex(cid))
        nonex_n = sum(n for cid, n in pokes if not is_ex(cid))
        print(f"\n[{res}] {os.path.basename(f)}  手数={len(steps)}  相手ポケ: ex={ex_n} 非ex={nonex_n}")
        for cid, n in sorted(pokes, key=lambda x: -x[1])[:8]:
            tag = "ex" if is_ex(cid) else "  "
            print(f"    x{n} {tag} {nm(cid)}  [{stage(cid)}]")


if __name__ == "__main__":
    main()
