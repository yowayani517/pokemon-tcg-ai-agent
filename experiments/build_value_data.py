"""フェーズ0: リプレイの各盤面に「その試合の最終勝敗」を付与し、
V(state)候補の妥当性をAUCで秒速検証できるデータセットを作る。
出力: value_data.npz (X=盤面特徴, y=勝敗0/1)。フーディン側視点のMAIN局面のみ。"""
import json, glob, sys, numpy as np
sys.path.insert(0, '.')
from cg import api

CARD = {c.cardId: c for c in api.all_card_data()}
ATK = {a.attackId: a for a in api.all_attack()}
ALA = 743
POWERFUL = 1072


def maxdmg(cid):
    c = CARD.get(cid)
    if not c:
        return 0
    return max([ATK[a].damage for a in c.attacks if a in ATK] or [0])


def prize_of(cid):
    c = CARD.get(cid)
    return 3 if (c and c.megaEx) else 2 if (c and c.ex) else 1


def feat(cur, pi):
    """盤面 -> フーディン側視点の特徴ベクトル(サイドレース基準)。"""
    me = cur['players'][pi]
    opp = cur['players'][1 - pi]
    myb = (me.get('active') or []) + (me.get('bench') or [])
    opb = (opp.get('active') or []) + (opp.get('bench') or [])
    myb = [p for p in myb if p]
    opb = [p for p in opb if p]
    my_prize = len(me.get('prize') or [])
    op_prize = len(opp.get('prize') or [])
    hand = me.get('handCount') or 0
    # フーディンが場にいて1エネ済か(攻撃態勢)
    ala_ready = any(p.get('id') == ALA and len(p.get('energies', [])) >= 1 for p in myb)
    ala_inplay = any(p.get('id') == ALA for p in myb)
    # 相手の最大打点 と 自アクティブHP(次ターン倒されるか)
    opp_maxdmg = max([maxdmg(p.get('id')) for p in opb] or [0])
    my_act = (me.get('active') or [None])[0]
    my_act_hp = my_act.get('hp', 0) if my_act else 0
    # パワフルハンド想定打点(手札×20) が相手アクティブをKOできるか
    op_act = (opp.get('active') or [None])[0]
    op_act_hp = op_act.get('hp', 999) if op_act else 999
    can_ko_active = (hand * 20) >= op_act_hp
    # 相手ベンチに育成中の進化前/ドローエンジン(将来サイド源)
    opp_dev = sum(1 for p in opb if prize_of(p.get('id')) >= 1 and len(p.get('energies', [])) == 0)
    return [
        op_prize - my_prize,            # サイド差(自分優勢=正) ← 主項
        hand,                           # 手札=火力
        int(ala_ready), int(ala_inplay),
        len(myb), len(opb),
        my_act_hp - opp_maxdmg,         # 次ターン耐えられるバッファ
        int(can_ko_active),
        opp_dev,
        cur.get('turn', 0),
    ]


def deck_of(r, pi):
    a = r['steps'][1][pi].get('action') if len(r['steps']) > 1 else None
    return a if isinstance(a, list) and len(a) == 60 else []


X, y = [], []
files = glob.glob('alakazam_logs/*.json') + glob.glob('ala_big/*.json')
ng = 0
for fn in files:
    try:
        r = json.load(open(fn, encoding='utf-8'))
    except Exception:
        continue
    d0, d1 = deck_of(r, 0), deck_of(r, 1)
    pi = 0 if d0.count(ALA) >= 3 else 1 if d1.count(ALA) >= 3 else None
    if pi is None:
        continue
    rew = r['steps'][-1][pi].get('reward')
    if rew not in (1, -1):
        continue
    win = 1 if rew == 1 else 0
    ng += 1
    for st in r['steps']:
        cell = st[pi]
        o = cell.get('observation')
        if not isinstance(o, dict):
            continue
        cur = o.get('current')
        sel = o.get('select')
        if not cur or not sel or sel.get('context') != 0:
            continue
        if cur.get('yourIndex') != pi:
            continue
        try:
            X.append(feat(cur, pi)); y.append(win)
        except Exception:
            pass

X = np.array(X, dtype=float); y = np.array(y)
np.savez('value_data.npz', X=X, y=y)
print('games:', ng, 'states:', len(y), 'win-rate:', round(y.mean(), 3))
print('feature dim:', X.shape[1])
