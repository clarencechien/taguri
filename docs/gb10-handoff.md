# Taguri 在 GB10 上的接手文件

版本：2026-11-11，對應 `main`。給在 GB10 上接手的人（或 Claude Code）。

這份文件從頭照做就可以，不需要先讀別的。每一階段的寫法都一樣，依序是要做什麼、指令、應該看到什麼、門檻、沒過怎麼辦。門檻都是先寫好的，跑完照門檻填結論，沒過的照實寫。

## 一頁總覽

| 階段 | 做什麼 | 要不要判官 | 過關的條件 |
|---|---|---|---|
| 準備 | 在有網路的機器上備齊程式、套件、模型，帶進 GB10 | | 檔案的 sha256 對得上 |
| 0 | 確認環境，跑關鍵字那一層 | 不用 | 分數和下表一模一樣 |
| 1 | 判官冒煙測試，10 題 | 要 | 沒有失敗的題目，機率讀得到 |
| 2 | **單獨一題要等多久**，20 題 | 要 | 中位數 ≤ 10 秒可互動 |
| 3 | 品質重現，300 題 | 要 | 和雲端的差，信賴區間下界 > −3 |
| 4 | 用自己的文件試用（4a 會議記錄，4b 工廠記錄） | 要 | 比只用關鍵字多找到 10 個百分點 |
| 5 | 加上 EG2（向量補撈） | 要 | 接得起來，用詞不同的問題有改善 |
| 6 | 大語料（51 萬份文件），選做 | 要 | 每題的檢索時間 ≤ 10 秒 |

階段 0 到 3 用 repo 裡附的公開題組，不需要任何自己的資料。**最重要的是階段 2**，它決定這套東西能不能互動使用。

## 1. Taguri 是什麼

Taguri 是一個找資料的元件。問題的答案散在好幾份文件時，要先讀到第一份才知道第二份該找什麼，它處理的是這種問題。

每一題的流程：

1. 用關鍵字從 SQLite 索引取出 50 段。
2. 判官（Gemma 4 26B）一段一段判「這段對回答問題有沒有用」。只讀它回答的第一個字的機率，不讓它寫字。
3. 程式從有用的段落裡列出幾個詞，判官選下一步該查哪一個。
4. 把選到的詞加進查詢再取一次，回到第 2 步。這樣走兩輪。
5. 依判官的把握程度排序，交出前 10 段。

它不呼叫外部服務，也不寫答案。它交出來的是「最可能有答案的 10 段」。

三個入口：

| 指令 | 用途 |
|---|---|
| `python -m taguri.run` | 跑一整批題目並計分（要有標準答案） |
| `python -m taguri.query` | 問一個問題，印出找到的段落（不用標準答案） |
| `python tools/ingest_files.py` | 把一個資料夾的文字檔做成語料和索引 |

## 2. 規則

1. **真實資料不離開 GB10。** 不上雲端，不進 git。報告只放彙總數字和你自己寫的評語，不放文件原文。
2. 不改 `taguri/decide.py` 裡的模板（`GEMMA4_TEMPLATE_NOTHINK`）和已鎖定的題目寫法。不用真實資料調 `results/thresholds.lock.json`。要試省一點的設定請用副本（第 7 節）。
3. 判斷用的伺服器**不開 MTP 草稿頭**，也不和開了 MTP 的生成伺服器共用。開了之後第一個 token 的機率會不穩定。
4. 每個階段結束 commit（分支自己開，例如 `gb10/<日期>`），結果放 `results/gb10/`。
5. 不要去讀上游系統（Zleap 的 SAG／SAG2）的程式、套件或論文。這個實作是 clean-room 做的，規則在 [`clean-room-log.md`](clean-room-log.md)。

## 3. 現在知道什麼、不知道什麼

雲端（Modal L40S、SGLang、FP8 權重）上量過的：

| | 數字 |
|---|---|
| 英文多跳題（MuSiQue） | dev 300 題 R@5 80.17，沒碰過的 test 700 題 80.20，和上游做法配商用判官打平 |
| 51 萬份企業文件（EnterpriseRAG） | 前 10 份找到的比例 74.50。加 EG2 後 80.71，和上游做法配商用判官的 81.10 打平 |
| 每題的工作量 | 見下表 |
| 154 萬段的關鍵字檢索 | 單獨一題約 4 秒（已經最佳化過） |
| 省一點的設定 | 判斷次數少 11%、token 少 17%，分數沒有可量測的差別（`results/thresholds.lite.json`） |

GB10 上才能回答的：

| | 狀態 |
|---|---|
| llama-server 這條路 | **沒接過真的 llama-server。** 程式只用模擬伺服器驗過流程。階段 1 |
| 單獨一題要等多久 | **沒量過。** 雲端都是 16 題一起跑。階段 2 |
| 換成量化權重（GGUF）後品質有沒有變 | **沒量過。** 階段 3 |
| 自己的文件 | **沒量過。** 會議記錄只有間接的數字，工廠記錄完全沒有。階段 4 |
| 繁體中文 | 只有機器翻譯題組的數字，比英文低約 13 分。真實繁中文件沒量過 |
| 本機的 EG2 配真的判官 | **沒跑過。** 只用替身判官跑通。階段 5 |

雲端量到的工作量，估延遲用：

| 段落長度 | 每題判斷次數（中位數／第 90 百分位） | 每題輸入 token |
|---|---:|---:|
| 約 400 字元（MuSiQue） | 143／170 | 9.2 萬 |
| 約 1,000 字元（MultiHop-RAG） | 139／158 | 23.5 萬 |
| 約 2,000 字元（EnterpriseRAG） | 168／195 | 56 萬 |

