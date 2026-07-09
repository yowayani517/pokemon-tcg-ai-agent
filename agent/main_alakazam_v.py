"""PTCG AI - フーディン 学習V(state)探索エージェント (Stage2).

点数加算の頭打ちを受け、公式Search APIで各候補手の後継盤面を生成し、
289上位リプレイで学習した価値関数V(state)=P(win)(AUC0.937, GBM300木を
numpy化, 依存numpyのみ)で評価してargmaxを選ぶ。全判断がV貪欲。
値モデルが読めない/探索が失敗した局面は、実績あるヒューリスティック
(AlakazamPolicy)へ安全にfallback。
"""
from __future__ import annotations
import os
import numpy as np

from cg import api
from cg.api import (AreaType, CardType, Observation, OptionType, SelectContext,
                    all_attack, all_card_data, to_observation_class)

# 実績あるヒューリスティックを候補生成/フォールバックに再利用
import importlib.util as _il
_here = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name):
    for base in (_here, "/kaggle_simulations/agent", "."):
        p = os.path.join(base, name)
        if os.path.exists(p):
            s = _il.spec_from_file_location(name[:-3], p)
            m = _il.module_from_spec(s); s.loader.exec_module(m); return m
    return None


_H = _load_sibling("main_alakazam.py")     # ヒューリスティック(候補生成+fallback)
MY_DECK = _H.MY_DECK if _H else []

CARD = {c.cardId: c for c in all_card_data()}
ATK = {a.attackId: a for a in all_attack()}
ALA = 743; ABRA = 741; CANDY = 1079


def _maxdmg(cid):
    c = CARD.get(cid)
    return max([ATK[a].damage for a in c.attacks if a in ATK] or [0]) if c else 0


def _prize(cid):
    c = CARD.get(cid)
    return 3 if (c and c.megaEx) else 2 if (c and c.ex) else 1


# ---- 価値モデル(numpy GBM) 読み込み ----
def _load_model():
    for base in (_here, os.path.join(_here, "..", "experiments"),
                 "/kaggle_simulations/agent", "."):
        p = os.path.join(base, "value_gbm.npz")
        if os.path.exists(p):
            try:
                return {k: v for k, v in np.load(p).items()}
            except Exception:
                pass
    return None


_M = _load_model()


def _v_predict(x):
    """pure-numpy GBM: 特徴ベクトル -> P(win)。"""
    d = _M
    FEAT, THR, LEFT, RIGHT, VAL, OFF = d['FEAT'], d['THR'], d['LEFT'], d['RIGHT'], d['VAL'], d['OFF']
    base = float(d['base']); lr = float(d['lr'])
    out = base
    T = len(OFF) - 1
    for i in range(T):
        o = int(OFF[i]); node = 0
        while LEFT[o + node] != -1:
            node = LEFT[o + node] if x[FEAT[o + node]] <= THR[o + node] else RIGHT[o + node]
        out += lr * VAL[o + node]
    return 1.0 / (1.0 + np.exp(-out))


def _en(pk):
    return len(pk.energies) if pk and pk.energies else 0


def _feat(state, pi):
    """State(dataclass) -> 26特徴(build_value_data2.py と一致)。フーディン側視点。"""
    me = state.players[pi]; opp = state.players[1 - pi]
    myb = [p for p in list(me.active) + list(me.bench) if p]
    opb = [p for p in list(opp.active) + list(opp.bench) if p]
    my_prize = len(me.prize); op_prize = len(opp.prize)
    hand = me.handCount; deckn = me.deckCount
    ala = [p for p in myb if p.id == ALA]
    ala_ready = sum(1 for p in ala if _en(p) >= 1)
    my_act = me.active[0] if me.active else None
    op_act = opp.active[0] if opp.active else None
    my_act_hp = my_act.hp if my_act else 0
    my_act_id = my_act.id if my_act else 0
    op_act_hp = op_act.hp if op_act else 999
    op_act_maxhp = op_act.maxHp if op_act else 999
    opp_maxdmg = max([_maxdmg(p.id) for p in opb] or [0])
    pwr = hand * 20
    ko_reach = sum(1 for p in opb if pwr >= p.hp)
    ko_ex_reach = sum(1 for p in opb if pwr >= p.hp and _prize(p.id) >= 2)
    opp_ex = sum(1 for p in opb if _prize(p.id) >= 2)
    opp_dev = sum(1 for p in opb if _en(p) == 0)
    hc = [c.id for c in (me.hand or [])]
    has_abra = any(p.id == ABRA for p in myb)
    ala_in_hand = hc.count(ALA)
    lose_next = int(opp_maxdmg >= my_act_hp and my_act_hp > 0)
    return np.array([
        op_prize - my_prize, my_prize, op_prize,
        hand, deckn,
        len(ala), ala_ready, int(bool(ala)),
        len(myb), len(opb),
        my_act_hp, my_act_hp - opp_maxdmg, lose_next,
        op_act_hp, op_act_maxhp - op_act_hp,
        pwr, pwr - op_act_hp,
        ko_reach, ko_ex_reach, opp_ex, opp_dev,
        int(has_abra), ala_in_hand, int(ALA in hc), int(CANDY in hc),
        int(my_act_id == ALA),
    ], dtype=float)


