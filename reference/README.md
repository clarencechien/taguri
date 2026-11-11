# reference/：各參考方法的逐題分數

每個檔案一行一題：`{"qid", "R@1", "AE@1", "R@2", "AE@2", "R@5", "AE@5", "R@10", "AE@10"}`，數值是 0 到 1。只有題號和指標，沒有檢索名單。

B0 的檔案只涵蓋 dev（MuSiQue 300 題、2Wiki 100 題）；其他方法在多跳題組上涵蓋全部 1,000 題，用 `--split dev` 或 `--split test` 取子集。

## musique

| 檔案 | 方法 | 涵蓋題數 | dev R@5 | dev R@10 | dev AE@10 |
|---|---|---:|---:|---:|---:|
| `b0.jsonl` | B0：SAG2 迴圈＋jevlike，兩輪擴展（H2） | 300 | 77.47 | 83.03 | 63.00 |
| `b0_h0.jsonl` | B0，H0 階段 | 300 | 50.25 | 60.14 | 26.67 |
| `b0_h1.jsonl` | B0，H1 階段 | 300 | 72.14 | 77.83 | 53.33 |
| `bm25.jsonl` | 上游 BM25（我們自己跑的） | 1000 | 44.69 | 51.83 | 14.67 |
| `bm25_jina_single.jsonl` | BM25＋Jina v3.5 單輪 | 1000 | 62.50 | 66.61 | 34.00 |
| `bm25_paper_control.jsonl` | 上游對照紀錄裡的 BM25（和上一列逐題相同） | 1000 | 44.69 | 51.83 | 14.67 |
| `bm25_qwen3rerank_302_single.jsonl` | BM25＋qwen3-rerank（302 平台）單輪 | 1000 | 58.64 | 65.72 | 30.33 |
| `sag2_jev.jsonl` | SAG2＋Jev，兩輪擴展（H2） | 1000 | 79.94 | 86.72 | 68.67 |
| `sag2_jev_h0.jsonl` | SAG2＋Jev，H0 階段 | 1000 | 59.78 | 67.31 | 34.00 |
| `sag2_jev_h1.jsonl` | SAG2＋Jev，H1 階段 | 1000 | 77.64 | 83.31 | 62.33 |
| `sag2_jina.jsonl` | SAG2＋Jina v3.5，兩輪擴展 | 1000 | 64.17 | 71.53 | 43.00 |
| `sag2_qwen3rerank_302.jsonl` | SAG2＋qwen3-rerank（302 平台，不是 Qwen 0.6B），兩輪擴展 | 1000 | 54.22 | 71.33 | 44.00 |

## 2wikimultihopqa

| 檔案 | 方法 | 涵蓋題數 | dev R@5 | dev R@10 | dev AE@10 |
|---|---|---:|---:|---:|---:|
| `b0.jsonl` | B0：SAG2 迴圈＋jevlike，兩輪擴展（H2） | 100 | 97.25 | 97.25 | 92.00 |
| `b0_h0.jsonl` | B0，H0 階段 | 100 | 58.00 | 64.25 | 41.00 |
| `b0_h1.jsonl` | B0，H1 階段 | 100 | 89.75 | 90.25 | 78.00 |
| `bm25.jsonl` | 上游 BM25（我們自己跑的） | 1000 | 66.50 | 69.25 | 36.00 |
| `sag2_jev.jsonl` | SAG2＋Jev，兩輪擴展（H2） | 1000 | 97.75 | 97.75 | 93.00 |
| `sag2_jina.jsonl` | SAG2＋Jina v3.5，兩輪擴展 | 1000 | 83.50 | 88.00 | 68.00 |

## multihop-rag

| 檔案 | 方法 | 涵蓋題數 | sample300 R@5 | sample300 R@10 | sample300 AE@10 |
|---|---|---:|---:|---:|---:|
| `b0.jsonl` | B0：SAG2 迴圈＋jevlike，兩輪擴展（H2） | 300 | 60.56 | 70.89 | 45.33 |
| `bm25.jsonl` | 上游 BM25（我們自己跑的） | 300 | 39.92 | 52.42 | 24.33 |

## Taguri 自己的逐題分數（Session B 加的）

雲端（Modal L40S、SGLang、FP8 權重）跑出來的結果，給之後在別的環境重現時做配對比較用。

| 檔案 | 內容 | 涵蓋 |
|---|---|---|
| `musique/taguri_n1.jsonl` | Taguri 定案設定 N1 | dev 300 題（R@5 80.17）＋ test 700 題（R@5 80.20） |
| `musique/taguri_n0.jsonl` | 只有詞彙層 | dev 300 題（R@5 47.72） |
| `2wikimultihopqa/taguri_n1.jsonl` | N1 | dev 100 題（R@5 100.00） |
| `multihop-rag/taguri_n1.jsonl` | N1 | sample300（R@10 72.17） |

## 歸因補測的逐題分數

Session A 在 [`handoff/A-to-B-attribution.md`](../handoff/A-to-B-attribution.md) 第 5 節列的檔案。企業文件的三個已經放進來，用 `analysis/attribution_check.py` 重算過，和說明文件的數字相同。

| 檔案 | 內容 | 題數 | 平均 R@10 |
|---|---|---:|---:|
| `enterprise/sag2_jev.jsonl` | SAG2＋Jev，文件層級 | 470 | 81.10 |
| `enterprise/bm25_upstream.jsonl` | 上游 BM25，文件層級 | 470 | 67.82 |
| `enterprise/b0.jsonl` | B0，只有專案相關和完整性 | 60 | 68.94 |

中文的 B0 與上游 BM25 逐題分數（`musique-zhtw2/`、`musique-zhcn2/`）沒有放進來，也不打算要。中文的結論是要靠真實繁中資料，重算只有驗算的價值。

Taguri 這一側要配對用的逐題分數已經匯出（2026-11-11，從既有的 `run.jsonl` 重新計分，平均值和各段報告一致）：

| 檔案 | 內容 | 題數 | 平均 |
|---|---|---:|---|
| `enterprise/taguri_n0.jsonl` | 只有詞彙層，文件層級 | 470 | R@10 68.98 |
| `enterprise/taguri_n1.jsonl` | N1，文件層級 | 470 | R@10 74.50 |
| `enterprise/taguri_n1_eg2.jsonl` | N1＋EG2（先跑 300 題，後補 170 題） | 470 | R@10 80.71 |
| `musique-zhtw2/taguri_n0.jsonl`、`taguri_n1.jsonl`、`taguri_n1_eg2.jsonl` | 繁中，重翻問題後的版本，切分 `dev_zh` | 100 | R@5 38.58、66.33、66.42 |
| `musique-zhcn2/` 同名三個檔 | 簡中 | 100 | R@5 38.58、67.58、71.58 |
| `musique-dev-zh-en/` 同名三個檔 | 同一批 100 題的英文原題（`data/musique` 的切分 `dev_zh_source`） | 100 | R@5 46.08、80.25、81.58 |

EnterpriseRAG 和中文題組的題目檔不在 repo 裡（在 Volume `taguri-b-results`），用 `evalkit compare` 時要用 `--root` 指到放題目檔的資料夾。
