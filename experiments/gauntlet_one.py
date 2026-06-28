import sys,os,subprocess
HERE=os.path.dirname(os.path.abspath(__file__))
opp=sys.argv[1]; N=int(sys.argv[2]) if len(sys.argv)>2 else 30
runner=sys.argv[3] if len(sys.argv)>3 else "run_one_game.py"
w=l=d=0
for g in range(N):
    env=dict(os.environ,PYTHONIOENCODING="utf-8")
    out=subprocess.run([sys.executable,os.path.join(HERE,runner),opp,str(g%2)],capture_output=True,text=True,env=env).stdout.strip().splitlines()
    r=(out[-1].split() or ["DRAW"])[0] if out else "DRAW"
    w+=r=="WIN"; l+=r=="LOSE"; d+=r=="DRAW"
print(f"{opp}: {w}W {l}L {d}D ({w/max(1,w+l+d):.0%})")