每題的判斷分成 30 多個批次**依序**送出（每 5 段一批，批與批之間要更新已有的證據）。所以單題延遲不會因為伺服器能並行就等比例變快。

## 4. 事前準備

### 4.1 在有網路的機器上

最好用 arm64、Python 版本和 GB10 相同的機器，這樣下載到的套件才裝得上。Python 要 3.10 以上。

```bash
mkdir -p taguri-bundle/wheels taguri-bundle/models && cd taguri-bundle

# 程式
git clone https://github.com/clarencechien/taguri.git
git clone https://github.com/clarencechien/jevlike.git      # 查模板和 llama-server 的檢查腳本用

# 一定要的套件
pip download -d wheels numpy "opencc-python-reimplemented==0.1.7" "snowballstemmer==3.1.1" requests setuptools wheel
pip wheel "jieba==0.42.1" -w wheels      # jieba 只有原始碼包，在這裡先做成 wheel
pip download --no-deps --no-binary :all: "jieba==0.42.1" -d wheels    # 原始碼包也帶著，wheel 裝不起來時用

# EG2 要用的套件（階段 5、6）
pip download -d wheels torch torchvision pillow "sentence-transformers>=6.1.0" "transformers>=5.19.0"

# 模型
huggingface-cli download unsloth/gemma-4-26B-A4B-it-GGUF gemma-4-26B-A4B-it-UD-Q4_K_M.gguf --local-dir models/gemma
huggingface-cli download google/embeddinggemma-2 --revision 914f7f89142e33e77833254d9c9b90c3cef7303b --local-dir models/embeddinggemma-2

sha256sum models/gemma/*.gguf models/embeddinggemma-2/model.safetensors > SHA256SUMS
```

| 東西 | 大小 | 說明 |
|---|---|---|
| `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf` | 17 GB | 判官。有空間的話再帶 `Q8_0`（27 GB），階段 3 有落差時用來分辨是不是量化造成的 |
| `embeddinggemma-2/` 資料夾 | 1.5 GB | EG2。`model.safetensors` 是 1,488,915,288 位元組，sha256 開頭 `197a3296`，結尾 `d5553d79` |
| llama.cpp | | 要 **b11371 以上**、arm64 加 CUDA（sm_121）的 build。細節見 jevlike 的 `docs/handoff-gb10.md` 第 1 節 |
| `torch` | | EG2 才需要。GB10 上已經有能用 GPU 的 torch 就用那一版（見 4.2）。上面下載的那一份是備用的，可能是 CPU 版，查詢夠用，只有建向量會慢 |

- EG2 不需要金鑰。英文多跳題用不到它，企業文件和會議記錄這類語料要用。
- `tokenizers` 套件只有走 SGLang 那條路才需要。
- 階段 6 要另外帶三個檔，清單在那一節。

### 4.2 帶進 GB10 之後

下面假設整包放在 `/opt/taguri-bundle`。

```bash
cd /opt/taguri-bundle && sha256sum -c SHA256SUMS

cd taguri
python -m venv .venv && . .venv/bin/activate
pip install --no-index --find-links ../wheels numpy jieba opencc-python-reimplemented snowballstemmer requests
pip install --no-index --find-links ../wheels -e .
mkdir -p results/gb10
```

- jieba 裝不起來的話，它是純 Python 的，可以直接解開 `wheels/jieba-0.42.1.tar.gz`，把裡面的 `jieba/` 資料夾複製到 site-packages。雲端的環境就遇過 wheel 做不出來，是這樣解的。
- GB10 上已經有能用 GPU 的 torch 的話，建 venv 時改用 `python -m venv --system-site-packages .venv`，這樣階段 5 就會沿用那一份。這一點沒有在 GB10 上驗過。
- EG2 的套件等到階段 5 再裝。

之後的指令都在 `/opt/taguri-bundle/taguri` 底下、啟用 `.venv` 之後執行。

## 5. 啟動判官

階段 1 之後都要。開一個終端機讓它一直跑著。

**llama-server（GB10 的預設）**

```bash
llama-server -m /opt/taguri-bundle/models/gemma/gemma-4-26B-A4B-it-UD-Q4_K_M.gguf \
  --jinja --reasoning-budget 0 --swa-full -np 4 -c 65536 --host 127.0.0.1 --port 8080
```

- 每個 slot 的 context 是 `-c ÷ -np`，要 **16384 以上**（上面是 65536 ÷ 4）。
- `--swa-full` 一定要開。不開的話同一輪的候選沒辦法共用「問題加已有證據」這段開頭，時間會多好幾倍。
- `--jinja --reasoning-budget 0` 一定要帶。
- Taguri 這邊用 `--judge llama --base-url http://127.0.0.1:8080`，`--llama-parallel` 設成和 `-np` 一樣。

**SGLang（選配，重現性最好）**

雲端實驗用的是這一條。權重是 `RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic` @ `ed35d7abe5d9`。

```bash
python -m sglang.launch_server --model-path <FP8 權重目錄> --context-length 16384 \
  --max-running-requests 64 --mem-fraction-static 0.8 --host 127.0.0.1 --port 30000
```

Taguri 這邊用 `--judge sglang --base-url http://127.0.0.1:30000 --tokenizer <FP8 權重目錄>/tokenizer.json`。

兩條路的差別：

| | llama-server | SGLang |
|---|---|---|
| `<bos>` | 伺服器自己加。Taguri 送出時會把模板開頭的 `<bos>` 拿掉 | Taguri 送 token id，自己帶 `<bos>` |
| 讀到的機率 | 只有前 40 名的 token。選項字母不在裡面時用「比第 40 名再低 1」代替 | 指定 token，精確 |
| 對分數的影響 | 很負的分數會被截平。明確被否決的段落之間改由關鍵字分數決定先後，不影響前幾名 | 無 |
| 一次送很多題 | 不支援整批，用 `-np` 個連線並行 | 支援整批 |

