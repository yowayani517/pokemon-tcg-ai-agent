"""フェーズ1改: リッチな盤面特徴でV(state)の質(AUC)を上げる。
フーディン側MAIN局面 -> 特徴。学習GBMの葉評価器を強くするのが目的。"""
import json, glob, sys, numpy as np
sys.path.insert(0, '.')
from cg import api

CARD = {c.cardId: c for c in api.all_card_data()}
ATK = {a.attackId: a for a in api.all_attack()}
ALA = 743; KADABRA = 742; ABRA = 741; CANDY = 1079


def maxdmg(cid):
    c = CARD.get(cid)
    return max([ATK[a].damage for a in c.attacks if a in ATK] or [0]) if c else 0


def prize_of(cid):
    c = CARD.get(cid)
    return 3 if (c and c.megaEx) else 2 if (c and c.ex) else 1


def feat(cur, pi, handcards):
    me = cur['players'][pi]; opp = cur['players'][1 - pi]
    myb = [p for p in (me.get('active') or []) + (me.get('bench') or []) if p]
    opb = [p for p in (opp.get('active') or []) + (opp.get('bench') or []) if p]
    my_prize = len(me.get('prize') or []); op_prize = len(opp.get('prize') or [])
    hand = me.get('handCount') or 0
    deckn = me.get('deckCount') or 0
    ala = [p for p in myb if p.get('id') == ALA]
    ala_ready = sum(1 for p in ala if len(p.get('energies', [])) >= 1)
    my_act = (me.get('active') or [None])[0]
    op_act = (opp.get('active') or [None])[0]
    my_act_hp = my_act.get('hp', 0) if my_act else 0
    my_act_id = my_act.get('id', 0) if my_act else 0
    op_act_hp = op_act.get('hp', 999) if op_act else 999
    op_act_maxhp = op_act.get('maxHp', 999) if op_act else 999
    opp_maxdmg = max([maxdmg(p.get('id')) for p in opb] or [0])
    pwr = hand * 20
    # 相手ボード上でパワフルハンドでKOできる数(active+ボスでベンチ)
    ko_reach = sum(1 for p in opb if pwr >= p.get('hp', 999))
    ko_ex_reach = sum(1 for p in opb if pwr >= p.get('hp', 999) and prize_of(p.get('id')) >= 2)
    # 相手の残サイド価値(exが多い=取りやすい2-3枚)
    opp_ex = sum(1 for p in opb if prize_of(p.get('id')) >= 2)
    opp_dev = sum(1 for p in opb if len(p.get('energies', [])) == 0)
    # コンボ完成度: 手札/場のライン
    hc = handcards or []
    has_abra_board = any(p.get('id') == ABRA for p in myb)
    has_candy = ALA in [c for c in hc] and CANDY in hc  # 進化即行けるか(手札)
    ala_in_hand = hc.count(ALA)
    # 次ターン被KO(相手最大打点 >= 自アクティブHP)
    lose_active_next = int(opp_maxdmg >= my_act_hp and my_act_hp > 0)
    return [
        op_prize - my_prize, my_prize, op_prize,
        hand, deckn,
        len(ala), ala_ready, int(bool(ala)),
        len(myb), len(opb),
        my_act_hp, my_act_hp - opp_maxdmg, lose_active_next,
        op_act_hp, op_act_maxhp - op_act_hp,  # 相手アクティブの傷
        pwr, pwr - op_act_hp,                  # 打点余裕
        ko_reach, ko_ex_reach, opp_ex, opp_dev,
        int(has_abra_board), ala_in_hand, int(ALA in hc), int(CANDY in hc),
        int(my_act_id == ALA),
    ]


def deck_of(r, pi):
    a = r['steps'][1][pi].get('action') if len(r['steps']) > 1 else None
    return a if isinstance(a, list) and len(a) == 60 else []


X, y = [], []
for fn in glob.glob('alakazam_logs/*.json') + glob.glob('ala_big/*.json'):
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
    for st in r['steps']:
        cell = st[pi]; o = cell.get('observation')
        if not isinstance(o, dict):
            continue
        cur = o.get('current'); sel = o.get('select')
        if not cur or not sel or sel.get('context') != 0 or cur.get('yourIndex') != pi:
            continue
        try:
            hc = [c.get('id') for c in (cur['players'][pi].get('hand') or []) if isinstance(c, dict)]
            X.append(feat(cur, pi, hc)); y.append(win)
        except Exception:
            pass

X = np.array(X, dtype=float); y = np.array(y)
np.savez('value_data2.npz', X=X, y=y)
print('states:', len(y), 'features:', X.shape[1])
