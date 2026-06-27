"""PTCG AI - Mega Starmie ex Search Agent (本物の前方探索版).

cg.api の search_begin / search_step (エンジン内蔵フォワードシミュレータ) を使い、
MAIN局面で「各候補手 -> 自分のターン終わりまでロールアウト -> 結果の盤面を評価」
して、最もサイドを奪える/KOに繋がる手を選ぶ。サブ選択・相手ターン・探索不能時は
planning版(StarmiePolicy)のヒューリスティックにフォールバック。

予測情報: 自分の山札は完全に分かる(60枚 - 見えてる札)。相手は自ターン中は動かない
ので基本エネ(filler)で埋める。
"""
from __future__ import annotations

import os
import collections

from cg.api import (
    AreaType,
    EnergyType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_card_data,
    search_begin,
    search_step,
    search_end,
    to_observation_class,
)

# planning版を土台として流用(デッキ/カード表/ヒューリスティック方策)
import main_plan as MP

MY_DECK = MP.MY_DECK
CARD_TABLE = MP.CARD_TABLE
FILLER = 3  # 基本水エネ(相手の隠し札の穴埋め用)

# 探索パラメータ(速度と強さのトレードオフ)
TOP_K = 6        # MAINで評価する候補手の数(ヒューリスティック上位)
MAX_ROLLOUT = 18  # 1ロールアウトの最大ステップ
OVERRIDE_MARGIN = 50000  # ヒューリスティック第1候補を覆すのに必要な優位(半サイド分)
pre_turn = -1


def _predict_inputs(obs: Observation):
    """search_begin に渡す予測情報を組み立てる。"""
    cur = obs.current
    me = cur.yourIndex
    opp = 1 - me
    mep = cur.players[me]
    opl = cur.players[opp]

    vis = collections.Counter()
    for c in (mep.hand or []):
        vis[c.id] += 1
    for area in (mep.active, mep.bench):
        for pk in area:
            if pk is None:
                continue
            vis[pk.id] += 1
            for e in pk.energyCards:
                vis[e.id] += 1
            for t in pk.tools:
                vis[t.id] += 1
            for pe in pk.preEvolution:
                vis[pe.id] += 1
    for c in mep.discard:
        vis[c.id] += 1

    rem = list((collections.Counter(MY_DECK) - vis).elements())
    dc = mep.deckCount
    pz = len(mep.prize)
    # 足りない場合(予測ズレ)はfillerで補う
    while len(rem) < dc + pz:
        rem.append(FILLER)
    your_deck = rem[:dc]
    your_prize = rem[dc:dc + pz]

    opp_deck = [FILLER] * opl.deckCount
    opp_prize = [FILLER] * len(opl.prize)
    opp_hand = [FILLER] * opl.handCount
    # 相手アクティブが裏向き(None)の時だけ予測が要る
    opp_active = []
    if opl.active and opl.active[0] is None:
        opp_active = [664]  # 適当なたねポケ(Scorbunny)
    return your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active


def _evaluate(obs: Observation, me: int) -> float:
    """自分(me)視点で盤面を評価。サイドを奪う(KO)が最重要。"""
    cur = obs.current
    if cur is None:
        return 0.0
    opp = 1 - me
    mep = cur.players[me]
    opl = cur.players[opp]
    score = 0.0
    # 取ったサイド(相手の残りサイドが減るほど良い)
    score += (6 - len(opl.prize)) * 100000
    score -= (6 - len(mep.prize)) * 90000
    # 勝敗
    if cur.result == me:
        score += 1_000_000
    elif cur.result == opp:
        score -= 1_000_000
    # 相手場へのダメージ(非KO分)
    for pk in list(opl.active) + list(opl.bench):
        if pk is not None:
            score += (pk.maxHp - pk.hp) * 2
    # 自分の育成(メガスターミーのエネ/HP)
    for pk in list(mep.active) + list(mep.bench):
        if pk is None:
            continue
        if pk.id == MP.C.MEGA_STARMIE:
            score += min(3, len(pk.energies)) * 60 + 40
        elif pk.id == MP.C.STARYU:
            score += len(pk.energies) * 20
        score += pk.hp * 0.2
    return score


def _heuristic_pick(obs: Observation):
    """planning版の方策で選択肢の順位を返す(ロールアウト/フォールバック用)。"""
    try:
        return MP.StarmiePolicy(obs).choose()
    except Exception:
        n = len(obs.select.option) if obs.select else 0
        return list(range(n))


def _need(sel):
    return max(1, sel.minCount or 0, sel.maxCount or 1)


def _rollout(state, me: int) -> float:
    """現在の探索状態から、自分のターン終わりまでヒューリスティックで進めて評価。"""
    sid = state.searchId
    obs = state.observation
    for _ in range(MAX_ROLLOUT):
        sel = obs.select
        if sel is None or not sel.option:
            break
        if obs.current is not None and obs.current.yourIndex != me:
            break  # 相手のターンに移った -> 自分のターン終了
        order = _heuristic_pick(obs)
        k = min(_need(sel), len(sel.option))
        pick = [i for i in order if 0 <= i < len(sel.option)][:k] or list(range(k))
        try:
            state = search_step(sid, pick)
        except Exception:
            break
        sid = state.searchId
        obs = state.observation
    return _evaluate(obs, me)


def _search_action(obs: Observation):
    """MAIN局面: 各候補手をロールアウト評価し、最良の最初の手を返す。"""
    sel = obs.select
    me = obs.current.yourIndex
    try:
        inputs = _predict_inputs(obs)
        root = search_begin(obs, *inputs)
    except Exception:
        return None  # 探索不能 -> フォールバック
    root_id = root.searchId
    cand = [i for i in _heuristic_pick(obs) if 0 <= i < len(sel.option)][:TOP_K]
    if not cand:
        cand = list(range(min(TOP_K, len(sel.option))))

    # ヒューリスティック第1候補を基準にロールアウト評価
    h0 = cand[0]
    try:
        base_v = _rollout(search_step(root_id, [h0]), me)
    except Exception:
        try:
            search_end()
        except Exception:
            pass
        return None

    # 他候補は「基準より明確に良い(=サイドを余分に取れる)」時だけ上書き
    best_i, best_v = h0, base_v
    for a in cand[1:]:
        try:
            v = _rollout(search_step(root_id, [a]), me)
        except Exception:
            continue
        if v > best_v + OVERRIDE_MARGIN:
            best_v, best_i = v, a
    try:
        search_end()
    except Exception:
        pass
    return best_i


def agent(obs_dict: dict):
    try:
        obs = to_observation_class(obs_dict)
    except Exception:
        if obs_dict.get("select") is None:
            return MY_DECK
        return [0]
    if obs.select is None:
        return MY_DECK
    global pre_turn
    try:
        if obs.current is not None and pre_turn != obs.current.turn:
            pre_turn = obs.current.turn
            MP.plan = MP.AttackPlan()
        sel = obs.select
        # MAIN局面のみ探索。それ以外はヒューリスティック。
        if sel.context == SelectContext.MAIN and obs.current is not None and obs.current.turn >= 2:
            a = _search_action(obs)
            if a is not None and not os.environ.get("SEARCH_DRYRUN"):
                return [a]
        order = _heuristic_pick(obs)
        n = len(sel.option)
        order = [i for i in order if 0 <= i < n]
        k = min(sel.maxCount, n)
        k = max(k, min(max(1, sel.minCount), n))
        return order[:k] if order else MP._fallback(sel)
    except Exception:
        return MP._fallback(obs.select)
