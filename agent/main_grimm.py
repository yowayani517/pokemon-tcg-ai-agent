"""PTCG AI - マリィのオーロンゲex (悪) Planning Agent.

現ラダー1〜3位(1340/1310/1287)が全てこのデッキ。設計思想は main_arch と同じ
「ターン頭で攻撃プランを1つ確定→全ての手をそれに従属」。
勝ち筋は一直線: ベロバーを並べる→ふしぎなアメで即オーロンゲex(HP320)→
悪2エネで Shadow Bullet 180+ベンチ30 を毎ターン連打。
エンジン: スパイクタウンジム(毎ターン無料サーチ)/ノココッチ(3ドローして山へ戻る)/
マシマシラ(受けたダメカン3個を相手へ移動=タンクが火力になる)/スボミー(0エネで
アイテムロック=序盤の壁)。依存は cg.api のみ。
"""
from __future__ import annotations

import os
from collections import defaultdict

from cg.api import (
    AreaType, Card, CardType, EnergyType, Observation, OptionType, Pokemon,
    SelectContext, all_attack, all_card_data, to_observation_class,
)


class C:
    GRIMM = 648           # マリィのオーロンゲex HP320 st2, Shadow Bullet 937: 悪2->180+ベンチ30
    MORGREM = 647         # マリィのギモー HP100 st1
    IMPIDIMP = 646        # マリィのベロバー HP70 たね
    DUNSPARCE = 305       # ノコッチ HP70
    DUDUN = 66            # ノココッチ HP140 特性: 3ドローして自分ごと山へ戻る
    MUNKI = 112           # マシマシラ HP110 特性: 悪エネ付きなら自分のダメカン3個を相手へ
    BUDEW = 235           # スボミー HP30 0エネ10+アイテムロック
    YVELTAL = 689         # イベルタル HP110
    FEZ = 140             # キチキギスex HP210
    DARK = 7              # 基本悪エネ
    CANDY = 1079          # ふしぎなアメ
    POFFIN = 1086         # なかよしポフィン(HP70以下たね2体ベンチへ)
    POKE_PAD = 1152       # ポケパッド
    DAWN = 1231           # ヒカリ(たね+1進化+2進化サーチ)
    LILLIE = 1227         # リーリエの決心
    BOSS = 1182           # ボスの指令
    SPIKEMUTH = 1259      # スパイクタウンジム(毎ターン マリィのポケモンをサーチ)
    RUINS = 1260          # 危ない廃墟(非悪たねベンチ登場に2ダメカン)
    XEROSIC = 1197        # クセロシキのたくらみ
    SCRAPPER = 1137       # ツールスクラッパー
    CAPE = 1159           # ヒーローマント(+100HP)


SHADOW_BULLET = 937
ITCHY_POLLEN = 323     # スボミー 0エネ: 10+アイテムロック
GRIMM_LINE = {C.GRIMM, C.MORGREM, C.IMPIDIMP}
ALAKAZAM_LINE = {109, 742, 245}
WALL_IDS = {344, 345}
LOW_DECK_COUNT = 8

DECK = ([C.DARK] * 10 + [C.IMPIDIMP] * 4 + [C.GRIMM] * 4 + [C.MORGREM] * 2 +
        [C.DUNSPARCE] * 3 + [C.DUDUN] * 3 + [C.MUNKI] * 3 + [C.BUDEW] * 1 +
        [C.YVELTAL] * 1 + [C.FEZ] * 1 +
        [C.CANDY] * 4 + [C.POFFIN] * 4 + [C.POKE_PAD] * 4 + [C.LILLIE] * 4 +
        [C.DAWN] * 3 + [C.SPIKEMUTH] * 3 + [C.BOSS] * 2 +
        [C.RUINS] * 1 + [C.XEROSIC] * 1 + [C.SCRAPPER] * 1 + [C.CAPE] * 1)


def _load_deck():
    for p in ("deck.csv", "/kaggle_simulations/agent/deck.csv"):
        try:
            if os.path.exists(p):
                d = [int(x) for x in open(p, encoding="utf-8").read().split() if x.strip()]
                if len(d) == 60:
                    return d
        except Exception:
            pass
    return DECK


MY_DECK = _load_deck()
CARD_TABLE = {c.cardId: c for c in all_card_data()}
ATK_TABLE = {a.attackId: a for a in all_attack()}


def _max_atk_damage(card):
    if not card:
        return 0
    return max([ATK_TABLE[a].damage for a in card.attacks if a in ATK_TABLE] or [0])