## 6. 階段

### 階段 0　環境（只用 CPU，約 10 分鐘）

```bash
python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute('create virtual table t using fts5(a)'); print(sqlite3.sqlite_version, 'fts5 ok')"
python -c "import jieba, opencc, snowballstemmer, numpy; print('packages ok')"
python -m taguri.run --config N0 --dataset musique --split dev --idx-dir /tmp/taguri-idx
python -m taguri.run --config N0 --dataset 2wikimultihopqa --split dev --idx-dir /tmp/taguri-idx
```

第一次跑會自動建索引（MuSiQue 1.2 萬段，約 5 秒，18 MB）。每次執行的最後一行是一筆 JSON，裡面有 `R@5`、`R@10`、`AE@10`。

**門檻**：關鍵字這一層是確定性的，數字要一模一樣。

| | R@5 | R@10 | AE@10 |
|---|---:|---:|---:|
| MuSiQue dev 300 題 | 47.72 | 53.47 | 15.67 |
| 2Wiki dev 100 題 | 67.25 | | 36.00 |

- 完全相同就繼續。
- 差在 0.5 以內：記下 SQLite 的版本，繼續。不同版本的 SQLite 可能有細微差異（3.40.1 和 3.53.1 驗過是相同的）。
- 差超過 0.5 就**停**。先查 jieba 和 OpenCC 的版本。

### 階段 1　判官冒煙測試（約 10 分鐘）

先確認判官已經照第 5 節啟動。

```bash
python -m taguri.run --config N1 --dataset musique --split dev --limit 10 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --out results/gb10/smoke

python - <<'EOF'
import gzip, json, statistics as st
t = [json.loads(l) for l in gzip.open("results/gb10/smoke/trace.jsonl.gz", "rt")]
print("每題最低 option mass 的中位數:", st.median(x["stats"]["min_mass"] for x in t))
print("每題秒數:", sorted(round(x["wall_s"], 1) for x in t))
EOF
```

**門檻**

1. 最後一行的 `failed_questions` 是 0，沒有 context 超長的錯誤。
2. 每題最低 option mass 的中位數 ≥ 0.9。option mass 是選項字母的機率加起來有多少，接近 1 表示模型確實在回答選擇題。
   - 選橋接詞那一題（四選一）本來就有一成多的判斷低於 0.5，所以偶爾有一題很低是正常的。要看的是「是不是幾乎每一題都很低」。
3. 這 10 題的 R@5 ≥ 60。雲端上同樣 10 題是 78.3。10 題的變動很大，這裡只是擋掉完全壞掉的情況。

**沒過怎麼辦**

- option mass 普遍很低：模板或 `<bos>` 有問題。先用 jevlike 的 `bench/run_local.py --which smoke` 確認伺服器本身沒問題，再看啟動時有沒有帶 `--jinja --reasoning-budget 0`。**修兩次還是不行就停**，回報樣本。
- R@5 很低但 option mass 正常：看 trace 裡 `judged` 的 `lo` 是不是全部擠在同一個值。是的話代表前 40 名截斷太嚴重，改用 SGLang 那條路重測。
- 這是 llama-server 這條路第一次接真的伺服器。程式有問題的話，改 `taguri/decide.py` 的 `LlamaBackend`，不要動模板。

### 階段 2　單獨一題要等多久（這一階段最重要）

一次只跑一題，量真正的等待時間。用沒跑過的 test 題目，而且**不要給 `--cache-dir`**，否則量到的是快取。

```bash
# 段落約 400 字元
python -m taguri.run --config N1 --dataset musique --split test --limit 20 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --out results/gb10/latency-musique

# 段落約 1,000 字元
python -m taguri.run --config N1 --dataset multihop-rag --split sample300 --limit 20 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --out results/gb10/latency-mhr

# 省一點的設定（判斷次數少 11%）
python -m taguri.run --config N1 --dataset musique --split test --limit 20 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --lock results/thresholds.lite.json \
  --idx-dir /tmp/taguri-idx --out results/gb10/latency-musique-lite

# 四個人同時問
python -m taguri.run --config N1 --dataset musique --split test --limit 20 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 4 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --out results/gb10/latency-musique-w4
```

每次執行的最後一行有 `per_question_s`（中位數、第 90 百分位、最大值）。時間花在哪裡用這段看，把資料夾名稱換掉就可以：

```bash
python - <<'EOF'
import gzip, json, statistics as st
t = [json.loads(l) for l in gzip.open("results/gb10/latency-musique/trace.jsonl.gz", "rt")]
w = [x["wall_s"] for x in t]; j = [x["stats"]["judge_s"] for x in t]
print("每題秒數 中位數 %.1f  第 90 百分位 %.1f" % (st.median(w), sorted(w)[int(0.9 * (len(w) - 1))]))
print("其中等判官 %.1f 秒（%.0f%%）" % (st.median(j), 100 * sum(j) / sum(w)))
print("每題判斷次數 %d  輸入 token %d" % (st.median(x["stats"]["calls"] for x in t), st.median(x["stats"]["tokens"] for x in t)))
EOF
```

`wall_s` 是一題的總時間，`judge_s` 是等判官的時間，差額是關鍵字檢索和程式本身。這種小語料上應該幾乎都是等判官。

**判定（MuSiQue 的單題中位數）**

