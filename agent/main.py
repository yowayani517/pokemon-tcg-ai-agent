"""PTCG AI Battle Challenge - イワパレス(Crustle)壁デッキ + ルールベースAI.

注意（Kaggle実行仕様）:
- main.py は文字列として exec({}, ...) される。__file__ は未定義なので
  外部ファイル(deck.csv)を __file__ 基準で読んではいけない。デッキは下に直接埋め込む。
- エージェントとして採用されるのは「最後に定義された callable」。よって agent() を最後に置く。
"""

# OptionType -> 優先度（大きいほど先に実行）
# 0 NUMBER 1 YES 2 NO 3 CARD 4 TOOL 5 ENERGY_CARD 6 ENERGY 7 PLAY 8 ATTACH
# 9 EVOLVE 10 ABILITY 11 DISCARD 12 RETREAT 13 ATTACK 14 END 15 SKILL 16 SP_COND
PRIORITY = {
    10: 9,   # ABILITY
    15: 8,   # SKILL
    9:  7,   # EVOLVE
    7:  6,   # PLAY
    8:  5,   # ATTACH energy
    3:  4,   # CARD
    1:  4,   # YES
    13: 2,   # ATTACK (ターンを終わらせるので準備後)
    12: 1,   # RETREAT
    2:  1,   # NO
    14: 0,   # END
}
DEFAULT_PRIORITY = 3

# Shun の純壁デッキ (60枚) — 実ラダー923.9で我々のベスト。エネ配分改善と組合せる
DECK = (
    [344] * 4 + [345] * 4 + [1159] * 1         # Dwebble / Crustle / Hero's Cape(tool)
    + [1086] * 4 + [1147] * 4                   # Buddy-Buddy Poffin / Jumbo Ice Cream
    + [1212] * 4 + [1227] * 4 + [1235] * 4      # Cook / Lillie's Determination / Waitress
    + [1] * 19                                  # Basic Grass Energy
    + [11] * 4 + [14] * 4 + [18] * 4            # Mist / Spiky / Grow Grass (Special Energy)
)


ACTIVE_AREA = 4   # inPlayArea: 4=ACTIVE 5=BENCH
ATTACK_COST = 3   # 攻撃に必要なエネ数 (イワパレス/タイフロージョン共に3)。これ以上は不要
DOOMED_HP = 0.35  # 最大HPのこの割合以下なら「攻撃前に倒されそう」とみなし犠牲にする


def _my_poke(obs, inplay_area, inplay_idx):
    """自分の場のポケモン(アクティブ/ベンチ)を取得。無ければ None。"""
    try:
        cur = obs.get("current")
        me = cur["yourIndex"]
        p = cur["players"][me]
        if inplay_area == ACTIVE_AREA:
            a = p.get("active") or []
            return a[0] if a and isinstance(a[0], dict) else None
        if inplay_area == 5:
            b = p.get("bench") or []
            return b[inplay_idx] if 0 <= inplay_idx < len(b) and isinstance(b[inplay_idx], dict) else None
    except Exception:
        return None
    return None


def _energy_attach_score(o, obs):
    """エネ付け(type 8)の賢い配分: 3個で打ち止め・アクティブ優先・瀕死は見切ってベンチへ。"""
    poke = _my_poke(obs, o.get("inPlayArea"), o.get("inPlayIndex", 0))
    if poke is None:
        return 0
    ne = len(poke.get("energies", []) or [])
    hp = poke.get("hp", 999)
    mhp = poke.get("maxHp", hp) or hp or 1
    if ne >= ATTACK_COST:
        return -400          # 3個で十分 -> 付けない(攻撃やベンチ育成を優先)
    if o.get("inPlayArea") == ACTIVE_AREA:
        if hp <= DOOMED_HP * mhp:
            return -150      # 攻撃前に倒されそう -> アクティブは犠牲、ベンチに回す
        return 60            # 健全なアクティブ(アタッカー)に最優先で燃料
    return 30                # ベンチ: 次のアタッカーを準備


