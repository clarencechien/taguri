# Session A 交給 Session B 的說明

日期：2026-11-10。Session A 做完 S0 到 S5。這份文件只寫量到的數字、執行環境的實測、jevlike 的判斷行為，以及 `evalkit` 的用法。

## 1. 交付了什麼

| 路徑 | 內容 |
|---|---|
| `evalkit/`、`pyproject.toml` | 資料載入與指標（R@k、AE@k、配對 bootstrap）。只依賴 numpy |
| `data/musique/`、`data/2wikimultihopqa/` | 正規化後的語料、題目、切分名單 |
| `data/multihop-rag/` | MultiHop-RAG 的語料（已分段）、題目、300 題抽樣名單 |
| `reference/` | 各參考方法的逐題分數（只有題號和指標），說明在 `reference/README.md` |
| `SAG2POC-handoff.md` | 交接文件 v0.5 |

## 2. 資料

| 題組 | 段落數 | 題數 | 切分（`splits.json` 的鍵） |
|---|---:|---:|---|
| `musique` | 11,656 | 1,000 | `dev` 300、`calib` 150（dev 的前半）、`check` 150（dev 的後半）、`dev_zh_source` 100（dev 的前 100 題）、`test` 700 |
| `2wikimultihopqa` | 6,119 | 1,000 | `dev` 100 |
| `multihop-rag` | 6,440 | 2,255 | `sample300` 300 |

- `pid` 是字串。`type`：MuSiQue 是 `2hop`／`3hop`／`4hop`；2Wiki 是 `compositional`／`comparison`／`bridge_comparison`／`inference`；MultiHop-RAG 是 `comparison_query`／`inference_query`／`temporal_query`。
- MuSiQue 和 2Wiki 的 dev 都是檔案的前 N 題（分布和整體相差不到 5 個百分點）。dev 的跳數：2 跳 161、3 跳 87、4 跳 52。
- **MuSiQue dev 比整體難一點**：BM25 的 R@5 在 dev 是 44.69，在全部 1,000 題是 47.66。
- 金標段落全部對得到語料。
- **MultiHop-RAG**：609 篇新聞在段落邊界切開，每段不超過 1,200 字元，`title` 是新聞標題。已排除沒有答案的題型。金標是「包含證據句的段落」，6,084 句證據全部對得到。有 13 句證據同時出現在同一篇文章的兩個段落，這種金標記成一串 pid，意思是「任一段命中就算」；`evalkit` 會自動處理。這個題組**只用 `sample300` 評分，不拿來調參數**。
- 來源與檔案雜湊記在 `data/MANIFEST.json` 和 `data/multihop-rag/MANIFEST.json`。

## 3. `evalkit` 的用法

```bash
pip install -e .
```

檢索結果寫成 run 檔，一行一題，`retrieved` 依名次排列：

```json
{"qid": "2hop__13548_13529", "retrieved": ["1", "12", "8"]}
```

```bash
# 計分，並把逐題分數寫出來
python -m evalkit score --dataset musique --split dev --run my_run.jsonl --out my_scores.jsonl

# 看某個參考方法在某個切分上的總分
python -m evalkit agg --dataset musique --split dev --scores reference/musique/b0.jsonl

# 兩組逐題分數做配對 bootstrap（10,000 次，95% 信賴區間），印出 a − b
python -m evalkit compare --dataset musique --split dev --a my_scores.jsonl --b reference/musique/b0.jsonl --metrics R@5 R@10 AE@10
```

在 Python 裡：

```python
from evalkit import load_questions, load_split, load_run, load_scores, score_run, aggregate, paired_bootstrap

questions = load_questions("musique")
qids = load_split("musique", "dev")
mine = score_run(questions, load_run("my_run.jsonl"), qids)
print(aggregate(mine, qids))                       # 百分比
print(paired_bootstrap(mine, load_scores("reference/musique/b0.jsonl"), qids, "R@5"))
```

- 計分前會先去重（保留第一次出現的 pid），再取前 k 名。
- run 檔少了任何一題會直接報錯，不會當成 0 分。
- `paired_bootstrap` 的亂數種子固定，重跑結果相同。
- 以文件為單位計分的題組（EnterpriseRAG）：把 `retrieved` 寫成文件編號、`gold_pids` 也用文件編號即可，去重規則相同。

## 4. 各段的數字和結論

### S0　重現（結論：繼續）

- 上游的三個驗證全部通過。
- 自己跑的上游 BM25，MuSiQue 1,000 題：R@5 47.66、R@10 54.50、AE@10 17.50。
- 用 `evalkit` 重算 SAG2＋Jev，MuSiQue 1,000 題：R@5 80.675、R@10 86.62、AE@10 69.50，和上游紀錄逐題零差異。