class AttackPlan:
    def __init__(self, attacker=-1, target=-1, attack_id=-1, ko=False, needs_energy=False):
        self.attacker = attacker
        self.target = target
        self.attack_id = attack_id
        self.ko = ko
        self.needs_energy = needs_energy


plan = AttackPlan()
pre_turn = -1


def get_card(obs, area, index, pi):
    p = obs.current.players[pi]
    if area == AreaType.HAND:
        return p.hand[index] if p.hand else None
    if area == AreaType.ACTIVE:
        return p.active[index] if p.active else None
    if area == AreaType.BENCH:
        return p.bench[index]
    if area == AreaType.DISCARD:
        return p.discard[index]
    if area == AreaType.DECK:
        return obs.select.deck[index] if obs.select.deck else None
    if area == AreaType.STADIUM:
        return obs.current.stadium[index]
    return None


def prize_count(pk):
    d = CARD_TABLE.get(pk.id)
    return 3 if (d and d.megaEx) else 2 if (d and d.ex) else 1


def target_score(pk):
    d = CARD_TABLE.get(pk.id)
    s = prize_count(pk) * 1000 + len(pk.energies) * 150 + len(pk.tools) * 80
    if d:
        s += 250 if d.stage2 else 130 if d.stage1 else 0
    s += pk.hp
    return s


