# Taguri 在 GB10 上的接手文件

給在 GB10 上接手的人（或 Claude Code）。目的有三個。**先在不連外網的 GB10 上把環境重現出來，再量出單題延遲，最後用自己的文件試用。**

先讀 [`README.md`](../README.md) 的第 2、3、6 節，再回來這裡。每一階段都先看門檻再跑，跑完照門檻填結論。沒過的照實寫。

## 0. 範圍與規則

**試用範圍**：GB10 單機，不連外網，文件放在本機檔案系統。

**規則**

1. **真實資料不離開 GB10**：不上雲端、不進 git。報告只放彙總數字和你自己寫的評語，不放文件原文。
2. 不改 `taguri/decide.py` 裡的模板（`GEMMA4_TEMPLATE_NOTHINK`）和已鎖定的題目寫法。不用真實資料調 `results/thresholds.lock.json`。要試降配請用副本（第 6 節）。
3. 判斷用的伺服器**不開 MTP 草稿頭**，也不和開了 MTP 的生成伺服器共用（jevlike v18：第一個 token 的機率會不穩定）。
4. 每個階段結束 commit（分支自己開，例如 `gb10/<日期>`），結果放 `results/gb10/`。

## 1. 現在知道什麼、不知道什麼

| | 狀態 |
|---|---|
| 英文多跳檢索的品質（Modal L40S、SGLang、FP8 權重） | 已量：MuSiQue dev R@5 80.17、test 80.20 |
| 換成 GB10 的量化權重（GGUF）後品質有沒有變 | **沒量過**，階段 2 |
| 換成 llama-server 後讀機率的行為 | **沒接過真的 llama-server**。`LlamaBackend` 只用模擬伺服器驗過流程，階段 1 要先確認 |
| 單獨一題要等多久 | **沒量過**。雲端實驗都是 16 題並行，階段 3 |
| 自己的文件上好不好用 | **沒量過**，階段 4 |
| 繁中 | 機器翻譯題組上比英文低約 13 分，另一套迴圈配同一顆判官也掉 7 到 10 分（[`results/attribution.md`](../results/attribution.md)）。真實繁中文件沒量過 |

雲端量到的工作量（估延遲用）：

| 段落長度 | 每題判斷次數（中位數／第 90 百分位） | 每題輸入 token |
|---|---:|---:|
| 約 400 字元（MuSiQue） | 143／170 | 9.2 萬 |
| 約 1,000 字元（MultiHop-RAG） | 139／158 | 23.5 萬 |
| 約 2,000 字元（EnterpriseRAG） | 168／195 | 56 萬 |

每題的判斷分成 30 多個批次**依序**送出（每 5 段一批，批與批之間要更新已有的證據），所以單題延遲不會因為伺服器能並行就等比例變快。

## 2. 資料怎麼存：檔案加 SQLite

沒有任何服務要架，也不需要連網。

| 東西 | 形式 | 說明 |
|---|---|---|
| 語料 | `corpus.jsonl` | 每行一段：`pid`、`doc`、`title`、`text` |
| 詞彙索引 | **一個 SQLite 檔**（`.db`） | FTS5 全文索引、段落原文、標題查表都在裡面。查詢時只需要這個檔 |
| EG2 向量（選配） | 一個 `.npy` 檔 | float16 矩陣，載入記憶體後暴力比對，沒有向量資料庫 |
| 判官 | 本機的 llama-server 或 SGLang | 透過 `127.0.0.1` 的 HTTP 呼叫 |
| 判斷結果快取（選配） | 資料夾裡的 `.jsonl` | 給 `--cache-dir` 時才有。重跑同樣的題目不用再算 |

大小參考：MuSiQue 1.2 萬段的索引 18 MB、建 5 秒。EnterpriseRAG 154 萬段的索引 7.7 GB、建 5 分鐘（14 個行程）。

**文件怎麼進來**

```bash
python tools/ingest_files.py --src /path/to/docs --out /path/to/store --name mydocs
```

