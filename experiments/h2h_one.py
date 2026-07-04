# 2つのagentを直接対決させ1試合の結果(左視点)を返す。プロセス隔離用。
import sys,os,importlib.util
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from kaggle_environments import make
def load(p,n):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load(sys.argv[1],'AA'); B=load(sys.argv[2],'BB'); seat=int(sys.argv[3])
env=make("cabt")
if seat==0: env.run([A.agent,B.agent]); r=env.steps[-1][0].reward
else: env.run([B.agent,A.agent]); r=env.steps[-1][1].reward
r=r or 0
print("WIN" if r>0 else "LOSE" if r<0 else "DRAW")