| 單題中位數 | 判定 | 接下來 |
|---|---|---|
| ≤ 10 秒 | **可以互動使用** | 繼續階段 3 |
| 10 到 30 秒 | **只適合非即時**（背景查詢、批次整理） | 繼續階段 3。另外做第 7 節的降配，看能壓到多少 |
| > 30 秒 | **照現在的設定不能用** | 先做第 7 節的降配，回報「延遲對分數」的取捨。階段 3 改跑 150 題 |

MultiHop-RAG 的數字另外記。雲端上它每題的 token 是 MuSiQue 的 2.6 倍，延遲預期也是兩到三倍。有 SGLang 的話兩條路都量。

### 階段 3　品質重現（300 題）

需要的時間最多是「300 × 階段 2 量到的單題秒數」，四題並行有效的話會短一些。這裡給了 `--cache-dir`，中斷之後重跑不會從頭算。

```bash
python -m taguri.run --config N1 --dataset musique --split dev \
  --judge llama --base-url http://127.0.0.1:8080 --workers 4 --llama-parallel 4 \
  --idx-dir /tmp/taguri-idx --cache-dir results/gb10/cache --out results/gb10/musique-dev-N1

python -m evalkit score --dataset musique --split dev \
  --run results/gb10/musique-dev-N1/run.jsonl --out results/gb10/musique-dev-N1.scores.jsonl
python -m evalkit compare --dataset musique --split dev \
  --a results/gb10/musique-dev-N1.scores.jsonl --b reference/musique/taguri_n1.jsonl --metrics R@5 R@10 AE@10
```

`reference/musique/taguri_n1.jsonl` 是雲端跑出來的逐題分數。`compare` 會印出 GB10 減雲端的差和 95% 信賴區間。

時間不夠的話改跑校準半的 150 題（三個指令的 `--split dev` 都換成 `--split calib`，雲端是 R@5 80.56）。

**門檻（MuSiQue dev 300 題的 R@5，雲端是 80.17）**

| GB10 的結果 | 判定 |
|---|---|
| 和雲端的差，信賴區間下界 > −3 | **重現成功**：量化與伺服器沒有明顯影響 |
| 點估計在 −3 到 −6 之間 | **可用但有落差**：註明量化版本。有 Q8 的話用 Q8 再跑一次，看落差是不是量化造成的 |
| 點估計 < −6 | **停**：先用 SGLang 加 FP8 權重重跑。那樣就對得上的話，問題在 llama-server 這條路（前 40 名截斷或量化）。還是對不上，問題在環境 |

### 階段 4　用自己的文件試用

**把文件做成索引**

```bash
python tools/ingest_files.py --src /secure/docs --out /secure/taguri-store --name mydocs
```

- 會遞迴讀 `.txt`、`.md`、`.log`、`.csv`、`.json`、`.html`、`.rst`，一個檔案算一份文件。
- 超過 2,000 字元的文件在段落邊界切開。標題取第一個 `#` 標題，沒有就用檔名。
- 產出 `/secure/taguri-store/mydocs/corpus.jsonl` 和 `/secure/taguri-store/idx/mydocs.db`。
- **PDF、Word、Excel 要先自己轉成文字**，這個工具不解析它們。
- 文件有新增或修改時，只能整個重建。

**問一個問題**

```bash
python -m taguri.query --db /secure/taguri-store/idx/mydocs.db --doc-level \
  --question "……" --lang zh --judge llama --base-url http://127.0.0.1:8080

python -m taguri.query --db /secure/taguri-store/idx/mydocs.db --doc-level \
  --question "……" --lang zh --judge none          # 只用關鍵字，當對照
```

| 參數 | 說明 |
|---|---|
| `--lang zh` | 語料是中文時給。prompt 會用繁體中文，並套用中文的候選詞設定。英文給 `en`，混雜時用占多數的語言 |
| `--doc-level` | 同一份文件只列一次 |
| `--judge none` | 只用關鍵字那一層 |
| `--json` | 輸出完整結果，包含每段的分數（`log_odds`）、判官選的橋接詞、判斷次數與秒數 |
| `--top 10`、`--chars 300` | 列幾筆，每筆印幾個字 |

**怎麼評**：準備 20 到 30 個你知道答案在哪份文件的問題，每題記三件事。

1. 該找到的文件有沒有在前 5 名、前 10 名。
2. 同一題用 `--judge none` 的結果。
3. 花了幾秒。

**門檻（先寫好）**

| | 判定 |
|---|---|
| 前 10 名找到的比例，Taguri 比只用關鍵字高 10 個百分點以上 | 判官迴圈在這批文件上有用 |
| 差距在 ±10 個百分點以內 | 這批文件用關鍵字就夠了。這是合理的結果：問題和文件用詞一致、不需要接兩份文件時，判官沒有東西可以加 |
| Taguri 比較差 | 把變差的題目和 `--json` 的輸出留下來（只留在 GB10 上），回報題型 |

**想要算分數的話**：把問題寫成 `/secure/taguri-store/mydocs/questions.jsonl`，每行 `{"qid": "q1", "question": "……", "gold_pids": ["子資料夾/檔名.md"], "type": "x"}`，`gold_pids` 填文件相對於 `--src` 的路徑。再寫一個 `splits.json`，內容是 `{"all": ["q1", "q2"]}`。然後：

```bash
python -m taguri.run --config N1 --data-dir /secure/taguri-store --dataset mydocs --split all --doc-level --lang zh \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --idx-dir /secure/taguri-store/idx --out results/gb10/mydocs-N1
```

把 `--config N1` 換成 `N0`、拿掉 `--judge` 那一行，就是只用關鍵字的對照組。`results/gb10/` 裡只有文件路徑和分數，沒有文件內容。但 trace 裡有查詢的文字，**含真實資料的 trace 不要 commit**。

### 階段 4a　會議記錄

