import os,sys,subprocess,itertools
HERE=os.path.dirname(os.path.abspath(__file__))
decks={"Archaludon":"01_Archaludon","Starmie":"02_Starmie","Dragapult":"10_Dragapult",
       "Alakazam":"07_Alakazam","Fezandipiti":"08_Fezandipiti","Togekiss":"26_Togekiss"}
N=int(sys.argv[1]) if len(sys.argv)>1 else 6
PY_=sys.executable
names=list(decks)
wins={n:0 for n in names}; games={n:0 for n in names}
mat={a:{b:None for b in names} for a in names}
def play(a,b,n):
    aw=bw=0
    fa=os.path.join(HERE,"curmeta",decks[a]+".csv"); fb=os.path.join(HERE,"curmeta",decks[b]+".csv")
    for g in range(n):
        env=dict(os.environ,PYTHONIOENCODING="utf-8")
        out=subprocess.run([PY_,os.path.join(HERE,"run_one_pair.py"),fa,fb,str(g%2)],capture_output=True,text=True,env=env).stdout.strip().splitlines()
        r=out[-1] if out else "D"
        if r=="A": aw+=1
        elif r=="B": bw+=1
    return aw,bw
for a,b in itertools.combinations(names,2):
    aw,bw=play(a,b,N)
    mat[a][b]=aw; mat[b][a]=bw
    wins[a]+=aw; wins[b]+=bw; games[a]+=aw+bw; games[b]+=aw+bw
    print(f"{a} vs {b}: {aw}-{bw}",flush=True)
print("\n=== 相性表(行が列に勝った数 / N="+str(N)+") ===")
print("　　　　"+" ".join(f"{n[:5]:>6}" for n in names))
for a in names:
    print(f"{a[:8]:8s}"+" ".join((f"{mat[a][b]:>6}" if mat[a][b] is not None else "　　　-") for b in names))
print("\n=== 総合勝率ランキング ===")
for n in sorted(names,key=lambda x:-(wins[x]/max(1,games[x]))):
    print(f"  {n:12s} {wins[n]}/{games[n]} ({wins[n]/max(1,games[n]):.0%})")
