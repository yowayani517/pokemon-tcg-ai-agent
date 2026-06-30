import sys,os,importlib.util,random
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from kaggle_environments import make
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
def load(p,n):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
WALL=load(os.path.join(ROOT,"agent","main.py"),"wall")
dA=[int(x) for x in open(sys.argv[1]) if x.strip()]
dB=[int(x) for x in open(sys.argv[2]) if x.strip()]
seat=int(sys.argv[3])
def mk(dk):
    def ag(o): return dk if o["select"] is None else WALL.agent(o)
    return ag
A,B=mk(dA),mk(dB)
env=make("cabt")
if seat==0: env.run([A,B]); r=env.steps[-1][0].reward
else: env.run([B,A]); r=env.steps[-1][1].reward
r=r or 0
print("A" if r>0 else "B" if r<0 else "D")