**現在知道的**：只有間接的數字。EnterpriseRAG 題組裡答案在會議逐字稿的 25 題，前 10 份找到的比例是 Taguri 78.4、只用關鍵字 72.2。那是英文、模擬的公司資料，題數也少，只能當方向。

**準備文件**

- 一場會議一個檔案。逐字稿很長，會被切成每段 2,000 字元，每段單獨看時上下文很少，所以**標題要帶足資訊**。檔案第一行寫成 `# <會議名稱>｜<日期>｜<專案>｜<與會者>`，這一行會變成每一段的標題。
- 有整理過的會議摘要的話，摘要和逐字稿都放進去，各自一個檔案。
- 說話者標記保留（`王經理：……`）。

**問題要涵蓋四種**（每種 5 到 8 題，都要是你知道答案在哪場會議的）

| 類型 | 例子 | 預期 |
|---|---|---|
| 單一會議查得到 | 「10 月的產銷會議決定 A 產品的交期是哪一天？」 | 關鍵字就找得到，兩邊應該差不多 |
| 要接兩場會議 | 「負責 B 專案導入的人，後來回報的進度落後原因是什麼？」 | Taguri 應該比較好：先找到負責人，再用人名去找後續的會議 |
| 問法和記錄用詞不同 | 記錄寫「良率掉了」，問題問「品質異常」 | 兩邊都可能找不到。記下來，階段 5 加 EG2 之後再問一次 |
| 要找齊多場 | 「把 C 專案歷次會議的決議都列出來」 | **預期 Taguri 沒有幫助**。雲端上這類題型沒有進步，加 EG2 也沒有。確認是不是如此 |

**執行**：同階段 4，給 `--lang zh --doc-level`。每題記四件事：該找到的會議在第幾名，`--judge none` 時在第幾名，花了幾秒，以及 `--json` 輸出裡判官選了哪些橋接詞。

**門檻（先寫好）**

| | 判定 |
|---|---|
| 「要接兩場會議」那一類，Taguri 在前 10 名找到的題數比只用關鍵字多 2 題以上 | 多跳的設計在會議記錄上有用 |
| 四類合計，Taguri 比只用關鍵字高 10 個百分點以上 | 整體有用 |
| 「要找齊多場」那一類兩邊一樣差 | 符合預期。記進 `TODO.md` 的 B3 |
| 判官選的橋接詞多半是人名、專案名、日期 | 正常。如果多半是斷詞碎片或口語詞（「那個」「然後」），回報例子，中文候選詞的抽法要再調 |

**另外觀察**：口語的指代（「上次說的那個案子」）會不會讓該找到的段落判不出來。看 `--json` 輸出裡那一段的 `log_odds`，段落有被撈到但分數很低，就是這種情況。

### 階段 4b　工廠記錄

**現在知道的**：沒有任何數字。雲端用的題組都不是製造業文件，下面的預期都是依架構推論的。

**準備文件**

- 先挑**描述性文字多**的記錄：RCA 報告、維修日誌、異常處理記錄、8D 報告。純欄位的記錄（站別、時間、代碼各一欄，沒有文字描述）先不要放，那種用 SQL 查比較準。
- 一筆記錄一個檔案。第一行寫成 `# <記錄類型>｜<機台或產線>｜<日期>｜<警報碼或料號>`。
- **編號照原樣寫**（`AOI-07`、`E-4012`、`FDR-220`）。含數字、三個字元以上的英數字串會被當成編號整段保留。同一個編號在不同記錄裡的寫法要一致，`E4012` 和 `E-4012` 會被當成兩個不同的編號。寫法不一致的話先記下各種寫法的比例。
- 數值的判斷（溫度超過幾度、連續幾次超限）不是檢索能做的。記錄裡如果只有原始數值，問題就不要問「有沒有超限」。

確認編號有沒有被認出來：

```bash
python -c "from taguri.analyze import Analyzer; print(Analyzer().analyze('AOI-07 上次出現 E-4012 時換的零件').keys('ids'))"
# 應該印出 ['aoi-07', 'e-4012']
```

**問題要涵蓋四種**（每種 5 到 8 題）

| 類型 | 例子 | 預期 |
|---|---|---|
| 靠編號就找得到 | 「E-4012 這個警報的處理步驟是什麼？」 | 關鍵字就找得到。兩邊應該差不多。**這一類要確認編號沒有被切壞** |
| 要接兩筆記錄 | 「AOI-07 上次出現 E-4012 時換的零件，供應商是哪一家？」 | Taguri 應該比較好 |
| 用現象描述、沒有編號 | 「貼片偏移而且只發生在換線後」 | 看有沒有找到對的 RCA。用詞不同時兩邊都可能找不到，階段 5 再試 |
| 很多筆長得很像 | 同一個警報碼有幾十筆記錄，問其中特定一次（「10 月第二週那次」） | **預期是弱點**。雲端上工單類是唯一比關鍵字差的來源（73.9 對 70.7），判官容易把相近但不對的記錄也判成證據 |

**執行**：同階段 4。另外對每個含編號的問題跑一次 `--judge none`，確認第一名就是含那個編號的記錄。

**門檻（先寫好）**

| | 判定 |
|---|---|
| 「靠編號就找得到」那一類，只用關鍵字在前 3 名找到的比例 ≥ 90% | 編號的處理沒問題。沒到的話先修這個，其他類不用看 |
| 「要接兩筆記錄」那一類，Taguri 比只用關鍵字多找到 2 題以上 | 多跳的設計在工廠記錄上有用 |
| 「很多筆長得很像」那一類，Taguri 比只用關鍵字差 | 符合預期的弱點。把 `--json` 輸出裡被誤判成證據的記錄數量記下來 |
| 四類合計，Taguri 比只用關鍵字高 10 個百分點以上 | 整體有用 |

