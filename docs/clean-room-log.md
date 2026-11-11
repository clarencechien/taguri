# Clean-room 紀錄（Session B）

規則見 `TAGURI-handoff.md` §2.3、§2.4。每次查閱 repo 以外的資料都記在這裡。

## 禁止清單（開工時確認）

- 不讀、不下載、不安裝、不搜尋：`Zleap-AI/*`、PyPI `zleap-sag`／`zleap-sag2`、arXiv 2606.15971／2608.12129／2610.22588、介紹 SAG2 實作的文章。
- 不讀 `clarencechien/sag2poc-baseline`，也不加進 session。
- 不用網路搜尋 SAG2 的做法。

## 查閱紀錄

| 時間（UTC） | 來源 | 用途 | 備註 |
|---|---|---|---|
| 2026-11-10 | 本 repo：`TAGURI-handoff.md`、`handoff/A-to-B.md`、`reference/README.md`、`evalkit/`、`data/` | 任務說明、評測工具、資料 | Session A 交付包 |
| 2026-11-10 | `clarencechien/jevlike` @ `4f842ed`（淺層 clone，只讀）：`README.md`、`decide/prompt.py`、`decide/client.py`、`modal_sglang.py`、`scripts/modal.sh`、`bench/jevbench.py`、`bench/embed_route.py` | 模板 `GEMMA4_TEMPLATE_NOTHINK_BOS`、英文題寫法（v8）、SGLang 啟動參數與 fused-MoE 設定檔、EG2 模型 ID 與 revision、EG2 的 task prompt 寫法 | 讀之前先 `grep -ril 'zleap\|sag2\|SAG-Bench'`，沒有任何命中 |
| 2026-11-10 | PyPI：`jieba`、`opencc-python-reimplemented`、`snowballstemmer`、`tokenizers`、`numpy`、`requests`、`modal` | 套件安裝 | 版本記在 `docs/design-decisions.md` |
| 2026-11-10 | `github.com/DRCKnowledgeTeam/DRCD` @ `b944790`（官方發布版：`DRCD_training.json`、`DRCD_dev.json`、`DRCD_test.json`、README） | S7a 的中文詞彙層選型 | 題組官方說明，§2.4 允許；資料檔不進 git |
| 2026-11-10 | `raw.githubusercontent.com/fxsjy/jieba/master/extra_dict/dict.txt.big` | S7a 的 `s2twp` 組別要用 jieba 繁體大詞典 | jieba 官方 repo 的詞典檔；不進 git |
| 2026-11-10 | Hugging Face API：`google/embeddinggemma-2`、`onyx-dot-app/EnterpriseRAG-Bench` 的模型／資料集中繼資料（只看是否公開、授權、revision） | 確認 EG2 不需要金鑰；記下 EnterpriseRAG-Bench 的 revision `69916e3`（S10 沒有跑，資料沒有下載） | |
| 2026-11-10 | Hugging Face：`google/embeddinggemma-2` @ `914f7f8` 權重（在 Modal 容器內下載到 Volume `taguri-b-results`） | N4 | |
| 2026-11-10 | PyPI（Modal image 內）：`torch`、`torchvision`、`torchaudio`、`pillow`、`sentence-transformers`、`transformers` | EG2 的獨立環境 | |
| 2026-11-10 | jevlike `modal_v14.py`（只看 EG2 image 的套件版本要求） | 修 EG2 載入失敗 | |
| 2026-11-10 | Hugging Face：`onyx-dot-app/EnterpriseRAG-Bench` @ `69916e3` 的 README（資料集卡）、`data/questions/test.parquet`、`data/documents/test.parquet`（後兩者在 Modal 容器內下載） | S10 | 題組官方說明，§2.4 允許。只讀了資料集卡的欄位說明和題型表；沒有開排行榜、論文和 GitHub repo |
| 2026-11-11 | `clarencechien/imitator` @ `f9d9b9f`（`README.md`、`CLAUDE.md`、`style/STYLE.md`、`style/report.css`、`style/mockup.html`） | 照它的版面規範寫 `docs/report/taguri.html` | Clarence 指定。唯讀 clone，CSS 骨架貼進報告裡 |
| 2026-11-11 | `clarencechien/twtonepoc` @ `940bab2`（`twtone` 檢查工具，會下載它用的 zhtw-mcp 執行檔） | 檢查給人看的文件的繁中語感 | Clarence 指定。只在本機跑，不呼叫模型 |

全程沒有用網路搜尋。

## 違規紀錄

（無）
