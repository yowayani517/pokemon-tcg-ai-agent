import sys, os, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaggle_environments import make
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
def load(p,n):
    s=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ARCH=load(os.environ.get("AGENT_PATH", os.path.join(ROOT,"agent","main_arch.py")),"main_arch")
WALL=load(os.path.join(ROOT,"agent","main.py"),"wall")
oppspec=sys.argv[1]; seat=int(sys.argv[2])
if oppspec=="wall": opp=WALL.agent
elif oppspec=="starmie":
    PLAN=load(os.path.join(ROOT,"agent","main_plan.py"),"main_plan"); opp=PLAN.agent
else:
    dk=[int(x) for x in open(oppspec) if x.strip()]
    def opp(o): return dk if o["select"] is None else WALL.agent(o)
env=make("cabt")
if seat==0: env.run([ARCH.agent,opp]); r=env.steps[-1][0].reward
else: env.run([opp,ARCH.agent]); r=env.steps[-1][1].reward
r=r or 0
print("WIN" if r>0 else "LOSE" if r<0 else "DRAW")