**兩類都試的話，先試會議記錄**。它有間接的數字支持，問題的型態也比較吻合。

### 階段 5　加上 EG2

EG2 是一個小的向量模型，只負責多撈一些候選進來，誰是證據仍然由判官決定。沒有向量資料庫，向量就是一個 `.npy` 檔。

| 語料 | 要不要加 |
|---|---|
| 英文多跳題（維基百科那類） | 不用。多 0.8 分，在雜訊範圍內 |
| 企業文件、會議記錄，問法和文件用詞常常不同 | **要**。雲端上不加時比商用判官低 6.6 分，加了打平 |
| 中文問、英文文件 | **一定要**。不加幾乎找不到（R@5 16.6 對 65.4） |
| 要把同一件事的文件找齊 | 沒有幫助 |

**裝套件**

```bash
pip install --no-index --find-links ../wheels torchvision pillow sentence-transformers transformers   # 會連帶裝 torch，已經有的話沿用
python -c "import torch, torchvision, sentence_transformers; print(torch.__version__, torch.cuda.is_available())"
```

少了 `torchvision` 模型會載入失敗，雲端和本機都踩過。

**5.1 先用公開題組確認接得起來**

```bash
# 建向量。一段一列，1.2 萬段在 L40S 上 21 秒。沒有 GPU 版的 torch 就把 cuda 換成 cpu，約 15 分鐘
python -m taguri.dense build --db /tmp/taguri-idx/musique.db --out /tmp/taguri-idx/musique.eg2.npy \
  --model /opt/taguri-bundle/models/embeddinggemma-2 --device cuda

python -m taguri.run --config N1+EG2 --dataset musique --split dev --limit 10 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --dense-vectors /tmp/taguri-idx/musique.eg2.npy --eg2-model /opt/taguri-bundle/models/embeddinggemma-2 --eg2-device cpu \
  --idx-dir /tmp/taguri-idx --out results/gb10/eg2-smoke

python - <<'EOF'
import gzip, json
t = [json.loads(l) for l in gzip.open("results/gb10/eg2-smoke/trace.jsonl.gz", "rt")]
print("每題只靠 EG2 進來的段落數:", [len(x.get("dense_only", [])) for x in t])
EOF
```

- `--eg2-device cpu`：查詢的向量在 CPU 上算（x86 4 核上每次約 0.07 秒），GPU 留給判官。
- 向量檔的列數和索引的段落數不一樣時會直接報錯。

**門檻**

1. `failed_questions` 是 0。
2. 每題只靠 EG2 進來的段落數大多在 10 到 30 之間。全部是 0 表示 EG2 沒有接上。
3. 每題的秒數比階段 1 多不到三成。雲端上加 EG2 每題多約 17% 的判斷次數。

要完整對數字的話，把 `--limit 10` 拿掉、加上 `--cache-dir results/gb10/cache`，跑完用 `evalkit score` 和 `evalkit compare` 對 `reference/musique/taguri_n1_eg2.jsonl`（雲端 R@5 80.94）。門檻和階段 3 相同。這一步不是必要的。

**5.2 用在自己的文件上**

```bash
python -m taguri.dense build --db /secure/taguri-store/idx/mydocs.db --out /secure/taguri-store/idx/mydocs.eg2.npy \
  --model /opt/taguri-bundle/models/embeddinggemma-2 --device cuda

python -m taguri.query --db /secure/taguri-store/idx/mydocs.db --doc-level \
  --question "……" --lang zh --judge llama --base-url http://127.0.0.1:8080 \
  --dense-vectors /secure/taguri-store/idx/mydocs.eg2.npy --eg2-model /opt/taguri-bundle/models/embeddinggemma-2
```

`taguri.query` 給了 `--dense-vectors` 就會開 EG2。`taguri.run` 要另外把 `--config` 改成 `N1+EG2`。文件有增修、索引重建之後，向量也要重建。

把階段 4a、4b 裡「問法和記錄用詞不同」「用現象描述」那兩類的問題重問一次。

**門檻（先寫好）**

| | 判定 |
|---|---|
| 用詞不同的那一類，加 EG2 之後前 10 名多找到 2 題以上 | 這批文件值得開 EG2 |
| 沒有差別，而且每題多花的時間超過兩成 | 不用開 |
| 其他類變差 | 回報題型。雲端上「要找齊多份」的題目加 EG2 之後略差 |

### 階段 6　大語料（選做）

想知道幾十萬份文件時撐不撐得住才做。用的是公開的 EnterpriseRAG-Bench，51 萬份文件、154 萬段。

**要另外帶的檔案**（在有網路、裝了 Modal 的機器上，從這個專案的 Volume 取）

```bash
mkdir -p taguri-bundle/ent/enterprise taguri-bundle/ent/idx && cd taguri-bundle/ent
modal volume get taguri-b-results /data/enterprise/questions.jsonl enterprise/
modal volume get taguri-b-results /data/enterprise/splits.json enterprise/
modal volume get taguri-b-results /idx/enterprise-tw2sp.db idx/ && mv idx/enterprise-tw2sp.db idx/enterprise.db      # 7.7 GB
modal volume get taguri-b-results /dense/results_data-enterprise.npy idx/ && mv idx/results_data-enterprise.npy idx/enterprise.eg2.npy   # 2.4 GB
```

Volume 之後可能會清掉（`TODO.md` 的 D3）。沒有的話要重建：`modal_taguri.py` 的 `prep` 入口會下載題組、分段、建索引，`eg` 入口建向量，建向量在雲端花了約 $4.3。

