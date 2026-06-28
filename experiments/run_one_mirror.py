import sys,os,importlib.util
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from kaggle_environments import make
def loadf(name):
    s=importlib.util.spec_from_file_location(name,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'agent','main_plan.py'))
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
A=loadf('plan_a'); B=loadf('plan_b')
seat=int(sys.argv[2])
env=make('cabt')
if seat==0: env.run([A.agent,B.agent]); r=env.steps[-1][0].reward
else: env.run([B.agent,A.agent]); r=env.steps[-1][1].reward
r=r or 0
print("WIN" if r>0 else "LOSE" if r<0 else "DRAW")
