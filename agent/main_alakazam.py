"""PTCG AI - フーディン(Alakazam, 超) Planning Agent.

現メタ第2勢力=exを狩るアンチメタ。勝ち筋:
ケーシィ(741)→ふしぎなアメでフーディン(743,HP140非ex)へ進化→技パワフルハンド(1072,超1)
=「手札の枚数×2ダメカン(=20ダメージ)」。手札10枚で1エネ200ダメージ。
1サイドの非exなので2-3サイドのexと殴り合えばサイド勝ち。

設計の肝(通常デッキと逆): **手札を最大化してから殴る**。
ドローエンジン(進化時サイキックドロー3/ノココッチのにげドロー3/リッチエネ4ドロー)で
手札を膨らませ、攻撃ターンは余計なカードを使わず温存する。依存は cg.api のみ。
"""
from __future__ import annotations

import os
from collections import defaultdict

from cg.api import (
    AreaType, Card, CardType, EnergyType, Observation, OptionType, Pokemon,
    SelectContext, all_attack, all_card_data, to_observation_class,
)


class C:
    ABRA = 741            # ケーシィ HP50 たね
    KADABRA = 742         # ユンゲラー HP80 st1 サイキックドロー2
    ALAKAZAM = 743        # フーディン HP140 st2 サイキックドロー3 / パワフルハンド
    DUNSPARCE = 305       # ノコッチ HP70 たね
    DUDUNSPARCE = 66      # ノココッチ HP140 にげドロー3(自身を山へ)
    RARE_CANDY = 1079     # ふしぎなアメ (ケーシィ→フーディン)
    ENHANCED_HAMMER = 1081  # 改造ハンマー: 相手の特殊エネを1枚トラッシュ
    POFFIN = 1086         # なかよしポフィン(HP70以下たね2体)
    POKE_PAD = 1152       # ポケパッド
    HILDA = 1225          # トウコ: 進化ポケ+エネをサーチ
    DAWN = 1231           # ヒカリ: たね+1進化+2進化サーチ
    NIGHT_STRETCHER = 1097  # 夜のタンカ
    BOSS = 1182           # ボスの指令
    LANA = 1184           # スイレンのお世話(非ルールボックス回収)
    HOLY_ASH = 1129       # せいなるはい
    PSY_ENERGY = 5        # 基本超エネ
    TELEPATH = 19         # テレパス超エネ(付けたらサーチ)
    ENRICH = 13           # リッチエネルギー(付けたら4ドロー)
    BATTLE_CAGE = 1264    # バトルコロシアム(ベンチにダメカン置かせない)


POWERFUL_HAND = 1072   # フーディン: 超1 -> 手札枚数×2ダメカン(=×20ダメージ)
SUPER_PSY_BOLT = 1071  # ユンゲラー: 超1 -> 30
LAND_CRUSH = 76        # ノココッチ: 3エネ -> 90
ALAKAZAM_EVOLVE_LINE = {C.ABRA, C.KADABRA, C.ALAKAZAM}
PSY_ENERGIES = {C.PSY_ENERGY, C.TELEPATH, C.ENRICH}
WALL_IDS = {344, 345}
LOW_DECK_COUNT = 6

DECK = ([19] * 4 + [305] * 4 + [741] * 4 + [742] * 4 + [743] * 4 +
        [1079] * 4 + [1081] * 4 + [1086] * 4 + [1152] * 4 + [1225] * 4 +
        [1231] * 4 + [5] * 3 + [66] * 3 + [1097] * 3 + [1182] * 3 +
        [13] * 1 + [1129] * 1 + [1184] * 1 + [1264] * 1)


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
    s = prize_count(pk) * 1000 + len(pk.energies) * 120 + len(pk.tools) * 60
    if d:
        s += 250 if d.stage2 else 130 if d.stage1 else 0
    s += pk.hp
    return s