class GrimmPolicy:
    def __init__(self, obs: Observation):
        self.obs = obs
        self.select = obs.select
        self.context = obs.select.context
        self.state = obs.current
        self.my = self.state.yourIndex
        self.op = 1 - self.my
        self.me = self.state.players[self.my]
        self.opp = self.state.players[self.op]

        self.hand_counts = defaultdict(int)
        self.field_counts = defaultdict(int)
        for c in (self.me.hand or []):
            self.hand_counts[c.id] += 1
        for pk in self._my_board():
            if pk is not None:
                self.field_counts[pk.id] += 1

        self.can_switch = False
        self.can_gust = False
        if self.context == SelectContext.MAIN:
            for o in self.select.option:
                if o.type == OptionType.PLAY:
                    c = get_card(self.obs, AreaType.HAND, o.index, self.my)
                    if c and c.id == C.BOSS:
                        self.can_gust = True
                elif o.type == OptionType.RETREAT:
                    self.can_switch = True

        self.opp_is_alakazam = any(p is not None and p.id in ALAKAZAM_LINE for p in self._opp_board())
        self.opp_max_dmg = 0
        for pk in self._opp_board():
            if pk is None:
                continue
            d = CARD_TABLE.get(pk.id)
            self.opp_max_dmg = max(self.opp_max_dmg, _max_atk_damage(d))
        self.opp_is_wall = any(p is not None and p.id in WALL_IDS for p in self._opp_board())
        self.my_confused = bool(getattr(self.me, "confused", False))
        a0 = self.me.active[0] if self.me.active else None
        self.my_act_hp = a0.hp if a0 else 0

    def _my_board(self):
        return list(self.me.active) + list(self.me.bench)

    def _opp_board(self):
        return list(self.opp.active) + list(self.opp.bench)

    def _low_deck(self):
        return self.me.deckCount <= LOW_DECK_COUNT

    def _attachable_now(self):
        if self.state.energyAttached:
            return 0
        return 1 if self.hand_counts[C.DARK] >= 1 else 0

    def _attacks_for(self, pk):
        ids = list(CARD_TABLE.get(pk.id).attacks) if CARD_TABLE.get(pk.id) else []
        out = []
        for aid in ids:
            a = ATK_TABLE.get(aid)
            if not a:
                continue
            dmg = a.damage
            if dmg <= 0 and aid != ITCHY_POLLEN:
                continue
            out.append((aid, len(a.energies), max(dmg, 0)))
        return out

    # ---- 攻撃プラン ----
    def _plan_attack(self):
        global plan
        plan = AttackPlan()
        if self.state.turn < 2:
            return
        best = -1
        board = self._my_board()
        extra = self._attachable_now()
        for ai, pk in enumerate(board):
            if pk is None:
                continue
            if ai != 0 and not self.can_switch:
                continue
            energy_now = len(pk.energies)
            attacker_is_ex = bool(CARD_TABLE.get(pk.id) and CARD_TABLE[pk.id].ex)
            for aid, need, dmg in self._attacks_for(pk):
                avail = energy_now + (extra if ai == 0 or True else 0)
                needs_energy = False
                if energy_now < need:
                    if avail >= need:
                        needs_energy = True
                    else:
                        continue
                for ti, opk in enumerate(self._opp_board()):
                    if opk is None:
                        continue
                    if ti != 0 and not self.can_gust:
                        continue
                    # イワパレス: exの攻撃を無効化。ex(オーロンゲ/キチキギス)では殴らない
                    if attacker_is_ex and opk.id == 345:
                        continue
                    damage = dmg
                    od = CARD_TABLE.get(opk.id)
                    if od:
                        if od.weakness == EnergyType.DARKNESS:
                            damage *= 2
                        elif od.resistance == EnergyType.DARKNESS:
                            damage -= 30
                    ko = opk.hp <= damage
                    sc = target_score(opk)
                    if ko:
                        sc += 4000
                        if len(self.opp.prize) <= prize_count(opk):
                            sc = 90000
                    else:
                        sc *= damage / max(1, opk.hp)
                    sc += 600 if ai == 0 else 0
                    sc += 300 if ti == 0 else 0
                    if opk.id in ALAKAZAM_LINE:
                        sc += 1800 if opk.id == 245 else 1200
                        if ko:
                            sc += 3500
                    # 育つ前の脅威を狩る: 進化前のたね(ジュラルドン等)やエネが乗り始めた
                    # ポケモンをKOできるなら、育ち切る前に処理(サイドレースの主導権)
                    if opk.id == 169 and ko:
                        sc += 2500          # ジュラルドン(→ブリジュラスex)は着地前に狩る
                    if ko and len(opk.energies) >= 2 and prize_count(opk) == 1:
                        sc += 800           # エネ投資済み非exを狩る=相手のテンポを2ターン奪う
                    # 1位のログ分析: 勝ち試合はスボミー攻撃ほぼ0(0.06回)。ロックより
                    # 本命育成が全て。ボーナスは付けない(KOできる時だけ自然に選ばれる)
                    odmg = _max_atk_damage(od)
                    if self.my_act_hp and odmg >= self.my_act_hp:
                        sc += 900 if ko else 300
                    sc += energy_now
                    if sc > best:
                        best = sc
                        plan = AttackPlan(ai, ti, aid, ko, needs_energy)

    def _grimm_ready(self):
        for pk in self._my_board():
            if pk is not None and pk.id == C.GRIMM and len(pk.energies) >= 2:
                return True
        return False

    def _bench_ready(self):
        for pk in self.me.bench:
            if pk is not None and pk.id == C.GRIMM and len(pk.energies) >= 2:
                return True
        return False

    def _have_switch_item(self):
        return False   # このデッキに いれかえ は入っていない

    def _can_retreat_active(self):
        act = self.me.active[0] if self.me.active else None
        if not act:
            return False
        d = CARD_TABLE.get(act.id)
        return len(act.energies) >= (d.retreatCost if d else 0)

    def _promote_worth_it(self):
        # にげる=アクティブのエネを捨てる(悪エネは10枚しかない貴重資源)。
        # 安いKOのために逃げ回るとエネ経済が崩壊するので、価値がコストを上回る時だけ。
        if plan.attacker < 1:
            return False
        act = self.me.active[0] if self.me.active else None
        cost = 0
        if act is not None:
            d = CARD_TABLE.get(act.id)
            cost = min(d.retreatCost if d else 0, len(act.energies))
        bi = plan.attacker - 1
        bench = self.me.bench
        bp = bench[bi] if 0 <= bi < len(bench) else None
        if not bp:
            return False
        ready = bp.id == C.GRIMM and len(bp.energies) >= 2
        if plan.ko:
            # KOでも、2エネ捨ててまで取るのは2サイド級 or 完成オーロンゲを出す時だけ
            if cost == 0:
                return True
            if ready:
                return True
            if cost <= 1:
                tgt = self._opp_board()[plan.target] if 0 <= plan.target < len(self._opp_board()) else None
                return bool(tgt is not None and prize_count(tgt) >= 2)
            return False
        return ready and cost <= 1

    # ---- 選択 ----
    def choose(self):
        if not self.select.option or self.select.maxCount == 0:
            return []
        if self.context == SelectContext.MAIN:
            self._plan_attack()
        scores = [self._score(o) for o in self.select.option]
        return [i for i, _ in sorted(enumerate(scores), key=lambda kv: kv[1], reverse=True)]

    def _score(self, o):
        t = o.type
        if t == OptionType.NUMBER:
            return o.number or 0        # マシマシラ: 移すダメカンは常に最大
        if t == OptionType.YES:
            if self.context in (SelectContext.IS_FIRST, SelectContext.ACTIVATE):
                # ノココッチのドローも マシマシラの移動も スパイクタウンのサーチも常に使う
                return 100
            return 1
        if t == OptionType.NO:
            return 0
        if t == OptionType.CARD:
            return self._score_card(o)
        if t in (OptionType.ENERGY, OptionType.ENERGY_CARD):
            return 50
        if t == OptionType.PLAY:
            c = get_card(self.obs, AreaType.HAND, o.index, self.my)
            return self._score_play(c) if c else 0
        if t == OptionType.ATTACH:
            return self._score_attach(o)
        if t == OptionType.EVOLVE:
            return self._score_evolve(o)
        if t == OptionType.ABILITY:
            return 30000
        if t == OptionType.RETREAT:
            if self.my_confused and self._bench_ready():
                return 5000
            return 2000 if self._promote_worth_it() else -1
        if t == OptionType.ATTACK:
            if plan.attack_id < 0:
                return -1
            if self.my_confused and self._bench_ready():
                return -1
            return 1100 if o.attackId == plan.attack_id else 500
        if t == OptionType.END:
            return -100
        return 0

    # ---- エネ ----
    def _energy_target_score(self, pk, active):
        n = len(pk.energies)
        s = 8000 + (50 if active else 0)
        if pk.id == C.GRIMM:
            s += 400 if n < 2 else -200          # 本命: 2エネで完成
        elif pk.id in (C.MORGREM, C.IMPIDIMP):
            s += 200 if n < 2 else -150          # 進化前に前もって2まで育てる
        elif pk.id == C.MUNKI:
            # マシマシラの特性(毎ターン ダメカン3個を相手へ=実質+30打点&30回復)は
            # このデッキの隠れテンポエンジン。本命が2エネ完成したら3枚目はここへ。
            if n == 0:
                s += 700 if self._grimm_ready() else 250
            else:
                s -= 300
        else:
            # その他(スボミー等)には張らない。ただしベンチに完成オーロンゲがいるのに
            # 前が逃げられない時だけ逃げエネを許可(デッドロック回避)
            if (active and self._bench_ready() and not self._can_retreat_active()):
                return 6500
            return -1000
        return s

    def _score_attach(self, o):
        card = get_card(self.obs, AreaType.HAND, o.index, self.my)
        pk = get_card(self.obs, o.inPlayArea, o.inPlayIndex, self.my)
        if not isinstance(pk, Pokemon) or card is None:
            return 0
        active = o.inPlayArea == AreaType.ACTIVE
        if card.id == C.CAPE:
            s = 6500
            if pk.id == C.GRIMM:
                s += 300 + (150 if active else 0)   # 320+100=420 ほぼ不沈
            return s
        s = self._energy_target_score(pk, active)
        bidx = o.inPlayIndex + (0 if active else 1)
        if bidx == plan.attacker and plan.needs_energy:
            return 12000    # このエネで今ターン攻撃到達=最優先
        return s

    # ---- 進化 ----
    def _score_evolve(self, o):
        pk = get_card(self.obs, o.inPlayArea, o.inPlayIndex, self.my)
        ev = get_card(self.obs, o.area, o.index, self.my)
        if not isinstance(pk, Pokemon):
            return 0
        s = 9000 + len(pk.energies)
        if ev is not None and ev.id == C.GRIMM:
            if self.opp_is_wall:
                return -1000    # 壁相手にex進化は無意味(攻撃無効)
            s += 500            # オーロンゲ最優先
        if ev is not None and ev.id == C.DUDUN:
            s -= 300            # ノココッチは急がない(ドローが欲しい時に)
        return s

    # ---- トレーナー ----
    def _score_play(self, card):
        cid = card.id
        d = CARD_TABLE.get(cid)
        if d and d.cardType == CardType.POKEMON:
            return self._score_bench_from_hand(card)
        return self._score_play_trainer(card)

    def _score_bench_from_hand(self, card):
        bench_n = sum(1 for p in self.me.bench if p is not None)
        if bench_n >= 5:
            return -1
        cid = card.id
        if cid == C.IMPIDIMP:
            return 5000 - self.field_counts[C.IMPIDIMP] * 800   # 本命のたねを最優先で展開
        if cid == C.DUNSPARCE:
            return 3000 if self.field_counts[C.DUNSPARCE] + self.field_counts[C.DUDUN] == 0 else 800
        if cid == C.MUNKI:
            # マシマシラは3体並べる価値がある: 各自が特性でダメカン3個/T移動
            # =3体で毎T90点(相手の220打点を実質130へ)。2発KOレースを崩す核心。
            return 2800 - self.field_counts[C.MUNKI] * 300
        if cid == C.BUDEW:
            return 1200
        if cid == C.FEZ:
            return 900
        if cid == C.YVELTAL:
            return 600
        return 300

    def _grimm_line_missing(self):
        have_g = self.field_counts[C.GRIMM] + self.hand_counts[C.GRIMM]
        have_i = self.field_counts[C.IMPIDIMP]
        return have_g == 0 or have_i == 0

    def _established(self):
        for pk in self._my_board():
            if pk is not None and pk.id == C.GRIMM and len(pk.energies) >= 2:
                return True
        return False

    def _score_play_trainer(self, card):
        cid = card.id
        if cid == C.CANDY:
            # ふしぎなアメ: ベロバーが場&オーロンゲが手札なら即打ち(このデッキの心臓)
            if (self.field_counts[C.IMPIDIMP] >= 1 and self.hand_counts[C.GRIMM] >= 1
                    and not self.opp_is_wall):
                return 9600
            return -1
        if cid == C.POFFIN:
            # HP70以下のたね2体(ベロバー/ノコッチ/スボミー)をベンチへ
            bench_n = sum(1 for p in self.me.bench if p is not None)
            if bench_n >= 5:
                return -1
            if self.field_counts[C.IMPIDIMP] < 2:
                return 3600
            return 1500 if bench_n <= 3 else 400
        if cid == C.POKE_PAD:
            return 3300
        if cid == C.DAWN:
            # ヒカリ: たね+1進化+2進化を1枚でサーチ=ラインが欠けてる時最強
            if self._grimm_line_missing():
                return 3500
            return 1800 if self.hand_counts[C.GRIMM] == 0 else 600
        if cid == C.BOSS:
            return 3200 if plan.target >= 1 else -1
        if cid == C.LILLIE:
            if self._established() and self.me.handCount >= 3:
                return 600
            return 2800 if self.me.handCount <= 4 else 900
        if cid == C.XEROSIC:
            return 800
        if cid == C.SCRAPPER:
            opp_tools = sum(len(p.tools) for p in self._opp_board() if p is not None)
            return 1900 if opp_tools else -1
        if cid == C.SPIKEMUTH:
            cur = self.state.stadium
            if not cur:
                return 1600
            if cur[0].id not in (C.SPIKEMUTH, C.RUINS):
                return 1800    # 相手スタジアムを上書き
            return -1
        if cid == C.RUINS:
            cur = self.state.stadium
            if cur and cur[0].id == C.SPIKEMUTH:
                return -1      # 自分のジムは剥がさない
            if not cur:
                return 1000
            if cur[0].id != C.RUINS:
                return 1400
            return -1
        return 1000

    # ---- カード選択 ----
    def _score_card(self, o):
        card = get_card(self.obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0
        ctx = self.context
        if o.playerIndex is not None and o.playerIndex != self.my and isinstance(card, Pokemon):
            return self._score_opp_pokemon(o, card)
        if ctx in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
            return self._score_active_choice(o, card)
        if ctx in (SelectContext.SETUP_ACTIVE_POKEMON, SelectContext.SETUP_BENCH_POKEMON,
                   SelectContext.TO_BENCH, SelectContext.TO_FIELD):
            return self._score_to_field(card, ctx)
        if ctx == SelectContext.TO_HAND:
            return self._score_to_hand(card)
        if ctx == SelectContext.ATTACH_FROM and isinstance(card, Pokemon):
            return self._energy_target_score(card, o.area == AreaType.ACTIVE)
        if ctx in (SelectContext.DISCARD, SelectContext.TO_DECK, SelectContext.TO_DECK_BOTTOM):
            return self._score_discard(card)
        if isinstance(card, Pokemon) and o.playerIndex == self.my:
            # マシマシラの移動元: 一番ダメージを受けている自分のポケモン
            return (card.maxHp - card.hp)
        return 0

    def _score_opp_pokemon(self, o, pk):
        """相手ポケモンを選ぶ場面全般: Shadow Bulletのベンチ30 / ボス / マシマシラの移動先。
        30(または移動ダメ)でKOできる相手 > 高価値ターゲット。"""
        s = 0
        if pk.hp <= 30:
            s += 3000 + prize_count(pk) * 500   # スナイプKO圏
        if pk.id in ALAKAZAM_LINE:
            s += 1500
        if pk.id == 169:
            s += 900        # ジュラルドンにベンチ30を当てて2回目のスナイプでKO圏へ
        if o.index == plan.target - 1:
            s += 400
        s += target_score(pk) // 10
        s -= pk.hp // 5
        return s

    def _score_active_choice(self, o, card):
        if not isinstance(card, Pokemon):
            return 0
        if o.playerIndex != self.my:
            return 100 if o.index == plan.target - 1 else 0
        s = len(card.energies) * 5
        if o.index == plan.attacker - 1:
            s += 200
        if card.id == C.GRIMM:
            s += 50
        elif card.id == C.BUDEW:
            s += 15     # 壁役として悪くない(0エネロック)
        return s

    def _score_to_field(self, card, ctx=None):
        if ctx == SelectContext.SETUP_ACTIVE_POKEMON:
            # 前衛: スボミー(0エネでアイテムロックの時間稼ぎ) > ノコッチ > ベロバーは温存
            if card.id == C.BUDEW:
                return 60
            if card.id == C.DUNSPARCE:
                return 45
            if card.id == C.MUNKI:
                return 35
            if card.id == C.IMPIDIMP:
                return 25
            return 10
        # ベンチ: ベロバー(本命のたね)最優先
        if card.id == C.IMPIDIMP:
            return 60
        if card.id == C.DUNSPARCE:
            return 40
        if card.id == C.MUNKI:
            return 35
        if card.id == C.BUDEW:
            return 20
        return 15

    def _score_to_hand(self, card):
        def have(cid):
            return self.field_counts[cid] + self.hand_counts[cid]
        cid = card.id
        bench_pokemon = sum(1 for p in self.me.bench if p is not None)
        if cid == C.IMPIDIMP:
            s = 500 - have(C.IMPIDIMP) * 130
            if bench_pokemon == 0:
                s += 300
            return s
        if cid == C.GRIMM:
            if self.opp_is_wall:
                return -20
            return 480 - have(C.GRIMM) * 140
        if cid == C.CANDY:
            return 420 - self.hand_counts[C.CANDY] * 150
        if cid == C.MORGREM:
            # アメがあるならギモーは不要
            if self.hand_counts[C.CANDY] >= 1:
                return 60
            return 260 - have(C.MORGREM) * 120
        if cid == C.DUNSPARCE:
            return 150 if have(C.DUNSPARCE) + have(C.DUDUN) == 0 else -50
        if cid == C.DUDUN:
            return 140 if self.field_counts[C.DUNSPARCE] >= 1 and have(C.DUDUN) == 0 else -50
        if cid == C.MUNKI:
            return 130 if have(C.MUNKI) <= 2 else -60   # 3体目まで確保する価値あり
        if cid == C.DARK:
            return -30
        return 0

    def _score_discard(self, card):
        # 捨て優先: エネ > 余りポケ > グッズ > サポート。核(オーロンゲ/アメ/ベロバー)死守
        cid = card.id
        if cid == C.DARK:
            return 120
        if cid in (C.YVELTAL, C.BUDEW, C.FEZ, C.DUNSPARCE):
            return 60
        if cid in (C.GRIMM, C.IMPIDIMP, C.CANDY):
            return -200
        if cid in (C.LILLIE, C.DAWN, C.BOSS, C.XEROSIC):
            return -150
        return 20


def _fallback(select):
    try:
        n = len(select.option)
        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = max(0, min(lo, hi, n))
        return list(range(n))[:k] if k > 0 else [0]
    except Exception:
        return [0]


def agent(obs_dict: dict):
    try:
        obs = to_observation_class(obs_dict)
    except Exception:
        if obs_dict.get("select") is None:
            return MY_DECK
        return [0]
    if obs.select is None:
        return MY_DECK
    global pre_turn, plan
    try:
        if obs.current is not None and pre_turn != obs.current.turn:
            pre_turn = obs.current.turn
            plan = AttackPlan()
        ordered = GrimmPolicy(obs).choose()
        n = len(obs.select.option)
        ordered = [i for i in ordered if 0 <= i < n]
        if not ordered:
            return _fallback(obs.select)
        k = min(obs.select.maxCount, n)
        k = max(k, min(max(1, obs.select.minCount), n))
        return ordered[:k]
    except Exception:
        return _fallback(obs.select)
