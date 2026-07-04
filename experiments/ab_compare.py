import subprocess,os,sys,glob
PY=sys.executable
N=int(sys.argv[1]) if len(sys.argv)>1 else 40
ROOT=os.path.dirname(os.path.abspath('.'))
V3=os.path.abspath(os.path.join('..','backups','arch_867','main.py'))   # 867.4
CUR=os.path.abspath(os.path.join('..','agent','main_arch.py'))          # 現HEAD
decks=sorted(glob.glob('curmeta/*.csv'))
def run(agent_path,deck,n):
    w=l=d=0
    for g in range(n):
        env=dict(os.environ,PYTHONIOENCODING='utf-8',AGENT_PATH=agent_path)
        out=subprocess.run([PY,'run_one_arch.py',deck,str(g%2)],capture_output=True,text=True,env=env).stdout.strip().splitlines()
        r=out[-1] if out else 'DRAW'; w+=r=='WIN';l+=r=='LOSE';d+=r=='DRAW'
    return w,l,d
print(f'=== A/B: 867.4(v3) vs 現HEAD  N={N}/deck ===',flush=True)
print(f'{"相手":14s} {"867.4版":>10s} {"現HEAD":>10s}',flush=True)
t3=tc=tot=0
for p in decks:
    n=os.path.basename(p)[3:-4]
    w3,l3,_=run(V3,p,N); wc,lc,_=run(CUR,p,N)
    t3+=w3; tc+=wc; tot+=N
    print(f'{n:14s} {w3:>3}/{N} ({w3/N:.0%})  {wc:>3}/{N} ({wc/N:.0%})',flush=True)
print(f'{"総合":14s} {t3}/{tot} ({t3/tot:.0%})  {tc}/{tot} ({tc/tot:.0%})',flush=True)
