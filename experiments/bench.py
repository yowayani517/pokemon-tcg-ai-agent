"""信頼できるベンチ: 候補エージェント vs 基準(実測867.4版)の直接対決。

弱いbot相手の勝率はアテにならない(v4事故の教訓: ローカル互角→実ラダー-145点)。
強い相手との直接対決 + 統計的有意性(二項検定)だけを合否判定に使う。

使い方:
  python bench.py <candidate.py> [N] [--ref <reference.py>]
  既定: ref = ../backups/arch_867/main.py (実測867.4), N = 150

判定基準:
  p < 0.05 で勝ち越し  → 採用(GO)
  p < 0.05 で負け越し  → 棄却(NO-GO)
  それ以外             → 判定保留(差が小さい: Nを増やすか変更を大きく)
"""
import sys, os, subprocess
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def binom_p_two_sided(w, n):
    """p=0.5帰無仮説の両側二項検定。"""
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(0, min(w, n - w) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def run(cand, ref, n):
    w = l = d = 0
    for g in range(n):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        out = subprocess.run(
            [PY, os.path.join(HERE, "h2h_one.py"), cand, ref, str(g % 2)],
            capture_output=True, text=True, env=env).stdout.strip().splitlines()
        r = out[-1] if out else "DRAW"
        w += r == "WIN"; l += r == "LOSE"; d += r == "DRAW"
        if (g + 1) % 25 == 0:
            print(f"  {g+1}/{n}: {w}W {l}L {d}D ({w/max(1,w+l):.0%})", flush=True)
    return w, l, d


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cand = os.path.abspath(args[0]) if args else os.path.join(HERE, "..", "agent", "main_arch.py")
    n = int(args[1]) if len(args) > 1 else 150
    ref = os.path.abspath(os.path.join(HERE, "..", "backups", "arch_867", "main.py"))
    if "--ref" in sys.argv:
        ref = os.path.abspath(sys.argv[sys.argv.index("--ref") + 1])
    print(f"=== bench: {os.path.basename(cand)} vs {os.path.basename(os.path.dirname(ref))}/{os.path.basename(ref)}  N={n} ===", flush=True)
    w, l, d = run(cand, ref, n)
    dec = w + l
    p = binom_p_two_sided(w, dec)
    wr = w / max(1, dec)
    print(f"\n結果: {w}W {l}L {d}D  勝率{wr:.1%}  p={p:.3f}")
    if p < 0.05 and wr > 0.5:
        print("判定: ✅ GO (統計的に有意に強い)")
    elif p < 0.05:
        print("判定: ❌ NO-GO (有意に弱い)")
    else:
        print("判定: ⏸ 保留 (有意差なし — Nを増やすか、変更を大きく)")


if __name__ == "__main__":
    main()