class AlakazamPolicy:
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

        self.hand_size = self.me.handCount
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

        self.opp_is_wall = any(p is not None and p.id in WALL_IDS for p in self._opp_board())
        self.opp_max_dmg = 0
        for pk in self._opp_board():
            if pk is not None:
                self.opp_max_dmg = max(self.opp_max_dmg, _max_atk_damage(CARD_TABLE.get(pk.id)))
        self.opp_special_energy = self._opp_has_special_energy()
        self.my_confused = bool(getattr(self.me, "confused", False))
        a0 = self.me.active[0] if self.me.active else None
        self.my_act_hp = a0.hp if a0 else 0

    def _my_board(self):
        return list(self.me.active) + list(self.me.bench)

    def _opp_board(self):
        return list(self.opp.active) + list(self.opp.bench)

    def _low_deck(self):
        return self.me.deckCount <= LOW_DECK_COUNT

    def _opp_has_special_energy(self):
        for pk in self._opp_board():
            if pk is None:
                continue
            for e in (pk.energies or []):
                eid = getattr(e, "id", e)
                d = CARD_TABLE.get(eid)
                if d and d.cardType == CardType.SPECIAL_ENERGY:
                    return True
        return False

    def _attachable_now(self):
        if self.state.energyAttached:
            return 0
        return 1 if any(self.hand_counts[e] >= 1 for e in PSY_ENERGIES) else 0

    def _powerful_hand_damage(self):
        # パワフルハンド: 攻撃時の手札枚数×20。攻撃選択時、その技を撃つと手札は減らない
        # (エネは既に付いている前提)。安全側に現手札枚数で見積もる。
        return self.hand_size * 20

    def _attacks_for(self, pk):
        ids = list(CARD_TABLE.get(pk.id).attacks) if CARD_TABLE.get(pk.id) else []
        out = []
        for aid in ids:
            a = ATK_TABLE.get(aid)
            if not a:
                continue
            dmg = a.damage
            if aid == POWERFUL_HAND:
                dmg = self._powerful_hand_damage()
            if dmg <= 0:
                continue
            out.append((aid, len(a.energies), dmg))
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
            for aid, need, dmg in self._attacks_for(pk):
                avail = energy_now + extra
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
                        if od.weakness == EnergyType.PSYCHIC:
                            damage *= 2
                        elif od.resistance == EnergyType.PSYCHIC:
                            damage -= 30
                    ko = opk.hp <= damage
                    # 攻撃規律(上位ログ): パワフルハンドは小さくチマチマ撃たない。
                    # KOできる/手札が十分大きい/倒される緊急時 以外は温存してドローで
                    # 手札を育てる(勝者は手札13で大型exを2発KO、敗者は小手札でチップ負け)。
                    odmg_pre = _max_atk_damage(CARD_TABLE.get(opk.id))
                    under_pressure = bool(self.my_act_hp and odmg_pre >= self.my_act_hp)
                    # 高火力アグロ(ルカリオ等)相手は貯めすぎるとレース負け=早めに殴りトレード。
                    hold_thresh = 8 if self.opp_max_dmg >= 200 else 11
                    if aid == POWERFUL_HAND and not ko and self.hand_size < hold_thresh \
                            and not under_pressure:
                        continue
                    sc = target_score(opk)
                    if ko:
                        sc += 4000
                        if len(self.opp.prize) <= prize_count(opk):
                            sc = 90000
                    else:
                        sc *= damage / max(1, opk.hp)
                    sc += 600 if ai == 0 else 0
                    sc += 300 if ti == 0 else 0
                    # ex/mega(2-3サイド)を狩るのがこのデッキの本分=高価値
                    if od and (od.ex or od.megaEx):
                        sc += 1500 if ko else 500
                    odmg = _max_atk_damage(od)
                    if self.my_act_hp and odmg >= self.my_act_hp:
                        sc += 700 if ko else 200
                    if sc > best:
                        best = sc
                        plan = AttackPlan(ai, ti, aid, ko, needs_energy)

    def _alakazam_ready(self):
        for pk in self._my_board():
            if pk is not None and pk.id == C.ALAKAZAM and len(pk.energies) >= 1:
                return True
        return False

    def _bench_alakazam_ready(self):
        for pk in self.me.bench:
            if pk is not None and pk.id == C.ALAKAZAM and len(pk.energies) >= 1:
                return True
        return False

    def _can_retreat_active(self):
        act = self.me.active[0] if self.me.active else None
        if not act:
            return False
        d = CARD_TABLE.get(act.id)
        return len(act.energies) >= (d.retreatCost if d else 0)

    def _promote_worth_it(self):
        if plan.attacker < 1:
            return False
        if plan.ko:
            return True
        bi = plan.attacker - 1
        bench = self.me.bench
        bp = bench[bi] if 0 <= bi < len(bench) else None
        if not bp:
            return False
        return bp.id == C.ALAKAZAM and len(bp.energies) >= 1

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
            return o.number or 0
        if t == OptionType.YES:
            # 進化時サイキックドロー・ノココッチのにげドロー等の起動は常にYES
            if self.context in (SelectContext.IS_FIRST, SelectContext.ACTIVATE):
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
            return 30000    # ドロー特性(サイキックドロー/にげドロー)は最優先=手札を膨らませる
        if t == OptionType.RETREAT:
            if self.my_confused and self._bench_alakazam_ready():
                return 5000
            return 2000 if self._promote_worth_it() else -1
        if t == OptionType.ATTACK:
            if plan.attack_id < 0:
                return -1
            if self.my_confused and self._bench_alakazam_ready():
                return -1
            return 1100 if o.attackId == plan.attack_id else 500
        if t == OptionType.END:
            return -100
        return 0

    # ---- エネ ----
    def _energy_target_score(self, pk, active):
        n = len(pk.energies)
        s = 8000 + (50 if active else 0)
        if pk.id == C.ALAKAZAM:
            s += 300 if n < 1 else -400   # フーディンは1エネで撃てる。過剰付けは不要
        elif pk.id == C.KADABRA:
            s += 150 if n < 1 else -300   # 繋ぎのユンゲラーにも1エネ
        elif pk.id == C.DUDUNSPARCE:
            s += 100 if n < 3 else -200   # 副アタッカー(ランドクラッシュ90)
        else:
            # 逃げ用の最小限を除き非ラインには付けない
            if (active and self._bench_alakazam_ready() and not self._can_retreat_active()):
                return 6000
            return -800
        return s

    def _score_attach(self, o):
        card = get_card(self.obs, AreaType.HAND, o.index, self.my)
        pk = get_card(self.obs, o.inPlayArea, o.inPlayIndex, self.my)
        if not isinstance(pk, Pokemon) or card is None:
            return 0
        active = o.inPlayArea == AreaType.ACTIVE
        s = self._energy_target_score(pk, active)
        bidx = o.inPlayIndex + (0 if active else 1)
        if bidx == plan.attacker and plan.needs_energy:
            return 12000   # このエネで今ターン殴れる=最優先
        return s

    # ---- 進化 ----
    def _score_evolve(self, o):
        pk = get_card(self.obs, o.inPlayArea, o.inPlayIndex, self.my)
        ev = get_card(self.obs, o.area, o.index, self.my)
        if not isinstance(pk, Pokemon):
            return 0
        s = 9000 + len(pk.energies)
        if ev is not None and ev.id == C.ALAKAZAM:
            s += 800    # フーディン進化=サイキックドロー3+攻撃態勢。最優先
        if ev is not None and ev.id == C.KADABRA:
            s += 300    # 繋ぎ(アメが無い時)。サイキックドロー2
        if ev is not None and ev.id == C.DUDUNSPARCE:
            s -= 200    # ノココッチは手札が細い時のドロー用(急がない)
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
        if cid == C.ABRA:
            return 5000 - self.field_counts[C.ABRA] * 700   # 本命ラインのたねを展開
        if cid == C.DUNSPARCE:
            return 3000 if self.field_counts[C.DUNSPARCE] + self.field_counts[C.DUDUNSPARCE] == 0 else 700
        return 300

    def _line_missing(self):
        have_a = self.field_counts[C.ALAKAZAM] + self.hand_counts[C.ALAKAZAM]
        have_ab = self.field_counts[C.ABRA]
        return have_a == 0 or have_ab == 0

    def _score_play_trainer(self, card):
        cid = card.id
        # 攻撃態勢が整っている(場に1エネ以上のフーディン)なら、パワフルハンドの火力を
        # 減らさないため不要なカードは温存する(=手札を残す)。育成/サーチのみ許可。
        established = self._alakazam_ready()

        if cid == C.RARE_CANDY:
            # ふしぎなアメ: ケーシィが場&フーディンが手札なら即進化(このデッキの心臓)
            if self.field_counts[C.ABRA] >= 1 and self.hand_counts[C.ALAKAZAM] >= 1:
                return 9600
            return -1
        if cid == C.ENRICH:
            # リッチエネルギー: 付けると4ドロー。手札を大きく増やす=火力源。エネ付け枠で処理
            return -1  # ATTACH経由で付ける(ここでは何もしない)
        if cid == C.POFFIN:
            bench_n = sum(1 for p in self.me.bench if p is not None)
            if bench_n >= 5:
                return -1
            if self.field_counts[C.ABRA] < 2:
                return 3600
            return 1200 if bench_n <= 3 else -1
        if cid == C.POKE_PAD:
            return 3300 if (self._line_missing() or not established) else 200
        if cid == C.HILDA:
            # トウコ: 進化ポケ+エネをサーチ=ライン補完の主力
            return 3400 if self._line_missing() else 800
        if cid == C.DAWN:
            return 3500 if self._line_missing() else 700
        if cid == C.ENHANCED_HAMMER:
            # 改造ハンマー: 相手が特殊エネを使っていれば妨害。基本エネのみなら腐る
            return 2600 if self.opp_special_energy else -1
        if cid == C.BOSS:
            return 3200 if plan.target >= 1 else -1
        if cid == C.NIGHT_STRETCHER:
            return 1200 if self._line_missing() else -1
        if cid == C.LANA:
            cur = self.state.stadium
            if cur and cur[0].id == C.LANA:
                return -1
            return 900 if self._low_deck() else 300
        if cid == C.BATTLE_CAGE:
            cur = self.state.stadium
            if cur and cur[0].id == C.BATTLE_CAGE:
                return -1
            return 1000
        if cid == C.HOLY_ASH:
            return 400 if self._low_deck() else -1
        return 500 if not established else -1

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
        return 0

    def _score_opp_pokemon(self, o, pk):
        s = 0
        d = CARD_TABLE.get(pk.id)
        if d and (d.ex or d.megaEx):
            s += 2000 + prize_count(pk) * 500   # ex/megaを釣る/狙う
        if o.index == plan.target - 1:
            s += 400
        s += target_score(pk) // 10
        s -= pk.hp // 6
        return s

    def _score_active_choice(self, o, card):
        if not isinstance(card, Pokemon):
            return 0
        if o.playerIndex != self.my:
            return 100 if o.index == plan.target - 1 else 0
        s = len(card.energies) * 5
        if o.index == plan.attacker - 1:
            s += 200
        if card.id == C.ALAKAZAM:
            s += 60
        elif card.id == C.DUNSPARCE:
            s += 12    # 壁役の捨て駒として悪くない
        return s

    def _score_to_field(self, card, ctx=None):
        if ctx == SelectContext.SETUP_ACTIVE_POKEMON:
            # 前衛はノコッチ(捨て駒・ドロー源)を優先。育てたいケーシィはベンチで安全に。
            if card.id == C.DUNSPARCE:
                return 55
            if card.id == C.ABRA:
                return 25
            return 10
        if card.id == C.ABRA:
            return 60
        if card.id == C.DUNSPARCE:
            return 45
        return 15

    def _score_to_hand(self, card):
        def have(cid):
            return self.field_counts[cid] + self.hand_counts[cid]
        cid = card.id
        bench_pokemon = sum(1 for p in self.me.bench if p is not None)
        if cid == C.ABRA:
            s = 500 - have(C.ABRA) * 120
            if bench_pokemon == 0:
                s += 300
            return s
        if cid == C.ALAKAZAM:
            return 480 - have(C.ALAKAZAM) * 130
        if cid == C.RARE_CANDY:
            return 430 - self.hand_counts[C.RARE_CANDY] * 140
        if cid == C.KADABRA:
            if self.hand_counts[C.RARE_CANDY] >= 1:
                return 50
            return 250 - have(C.KADABRA) * 110
        if cid == C.DUNSPARCE:
            return 150 if have(C.DUNSPARCE) + have(C.DUDUNSPARCE) == 0 else -40
        if cid in PSY_ENERGIES:
            return 120
        return 40

    def _score_discard(self, card):
        cid = card.id
        # 核(ケーシィ/フーディン/アメ)は死守。エネ>余りポケ>グッズ>サポの順で捨てる
        if cid in PSY_ENERGIES:
            return 100
        if cid in (C.DUNSPARCE, C.DUDUNSPARCE):
            return 60
        if cid in (C.ABRA, C.ALAKAZAM, C.RARE_CANDY, C.KADABRA):
            return -200
        if cid in (C.HILDA, C.DAWN, C.BOSS, C.LANA):
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
        ordered = AlakazamPolicy(obs).choose()
        n = len(obs.select.option)
        ordered = [i for i in ordered if 0 <= i < n]
        if not ordered:
            return _fallback(obs.select)
        k = min(obs.select.maxCount, n)
        k = max(k, min(max(1, obs.select.minCount), n))
        return ordered[:k]
    except Exception:
        return _fallback(obs.select)
