"""PTCG AI - Mega Starmie ex Planning Agent.

設計: 上位公開agent(LucarioPolicy)の「ターン頭で攻撃プランを1個確定し、
全ての手をそのプランに従属させて点数化する」planning方式を、実ラダー1位の
メガスターミーexデッキ用に作り替えたもの。1手ごと独立スコアのRL/壁と違い、
コンボ(進化→エネ充填→引きずり出し→攻撃)を逆算して一筆書きで組み立てる。

依存は cg.api のみ(numpy不要・~20KB)。全体 try-except でクラッシュセーフ。
"""
from __future__ import annotations

import os
from collections import defaultdict

from cg.api import (
    AreaType,
    Card,
    CardType,
    EnergyType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_attack,
    all_card_data,
    to_observation_class,
)


# ---- カードID ----
class C:
    STARYU = 1030
    MEGA_STARMIE = 1031          # Staryuから進化, HP330
    CINDERACE = 666              # 死に札(進化元なし)だが1位リストに準拠
    SCORBUNNY = 664
    RABOOT = 665

    WATER_ENERGY = 3             # 基本水
    IGNITION_ENERGY = 17         # 特殊(CCCを供給=ネビュラビーム一発充填)

    BUDDY_POFFIN = 1086
    NIGHT_STRETCHER = 1097
    CRUSHING_HAMMER = 1120
    ULTRA_BALL = 1121
    POKEGEAR = 1122
    MEGA_SIGNAL = 1145          # メガ進化exをサーチ
    HEROS_CAPE = 1159
    BOSS_ORDERS = 1182
    SALVATORE = 1189            # 進化サーチ(能力なし)
    HARLEQUIN = 1223
    HILDA = 1225               # 進化+エネをサーチ
    LILLIE = 1227
    WALLY = 1229               # メガexを全回復(エネは手札に戻る)

    DWEBBLE = 344
    CRUSTLE = 345              # 壁


# 技ID
JETTING_BLOW = 1487    # 水1 -> 120 (+ベンチ50)。※水エネ必須
NEBULA_BEAM = 1488     # 任意3 -> 210, 相手の弱点/効果を全無視(壁貫通)
WATER_GUN = 1486       # Staryu 水1 -> 20
TURBO_FLARE = 965      # Cinderace 1 -> 50 + 山から基本エネ3枚をベンチに加速(エンジン)

ATTACK_PIERCE = {NEBULA_BEAM}     # 弱点・相手効果を無視する技
ATTACK_NEED_WATER = {JETTING_BLOW, WATER_GUN}  # 水エネが必要な技
STARMIE_LINE = {1030, 1031}       # Staryu / Mega Starmie ex
ALAKAZAM_LINE = {109, 742, 245}   # Abra / Kadabra / Alakazam(エネ依存スケール火力=こちらのエネを盛ると痛い)
ARCHALUDON_LINE = {169, 190}      # Duraludon / Archaludon ex(現1位・鋼220。進化前に刈りたい)
WALL_IDS = {344, 345}             # Dwebble / Crustle (ex無効の壁)
LOW_DECK_COUNT = 8


def _max_atk_damage(card):
    """そのカードの最大攻撃ダメージ(脅威度判定用)。"""
    if not card:
        return 0
    best = 0
    for aid in card.attacks:
        a = ATK_TABLE.get(aid)
        if a:
            best = max(best, a.damage)
    return best


# ---- デッキ(1位 Yushin Ito 1404.2 を完全コピー) ----
DECK = (
    [3] * 9 + [17] * 4 + [666] * 4 + [1030] * 3 + [1031] * 3 +
    [1086] * 4 + [1097] * 2 + [1120] * 4 + [1121] * 1 + [1122] * 4 +
    [1145] * 4 + [1159] * 1 + [1182] * 1 + [1189] * 4 + [1223] * 2 +
    [1225] * 2 + [1227] * 4 + [1229] * 4
)


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