### S1　冒煙測試（結論：繼續）

- option mass 中位數 1.000，沒有低於 0.5 的判斷。
- 每 100 題約 $0.37。

### S2　單輪證據判斷（照原規則是「停」，Clarence 推翻後繼續）

MuSiQue dev 前 100 題，只判一輪：

| 方法 | R@5 | R@10 | AE@10 |
|---|---:|---:|---:|
| BM25 | 41.67 | 48.42 | 10.0 |
| jevlike 單輪 | 49.33 | 60.92 | 25.0 |
| Jev 單輪 | 57.08 | 65.42 | 26.0 |

- jevlike 減 BM25：ΔR@5 +7.67（95% 信賴區間 +1.83 到 +13.67），原門檻是 +8。
- AUROC 0.914（門檻 0.80）。

### S3　B0（結論：A 區，繼續）

MuSiQue dev 300 題，逐題配對：

| 方法 | R@1 | R@5 | R@10 | AE@10 |
|---|---:|---:|---:|---:|
| BM25 | 27.61 | 44.69 | 51.83 | 14.67 |
| SAG2＋Jina v3.5 兩輪 | 31.44 | 64.17 | 71.53 | 43.00 |
| **B0** | 33.56 | **77.47** | 83.03 | 63.00 |
| SAG2＋Jev | 35.19 | 79.94 | 86.72 | 68.67 |

- B0 減 SAG2＋Jev：ΔR@5 −2.47（−4.64，−0.17）、ΔR@10 −3.69（−5.83，−1.61）、ΔAE@10 −5.67（−10.00，−1.33）。
- B0 減 Jina 兩輪：ΔR@5 +13.31（+10.53，+16.28）。
- 依跳數的 R@5（B0／SAG2＋Jev）：2 跳 89.1／88.2，3 跳 68.6／76.2，4 跳 56.2／60.6。

各階段（MuSiQue dev 300 題）：

| 階段 | B0 R@5 | Jev R@5 | B0 AE@10 | Jev AE@10 |
|---|---:|---:|---:|---:|
| H0 | 50.25 | 59.78 | 26.67 | 34.00 |
| H1 | 72.14 | 77.64 | 53.33 | 62.33 |
| H2 | 77.47 | 79.94 | 63.00 | 68.67 |

2Wiki dev 100 題：B0 R@5 97.25、R@10 97.25、AE@10 92.0；SAG2＋Jev 97.75／97.75／93.0；BM25 66.50／69.25／36.0。各階段的 B0 R@5：58.00、89.75、97.25。

**dev 400 題合計，B0 的 R@5 是 82.42**（S6 的整體門檻用這個數字）。

S6 寫了「N2 在 2Wiki dev 的 R@5 ≥ 90 就跳過 N3」。B0 在同一批題目已經是 97.25，請留意這一條。

### S4　MultiHop-RAG（結論：繼續）

`sample300` 的 300 題：

| 方法 | R@1 | R@5 | R@10 | AE@10 |
|---|---:|---:|---:|---:|
| BM25 | 19.17 | 39.92 | 52.42 | 24.33 |
| **B0** | 24.56 | **60.56** | **70.89** | 45.33 |

- B0 減 BM25：ΔR@10 +18.47（+15.17，+21.92）。
- B0 各階段的 R@10：65.58、65.75、70.89；R@5：47.72、56.03、60.56。
- 依題型的 R@5（BM25／B0）：comparison 48.2／70.3，inference 37.3／61.4，temporal 31.4／45.1。
- S9 的門檻是「最佳 N − B0」的 ΔR@10，B0 的逐題分數在 `reference/multihop-rag/b0.jsonl`。

## 5. Modal 與 SGLang 的實測

### 環境

| 項目 | 實測 |
|---|---|
| GPU | Modal L40S（46 GB），以 $1.95／小時估算 |
| 模型 | `RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic` @ `ed35d7abe5d9`，權重在 jevlike 的 Volume `gb10-decide-hf`（已下載好，掛上去直接讀） |
| image | `lmsysorg/sglang:gemma4-mtp`，SGLang `0.5.12.post2.dev932`；L40S 要帶 jevlike `modal_sglang.py` 裡那份 fused-MoE Triton 設定檔 |
| 伺服器參數 | context 16,384、`--max-running-requests 64`、`--mem-fraction-static 0.8`；radix cache 是預設開啟；沒有開 MTP |
| 載入後的 GPU 記憶體 | 約 38 GB |
| Modal client | 在 Claude Code 網頁版的環境要裝 `modal[api-proxy-support]` 才連得上；金鑰在環境變數 `modal`、`modal_secret`，要對應到 `MODAL_TOKEN_ID`、`MODAL_TOKEN_SECRET` |
| 命令列參數 | `@app.local_entrypoint()` 的參數不要取名 `ctx`，會和 Modal 的命令列框架撞名 |

