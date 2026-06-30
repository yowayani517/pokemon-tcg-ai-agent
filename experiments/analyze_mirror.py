import json, glob, collections, sys
sys.path.insert(0, '.')
BOSS = 1182; SWITCH = 1123; RAGING = 224; HAMMERIN = 223; METALDEF = 253; ARCH = 190; RELI = 57


def is_arch(deck):
    return collections.Counter(deck).get(ARCH, 0) >= 3


def feats(r, pi):
    f = dict(first=0, first_atk=99, n_boss=0, n_rage=0, n_md=0, n_hi=0, n_switch=0,
             reli_turn=99, e3_turn=99, n_attacks=0)
    for st in r['steps']:
        cell = st[pi]
        o = cell.get('observation')
        if not isinstance(o, dict):
            continue
        cur = o.get('current'); sel = o.get('select')
        if cur and cur.get('firstPlayer') == pi:
            f['first'] = 1
        if cur and cur.get('yourIndex') == pi:
            p = cur['players'][pi]; a = (p.get('active') or [])
            if a and isinstance(a[0], dict) and a[0].get('id') == ARCH and len(a[0].get('energies', [])) >= 3:
                f['e3_turn'] = min(f['e3_turn'], cur.get('turn', 99))
            bd = (p.get('active') or []) + (p.get('bench') or [])
            if any(x and x.get('id') == RELI for x in bd):
                f['reli_turn'] = min(f['reli_turn'], cur.get('turn', 99))
        act = cell.get('action')
        if not (sel and isinstance(act, list) and act):
            continue
        if sel.get('context') != 0:
            continue
        opts = sel.get('option') or []
        if act[0] >= len(opts):
            continue
        opt = opts[act[0]]; t = opt.get('type'); turn = cur.get('turn', 0) if cur else 0
        if t == 13:
            f['n_attacks'] += 1; f['first_atk'] = min(f['first_atk'], turn)
            aid = opt.get('attackId')
            if aid == RAGING: f['n_rage'] += 1
            elif aid == METALDEF: f['n_md'] += 1
            elif aid == HAMMERIN: f['n_hi'] += 1
        elif t == 7:
            try:
                hand = cur['players'][pi].get('hand') or []
                cid = hand[opt['index']]['id'] if opt.get('index') is not None and opt['index'] < len(hand) else None
                if cid == BOSS: f['n_boss'] += 1
                elif cid == SWITCH: f['n_switch'] += 1
            except Exception:
                pass
    return f


W = collections.defaultdict(float); L = collections.defaultdict(float); n = 0
for fn in glob.glob('mirror_replays/*.json'):
    try:
        r = json.load(open(fn, encoding='utf-8'))
    except Exception:
        continue
    d0 = r['steps'][1][0].get('action'); d1 = r['steps'][1][1].get('action')
    if not (isinstance(d0, list) and isinstance(d1, list) and len(d0) == 60 and len(d1) == 60):
        continue
    if not (is_arch(d0) and is_arch(d1)):
        continue
    rew = r['steps'][-1][0].get('reward')
    if rew not in (1, -1):
        continue
    win = 0 if rew == 1 else 1
    n += 1
    fw = feats(r, win); fl = feats(r, 1 - win)
    for k in fw:
        W[k] += fw[k]; L[k] += fl[k]

print('ブリジュラスミラー解析:', n, '試合')
labels = {'first': '先攻率', 'first_atk': '初攻撃ターン', 'e3_turn': '3エネ到達T',
          'n_boss': 'ボス回数', 'n_rage': 'レイジング回', 'n_md': 'メタルディフェ回',
          'n_hi': 'ハンマーイン回', 'n_switch': 'いれかえ回', 'reli_turn': 'ジーランス設置T',
          'n_attacks': '総攻撃回数'}
print('%-14s %8s %8s' % ('指標', '勝者', '敗者'))
for k in ['first', 'e3_turn', 'first_atk', 'n_attacks', 'n_md', 'n_rage', 'n_hi', 'n_boss', 'n_switch', 'reli_turn']:
    print('%-14s %8.2f %8.2f' % (labels[k], W[k] / max(1, n), L[k] / max(1, n)))