**6.1 關鍵字那一層**

```bash
python -m taguri.run --config N0 --dataset enterprise --split recall470 --doc-level \
  --data-dir /opt/taguri-bundle/ent --idx-dir /opt/taguri-bundle/ent/idx --lex-procs 8 --out results/gb10/ent-N0
```

應該看到 R@10 68.98、R@5 61.00。這一步驗過，檔案照上面的名字放就可以。

**6.2 單獨一題要等多久**

```bash
python -m taguri.run --config N1 --dataset enterprise --split recall470 --doc-level --limit 20 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --data-dir /opt/taguri-bundle/ent --idx-dir /opt/taguri-bundle/ent/idx --out results/gb10/ent-latency

python -m taguri.run --config N1+EG2 --dataset enterprise --split recall470 --doc-level --limit 20 \
  --judge llama --base-url http://127.0.0.1:8080 --workers 1 --llama-parallel 4 \
  --dense-vectors /opt/taguri-bundle/ent/idx/enterprise.eg2.npy --eg2-model /opt/taguri-bundle/models/embeddinggemma-2 --eg2-device cpu \
  --data-dir /opt/taguri-bundle/ent --idx-dir /opt/taguri-bundle/ent/idx --out results/gb10/ent-latency-eg2
```

用階段 2 那段程式看時間花在哪。向量檔載進記憶體要 4.7 GB（CPU 上會轉成 float32）。

**門檻**

| | 判定 |
|---|---|
| 檢索的時間（`wall_s` 減 `judge_s`）中位數 ≤ 10 秒 | 符合預期。x86 4 核和 16 核上量到的都是 4 到 5 秒 |
| 檢索的時間超過 30 秒 | 不對。先確認用的是 `main` 最新的程式（2026-11-11 之前的版本每題要 40 多秒） |
| 等判官的時間 | 照實記。這個題組每題 168 次判斷、56 萬 token，是 MuSiQue 的 6 倍，預期會比階段 2 長很多 |

- `--workers` 開到 4 以上時，加 `--lex-procs N`（N 取 CPU 核心數的一半）。同一個行程裡的執行緒不會讓檢索變快，原因見第 8 節。
- 想對品質的話，470 題全跑完，`evalkit score` 和 `evalkit compare` 都加 `--root /opt/taguri-bundle/ent --dataset enterprise --split recall470`，對 `reference/enterprise/taguri_n1.jsonl`（雲端 R@10 74.50）或 `taguri_n1_eg2.jsonl`（80.71）。這要跑很久，不是必要的。

## 7. 延遲太長時可以調的

**先用現成的**：`--lock results/thresholds.lite.json`。每輪重判 10 段、證據池最多 5 段。雲端上判斷次數少 11%、token 少 17%，MuSiQue 兩批各 150 題的 R@5 都沒有可量測的差別。

**還不夠的話**，複製一份 `results/thresholds.lock.json`，改副本，再用 `--lock <副本>` 執行。每次只改一個，在 MuSiQue 校準半（`--split calib`，150 題，定案設定是 R@5 80.56）上看分數掉多少，連同延遲一起報告。

| 旋鈕（副本裡的鍵） | 現值 | 試 | 雲端量到的 |
|---|---:|---|---|
| `rejudge_each`（每輪重判幾段） | 20 | 10 | 判斷次數 −11%，R@5 −0.9 與 −0.1。降到 5 會掉 3 分。完全不重判會掉 10 分，不要設 0 |
| `m`（證據池最多幾段，副本裡加這個鍵） | 8 | 5 | 次數不變，token −4% 到 −6%，分數沒有變差 |
| `chunk`（判證據的批次大小） | 5 | 10 | 依序送出的批次數減半，對單題延遲最直接。分數低約 1 到 2 分 |
| `rounds`（擴展輪數，副本裡加這個鍵） | 2 | 1 | 判斷次數 −28%。R@5 只掉 0.5 到 1.7 分，但全部找齊的題目少 3 到 7 個百分點 |
| `K`（每輪取幾段，副本裡加這個鍵） | 50 | 30 | 判斷次數 −29%。全部找齊的題目少約 5 個百分點 |

完整的表在 [`results/b1-b4-b7.md`](../results/b1-b4-b7.md) 第 3 節。結論是能白拿的只有一成多，再省就是拿分數換。

還沒做、要寫程式的方向：小模型（E4B）先判，低信心才送 26B。

## 8. 踩過的坑

**判官**

- **生成和讀機率的請求不要送進同一個 SGLang 伺服器的同一批。** 雲端的 SGLang 版本會讓排程器當掉（`'list' object has no attribute 'tolist'`）。要同時做生成和判斷時分兩階段或兩個伺服器。llama-server 有沒有同樣的問題沒測過。
- **長段落會超過 context。** 已有證據 8 段、每段 2,000 字元時到過 17,776 token。現在已有證據會自動截到 10,000 token 以內。llama-server 這條路沒有 tokenizer，用「2 個字元算 1 個 token」估計。中文密度高的文件如果還是超長，把 `taguri/decide.py` 的 `EV_TOKEN_BUDGET` 調小。
- **llama-server 的並行。** jevlike 在 L4 上量到多個 slot 並行不增加吞吐量。GB10 上 `--llama-parallel` 開大有沒有用要實測。沒有用就設 1，結果一樣。
- **同分。** 判官的分數會有同分，llama-server 這條路還有截斷。程式用關鍵字分數和段落編號當次要排序鍵，結果是確定的。

**量測**

- **快取會讓延遲看起來是 0。** 量延遲時不要給 `--cache-dir`。
- **並行時每題的時間不是單題延遲。** `--workers 4` 量到的每題秒數會比 `--workers 1` 長。

