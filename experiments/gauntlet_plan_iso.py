"""プロセス隔離ガントレット: 1試合ごとにrun_one_game.pyをsubprocessで起動。"""
import sys, os, glob, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
PY = sys.executable


def run_match(oppspec, n):
    w = l = d = 0
    for g in range(n):
        seat = g % 2
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        out = subprocess.run([PY, os.path.join(HERE, "run_one_game.py"), oppspec, str(seat)],
                             capture_output=True, text=True, env=env).stdout.strip().splitlines()
        res = out[-1] if out else "DRAW"
        w += res == "WIN"; l += res == "LOSE"; d += res == "DRAW"
    return w, l, d


def main():
    print(f"=== Mega Starmie ex Planning Agent (isolated, {N} games each) ===", flush=True)
    w, l, d = run_match("wall", N)
    print(f"vs 壁(現提出)        : {w}W {l}L {d}D  ({w/max(1,w+l+d):.0%})", flush=True)
    tw = tot = 0
    for p in sorted(glob.glob(os.path.join(HERE, "meta_now", "*.csv"))):
        dn = os.path.basename(p)[:-4]
        w, l, d = run_match(p, N)
        tw += w; tot += w + l + d
        print(f"vs {dn[3:][:12]:12s}: {w}W {l}L {d}D  ({w/max(1,w+l+d):.0%})", flush=True)
    print(f"--- 対メタ総合: {tw}/{tot}  ({tw/max(1,tot):.0%}) ---", flush=True)


if __name__ == "__main__":
    main()