### 冷啟動

四次分別是 100、175、419、472 秒（從啟動 SGLang 到 health 通過）。變動很大；後兩次是兩個容器同時啟動。每次冷啟動約 $0.05 到 $0.26，估成本時用 $0.25 比較保險。**同一個容器裡連續跑多組題目可以省掉重複的冷啟動。**

### 吞吐量與成本

| 設定 | 每題判斷次數 | 每題輸入 token | 快取命中 | 每題實際要算的 token | 每題 GPU 秒 | 每 100 題 |
|---|---:|---:|---:|---:|---:|---:|
| 單輪，MuSiQue（沒有共用的長前綴） | 100 | 28,531 | 20.8% | 22,585 | 1.07 | $0.06 |
| B0 兩輪擴展，MuSiQue | 334 | 613,656 | 82.8% | 105,742 | 6.9 | $0.37 |
| B0 兩輪擴展，2Wiki | 334 | 616,978 | 82.8% | 106,191 | 7.1 | $0.39 |
| B0 兩輪擴展，MultiHop-RAG（段落約兩倍長） | 333 | 1,061,480 | 85.7% | 151,382 | 10.4 | $0.56 |

- **成本大致跟著「沒命中快取的 token 數」走**：每秒約 14,500 到 21,000 個（長前綴時靠下限，短 prompt 時靠上限）。估新流程的成本，用「每題判斷次數 × 每次判斷不共用的 token 數 ÷ 15,000」估秒數，再乘 $1.95／3,600。
- 每秒可以做 48 次（長前綴）到 93 次（短 prompt）判斷。
- 題目並行 16、每批 64 個 prompt、伺服器同時處理上限 64，沒有遇到記憶體問題。
- **共用前綴的做法**：把同一題所有候選共用的部分（模板開頭、問題、已有證據）放在 prompt 前面，候選段落和問句放後面；先送一個候選把前綴算進快取，再把其餘的整批送出。這樣快取命中率有八成多。
- 交接文件原本用每 100 題 $1.2 估預算，實際約為三分之一到二分之一。

### 讀法

- 用 HF `tokenizers` 直接載入模型目錄的 `tokenizer.json`，以 `add_special_tokens=False` 編碼；模板字串裡的 `<bos>` 會被對成特殊 token（id 2）。送 `input_ids`。
- `A`、`B` 各是單一 token（id 236776、236799）。用 `/generate` 的 `token_ids_logprob` 直接取這兩個 token 的 logprob，不必掃 top-k。
- **option mass 一直很健康**：四次執行共約 24 萬次判斷，中位數都是 1.000，最小值 0.968，沒有任何一次低於 0.5。模板第一次就對，沒有修過。
- **長 prompt 沒有問題**：最長到 7,808 token（MultiHop-RAG，prompt 帶已有證據），option mass 沒有下降。context 開 16,384 綽綽有餘；MuSiQue 最長 6,932 token。
- 英文題沿用 jevlike v8 的英文寫法（`[State]`、`[Question]`、英文 system 句、`A. Yes`／`B. No`、最後一句要求只回答字母），模板 `GEMMA4_TEMPLATE_NOTHINK_BOS` 沒有改。

## 6. jevlike 判斷行為的觀察

下面的數字都是 jevlike 回答「這段是不是證據」這類是非題時量到的。題目文字和你們要寫的不同，數字會變，但行為的型態應該類似。

### 6.1 機率非常兩極

- 單輪（S2）：87% 的判斷 P(是) < 0.0001，72% 四捨五入到小數六位後是 0。
- 金標證據的 P(是) 不是接近 1 就是接近 0，中間很少：MuSiQue 單輪的第 25／50／75 百分位是 0.0003／0.037／0.996。
- **用機率設門檻或排序會遇到大量同分，請用 log-odds（log P(A) − log P(B)），並且存原始的兩個 logprob。**
- log-odds 也不是完全沒有同分：S3 的判斷中，相異的 log-odds 值只占 56% 到 79%（伺服器回傳的 logprob 精度有限）。排序時要有固定的次要排序鍵（例如詞彙分數或段落編號）。

### 6.2 沒有已有證據時，金標容易被判成「否」；帶上已有證據後明顯改善，但沒有完全解決

每個階段實際被送進判斷的段落（H0 沒有已有證據；H1、H2 的 prompt 帶已有證據）：