# ---- ターンをまたぐ状態 ----
class AttackPlan:
    def __init__(self, attacker=-1, target=-1, attack_id=-1, ko=False, needs_energy=False):
        self.attacker = attacker        # 自盤面index (0=active, 1..=bench)
        self.target = target            # 相手盤面index
        self.attack_id = attack_id
        self.ko = ko                    # この攻撃で相手をKOできるか
        self.needs_energy = needs_energy


plan = AttackPlan()
pre_turn = -1


def get_card(obs, area, index, player_index):
    p = obs.current.players[player_index]
    if area == AreaType.DECK:
        return obs.select.deck[index] if obs.select.deck else None
    if area == AreaType.HAND:
        return p.hand[index] if p.hand else None
    if area == AreaType.DISCARD:
        return p.discard[index]
    if area == AreaType.ACTIVE:
        return p.active[index] if p.active else None
    if area == AreaType.BENCH:
        return p.bench[index]
    if area == AreaType.PRIZE:
        return p.prize[index]
    if area == AreaType.STADIUM:
        return obs.current.stadium[index]
    if area == AreaType.LOOKING:
        return obs.current.looking[index]
    return None


def prize_count(pokemon):
    d = CARD_TABLE.get(pokemon.id)
    if not d:
        return 1
    return 3 if d.megaEx else 2 if d.ex else 1


def target_score(pokemon):
    """相手ポケを倒す価値。サイド枚数・エネ量・進化段階で重み付け。"""
    d = CARD_TABLE.get(pokemon.id)
    score = prize_count(pokemon) * 1000
    score += len(pokemon.energies) * 150       # エネが多い=育った脅威を優先
    score += len(pokemon.tools) * 80
    if d:
        if d.stage2:
            score += 250
        elif d.stage1:
            score += 130
    score += pokemon.hp
    return score


