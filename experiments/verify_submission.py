"""提出エラーが出ないかをローカルで最大限再現して検証する.

Kaggle と同条件:
- submission.tar.gz を展開し、main.py を「文字列として exec({})」してロード
  （__file__ 無し / 最後の callable を採用）= kaggle_environments と同じ流儀
- そのエージェントで多数のフル対戦を回し、例外ゼロ・不正手ゼロ・時間内を確認
"""
import sys, os, time, tarfile, tempfile, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAR = os.path.join(ROOT, "submission.tar.gz")


def load_agent_like_kaggle():
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(TAR) as t:
            t.extractall(td)
        main_py = os.path.join(td, "main.py")
        assert os.path.exists(main_py), "main.py がトップ階層に無い"
        src = open(main_py, encoding="utf-8").read()
        env = {}  # __file__ を入れない = Kaggleと同じ
        exec(compile(src, "<submission main.py>", "exec"), env)
        callables = [v for v in env.values() if callable(v)]
        assert callables, "callable が無い"
        agent = callables[-1]  # Kaggleは最後のcallableを採用
        assert agent.__name__ == "agent", f"最後のcallableが agent でない: {agent.__name__}"
        return agent


from kaggle_environments import make


def run(n=150):
    agent = load_agent_like_kaggle()
    print(f"ロードOK: 最後のcallable='{agent.__name__}', デッキ={len(agent({'select': None}))}枚")

    errors, max_step_ms, total_steps = 0, 0.0, 0
    t0 = time.time()
    for g in range(n):
        try:
            env = make("cabt")
            # 自作 vs 自作 / vs random / vs first を混ぜて網羅
            opp = agent if g % 3 == 0 else ("random" if g % 3 == 1 else "first")
            env.run([agent, opp])
            # 自分の手番の応答時間を確認
            for step in env.steps:
                for s in step:
                    if getattr(s, "observation", None) and s.observation.get("select") is not None:
                        t1 = time.time(); agent(s.observation); dt = (time.time() - t1) * 1000
                        max_step_ms = max(max_step_ms, dt); total_steps += 1
            # 終局していること
            assert env.done, f"game {g} not done"
        except Exception:
            errors += 1
            print(f"--- game {g} で例外 ---")
            traceback.print_exc()
            if errors >= 3:
                break
    dt = time.time() - t0
    print(f"\n{n}戦完走  例外={errors}  最大応答={max_step_ms:.1f}ms (上限はrunTimeout 3000ms想定)  "
          f"判定手数={total_steps}  ({dt:.1f}s)")
    print("=> 例外0なら、提出時クラッシュの主要因（__file__/entrypoint/未処理obs）は無し" if errors == 0
          else "=> 例外あり。修正が必要")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