| 題組 | 階段 | 金標 P(是) ≥ 0.5 | 金標 P(是) 中位數 | 非證據 P(是) ≥ 0.5 |
|---|---|---:|---:|---:|
| MuSiQue dev 300 | H0 | 46.9% | 0.112 | 1.85% |
| | H1 | 60.0% | 0.952 | 0.52% |
| | H2 | 61.3% | 0.984 | 0.51% |
| 2Wiki dev 100 | H0 | 32.4% | 0.008 | 2.74% |
| | H1 | 84.5% | 0.999 | 0.05% |
| | H2 | 85.7% | 1.000 | 0.01% |
| MultiHop-RAG 300 | H0 | 50.6% | 0.621 | 9.81% |
| | H1 | 62.9% | 0.987 | 3.24% |
| | H2 | 53.7% | 0.858 | 3.31% |

（S2 的前 100 題單輪是 40.9%。）

- 帶上已有證據之後，金標判「是」的比例上升、誤判成「是」的非證據下降，兩個方向都改善。2Wiki 最明顯。
- MuSiQue 帶了已有證據之後，仍有約四成被送進判斷的金標被判成「否」。
- **新聞語料的誤判率高得多**：MultiHop-RAG 的非證據有 3% 到 10% 被判成「是」，數量是金標的 3 到 8 倍。同一事件有很多篇相關報導，這些段落內容相關但不是標註的證據。

### 6.3 log-odds 的分布（MuSiQue dev 300 題，給設 τ 參考）

金標證據的 log-odds 百分位：

| 階段 | 第 10 | 第 25 | 第 50 | 第 75 | 第 90 |
|---|---:|---:|---:|---:|---:|
| H0 | −13.6 | −8.6 | −2.1 | +6.1 | +9.8 |
| H1 | −10.3 | −5.8 | +3.0 | +7.1 | +10.3 |
| H2 | −10.7 | −5.8 | +4.1 | +8.3 | +11.4 |

非證據的 log-odds：中位數約 −19 到 −21；第 99 百分位 H0 是 +3.6，H1、H2 約 −4.5。

不同門檻留下的比例：

| 門檻（log-odds ≥） | H0 金標留下 | H0 每題留下的非證據 | H1 金標留下 | H1 每題留下的非證據 |
|---:|---:|---:|---:|---:|
| −6 | 64.4% | 4.9 段 | 75.7% | 1.6 段 |
| −4 | 55.8% | 3.2 段 | 68.9% | 1.0 段 |
| −2 | 49.9% | 2.3 段 | 63.0% | 0.8 段 |
| 0 | 46.9% | 1.8 段 | 60.0% | 0.6 段 |
| +2 | 41.2% | 1.4 段 | 54.0% | 0.4 段 |

把門檻從 0 降到 −6，金標多留約 16 到 18 個百分點，代價是每題多留 1 到 3 段非證據。這張表是在別的題目文字下量的，只能當起點；τ 仍然要照交接文件在校準半上調。

### 6.4 log-odds 事後重排對最終前十名沒有影響

把每題所有判過的段落（取每段最後一次判斷）改用 log-odds 排序取前十：

| 題組 | B0 實際 R@5 | log-odds 重排 R@5 | 差（95% 信賴區間） |
|---|---:|---:|---:|
| MuSiQue dev 300 | 77.47 | 77.33 | −0.14（−0.56，+0.17） |
| 2Wiki dev 100 | 97.25 | 97.25 | 0 |
| MultiHop-RAG 300 | 60.56 | 60.47 | −0.08（−1.28，+1.14） |

R@10 和 AE@10 完全相同。經過兩輪之後，前十名的分數都離 0 很遠，機率本來就不會同分。log-odds 的價值在設門檻、處理名單後段、以及事後分析，不在於改變最終排序。

### 6.5 每題判斷次數

B0 每題約 334 次判斷（第 90 百分位 337），三個題組都一樣。這超過交接文件 150 次的標示線，會直接影響 GB10 上的延遲。新架構如果每題判斷次數少，成本和延遲都會等比例下降。

## 7. 還沒做、要留意的事

- **花費是用容器時間乘單價估的，沒有和 Modal 帳單核對。** Session A 四次執行合計約 $3.98。兩個 session 共用同一個 Modal 帳號，開工前先看一次累計花費。
- Session A 用的 Modal app 是 `sag2poc-a-baseline`、Volume 是 `sag2poc-a-results`。Session B 請用 `sag2poc-b-*`。
- Jev 的各階段分數（`sag2_jev_h0`、`sag2_jev_h1`）是上游紀錄裡的數值；其餘 Jev、Jina 的分數是用 `evalkit` 從上游的檢索名單重算的，和上游紀錄逐題一致。
- `reference/` 裡沒有 Qwen3-Reranker-0.6B：上游只留了總平均，沒有逐題紀錄。`sag2_qwen3rerank_302` 是 302 平台的 `qwen3-rerank`，是另一個模型。
- MultiHop-RAG 沒有 SAG2＋Jev 的紀錄，只能和 B0、BM25 比。
