import subprocess,sys,os,re
teams={"ShumpeiNomura":16393745,"Takaaki":16371783,"NukoNiko15":16385025,
       "Morim":16381755,"pztriatomic":16375173,"rasuharu":16408973}
HERE=os.path.dirname(os.path.abspath(__file__))
def run(*a):
    return subprocess.run([sys.executable,"-m","kaggle",*a],capture_output=True,text=True,
                          env=dict(os.environ,PYTHONIOENCODING="utf-8")).stdout
def first_num(txt,col=0):
    for ln in txt.splitlines():
        m=re.match(r"\s*(\d{6,})",ln)
        if m: return m.group(1)
    return None
got=0
for name,tid in teams.items():
    subs=run("competitions","team-submissions",str(tid))
    # best score submission id
    best=None;bs=-1
    for ln in subs.splitlines():
        m=re.match(r"\s*(\d{6,})\s+\S+\s+\S+\s+([\d.]+)",ln)
        if m and float(m.group(2))>bs: bs=float(m.group(2));best=m.group(1)
    if not best: best=first_num(subs)
    if not best: continue
    eps=[l.split()[0] for l in run("competitions","episodes",str(best)).splitlines() if "COMPLETED" in l][:20]
    for ep in eps:
        f=os.path.join(HERE,"mirror_replays",f"{ep}.json")
        if os.path.exists(f): continue
        run("competitions","replay",ep,"-p",os.path.join(HERE,"mirror_replays"))
        got+=1
    print(name,"done, total dl",got,flush=True)
print("TOTAL",got)
