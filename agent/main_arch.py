"""PTCG AI - Archaludon ex (鋼) Planning Agent.

現環境#1のArchaludon exデッキ用。設計はStarmie版と同じ「ターン頭で攻撃プランを
1つ確定→全ての手をそれに従属」方式。鋼単色なのでエネ種類の複雑さが無く、
やる事は「Duraludon(たね130HP)→Archaludon ex に進化(特性で鋼エネ自動加速)→
3鋼でMetal Defender 220」の一直線＝AIが最も回しやすい。依存は cg.api のみ。
"""
from __future__ import annotations

import os
from collections import defaultdict

from cg.api import (
    AreaType, Card, CardType, EnergyType, Observation, OptionType, Pokemon,
    SelectContext, all_attack, all_card_data, to_observation_class,
)


class C:
    DURALUDON = 169       # たね HP130 ジュラルドン
    ARCHALUDON = 190      # ブリジュラスex HP300, メタルディフェンダー220(鋼3), 特性で進化時に捨て札から鋼エネ2加速
    RELICANTH = 57        # ジーランス HP100。特性メモリーダイブ=進化ポケが進化前の技を使える
    METAL = 8             # 基本鋼エネ
    HEROS_CAPE = 1159
    BOSS = 1182
    CARMINE = 1192        # ゼイユ(ドロー)
    LILLIE = 1227         # リーリエの決心
    JUDGE = 1213          # ジャッジマン
    ULTRA_BALL = 1121
    POKEGEAR = 1122
    POKE_PAD = 1152
    NIGHT_STRETCHER = 1097
    SWITCH = 1123         # ポケモンいれかえ(無料逃げ)
    FULL_METAL_LAB = 1244


# 技ID
METAL_DEFENDER = 253   # ブリジュラス: 鋼3 -> 220
HAMMER_IN = 223        # ジュラルドン: 鋼1 -> 30 (メモリーダイブでブリジュラスも使える=進化即攻撃)
RAGING_HAMMER = 224    # ジュラルドン: 鋼鋼+任意 -> 80 + 自分のダメカン×10 (傷ついた程強い)


ALAKAZAM_LINE = {109, 742, 245}
WALL_IDS = {344, 345}
LOW_DECK_COUNT = 8

DECK = ([8] * 14 + [190] * 4 + [169] * 4 + [57] * 2 + [1159] * 1 + [1097] * 4 +
        [1121] * 4 + [1122] * 3 + [1152] * 4 + [1182] * 3 + [1192] * 4 +
        [1227] * 4 + [1213] * 4 + [1244] * 3 + [1123] * 2)


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