**EG2**

- **少了 `torchvision` 模型會載入失敗。**
- **EG2 和判官搶同一張卡。** 雲端 L40S 上要把 SGLang 的記憶體比例從 0.8 降到 0.72。GB10 記憶體大，應該沒有這個問題，但要確認。查詢時用 `--eg2-device cpu` 可以完全避開。
- **索引重建之後向量也要重建。** 列數不符時程式會報錯，但列數剛好一樣、內容不同時不會。

**SQLite**（154 萬段時才看得出來，細節在 [`results/b1-b4-b7.md`](../results/b1-b4-b7.md) 第 1 節）

- `WHERE fts MATCH ? AND rowid IN (...)` 會讓 SQLite 一筆 rowid 跑一次查詢，FTS5 每次都把所有查詢詞的文件頻率重算一遍。154 萬段時每筆 0.125 秒，兩百筆就是 25 秒。寫成 `+rowid IN (...)` 才會掃一次。現在的程式已經這樣寫，改檢索程式時不要改回去。
- 同一個行程的多個執行緒做計分查詢，在 16 核的機器上完全不會變快，每個查詢反而從 0.5 秒拖到 12 秒。加大分頁快取和開記憶體映射都沒有用。要同時服務很多個問題時用 `--lex-procs N`。只有一個人在問時不用管。
- SQLite 每回傳一列，執行緒就要重新搶一次 Python 的全域鎖。回傳很多列的查詢在多執行緒下會互相等。段落編號的清單已經改成在 SQLite 裡併成一列。
- `bm25()` 不能放在會被 SQLite 攤平的子查詢裡，會報「unable to use function bm25 in the requested context」。
- 改檢索程式之前先用 `tools/lexical_profile.py` 重放一份 trace。它不用 GPU，可以量每一步的時間，也可以比對改動前後的輸出是否相同。

## 9. 回報格式

結果放 `results/gb10/`，寫一份 `results/gb10/REPORT.md`：

```
環境：GB10；llama.cpp build ___；模型檔 ___（sha256 ___）；Python ___；SQLite ___
階段 0：N0 MuSiQue dev R@5 ___（應為 47.72）／2Wiki ___（應為 67.25）
階段 1：10 題 R@5 ___；每題最低 option mass 的中位數 ___；失敗題數 ___
階段 2：單題延遲 MuSiQue 中位數 ___ 秒／第 90 百分位 ___ 秒；MultiHop-RAG ___／___
        等判官占 ___%；每題判斷 ___ 次、輸入 ___ token
        省一點的設定 ___ 秒；四題並行時每題 ___ 秒；判定 ___
階段 3：MuSiQue dev R@5 ___（雲端 80.17）；GB10 − 雲端 ___（信賴區間 ___）；判定 ___
階段 4：___ 份文件、___ 段、索引 ___ MB、建置 ___ 秒
        ___ 個問題；前 10 名找到：Taguri ___ %、只用關鍵字 ___ %；單題中位數 ___ 秒；判定 ___
階段 4a（會議記錄）：___ 場會議、___ 段；語言 ___
        單一會議 ___／___ 題、接兩場 ___／___ 題、用詞不同 ___／___ 題、找齊多場 ___／___ 題（Taguri／只用關鍵字，前 10 名找到的題數）
        橋接詞的型態：___；單題中位數 ___ 秒；判定 ___
階段 4b（工廠記錄）：記錄類型 ___、___ 筆、___ 段；語言 ___；編號寫法一致嗎 ___
        靠編號 ___／___ 題（關鍵字前 3 名 ___ %）、接兩筆 ___／___ 題、現象描述 ___／___ 題、相似記錄 ___／___ 題
        單題中位數 ___ 秒；判定 ___
階段 5（EG2）：建向量 ___ 段 ___ 秒（裝置 ___）；每題只靠 EG2 進來 ___ 段；每題多 ___ 秒
        用詞不同的題目：加 EG2 前 ___／___ 題、加之後 ___／___ 題；判定 ___
階段 6（大語料，有做的話）：N0 R@10 ___（應為 68.98）；單題 ___ 秒，其中檢索 ___ 秒、等判官 ___ 秒；加 EG2 ___ 秒
降配（有做的話）：旋鈕 ___ → 延遲 ___、校準半 R@5 ___（原 80.56）
結論：可以互動使用／只適合非即時／不能用；下一步建議 ___
```

## 附錄　資料怎麼存

沒有任何服務要架，也不需要連網。

| 東西 | 形式 | 說明 |
|---|---|---|
| 語料 | `corpus.jsonl` | 每行一段：`pid`、`doc`、`title`、`text` |
| 索引 | **一個 SQLite 檔**（`.db`） | FTS5 全文索引、段落原文、標題查表都在裡面。查詢時只需要這個檔 |
| EG2 向量（選配） | 一個 `.npy` 檔 | float16 矩陣，載入記憶體後直接比對，沒有向量資料庫 |
| 判官 | 本機的 llama-server 或 SGLang | 透過 `127.0.0.1` 的 HTTP 呼叫 |
| 判斷結果快取（選配） | 資料夾裡的 `.jsonl` | 給 `--cache-dir` 時才有。重跑同樣的題目不用再算 |
| 參數 | `results/thresholds.lock.json` | 執行時自動讀取。`--lock` 可以換成別的檔 |

大小參考：

| 語料 | 段落數 | 索引 | 建索引 | EG2 向量 |
|---|---:|---:|---:|---:|
| MuSiQue | 1.2 萬 | 18 MB | 5 秒 | 18 MB |
| EnterpriseRAG | 154 萬 | 7.7 GB | 5 分鐘（14 個行程） | 2.4 GB |
