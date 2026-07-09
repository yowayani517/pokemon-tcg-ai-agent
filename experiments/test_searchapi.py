"""Search APIがローカルsimで動くかの実地テスト。
実戦の途中でsearch_begin→search_stepを試み、成功/失敗と所要時間を記録する。
Stage2(V+探索)の go/no-go 判定。"""
import sys, os, time, importlib.util, json
sys.path.insert(0, '.')
from kaggle_environments import make
from cg import api
from cg.api import to_observation_class, OptionType, SelectContext

CARD = {c.cardId: c for c in api.all_card_data()}
# 汎用のたねポケモン(相手デッキ予測のfiller): ケーシィ741(HP50 basic)
FILLER_BASIC = 741
MY_DECKLIST = [int(x) for x in open('../agent/deck_alakazam.csv') if x.strip()]

log = {'begin_ok': 0, 'begin_fail': 0, 'step_ok': 0, 'step_fail': 0,
       'errs': {}, 'begin_ms': [], 'step_ms': []}


def try_search(obs):
    """MAIN局面でsearch_beginを試し、最初の合法手をsearch_stepで1手進める。"""
    try:
        cur = obs.current
        yi = cur.yourIndex
        me = cur.players[yi]
        opp = cur.players[1 - yi]
        # 自分の山: select.deck があれば渡さない([])、無ければ deckCount 枚を自デッキから
        your_deck = [] if obs.select.deck is not None else [FILLER_BASIC] * me.deckCount
        your_prize = [FILLER_BASIC] * len(me.prize)
        opp_deck = [FILLER_BASIC] * max(1, opp.deckCount)
        opp_prize = [FILLER_BASIC] * len(opp.prize)
        opp_hand = [FILLER_BASIC] * opp.handCount
        # 相手アクティブが伏せ(None)なら予測が必要
        opp_active = []
        if opp.active and opp.active[0] is None:
            opp_active = [FILLER_BASIC]
        t0 = time.time()
        st = api.search_begin(obs, your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active)
        log['begin_ms'].append((time.time() - t0) * 1000)
        log['begin_ok'] += 1
        # 1手進める(最初の合法手index=0)
        sel = st.observation.select
        if sel and sel.option:
            k = max(1, sel.minCount or 1)
            t1 = time.time()
            st2 = api.search_step(st.searchId if hasattr(st, 'searchId') else getattr(st, 'id', 0),
                                  list(range(k)))
            log['step_ms'].append((time.time() - t1) * 1000)
            log['step_ok'] += 1
        api.search_end()
        return True
    except Exception as e:
        msg = f"{type(e).__name__}:{e}"
        log['errs'][msg] = log['errs'].get(msg, 0) + 1
        if 'begin' not in str(log):
            log['begin_fail'] += 1
        try:
            api.search_end()
        except Exception:
            pass
        return False


_tried = [0]


def agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return MY_DECKLIST
    # MAINで最初の数回だけ探索を試す
    if obs.select.context == SelectContext.MAIN and _tried[0] < 6 and obs.current is not None:
        _tried[0] += 1
        try_search(obs)
    # 通常は最初の合法手
    n = len(obs.select.option)
    k = min(obs.select.maxCount, n); k = max(k, min(max(1, obs.select.minCount), n))
    return list(range(n))[:k]


if __name__ == '__main__':
    G = None
    spec = importlib.util.spec_from_file_location('grimm', '../agent/main_grimm.py')
    G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
    env = make('cabt')
    env.run([agent, G.agent])
    import statistics
    print('search_begin OK:', log['begin_ok'], 'FAIL:', log['begin_fail'])
    print('search_step  OK:', log['step_ok'])
    if log['begin_ms']:
        print('begin ms: 平均%.1f' % statistics.mean(log['begin_ms']))
    if log['step_ms']:
        print('step  ms: 平均%.1f' % statistics.mean(log['step_ms']))
    print('errors:', json.dumps(log['errs'], ensure_ascii=False))
