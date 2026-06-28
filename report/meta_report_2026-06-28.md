# 環境レポート — PTCG AI Battle 現メタ分析（2026-06-28）

ラダー上位50チームのデッキをリプレイから抽出し、主役アタッカー（megaEx > ex > Stage2 の打点ポケモン）でアーキタイプ分類した集計。

> 本レポートは**アーキタイプ単位の集計分析**のみ。個別プレイヤーの60枚デッキリストや個人名との紐付けは競技中のため非公開（生データはローカル保管）。

---

## アーキタイプ分布（上位50チーム）

| # | アーキタイプ | 数 | 割合 |
|---|---|---:|---:|
| 1 | **Mega Starmie ex**（水） | 13 | 26% |
| 2 | **Archaludon ex**（鋼） | 11 | 22% |
| 3 | **Dragapult ex**（超/竜） | 7 | 14% |
| 4 | Alakazam（超・アンチメタ） | 4 | 8% |
| 4 | Fezandipiti ex（悪） | 4 | 8% |
| 6 | Hop's Snorlax | 2 | 4% |
| – | Mega Abomasnow ex / Walrein / Mega Froslass ex / Togekiss / Mega Lopunny ex / Cynthia's Garchomp ex / Mega Lucario ex / Crustle Wall / その他 | 各1 | 各2% |

上位50に**15アーキタイプ**が混在＝多様化した環境。

## 上位帯（Top10）の顔ぶれ

| 順位 | スコア | アーキタイプ |
|---:|---:|---|
| 1 | 1420.3 | **Archaludon ex** ← 現1位 |
| 2 | 1368.2 | Mega Starmie ex |
| 3 | 1343.6 | Archaludon ex |
| 4 | 1329.7 | Mega Starmie ex |
| 5 | 1309.1 | Mega Starmie ex |
| 6 | 1273.9 | Mega Starmie ex |
| 7 | 1263.8 | Alakazam |
| 8 | 1260.3 | Fezandipiti ex |
| 9 | 1245.8 | Mega Starmie ex |
| 10 | 1238.8 | Dragapult ex |

---

## 主要な所見（メタの動き）

1. **首位交代 — Archaludon ex（鋼）が新1位（1420）**。少し前まで最上位だった Mega Starmie ex を抜いた。上位50で22%を占め、第二勢力にまで急拡大。
2. **Mega Starmie ex は最大母数（26%）で依然トップ層**。順位1位は譲ったが、Top10に5デッキと層が厚く、環境の中心デッキであることは変わらない。
3. **Crustle Wall（イワパレス壁）はほぼ絶滅（50中1）**。少し前は環境の半数を占めた壁が、貫通・効果無視系アタッカー（Mega Starmie ex の Nebula Beam 等）の普及で完全に淘汰された。
4. **Mega Lucario ex も失速（50中1）**。壁にブロックされる弱点と、Starmie/Archaludon の台頭で上位から後退。
5. **Dragapult ex が第三勢力（14%）に成長**。機動力のあるスナイプ系。
6. **Alakazam（超）がアンチメタとして定着（8%）**。技サイコが「相手のバトル場のエネ1個ごとに+50」とエネ集中型を罰する。Starmie/Archaludon のようにアタッカーへエネを盛るデッキの天敵。

## 我々のエージェントへの含意

- **採用デッキ（Mega Starmie ex）は環境最大母数で立ち位置は良好**。ただし**新1位 Archaludon ex（鋼）への対策が最優先課題**。
- 警戒すべき新興：**Archaludon ex（22%）/ Dragapult ex（14%）**。次の検証はこの2つとの相性測定。
- 既知の苦手 **Alakazam（超）** は依然8%で残存。エネを盛りすぎない立ち回り（安い技優先・進化前を早期処理）を継続。
- 壁・Lucario はほぼ消えたので、それら専用の対策の優先度は下げてよい。

---

*手法: ラダーCSV → 上位50チームのteam-submissions → episode → replay を取得し、初手アクションの60枚デッキを抽出 → 主役アタッカーで分類・集計（`experiments/extract_top50.py`, 生データは非公開）。*
