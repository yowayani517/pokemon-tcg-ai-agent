# PTCG AI Battle Challenge — Strategy 部門 プロジェクト

## コンペ概要
- ポケモンカードゲームを自動プレイするAIエージェントを作る
- Strategy部門: 期間 2026/6/16〜9/14、提出 = 動くエージェント + 戦略レポート
- 審査: 安定性 / デッキ構築の発想 / シミュ部門での成績
- 賞: 上位8組が決勝、優勝$50,000

## 提出物の形式
- `submission.tar.gz`（`tar -czvf submission.tar.gz *` で作成）
- トップ階層に `main.py`（エージェント本体）と `deck.csv`（デッキ）
- 毎ターン: 観測（ログ+盤面+合法手リスト）を受け取り、選んだ選択肢のindexを返す
- 1日5回まで提出可

## セットアップ手順
1. Kaggleでコンペに参加（Join Competition → Accept）
2. Settings → API → Create New Token で `kaggle.json` をDL
3. `kaggle.json` を `C:\Users\yoway\.kaggle\` に置く
4. `setup_and_download.ps1` を実行 → データが `data/` に落ちる

## ロードマップ
1. [完了] 環境セットアップ（CLI / 認証 / データDL）
2. [完了] ゲーム仕様の理解（cabtエンジン / 観測 / option type）
3. [完了] ベースラインエージェント（ルールベース）vs random 勝率82%
4. [次] デッキ設計（提供カードプール 2022枚から）
5. 戦略の改良（攻撃ダメージ計算・進化先優先・サイド差考慮 等）
6. 戦略レポート執筆

## 検証済み技術メモ（cabtエンジン）
- 公式docs: https://matsuoinstitute.github.io/cabt/
- エンジンは `kaggle-environments` の `cabt` 環境に同梱。
  インストール: `pip install --no-deps kaggle-environments`
  （pygame等のビルドを避けるため --no-deps。cabtはネイティブDLL同梱で動く）
- ローカル対戦: `make("cabt"); env.run([agent, "random"])` … Python 3.14でも動作確認済み
- カードプール: `EN_Card_Data.csv` 2022枚（Basic958/Stage1 618/Stage2 229,
  Item82/Supporter61/Tool28/Stadium26/SpecialEnergy12/BasicEnergy8）

### エージェントAPI
- `agent(obs) -> list[int]`
- `obs["select"] is None` のとき: デッキ(60枚のカードID list)を返す
- それ以外: `obs["select"]["option"]` から `maxCount` 個のindexを返す

### OptionType（option["type"]）
0 NUMBER / 1 YES / 2 NO / 3 CARD / 4 TOOL_CARD / 5 ENERGY_CARD / 6 ENERGY /
7 PLAY / 8 ATTACH / 9 EVOLVE / 10 ABILITY / 11 DISCARD / 12 RETREAT /
13 ATTACK / 14 END / 15 SKILL / 16 SPECIAL_CONDITION

### AreaType（area）
1 DECK / 2 HAND / 3 DISCARD / 4 ACTIVE / 5 BENCH / 6 PRIZE / 7 STADIUM /
8 ENERGY / 9 TOOL / 10 PRE_EVOLUTION / 11 PLAYER / 12 LOOKING

## よく使うコマンド
- 対戦テスト: `python experiments/run_match.py 50 random`
- 提出物作成: `./make_submission.ps1` -> submission.tar.gz