- 會遞迴讀 `.txt`、`.md`、`.log`、`.csv`、`.json`、`.html`、`.rst`，一個檔案算一份文件。
- 超過 2,000 字元的文件在段落邊界切開。標題取第一個 `#` 標題，沒有就用檔名。
- 產出 `store/mydocs/corpus.jsonl` 和 `store/idx/mydocs.db`。
- **PDF 和 Office 文件（Word、Excel）要先自己轉成文字**，這個工具不解析它們。
- 文件有新增或修改時，目前只能整個重建索引（沒有做增量更新）。

**已知的規模限制**：154 萬段時，每題的詞彙檢索要花數十秒到幾分鐘（SQLite FTS5 對很多詞的 OR 查詢沒有提前終止）。試用請先從十萬段以內開始。

## 3. 要帶進 GB10 的東西（離線清單）

在有網路的機器上備齊，連同 sha256 一起帶進去。

**程式**

- 這個 repo（`main`）。`data/` 裡已有三個公開題組，`reference/` 裡有逐題的參考分數。
- [jevlike](https://github.com/clarencechien/jevlike) repo（查模板與 llama-server 的檢查腳本用）。

**Python 套件**（先在同樣是 arm64、同版 Python 的機器上 `pip download -d wheels/ <套件>`，進去後 `pip install --no-index --find-links wheels/ <套件>`）

| 套件 | 這次用的版本 | 誰需要 |
|---|---|---|
| `numpy` | 2.x | 評測 |
| `jieba` | 0.42.1 | 詞彙層（詞典包在套件裡，不用另外下載） |
| `opencc-python-reimplemented` | 0.1.7 | 繁簡正規化（純 Python，設定檔包在套件裡） |
| `snowballstemmer` | 3.1.1 | 英文詞幹 |
| `requests` | 任意近期版本 | 呼叫判官 |
| `tokenizers` | 任意近期版本 | **只有 SGLang 路徑**需要 |
| `sentence-transformers` ≥ 6.1、`transformers` ≥ 5.19、`torch`、`torchvision`、`pillow` | | **只有 EG2** 需要 |

Python 內建的 `sqlite3` 要有 FTS5（確認方式見階段 0）。

**模型**

| 用途 | 檔案 | 備註 |
|---|---|---|
| 判官（llama-server，GB10 的預設路徑） | `unsloth/gemma-4-26B-A4B-it-GGUF` 的 `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`（17 GB）。有空間的話再帶 `Q8_0`（27 GB） | 和 jevlike 的 GB10 文件同一組 |
| 判官（SGLang，選配） | `RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic` @ `ed35d7abe5d9` | 雲端實驗用的就是這個，重現性最好 |
| EG2（選配） | `google/embeddinggemma-2` @ `914f7f89142e33e77833254d9c9b90c3cef7303b` | Apache 2.0，不需要金鑰。設 `HF_HUB_OFFLINE=1` |

llama.cpp 要 **≥ b11371**、arm64 + CUDA（sm_121）的 build。細節見 jevlike 的 `docs/handoff-gb10.md` 第 1 節。

## 4. 啟動判官

**llama-server（預設）**

```bash
llama-server -m gemma-4-26B-A4B-it-UD-Q4_K_M.gguf \
  --jinja --reasoning-budget 0 --swa-full -np 4 -c 65536 --host 127.0.0.1 --port 8080
```

- 每個 slot 的 context 是 `-c ÷ -np`，要 **≥ 16384**（上面是 65536 ÷ 4）。
- `--swa-full` 一定要開，否則同一輪的候選無法共用「問題＋已有證據」這段前綴，時間會多好幾倍。
- Taguri 這邊用 `--judge llama --base-url http://127.0.0.1:8080`。`--llama-parallel` 設成和 `-np` 一樣。

**SGLang（選配）**

```bash
python -m sglang.launch_server --model-path <FP8 權重目錄> --context-length 16384 \
  --max-running-requests 64 --mem-fraction-static 0.8 --host 127.0.0.1 --port 30000
```

Taguri 這邊用 `--judge sglang --base-url http://127.0.0.1:30000 --tokenizer <FP8 權重目錄>/tokenizer.json`。

兩條路徑的差別：

| | llama-server | SGLang |
|---|---|---|
| `<bos>` | 伺服器自己加。Taguri 送出時會把模板開頭的 `<bos>` 拿掉 | Taguri 送 token id，自己帶 `<bos>` |
| 讀到的機率 | 只有前 40 名的 token。選項字母不在裡面時用「比第 40 名再低 1」代替 | 指定 token，精確 |
| 對分數的影響 | 很負的 log-odds 會被截平。明確被否決的段落之間改由 BM25 分數決定先後，不影響前幾名 | 無 |
| 一次送很多題 | 不支援整批。用 `-np` 個連線並行 | 支援整批 |

## 5. 階段與門檻

### 階段 0　環境（只用 CPU，10 分鐘）

```bash
python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute('create virtual table t using fts5(a)'); print(sqlite3.sqlite_version, 'fts5 ok')"
pip install --no-index --find-links wheels/ -e .
python -m taguri.run --config N0 --dataset musique --split dev --idx-dir /tmp/taguri-idx
python -m taguri.run --config N0 --dataset 2wikimultihopqa --split dev --idx-dir /tmp/taguri-idx
```

**門檻**：詞彙層是確定性的，數字要一模一樣。

| | R@5 | R@10 | AE@10 |
|---|---:|---:|---:|
| MuSiQue dev 300 題 | 47.72 | 53.47 | 15.67 |
| 2Wiki dev 100 題 | 67.25 | | 36.00 |

- 完全相同 → 繼續。
- 差超過 0.5 → **停**。先查三個套件的版本：jieba、OpenCC 和 SQLite（SQLite 版本不同可能讓 FTS5 的 BM25 有細微差異，差在 0.5 以內就記下來繼續）。

### 階段 1　判官冒煙測試（10 分鐘）

```bash
python -m taguri.run --config N1 --dataset musique --split dev --limit 10 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --out results/gb10/smoke
```

最後一行會印出 `min_option_mass`、`per_question_s`、`failed_questions`。

**門檻**

1. `failed_questions` 是 0，沒有 context 超長的錯誤。
2. 是非題的 option mass 健康：在 `results/gb10/smoke/trace.jsonl.gz` 裡每題的 `stats.min_mass`，10 題的中位數 ≥ 0.9。雲端上是非題約 16 萬次判斷的中位數是 1.0000，低於 0.5 的只有 0.01%。
   - 注意：選橋接詞那一題（四選一）本來就有 11% 到 15% 的判斷 option mass 低於 0.5，所以 `min_mass` 偶爾很低是正常的。要看的是「是不是幾乎每一題都很低」。
3. 這 10 題的 R@5 ≥ 60（雲端上同樣 10 題是 78.3，10 題的變動很大，這裡只是擋掉完全壞掉的情況）。

**判斷**

- 都過 → 繼續。
- option mass 普遍很低 → 模板或 `<bos>` 有問題。先用 jevlike 的 `bench/run_local.py --which smoke` 確認伺服器本身沒問題。再看 `--jinja --reasoning-budget 0` 有沒有帶。**修兩次還是不行就停**，回報樣本。
- R@5 很低但 option mass 正常 → 看 `trace` 裡 `judged` 的 `lo` 是不是全部擠在同一個值（代表前 40 名截斷太嚴重）。是的話改用 SGLang 路徑重測。

### 階段 2　品質重現（約 300 題，時間依階段 3 的延遲而定）

```bash
python -m taguri.run --config N1 --dataset musique --split dev \
  --judge llama --base-url http://127.0.0.1:8080 --workers 4 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --cache-dir results/gb10/cache --out results/gb10/musique-dev-N1

python -m evalkit score --dataset musique --split dev --run results/gb10/musique-dev-N1/run.jsonl --out results/gb10/musique-dev-N1.scores.jsonl
python -m evalkit compare --dataset musique --split dev \
  --a results/gb10/musique-dev-N1.scores.jsonl --b reference/musique/taguri_n1.jsonl --metrics R@5 R@10 AE@10
```

`reference/musique/taguri_n1.jsonl` 是雲端（SGLang、FP8）跑出來的逐題分數，`compare` 會印出 GB10 減雲端的差和 95% 信賴區間。

如果單題延遲太長、300 題跑不完，先跑校準半的 150 題（`--split calib`，雲端是 80.56）。

**門檻（MuSiQue dev 300 題的 R@5，雲端是 80.17）**

| GB10 的結果 | 判定 |
|---|---|
| 和雲端的差，信賴區間下界 > −3 | **重現成功**：量化與伺服器沒有明顯影響 |
| 點估計在 −3 到 −6 之間 | **可用但有落差**：註明量化版本。有 Q8 的話用 Q8 再跑一次，看落差是不是量化造成的 |
| 點估計 < −6 | **停**：先用 SGLang 加 FP8 權重重跑。那樣就對得上的話，問題在 llama-server 路徑（前 40 名截斷或量化）。還是對不上，問題在環境 |

### 階段 3　單題延遲（這一階段最重要）

一次只跑一題，量真正的等待時間：

```bash
python -m taguri.run --config N1 --dataset musique --split test --limit 20 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --out results/gb10/latency-musique

python -m taguri.run --config N1 --dataset multihop-rag --split sample300 --limit 20 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --out results/gb10/latency-mhr
```

- **不要給 `--cache-dir`**，否則第二次跑會全部命中快取、量到的是 0 秒。
- test 的題目沒有在 GB10 上跑過，所以不會有快取。
- 另外用 `--workers 4` 各跑一次，看多人同時查詢時每題的時間變成多少。
- 有 SGLang 的話兩條路徑都量。

要記錄的數字（都在最後一行和 `summary.json`）：每題秒數的中位數和第 90 百分位，還有最大值，另外記每題的判斷次數與輸入 token。

**判定（單題中位數，段落約 400 字元的 MuSiQue）**

| 單題中位數 | 判定 |
|---|---|
| ≤ 10 秒 | **可以互動使用** |
| 10 到 30 秒 | **只適合非即時**（背景查詢、批次整理）。互動使用要降配，見第 6 節 |
| > 30 秒 | **照現在的設定不能用**。做第 6 節的降配實驗，回報「延遲對分數」的取捨 |

MultiHop-RAG（段落約 1,000 字元）的數字另外報告。雲端上它每題的 token 是 MuSiQue 的 2.6 倍，延遲預期也是兩到三倍。

**一定要回答的問題**：時間花在哪裡？`trace.jsonl.gz` 每題有 `wall_s`（總時間）和 `stats.judge_s`（等判官的時間），兩者的差就是詞彙檢索和程式本身。小語料上應該幾乎都是等判官。

### 階段 4　用自己的文件試用

```bash
python tools/ingest_files.py --src /secure/docs --out /secure/taguri-store --name mydocs

python -m taguri.query --db /secure/taguri-store/idx/mydocs.db --doc-level \
  --question "……" --lang zh --judge llama --base-url http://127.0.0.1:8080
```

- 語料是中文就給 `--lang zh`（prompt 用繁體中文，並套用中文的候選詞設定）。英文給 `--lang en`。語料混雜時用占多數的語言。
- `--doc-level`：同一份文件只列一次。
- `--judge none`：只用詞彙層，可以當對照。
- `--json`：輸出完整結果，包含每段的 log-odds 和判官選的橋接詞，也有判斷次數與秒數。

**怎麼評**：沒有標準答案的話，準備 20 到 30 個你知道答案在哪份文件的問題，每題記三件事：

1. 該找到的文件有沒有在前 5 名、前 10 名。
2. 同一題用 `--judge none` 的結果。
3. 花了幾秒。

**門檻（先寫好）**

| | 判定 |
|---|---|
| 前 10 名找到的比例，Taguri 比只用詞彙層高 10 個百分點以上 | 判官迴圈在這批文件上有用 |
| 差距在 ±10 個百分點以內 | 這批文件用詞彙層就夠了。這是合理的結果：問題和文件用詞一致、不需要多跳時，判官沒有東西可以加 |
| Taguri 比較差 | 把變差的題目和 `--json` 的輸出留下來（只留在 GB10 上），回報題型 |

要有標準答案才能算的分數（R@k）：把問題寫成 `questions.jsonl`（`gold_pids` 填文件的相對路徑）、`splits.json`，放在 `store/mydocs/`，再用 `python -m taguri.run --data-dir /secure/taguri-store --dataset mydocs --split <名稱> --doc-level --idx-dir /secure/taguri-store/idx ...`。

### 階段 4a　會議記錄

**現在知道的**：只有間接的數字。EnterpriseRAG 題組裡答案在會議逐字稿的 25 題，前 10 份文件找到標準文件的比例是 Taguri 78.4、只用詞彙層 72.2。那是英文、模擬的公司資料，題數也少，只能當方向。

**準備文件**

- 一場會議一個檔案。逐字稿很長，會被切成每段 2,000 字元，每段單獨看時上下文很少，所以**標題要帶足資訊**：檔案第一行寫成 `# <會議名稱>｜<日期>｜<專案>｜<與會者>`（`ingest_files.py` 會把第一個 `#` 標題當成每一段的標題）。
- 有整理過的會議摘要的話，摘要和逐字稿都放進去，各自一個檔案。
- 說話者標記保留（`王經理：……`）。

**問題要涵蓋四種**（每種 5 到 8 題，都要是你知道答案在哪場會議的）

| 類型 | 例子 | 預期 |
|---|---|---|
| 單一會議查得到 | 「10 月的產銷會議決定 A 產品的交期是哪一天？」 | 詞彙層就找得到，兩邊應該差不多 |
| 要接兩場會議 | 「負責 B 專案導入的人，後來回報的進度落後原因是什麼？」 | Taguri 應該比較好：先找到負責人，再用人名去找後續的會議 |
| 問法和記錄用詞不同 | 記錄寫「良率掉了」，問題問「品質異常」 | 詞彙層和 Taguri 都可能找不到。記下來，這是要不要加 EG2 的依據 |
| 要找齊多場 | 「把 C 專案歷次會議的決議都列出來」 | **預期 Taguri 沒有幫助**（雲端上這類題型沒有進步）。確認是不是如此 |

**執行**：同階段 4，中文會議記錄給 `--lang zh --doc-level`。每題記四件事：該找到的會議在第幾名，`--judge none` 時在第幾名，花了幾秒，以及 `--json` 輸出裡判官選了哪些橋接詞。

**門檻（先寫好）**

| | 判定 |
|---|---|
| 「要接兩場會議」那一類，Taguri 在前 10 名找到的題數比只用詞彙層多 2 題以上（每類 5 到 8 題） | 多跳的設計在會議記錄上有用 |
| 四類合計，Taguri 比詞彙層高 10 個百分點以上 | 整體有用 |
| 「要找齊多場」那一類兩邊一樣差 | 符合預期。記進 `TODO.md` 的 B3 |
| 判官選的橋接詞多半是人名、專案名、日期 | 正常。如果多半是斷詞碎片或口語詞（「那個」「然後」），回報例子：中文候選詞的抽法要再調 |

**要另外觀察的**：口語的指代（「上次說的那個案子」）會不會讓該找到的段落判不出來。看 `--json` 輸出裡那一段的 `log_odds`：段落有被撈到但分數很低，就是這種情況。

### 階段 4b　工廠記錄

**現在知道的**：沒有任何數字。雲端用的題組都不是製造業文件，下面的預期都是依架構推論的。

**準備文件**

- 先挑**描述性文字多**的記錄：RCA 報告、維修日誌、異常處理記錄、8D 報告。純欄位的記錄（站別和時間、代碼各一欄，沒有文字描述）先不要放，那種用 SQL 查比較準。
- 一筆記錄一個檔案（或一份報告一個檔案）。第一行寫成 `# <記錄類型>｜<機台或產線>｜<日期>｜<警報碼或料號>`。
- **編號照原樣寫**（`AOI-07`、`E-4012`、`FDR-220`）。含數字、三個字元以上的英數字串會被當成編號整段保留。同一個編號在不同記錄裡的寫法要一致（`E4012` 和 `E-4012` 會被當成兩個不同的編號）。寫法不一致的話先記下各種寫法的比例。
- 數值的判斷（溫度超過幾度、連續幾次超限）不是檢索能做的。記錄裡如果只有原始數值，問題就不要問「有沒有超限」。

**問題要涵蓋四種**（每種 5 到 8 題）

| 類型 | 例子 | 預期 |
|---|---|---|
| 靠編號就找得到 | 「E-4012 這個警報的處理步驟是什麼？」 | 詞彙層就找得到（編號完全相符）。兩邊應該差不多。**這一類要確認編號沒有被切壞** |
| 要接兩筆記錄 | 「AOI-07 上次出現 E-4012 時換的零件，供應商是哪一家？」 | Taguri 應該比較好 |
| 用現象描述、沒有編號 | 「貼片偏移而且只發生在換線後」 | 看有沒有找到對的 RCA。記錄和問題用詞不同時兩邊都可能找不到 |
| 很多筆長得很像 | 同一個警報碼有幾十筆記錄，問其中特定一次（「10 月第二週那次」） | **預期是弱點**：雲端上工單類是唯一比詞彙層差的來源（73.9 → 70.7），判官容易把相近但不對的記錄也判成證據 |

**執行**：同階段 4。另外對每個含編號的問題跑一次 `--judge none`，確認第一名就是含那個編號的記錄。不是的話，先查編號有沒有被當成編號（`python -c "from taguri.analyze import Analyzer; print(Analyzer().analyze('你的句子').keys('ids'))"`）。

**門檻（先寫好）**

| | 判定 |
|---|---|
| 「靠編號就找得到」那一類，只用詞彙層在前 3 名找到的比例 ≥ 90% | 編號的處理沒問題。沒到的話先修這個，其他類不用看 |
| 「要接兩筆記錄」那一類，Taguri 比只用詞彙層多找到 2 題以上 | 多跳的設計在工廠記錄上有用 |
| 「很多筆長得很像」那一類，Taguri 比只用詞彙層差 | 符合預期的弱點。把 `--json` 輸出裡被誤判成證據的記錄數量記下來 |
| 四類合計，Taguri 比詞彙層高 10 個百分點以上 | 整體有用 |

**兩類都試的話，先試會議記錄**：有間接的數字支持，問題的型態也比較吻合。

### 階段 5　選配

- **EG2**：只在「問法和文件用詞常常不同」或「中文問、英文文件」時值得試。企業文件的語意檢索上換到 +9.6 分，英文多跳題上沒有幫助。企業文件要追平上游的商用判官就得開（不開低 6.6 分，開了打平）。本機入口已經接好：先用 `python -m taguri.dense build --db <索引> --out <向量檔> --model <模型資料夾> --device cuda` 建向量，查詢時加 `--dense-vectors <向量檔> --eg2-model <模型資料夾>`，`taguri.run` 要把設定改成 `N1+EG2`。用法和驗過的範圍見 README 7.4 節與 [`results/b1-b4-b7.md`](../results/b1-b4-b7.md)。先確認階段 1 到 4 再做。
- **繁中**：`data/` 裡沒有中文題組（翻譯後的語料沒有進 git）。要量繁中請直接用真實的繁中文件走階段 4。

## 6. 延遲太長時可以調的旋鈕

複製一份 `results/thresholds.lock.json`，改副本，再用 `--lock <副本>` 執行。**每次只改一個**，在 MuSiQue 校準半（`--split calib`，150 題）上看分數掉多少，連同延遲一起報告。

| 旋鈕（lock 副本裡的鍵） | 現值 | 試 | 已知的事 |
|---|---:|---|---|
| `rejudge_each`（每輪重判幾段） | 20 | 10 | 10 沒量過。雲端上 20 和 30 沒有差別。完全不重判會掉 10 分，所以不要設 0 |
| `chunk`（判證據的批次大小） | 5 | 10 | 依序送出的批次數減半，是對單題延遲最直接的旋鈕。雲端校準半上，批次 5 比 10 高約 1 到 2 分，比完全不分批高約 1 分 |
| `rounds`（擴展輪數，副本裡加這個鍵） | 2 | 1 | 沒量過。判斷次數大約少三成。多跳題預期會掉分，單跳的查詢影響應該小 |
| `K`（每輪召回幾段，副本裡加這個鍵） | 50 | 30 | 沒量過。判斷次數大約少三成 |

其他方向（還沒做，需要寫程式）：

- 用小模型（E4B）先判、低信心才送 26B 的級聯。jevlike v3 在產線題上省了三分之二的 26B 負載。
- 換詞彙檢索引擎或加查詢最佳化，處理十萬段以上的語料。

## 7. 踩過的坑

- **生成和讀機率的請求不要送到同一個 SGLang 伺服器的同一批**：雲端的 SGLang 版本會讓排程器當掉（`'list' object has no attribute 'tolist'`）。要同時做生成和判斷時分兩階段或兩個伺服器。llama-server 有沒有同樣的問題沒測過。
- **長段落會超過 context**：已有證據 8 段、每段 2,000 字元時到過 17,776 token。現在已有證據會自動截到 10,000 token 以內。llama-server 路徑沒有 tokenizer，用「2 個字元算 1 個 token」估計，中文密度高的文件如果還是超長，把 `taguri/decide.py` 的 `EV_TOKEN_BUDGET` 調小。
- **快取會讓延遲看起來是 0**：量延遲時不要給 `--cache-dir`。
- **EG2 和判官搶同一張卡**：雲端 L40S 上要把 SGLang 的記憶體比例從 0.8 降到 0.72。GB10 記憶體大，應該沒有這個問題，但要確認。
- **llama-server 的併發**：jevlike 在 L4 上量到 llama-server 多個 slot 並行不增加吞吐量。GB10 上 `--llama-parallel` 開大有沒有用要實測。沒有用就設 1，結果一樣。
- **同分**：log-odds 會有同分（伺服器回傳的精度有限，llama-server 路徑還有截斷）。程式用 BM25 分數和段落編號當次要排序鍵，結果是確定的。

## 8. 回報格式

結果放 `results/gb10/`，寫一份 `results/gb10/REPORT.md`：

```
環境：GB10；llama.cpp build ___；模型檔 ___（sha256 ___）；Python ___；SQLite ___
階段 0：N0 MuSiQue dev R@5 ___（應為 47.72）／2Wiki ___（應為 67.25）
階段 1：10 題 R@5 ___；option mass 中位數 ___；失敗題數 ___
階段 2：MuSiQue dev R@5 ___（雲端 80.17）；GB10 − 雲端 ___（信賴區間 ___）；判定 ___
階段 3：單題延遲 MuSiQue 中位數 ___ 秒／第 90 百分位 ___ 秒；MultiHop-RAG ___／___
        四題並行時每題 ___ 秒；等判官占 ___%；每題判斷 ___ 次、輸入 ___ token；判定 ___
階段 4：___ 份文件、___ 段、索引 ___ MB、建置 ___ 秒
        ___ 個問題；前 10 名找到：Taguri ___ %、只用詞彙層 ___ %；單題中位數 ___ 秒；判定 ___
階段 4a（會議記錄）：___ 場會議、___ 段；語言 ___
        單一會議 ___／___ 題、接兩場 ___／___ 題、用詞不同 ___／___ 題、找齊多場 ___／___ 題（Taguri／只用詞彙層，前 10 名找到的題數）
        橋接詞的型態：___；單題中位數 ___ 秒；判定 ___
階段 4b（工廠記錄）：記錄類型 ___、___ 筆、___ 段；語言 ___；編號寫法一致嗎 ___
        靠編號 ___／___ 題（詞彙層前 3 名 ___ %）、接兩筆 ___／___ 題、現象描述 ___／___ 題、相似記錄 ___／___ 題
        單題中位數 ___ 秒；判定 ___
降配實驗（如果做了）：旋鈕 ___ → 延遲 ___、校準半 R@5 ___（原 80.56）
結論：可以互動使用／只適合非即時／不能用；下一步建議 ___
```