# 相手別対策: 我々の壁を倒す脅威(炎/格闘の非exアタッカー＋その進化前)。
# 育つ前に Boss で引きずり出して KO し、セットアップを妨害する。
THREAT = frozenset({353, 354, 663, 673, 674, 717, 934})
BOSS_ID = 1182
OUR_DAMAGE = 120          # Crustle のグレートシザー
BOSS_AREAS = (4, 5)       # ACTIVE / BENCH


def _opp_poke(obs, area, idx, pi):
    try:
        cur = obs.get("current"); me = cur["yourIndex"]
        if pi == me:
            return None
        p = cur["players"][pi]
        arr = p.get("active") if area == ACTIVE_AREA else p.get("bench")
        arr = arr or []
        return arr[idx] if 0 <= idx < len(arr) and isinstance(arr[idx], dict) else None
    except Exception:
        return None


def _boss_target_score(o, obs):
    """Boss対象選択: 『今KOできる脅威』を最優先で引きずり出す(drag-and-KO)。
    脅威の中でもエネが多いほど優先(進化したら即技を撃てる=一番危険)。
    倒せない脅威を出すと逆に殴られるので触らない。"""
    me = (obs.get("current") or {}).get("yourIndex", 0)
    pi = o.get("playerIndex", me)
    poke = _opp_poke(obs, o.get("area"), o.get("index", 0), pi)
    if poke is None:
        return 0
    koable = poke.get("hp", 999) <= OUR_DAMAGE
    ne = len(poke.get("energies", []) or [])      # 付いてるエネ(進化先に引き継がれる)
    if poke.get("id") in THREAT and koable:
        return 50 + ne * 12                       # エネ満載の育成中脅威を最優先でKO
    if koable:
        return 15 + ne * 3                        # 倒せる相手はエネ多い方を優先
    return -20                                    # 倒せない相手は引きずり出さない


def _has_snipe_target(obs):
    """KOできる脅威(育成中の炎/格闘アタッカー等)がベンチに居るか。"""
    try:
        cur = obs["current"]; me = cur["yourIndex"]; opp = cur["players"][1 - me]
        for poke in (opp.get("bench") or []):
            if (isinstance(poke, dict) and poke.get("id") in THREAT
                    and poke.get("hp", 999) <= OUR_DAMAGE):
                return True
    except Exception:
        pass
    return False


def _is_boss_play(o, obs):
    try:
        cur = obs["current"]; me = cur["yourIndex"]
        hand = cur["players"][me].get("hand") or []
        idx = o.get("index", -1)
        return 0 <= idx < len(hand) and isinstance(hand[idx], dict) and hand[idx].get("id") == BOSS_ID
    except Exception:
        return False


def _score(o, obs):
    """選択肢のスコア。種類の優先度を主軸に、エネ配分・進化先・相手別対策を補正。"""
    t = o.get("type")
    s = PRIORITY.get(t, DEFAULT_PRIORITY) * 100
    if t == 8:                                   # エネルギー付け
        s += _energy_attach_score(o, obs)
    elif t == 9 and o.get("inPlayArea") == ACTIVE_AREA:
        s += 30                                  # 進化はアクティブ(壁)を前に
    elif t == 3 and o.get("area") in BOSS_AREAS:  # 相手ポケ選択(Boss対象)
        s += _boss_target_score(o, obs)
    elif t == 7 and _is_boss_play(o, obs):        # Boss を出す
        s += 25 if _has_snipe_target(obs) else -30   # 狙える脅威がある時だけ
    return s


def agent(obs):
    sel = obs["select"]
    # デッキ選択フェーズ: 60枚のカードIDを返す
    if sel is None:
        return DECK

    options = sel["option"]
    if not options:
        return []

    order = sorted(range(len(options)), key=lambda i: _score(options[i], obs), reverse=True)
    need = max(sel.get("minCount", 0) or 0, sel.get("maxCount", 1) or 0, 1)
    return order[:need]