class ArchPolicy:
    def __init__(self, obs: Observation):
        self.obs = obs
        self.state = obs.current
        self.select = obs.select
        self.context = self.select.context
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
        self.opp_has_lightning = False
        for pk in self._opp_board():
            if pk is None:
                continue
            d = CARD_TABLE.get(pk.id)
            self.opp_max_dmg = max(self.opp_max_dmg, _max_atk_damage(d))
            if d and d.energyType == EnergyType.LIGHTNING:
                self.opp_has_lightning = True
        self.my_confused = bool(getattr(self.me, "confused", False))
        a0 = self.me.active[0] if self.me.active else None
        self.my_act_hp = a0.hp if a0 else 0

    def _my_board(self):
        return list(self.me.active) + list(self.me.bench)

    def _opp_board(self):
        return list(self.opp.active) + list(self.opp.bench)

    def _opp_is_wall(self):
        return any(p is not None and p.id in WALL_IDS for p in self._opp_board())

    def _low_deck(self):
        return self.me.deckCount <= LOW_DECK_COUNT

    def _attachable_now(self):
        if self.state.energyAttached:
            return 0
        return 1 if self.hand_counts[C.METAL] >= 1 else 0

    def _can_evolve_to_arch(self, board_index):
        for o in self.select.option:
            if o.type != OptionType.EVOLVE:
                continue
            c = get_card(self.obs, o.area, o.index, self.my)
            if c is None or c.id != C.ARCHALUDON:
                continue
            ti = o.inPlayIndex + (1 if o.inPlayArea == AreaType.BENCH else 0)
            if ti == board_index:
                return True
        return False

    def _memory_dive(self):
        # ジーランスが場にいれば特性メモリーダイブ=進化ポケが進化前の技を使える
        return any(p is not None and p.id == C.RELICANTH for p in self._my_board())

    def _attacks_for(self, pk, bi):
        ids = list(CARD_TABLE.get(pk.id).attacks) if CARD_TABLE.get(pk.id) else []
        evolve_accel = 0
        becomes_arch = pk.id == C.DURALUDON and self._can_evolve_to_arch(bi)
        if becomes_arch:
            ids = list(CARD_TABLE[C.ARCHALUDON].attacks)
            # 進化すると特性で捨て札から鋼エネを最大2枚加速できる
            evolve_accel = min(2, sum(1 for c in self.me.discard if c.id == C.METAL))
        # メモリーダイブ: ブリジュラス(進化後 or 今ブリジュラス化)はジュラルドンの技も使える
        is_arch = pk.id == C.ARCHALUDON or becomes_arch
        if is_arch and self._memory_dive():
            for aid in (HAMMER_IN, RAGING_HAMMER):
                if aid not in ids:
                    ids.append(aid)
        out = []
        for aid in ids:
            a = ATK_TABLE.get(aid)
            if not a or a.damage <= 0:
                continue
            dmg = a.damage
            if aid == RAGING_HAMMER:
                dmg = 80 + (pk.maxHp - pk.hp)   # 自分のダメカン×10=受けたダメ分だけ上乗せ
            out.append((aid, len(a.energies), dmg, evolve_accel))
        return out

    def _plan_attack(self):
        global plan
        plan = AttackPlan()
        if self.state.turn < 2:
            return
        best = -1
        board = self._my_board()
        extra = self._attachable_now()
        opp_bench = sum(1 for x in self.opp.bench if x is not None)
        for ai, pk in enumerate(board):
            if pk is None:
                continue
            if ai != 0 and not self.can_switch:
                continue
            energy_now = len(pk.energies)
            for aid, need, dmg, accel in self._attacks_for(pk, ai):
                avail = energy_now + extra + accel   # 今ターン用意できる総エネ(手動+進化加速)
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
                    damage = dmg
                    od = CARD_TABLE.get(opk.id)
                    if od:
                        if od.weakness == EnergyType.METAL:
                            damage *= 2
                        elif od.resistance == EnergyType.METAL:
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
                    # マッチアップ: 育つ前の脅威・自分を倒す相手を優先処理
                    if opk.id in ALAKAZAM_LINE:
                        sc += 1800 if opk.id == 245 else 1200
                    odmg = _max_atk_damage(od)
                    if self.my_act_hp and odmg >= self.my_act_hp:
                        sc += 900 if ko else 300
                    if od and od.energyType == EnergyType.LIGHTNING:
                        sc += 500
                    sc += energy_now
                    if sc > best:
                        best = sc
                        plan = AttackPlan(ai, ti, aid, ko, needs_energy)

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
            return o.number or 0
        if t == OptionType.YES:
            return 100 if self.context == SelectContext.IS_FIRST else 1
        if t == OptionType.NO:
            return 0
        if t == OptionType.CARD:
            return self._score_card(o)
        if t in (OptionType.ENERGY, OptionType.ENERGY_CARD):
            return 10
        if t == OptionType.PLAY:
            return self._score_play(o)
        if t == OptionType.ATTACH:
            return self._score_attach(o)
        if t == OptionType.EVOLVE:
            return self._score_evolve(o)
        if t == OptionType.ABILITY:
            return 30000
        if t == OptionType.RETREAT:
            if self.my_confused and self._has_ready_bench():
                return 5000
            return 2000 if plan.attacker >= 1 else -1
        if t == OptionType.ATTACK:
            return self._score_attack(o)
        if t == OptionType.END:
            return -100
        return 0

    def _has_ready_bench(self):
        for pk in self.me.bench:
            if pk is not None and pk.id == C.ARCHALUDON and len(pk.energies) >= 1:
                return True
        return False

    def _score_attack(self, o):
        if plan.attack_id < 0:
            return -1
        if self.my_confused and self._has_ready_bench():
            return -1
        return 1100 if o.attackId == plan.attack_id else 500

    def _energy_target_score(self, pk, active):
        n = len(pk.energies)
        s = 8000 + (50 if active else 0)
        if pk.id == C.ARCHALUDON:
            s += 300 if n < 3 else -200
            if self.opp_is_alakazam and active and n >= 1:
                s -= 250          # 対エスパー: アクティブに盛りすぎない
        elif pk.id == C.DURALUDON:
            s += 150 if n < 3 else -100   # 進化後を見越して少し乗せる
        else:
            s -= 300
        return s

    def _score_attach(self, o):
        card = get_card(self.obs, AreaType.HAND, o.index, self.my)
        pk = get_card(self.obs, o.inPlayArea, o.inPlayIndex, self.my)
        if not isinstance(pk, Pokemon) or card is None:
            return 0
        active = o.inPlayArea == AreaType.ACTIVE
        if card.id == C.HEROS_CAPE:
            s = 6500
            if pk.id == C.ARCHALUDON:
                s += 300 + (150 if active else 0)
                if self.opp_max_dmg >= 200:
                    s += 1500
            return s
        s = self._energy_target_score(pk, active)
        bidx = o.inPlayIndex + (0 if active else 1)
        if bidx == plan.attacker and plan.needs_energy:
            s += 500
        return s

    def _score_evolve(self, o):
        pk = get_card(self.obs, o.inPlayArea, o.inPlayIndex, self.my)
        ev = get_card(self.obs, o.area, o.index, self.my)
        if not isinstance(pk, Pokemon):
            return 0
        s = 9000 + len(pk.energies)
        if ev is not None and ev.id == C.ARCHALUDON:
            s += 1000   # 進化=特性で加速できるので最優先級
            if o.inPlayArea == AreaType.ACTIVE:
                s += 400   # アクティブを先に300HP化=脆い130Duraludonで殴られ続けない
        return s

    def _score_play(self, o):
        card = get_card(self.obs, AreaType.HAND, o.index, self.my)
        if card is None:
            return 0
        d = CARD_TABLE.get(card.id)
        if d and d.cardType == CardType.POKEMON:
            return self._score_play_pokemon(card)
        return self._score_play_trainer(card)

    def _score_play_pokemon(self, card):
        if card.id == C.DURALUDON:
            line = self.field_counts[C.DURALUDON] + self.field_counts[C.ARCHALUDON]
            return -1 if line >= 3 else 20000
        if card.id == C.RELICANTH:
            return 8000 if self.field_counts[C.RELICANTH] == 0 else -1
        return 15000

    def _score_play_trainer(self, card):
        cid = card.id
        if cid == C.SWITCH:
            # 無料逃げ: プランのアタッカーがベンチなら盤面に出す。こんらん中も脱出。
            if plan.attacker >= 1:
                return 2600
            if self.my_confused and self._has_ready_bench():
                return 2600
            return -1
        if cid == C.BOSS:
            return 3200 if plan.target >= 1 else -1
        if cid == C.ULTRA_BALL:
            # 進化パーツのサーチ＋コストで鋼を捨て札に送りAssemble Alloyを起動する二役。
            need = self.field_counts[C.ARCHALUDON] + self.field_counts[C.DURALUDON] < 2
            metal_in_disc = sum(1 for c in self.me.discard if c.id == C.METAL)
            # コストで鋼を捨て札に仕込みAssemble Alloyを起動(=進化即3エネ)。
            # この高速化が対Starmie等の勝因。
            fuel = self.hand_counts[C.METAL] >= 2 and metal_in_disc < 2
            return 3000 if (need or fuel) else 1500
        if cid == C.POKEGEAR:
            return 2400
        if cid == C.POKE_PAD:
            return 2300
        if cid in (C.LILLIE, C.CARMINE, C.JUDGE):
            if self._low_deck():
                return -1
            hc = self.me.handCount
            return 3000 if hc <= 4 else (1500 if hc <= 6 else 400)
        if cid == C.NIGHT_STRETCHER:
            return 1500
        if cid == C.FULL_METAL_LAB:
            return 1200 if not self.state.stadium else -1
        return 1000

    def _score_card(self, o):
        card = get_card(self.obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0
        ctx = self.context
        if ctx in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
            return self._score_active_choice(o, card)
        if ctx in (SelectContext.SETUP_ACTIVE_POKEMON, SelectContext.SETUP_BENCH_POKEMON,
                   SelectContext.TO_BENCH, SelectContext.TO_FIELD):
            return self._score_to_field(card)
        if ctx == SelectContext.TO_HAND:
            return self._score_to_hand(card)
        if ctx == SelectContext.ATTACH_FROM and isinstance(card, Pokemon):
            return self._energy_target_score(card, o.area == AreaType.ACTIVE)
        if ctx in (SelectContext.DISCARD, SelectContext.TO_DECK, SelectContext.TO_DECK_BOTTOM):
            return self._score_discard(card)
        return 0

    def _score_active_choice(self, o, card):
        if not isinstance(card, Pokemon):
            return 0
        if o.playerIndex != self.my:
            return 100 if o.index == plan.target - 1 else 0
        s = len(card.energies) * 5
        if o.index == plan.attacker - 1:
            s += 200
        if card.id == C.ARCHALUDON:
            s += 50
        elif card.id == C.DURALUDON:
            s += 10
        return s

    def _score_to_field(self, card):
        if card.id == C.DURALUDON:
            return 50
        if card.id == C.ARCHALUDON:
            return 40
        if card.id == C.RELICANTH:
            return 20
        return 10

    def _score_to_hand(self, card):
        s = 200 - self.hand_counts[card.id] * 50
        if card.id == C.ARCHALUDON:
            s += 150 if self.field_counts[C.DURALUDON] >= 1 else 60
        elif card.id == C.DURALUDON:
            line = self.field_counts[C.DURALUDON] + self.field_counts[C.ARCHALUDON]
            s += 120 if line == 0 else -10
        elif card.id == C.METAL:
            s += 60
        return s

    def _score_discard(self, card):
        # Assemble Alloy(進化時に捨て札から鋼エネ2枚を加速)を回すため、鋼を捨て札へ。
        # 重要札(進化パーツ)は残す。
        if card.id in (C.ARCHALUDON, C.DURALUDON, C.RELICANTH):
            return -200
        if card.id == C.METAL:
            return 120   # 捨て札の鋼=進化時に回収して即3エネ圏=最優先で捨て札に送る
        return 0


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
        ordered = ArchPolicy(obs).choose()
        n = len(obs.select.option)
        ordered = [i for i in ordered if 0 <= i < n]
        if not ordered:
            return _fallback(obs.select)
        k = min(obs.select.maxCount, n)
        k = max(k, min(max(1, obs.select.minCount), n))
        return ordered[:k]
    except Exception:
        return _fallback(obs.select)