# ---- 相手不確定の決定化(filler) ----
def _determinize(obs):
    cur = obs.current; yi = cur.yourIndex
    me = cur.players[yi]; opp = cur.players[1 - yi]
    your_deck = [] if obs.select.deck is not None else [ABRA] * me.deckCount
    your_prize = [ABRA] * len(me.prize)
    opp_deck = [ABRA] * max(1, opp.deckCount)
    opp_prize = [ABRA] * len(opp.prize)
    opp_hand = [ABRA] * opp.handCount
    opp_active = [ABRA] if (opp.active and opp.active[0] is None) else []
    return your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active


def _heur_order(obs):
    """ヒューリスティックの選好順(候補生成/fallback)。"""
    try:
        return _H.AlakazamPolicy(obs).choose()
    except Exception:
        return list(range(len(obs.select.option)))


def _rollout_value(sid, pi, depth=0):
    """自分のターンが続く限りヒューリスティックで進め、ターンが移った盤面のVを返す。"""
    try:
        st = api.search_step(sid, []) if False else None
    except Exception:
        st = None
    return None


def _rollout_pick(ob, pi):
    """探索状態の観測に対し、ヒューリスティックで選ぶ手(index列)。自分のMAIN手番のみ進める。"""
    sel = ob.select
    if sel is None or not sel.option:
        return None
    cur = ob.current
    if cur is None or cur.yourIndex != pi:
        return None      # 相手手番/不明 -> ロールアウト終了
    try:
        order = _H.AlakazamPolicy(ob).choose()
    except Exception:
        order = list(range(len(sel.option)))
    order = [i for i in order if 0 <= i < len(sel.option)] or [0]
    k = min(sel.maxCount, len(sel.option))
    k = max(k, min(max(1, sel.minCount), len(sel.option)))
    return order[:k]


def _eval_option(obs, opt_index, base_args):
    """候補手を適用→自分のターンをヒューリスティックで最後まで進め、
    ターンが移った(=相手手番/決着)盤面のVを返す。失敗はNone。"""
    pi = obs.current.yourIndex
    try:
        st = api.search_begin(obs, *base_args)
        sid = st.searchId
        sel = st.observation.select
        k = max(1, (sel.minCount or 1)) if sel else 1
        st = api.search_step(sid, [opt_index] if k == 1 else list(range(k)))
        # 自分のターンが続く限りヒューリスティックで進める(上限で安全打ち切り)
        for _ in range(40):
            ob = st.observation
            if ob.current is None:            # 決着
                break
            if ob.select is None or ob.current.yourIndex != pi:
                break                          # 相手手番へ移った=ターン終了
            pick = _rollout_pick(ob, pi)
            if pick is None:
                break
            st = api.search_step(sid, pick)
        cur = st.observation.current
        v = _v_predict(_feat(cur, pi)) if cur is not None else None
        api.search_end()
        return float(v) if v is not None else None
    except Exception:
        try:
            api.search_end()
        except Exception:
            pass
        return None


def _choose(obs):
    sel = obs.select
    n = len(sel.option)
    order = _heur_order(obs)              # ヒューリスティック順(fallback兼候補)
    # V探索はMAINの単一選択(minCount==1)局面のみ(複数選択/非MAINはヒューリスティック)
    if (_M is None or obs.current is None or sel.context != SelectContext.MAIN
            or (sel.maxCount or 1) != 1 or n <= 1):
        return order
    try:
        base_args = _determinize(obs)
        # コスト制御: ヒューリスティック上位min(n,14)候補だけV評価
        cand = order[:min(n, 14)]
        scored = []
        for oi in cand:
            v = _eval_option(obs, oi, base_args)
            if v is not None:
                scored.append((v, oi))
        if not scored:
            return order
        scored.sort(reverse=True)
        best = [oi for _, oi in scored]
        rest = [i for i in order if i not in best]
        return best + rest
    except Exception:
        return order


def agent(obs_dict: dict):
    try:
        obs = to_observation_class(obs_dict)
    except Exception:
        if obs_dict.get("select") is None:
            return MY_DECK
        return [0]
    if obs.select is None:
        return MY_DECK
    try:
        ordered = _choose(obs)
        n = len(obs.select.option)
        ordered = [i for i in ordered if 0 <= i < n]
        if not ordered:
            ordered = list(range(n))
        k = min(obs.select.maxCount, n)
        k = max(k, min(max(1, obs.select.minCount), n))
        return ordered[:k]
    except Exception:
        try:
            n = len(obs.select.option)
            return list(range(max(1, min(obs.select.minCount, n))))
        except Exception:
            return [0]
