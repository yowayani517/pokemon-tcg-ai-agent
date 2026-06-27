# イワパレス(Crustle)壁デッキ v1

## コンセプト
Crustle(ID345)の特性「しんぴのいしやど」= 相手のポケモンexからのダメージを完全無効。
環境がex主体なので、ex依存デッキを詰ませる「壁」。ワザ「グレートシザー」(120/効果無視)で削る。
Dwebble(ID344)の「Ascension」で山札から即進化でき、安定して壁が立つ。

## 弱点
- 特性を無視して通すワザ
- 非ex(ルールなし)の高火力アタッカー

## デッキリスト（60枚）
### ポケモン (8)
- 4x Dwebble (344) — 即進化のたね
- 4x Crustle (345) — 壁＋アタッカー

### グッズ (24)
- 4x Buddy-Buddy Poffin (1086) — HP70以下サーチ＝イシズマイ確保
- 4x Ultra Ball (1121)
- 4x Switch (1123)
- 3x Night Stretcher (1097)
- 3x Energy Retrieval (1118)
- 3x Energy Search (1119)
- 2x Energy Switch (1116)
- 1x Scramble Switch (1107)

### サポート (14)
- 4x Lillie's Determination (1227) — 6ドロー
- 3x Carmine (1192) — 先1から5ドロー
- 4x Judge (1213)
- 3x Boss's Orders (1182) — 呼び出し

### エネルギー (14)
- 14x Basic Grass Energy (1)

## 成績（ローカル / ルールベースAI v2）
- vs random: 90% (90勝10敗/100戦) ※サンプルデッキは82%
- vs first(組み込み): 81% (81勝19敗/100戦)
- v2(アクティブ集中) vs v1(種類優先のみ): 55.8% (67勝53敗) … 改良の効果を確認

## AIロジック (agent/main.py)
- 選択肢を OptionType の優先度で評価: 能力>進化>展開>エネ付け>攻撃>終了
- 壁デッキ最適化: エネ付け(8)・進化(9)は inPlayArea==4(アクティブ)を優先
- 未対応(今後): 攻撃ダメージ最大化(attackId→damageマップが要る), Boss呼び出し対象の選別

## 既知の制約
- ローカル同梱の cabt には all_attack()/all_card_data() が無く、attackId→ダメージの
  実行時マップが作れない（DLLの AllAttack/AllCard は引数/規約不明でバインド失敗）。

## 強化トグルのA/B検証結果（重要・正直な記録）
v2 を基準に各案を直接対戦で検証 → 大サンプルでは全て50%付近=効果なし:
- search(山札サーチ最適化): 400戦で 49.0%（200戦時の53.8%はブレ）
- promote(イワパレス優先昇格): 50.0%
- boss(低HP呼び出し): 49.4%
- KO-Boss(倒せる時だけBoss): 200戦 53.5%（誤差帯, 不確実）
結論: ルールベースの微調整は頭打ち。v2の強さは「壁デッキ構造＋基本優先度」由来。
さらに伸ばすには RL(大規模・不安定) か デッキ改良(弱点テック) が必要。

## ラダー分析（2026-06-17, score 673.9）
リプレイ(episodes/replay)で実対戦を解析 → 相手の約半数がイワパレス・ミラー。
gauntlet(実アーキタイプ再現)での v2 勝率:
- vs ogerpon_ex(全ex): 93%   ← 壁が完封
- vs iono_bellibolt(混成): 82%
- vs crustle_mirror: 48%      ← ボトルネック
スコア計算: ミラー0.5×50% + 非ミラー0.5×85% ≒ 67.5% ≒ score674 と一致。
=> 天井はミラー50%。シンプル壁デッキの自然な到達点。

## 天井を破るには（実験で確認した結論）
- ルールベース微調整(search/promote/boss/KO): 全て約50%=効果なし
- Fireテック(Volcanion 663)をデッキに足すだけ: AIが使い分けできず逆効果(総合75→69%)
- 必要なのは「Fireテック」+「対イワパレス時はVolcanionで弱点(×2)ワンパンする条件分岐AI」
  の"デッキ×ピロット"連動。= 本格的な開発項目。
- 代替: RL / 別アーキタイプへの乗り換え。
ツール: experiments/gauntlet_run.py, analyze_replays.py, tune_mirror.py で随時測定可。

## 提出安全性（検証済み 2026-06-17）
experiments/verify_submission.py で Kaggle と同条件ロード(__file__無し/最後のcallable)＋
120戦フル対戦 → 例外0 / 最大応答0.3ms。提出時クラッシュ要因なし。
