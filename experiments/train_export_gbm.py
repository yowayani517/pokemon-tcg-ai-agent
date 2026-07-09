"""GBM価値関数を全データで訓練し、pure-numpyに書き出す(Kaggle提出=依存numpyのみ)。
sklearnとnumpy版の出力一致を検証。出力: value_gbm.npz(木構造) + 標準化パラメータ。"""
import numpy as np, sys
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

d = np.load('value_data2.npz'); X = d['X']; y = d['y']
n = len(y); rng = np.random.RandomState(0); idx = rng.permutation(n)
tr, te = idx[:int(n*0.8)], idx[int(n*0.8):]

g = GradientBoostingClassifier(n_estimators=300, max_depth=3, learning_rate=0.05,
                               subsample=0.8, random_state=0).fit(X[tr], y[tr])
auc = roc_auc_score(y[te], g.predict_proba(X[te])[:, 1])
print('GBM AUC(hold-out)=%.3f' % auc)

# --- 木をnumpy配列に書き出す ---
T = len(g.estimators_)
feat = []; thr = []; left = []; right = []; val = []; tree_off = [0]
for i in range(T):
    t = g.estimators_[i, 0].tree_
    feat.append(t.feature.astype(np.int32))
    thr.append(t.threshold.astype(np.float64))
    left.append(t.children_left.astype(np.int32))
    right.append(t.children_right.astype(np.int32))
    val.append(t.value.reshape(-1).astype(np.float64))
    tree_off.append(tree_off[-1] + t.node_count)
FEAT = np.concatenate(feat); THR = np.concatenate(thr)
LEFT = np.concatenate(left); RIGHT = np.concatenate(right); VAL = np.concatenate(val)
OFF = np.array(tree_off, dtype=np.int32)
init = float(g.init_.class_prior_[1]); lr = float(g.learning_rate)
# GBは init を log-odds で持つ
from scipy.special import logit
base = float(logit(g.init_.class_prior_[1]))
np.savez('value_gbm.npz', FEAT=FEAT, THR=THR, LEFT=LEFT, RIGHT=RIGHT, VAL=VAL,
         OFF=OFF, base=base, lr=lr)


def np_predict(Xrow, d):
    """pure-numpy GBM予測(1サンプル=1次元配列 or 2次元)。返り=P(win)。"""
    FEAT, THR, LEFT, RIGHT, VAL, OFF = d['FEAT'], d['THR'], d['LEFT'], d['RIGHT'], d['VAL'], d['OFF']
    base, lr = float(d['base']), float(d['lr'])
    Xrow = np.atleast_2d(Xrow)
    out = np.full(len(Xrow), base)
    T = len(OFF) - 1
    for i in range(T):
        o = OFF[i]
        for r in range(len(Xrow)):
            node = 0
            while LEFT[o + node] != -1:
                if Xrow[r, FEAT[o + node]] <= THR[o + node]:
                    node = LEFT[o + node]
                else:
                    node = RIGHT[o + node]
            out[r] += lr * VAL[o + node]
    return 1.0 / (1.0 + np.exp(-out))


# 一致検証
dd = np.load('value_gbm.npz')
p_sklearn = g.predict_proba(X[te][:200])[:, 1]
p_numpy = np_predict(X[te][:200], dd)
maxerr = np.max(np.abs(p_sklearn - p_numpy))
print('numpy vs sklearn 最大誤差=%.2e' % maxerr)
print('木の総ノード数=%d, 木数=%d' % (len(FEAT), len(OFF)-1))
print('OK' if maxerr < 1e-6 else 'MISMATCH')