class StarmiePolicy:
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
        self._scan_options()

        # ---- 相手分析(マッチアップ対策の土台) ----
        self.opp_is_alakazam = self._opp_has(ALAKAZAM_LINE)
        self.opp_max_dmg = 0
        self.opp_has_lightning = False
        for pk in self._opp_board():
            if pk is None:
                continue
            d = CARD_TABLE.get(pk.id)
            self.opp_max_dmg = max(self.opp_max_dmg, _max_atk_damage(d))
            if d and d.energyType == EnergyType.LIGHTNING:
                self.opp_has_lightning = True   # 雷=こちらの弱点×2
        self.my_confused = bool(getattr(self.me, "confused", False))
        # 自分のアクティブHP(脅威評価用)
        my_act = self.me.active[0] if self.me.active else None
        self.my_act_hp = my_act.hp if my_act else 0

    # ---- 盤面 ----
    def _my_board(self):
        return list(self.me.active) + list(self.me.bench)

    def _opp_board(self):
        return list(self.opp.active) + list(self.opp.bench)

    def _opp_has(self, ids):
        return any(p is not None and p.id in ids for p in self._opp_board())

    def _opp_is_wall(self):
        return self._opp_has({C.DWEBBLE, C.CRUSTLE})

    def _low_deck(self):
        return self.me.deckCount <= LOW_DECK_COUNT

    def _scan_options(self):
        if self.context != SelectContext.MAIN:
            return
        for o in self.select.option:
            if o.type == OptionType.PLAY:
                c = get_card(self.obs, AreaType.HAND, o.index, self.my)
                if c and c.id == C.BOSS_ORDERS:
                    self.can_gust = True
            elif o.type == OptionType.RETREAT:
                self.can_switch = True

    # ---- エネ充填の見込み ----
    def _attachable_now(self):
        """今ターン手動エネ付けで足せる最大エネ数(Ignition=3, 水=1)。"""
        if self.state.energyAttached:
            return 0
        if self.hand_counts[C.IGNITION_ENERGY] >= 1:
            return 3
        if self.hand_counts[C.WATER_ENERGY] >= 1:
            return 1
        return 0

    def _can_evolve_to_starmie(self, board_index):
        for o in self.select.option:
            if o.type != OptionType.EVOLVE:
                continue
            c = get_card(self.obs, o.area, o.index, self.my)
            if c is None or c.id != C.MEGA_STARMIE:
                continue
            ti = o.inPlayIndex + (1 if o.inPlayArea == AreaType.BENCH else 0)
            if ti == board_index:
                return True
        return False

    def _water_count(self, pokemon):
        return sum(1 for e in pokemon.energies if e == EnergyType.WATER)

    def _attacks_for(self, pokemon, board_index):
        """このポケが今ターン使える(attack_id, energy_need, damage, pierce, need_water)を列挙。
        Staryu位置で進化可能ならMega Starmie exの技も先読みする。"""
        out = []
        ids = list(CARD_TABLE.get(pokemon.id).attacks) if CARD_TABLE.get(pokemon.id) else []
        if pokemon.id == C.STARYU and self._can_evolve_to_starmie(board_index):
            ids = list(CARD_TABLE[C.MEGA_STARMIE].attacks)
        for aid in ids:
            a = ATK_TABLE.get(aid)
            if not a or a.damage <= 0:
                continue
            out.append((aid, len(a.energies), a.damage, aid in ATTACK_PIERCE, aid in ATTACK_NEED_WATER))
        return out

    def _develop_need(self):
        """ベンチ含むスターミー系が「あと何エネで3エネに届くか」の合計(加速の価値)。"""
        need = 0
        for pk in self._my_board():
            if pk is not None and pk.id in (C.STARYU, C.MEGA_STARMIE):
                need += max(0, 3 - len(pk.energies))
        return need

    # ---- 攻撃プラン確定(planningの核) ----
    def _plan_attack(self):
        global plan
        plan = AttackPlan()
        if self.state.turn < 2:
            return
        best = -1
        board = self._my_board()
        extra = self._attachable_now()
        extra_water = 1 if (not self.state.energyAttached and self.hand_counts[C.WATER_ENERGY] >= 1) else 0

        for ai, pk in enumerate(board):
            if pk is None:
                continue
            if ai != 0 and not self.can_switch:
                continue  # ベンチから殴るには入れ替えが必要
            energy_now = len(pk.energies)
            water_now = self._water_count(pk)
            opp_bench_count = sum(1 for x in self.opp.bench if x is not None)
            for aid, need, dmg, pierce, need_water in self._attacks_for(pk, ai):
                # --- エンジン: エースバーンのターボフレア(加速)を develop plan として評価 ---
                if aid == TURBO_FLARE:
                    if ai != 0:
                        continue  # エースバーンが既にアクティブの時だけ(わざわざ引っ込めない)
                    if energy_now < need and energy_now + extra < need:
                        continue
                    dneed = self._develop_need()
                    if dneed <= 0:
                        continue  # 加速先がない(全部育ち切ってる)なら只の50ダメ -> 後段で評価
                    opp_act = self.opp.active[0] if self.opp.active else None
                    chip_ko = bool(opp_act and opp_act.hp <= 50)
                    sc = 2000 + dneed * 500 + (1500 if chip_ko else 0)
                    if sc > best:
                        best = sc
                        plan = AttackPlan(ai, 0, aid, chip_ko, energy_now < need)
                    continue

                # --- 通常の攻撃プラン ---
                needs_energy = False
                if need_water and water_now < 1 and water_now + extra_water < 1:
                    continue  # 水技なのに水エネが用意できない(Ignitionの無色では撃てない)
                if energy_now < need:
                    if energy_now + extra >= need:
                        needs_energy = True
                    else:
                        continue
                for ti, opk in enumerate(self._opp_board()):
                    if opk is None:
                        continue
                    if ti != 0 and not self.can_gust:
                        continue  # ベンチを狙うにはボスが必要
                    # 壁(イワパレス等のex無効特性)のアクティブは、効果無視の貫通技でしか倒せない
                    if not pierce and ti == 0 and opk.id in (C.DWEBBLE, C.CRUSTLE):
                        continue
                    damage = dmg
                    od = CARD_TABLE.get(opk.id)
                    if not pierce and od:
                        if od.weakness == EnergyType.WATER:
                            damage *= 2
                        elif od.resistance == EnergyType.WATER:
                            damage -= 30
                    ko = opk.hp <= damage
                    sc = target_score(opk)
                    if ko:
                        sc += 4000
                        if len(self.opp.prize) <= prize_count(opk):
                            sc = 90000  # 勝ち確
                    else:
                        sc *= damage / max(1, opk.hp)
                    sc += 600 if ai == 0 else 0      # アクティブで殴れる方が楽
                    sc += 300 if ti == 0 else 0
                    sc += 250 if pierce else 0       # 壁/弱点無視は信頼度高い
                    # ① 対エスパー: フーディン系は育つ前に最優先で刈る(エネ依存火力が脅威)
                    if opk.id in ALAKAZAM_LINE:
                        sc += 1800 if opk.id == 245 else 1200
                    # 対鋼: Archaludon ex(220)は脅威。進化前ジュラルドンを早期に刈れば220を防げる
                    if opk.id == 190:
                        sc += 1600                      # 完成Archaludonは最優先処理
                    elif opk.id == 169:
                        sc += 900 if ko else 400        # ジュラルドンは進化前にKOできるなら刈る
                    # ③ 自分を倒してくる脅威を先に処理(KOできる時ほど価値大)
                    odmg = _max_atk_damage(od)
                    if self.my_act_hp and odmg >= self.my_act_hp:
                        sc += 900 if ko else 300
                    # ④ 雷=こちらの弱点×2 -> 早めにKOしたい
                    if od and od.energyType == EnergyType.LIGHTNING:
                        sc += 500
                    # Jetting Blow(120+ベンチ50)はベンチに的がいる時に効率的=分散ダメージ
                    if aid == JETTING_BLOW and ti == 0 and opp_bench_count >= 1:
                        sc += 250
                    # ① 対エスパー: エネを盛らない方が返しダメが減る -> 安いJetting Blow優先
                    if self.opp_is_alakazam:
                        if aid == JETTING_BLOW:
                            sc += 700
                        elif aid == NEBULA_BEAM and not ko:
                            sc -= 600   # KOしないのに3エネ盛るのは損(返り討ち)
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

    # ---- 各手をプランに従属させて点数化 ----
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
        if t == OptionType.ENERGY or t == OptionType.ENERGY_CARD:
            return self._score_energy_pick(o)
        if t == OptionType.PLAY:
            return self._score_play(o)
        if t == OptionType.ATTACH:
            return self._score_attach(o)
        if t == OptionType.EVOLVE:
            return self._score_evolve(o)
        if t == OptionType.ABILITY:
            return 30000
        if t == OptionType.RETREAT:
            # ⑤ こんらん中は技が表裏で失敗する -> 控えが育ってるなら逃げて殴り直す
            if self.my_confused and self._has_ready_bench_attacker():
                return 5000
            return 2000 if plan.attacker >= 1 else -1
        if t == OptionType.ATTACK:
            return self._score_attack(o)
        if t == OptionType.END:
            return -100
        return 0

    def _has_ready_bench_attacker(self):
        for pk in self.me.bench:
            if pk is not None and pk.id == C.MEGA_STARMIE and len(pk.energies) >= 1:
                return True
        return False

    def _score_attack(self, o):
        if plan.attack_id < 0:
            return -1  # 殴る価値がある攻撃は計画されてない -> 撃たない
        # ⑤ こんらん中で控えが居るなら、まず逃げる(攻撃は後回し)
        if self.my_confused and self._has_ready_bench_attacker():
            return -1
        if o.attackId == plan.attack_id:
            return 1100
        return 500   # 一応プラン外の攻撃も合法手として低めに

    def _energy_target_score(self, pokemon, active):
        """エネはまず攻撃要員(active Mega Starmie/Staryu)に3個まで。余ったらベンチ育成。"""
        n = len(pokemon.energies)
        score = 8000 + (50 if active else 0)
        if pokemon.id in (C.MEGA_STARMIE, C.STARYU):
            score += 300 if n < 3 else -200   # 3で打ち止め
            # ① 対エスパー: アクティブにエネを盛るほどサイコの返しダメが増える
            #    -> アクティブは控えめ、控え(2体目)を優先的に育てる
            if self.opp_is_alakazam:
                if active and n >= 1:
                    score -= 250
                elif not active:
                    score += 200
            # ⑦ アクティブが完成(>=3)なら、ベンチの2体目スターミー系を育てる
            elif not active and n < 3:
                score += 80
        else:
            score -= 300                      # それ以外には付けない
        return score

    def _score_attach(self, o):
        card = get_card(self.obs, AreaType.HAND, o.index, self.my)
        pk = get_card(self.obs, o.inPlayArea, o.inPlayIndex, self.my)
        if not isinstance(pk, Pokemon) or card is None:
            return 0
        active = o.inPlayArea == AreaType.ACTIVE
        if card.id == C.HEROS_CAPE:
            # ② エネを溜めて戦うメガスターミーに+100HP。相手が高火力ほど価値大(430HPで耐える)
            s = 6500
            if pk.id == C.MEGA_STARMIE:
                s += 300 + (150 if active else 0) + len(pk.energies) * 30
                if self.opp_max_dmg >= 200:
                    s += 1500    # ルカリオ270/ハリヤマ210等を耐える=耐久レース勝ち
                if self.opp_has_lightning:
                    s += 800     # 雷弱点×2を食らうので尚更マントで耐える
            return s
        score = self._energy_target_score(pk, active)
        bidx = o.inPlayIndex + (0 if active else 1)
        if bidx == plan.attacker and plan.needs_energy:
            score += 500          # プランのアタッカーへの充填を最優先
        # イグニッション(CCC)は基本水を先に使い、3エネ完成/詰めの時に温存して使う
        if card.id == C.IGNITION_ENERGY and pk.id in (C.MEGA_STARMIE, C.STARYU):
            if len(pk.energies) >= 2:
                score += 200      # あと1枚で3エネ=一気にNebula圏内に乗る
            else:
                score -= 150      # 序盤は水を優先(イグニッションは温存)
        return score

    def _score_evolve(self, o):
        pk = get_card(self.obs, o.inPlayArea, o.inPlayIndex, self.my)
        ev = get_card(self.obs, o.area, o.index, self.my)
        if not isinstance(pk, Pokemon):
            return 0
        s = 9000 + len(pk.energies)
        if ev is not None and ev.id == C.MEGA_STARMIE:
            s += 1000             # メガスターミーexへの進化は最優先級
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
        if card.id == C.STARYU:
            line = self.field_counts[C.STARYU] + self.field_counts[C.MEGA_STARMIE]
            return -1 if line >= 3 else 20000
        if card.id in (C.SCORBUNNY, C.RABOOT, C.CINDERACE):
            return 5  # 基本出さない(死に札)
        return 18000

    def _score_play_trainer(self, card):
        cid = card.id
        if cid == C.BOSS_ORDERS:
            return 3200 if plan.target >= 1 else -1
        if cid == C.MEGA_SIGNAL:
            need_starmie = self.field_counts[C.MEGA_STARMIE] == 0
            return 3300 if need_starmie else 500
        if cid == C.HILDA:
            return -1 if self._low_deck() else 3000
        if cid == C.SALVATORE:
            # 進化先(メガスターミーex)を場に乗せられるなら最優先級
            return 3400 if self.field_counts[C.STARYU] >= 1 else -1
        if cid == C.BUDDY_POFFIN:
            return 3100
        if cid == C.ULTRA_BALL:
            return 2600
        if cid == C.POKEGEAR:
            return 2400
        if cid in (C.LILLIE, C.HARLEQUIN):
            # ドローサポート: 手札が少ない時だけ撃つ(グッズを先に使い切る/手札キープ)
            if self._low_deck():
                return -1
            hc = self.me.handCount
            return 3000 if hc <= 4 else (1500 if hc <= 6 else 400)
        if cid == C.CRUSHING_HAMMER:
            # ⑥ 相手のエースの育成エネを削る。場で一番エネを盛ってる脅威に多くエネがある時ほど価値大
            best_en = 0
            for pk in self._opp_board():
                if pk is not None:
                    best_en = max(best_en, len(pk.energies))
            if best_en <= 0:
                return -1
            return 2000 + best_en * 200 + (600 if self.opp_max_dmg >= 200 else 0)
        if cid == C.NIGHT_STRETCHER:
            return 1500
        if cid == C.WALLY:
            # 回復だがエネが全部手札に戻る(攻撃力リセット)=緊急時のみ。
            # メガスターミーexが瀕死で、かつ手札で再充填(Ignition)できる時だけ。
            act = self.me.active[0] if self.me.active else None
            if (act and act.id == C.MEGA_STARMIE and act.hp <= 100
                    and self.hand_counts[C.IGNITION_ENERGY] >= 1):
                return 1800
            return -1
        return 1000

    def _score_card(self, o):
        card = get_card(self.obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0
        ctx = self.context
        if ctx in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
            return self._score_active_choice(o, card)
        if ctx == SelectContext.SETUP_ACTIVE_POKEMON:
            return self._score_setup_active(card)
        if ctx in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH, SelectContext.TO_FIELD):
            return self._score_to_bench(card)
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
            # 相手アクティブを選ぶ(ボス等) -> プランの的
            return 100 if o.index == plan.target - 1 else 0
        score = len(card.energies) * 5
        if o.index == plan.attacker - 1:
            score += 200
        if card.id == C.MEGA_STARMIE:
            score += 50
        elif card.id == C.STARYU:
            score += 10
        return score

    def _score_setup_active(self, card):
        # 初手アクティブ: エースバーンを顔に(特性で場に出せる・逃げ0のエンジン)。
        # Staryuはベンチで育てたいので後回し。
        if card.id == C.CINDERACE:
            return 100
        if card.id == C.STARYU:
            return 30
        return 1

    def _score_to_bench(self, card):
        # ベンチには育成台のStaryu(→Mega Starmie)を最優先で並べる。
        if card.id == C.STARYU:
            return 60
        if card.id == C.MEGA_STARMIE:
            return 40
        if card.id in (C.SCORBUNNY, C.RABOOT, C.CINDERACE):
            return 1
        return 10

    def _score_to_hand(self, card):
        # サーチで手札に加える: 進化パーツ・エネを優先
        s = 200 - self.hand_counts[card.id] * 50
        if card.id == C.MEGA_STARMIE:
            s += 150 if self.field_counts[C.STARYU] >= 1 else 60
        elif card.id == C.STARYU:
            line = self.field_counts[C.STARYU] + self.field_counts[C.MEGA_STARMIE]
            s += 120 if line == 0 else -20
        elif card.id == C.IGNITION_ENERGY:
            s += 90
        elif card.id == C.WATER_ENERGY:
            s += 50
        elif card.id in (C.SCORBUNNY, C.RABOOT, C.CINDERACE):
            s -= 300
        return s

    def _score_discard(self, card):
        # 捨てる/山に戻す: 死に札・余りを優先的に処理
        if card.id in (C.CINDERACE, C.RABOOT, C.SCORBUNNY):
            return 300
        if card.id in (C.MEGA_STARMIE, C.STARYU, C.IGNITION_ENERGY, C.WATER_ENERGY):
            return -200
        return 0

    def _score_energy_pick(self, o):
        # エネを選ぶ系: 攻撃に使うエネは保持優先(=選ばせない方向の文脈もあるが既定で中庸)
        return 10


def _fallback(select):
    try:
        n = len(select.option)
        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = max(0, min(lo, hi, n))
        return list(range(n))[:k] if k > 0 else [0]
    except Exception:
        return [0]


def agent(obs_dict: dict) -> list[int]:
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
        ordered = StarmiePolicy(obs).choose()
        n = len(obs.select.option)
        ordered = [i for i in ordered if 0 <= i < n]
        if not ordered:
            return _fallback(obs.select)
        k = min(obs.select.maxCount, n)
        k = max(k, min(max(1, obs.select.minCount), n))
        return ordered[:k]
    except Exception:
        return _fallback(obs.select)
