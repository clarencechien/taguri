# 用到的公開先前技術

依交接文件 §2.4，新架構只用公開的一般性技術。下面每一項都是憑通用知識實作的，沒有為了這個專案另外去查文獻或程式碼；出處列的是該技術的原始發表。

| 技術 | 用在哪裡 | 出處 |
|---|---|---|
| BM25 | 詞彙召回的計分（SQLite FTS5 內建的 `bm25()`，k1=1.2、b=0.75） | Robertson、Walker 等人，Okapi at TREC-3（1994） |
| BM25F（欄位加權） | `title`、`cjk_bigram`、`cjk_word`、`latin`、`ids` 五個欄位各有權重，先把各欄位的詞頻加權相加再算 BM25 | Robertson、Zaragoza、Taylor，Simple BM25 Extension to Multiple Weighted Fields（CIKM 2004） |
| Rocchio 式的查詢擴展加權 | 下一輪查詢 = 原查詢分數 + β × 選中橋接詞的分數（`Index.fused_search`） | Rocchio，Relevance Feedback in Information Retrieval（1971） |
| 偽相關回饋（RM3 的想法） | 從已判成證據的段落抽出擴展詞。和 RM3 不同的是：擴展詞不是靠詞頻模型選，而是程式列候選、判官選（N1），或直接取 IDF 最高的（N1c） | Lavrenko、Croft，Relevance-Based Language Models（SIGIR 2001）；Abdul-Jaleel 等人，UMass at TREC 2004 |
| 迭代式檢索（IRCoT 的想法） | 「檢索 → 讀 → 決定下一步查什麼 → 再檢索」的多輪迴圈。和 IRCoT 不同的是：不生成推理文字，每一步都是讀選項字母的機率 | Trivedi 等人，Interleaving Retrieval with Chain-of-Thought Reasoning（ACL 2023） |
| 依題型決定檢索策略（Adaptive-RAG 的想法） | N2 的「證據是否足夠」決定要不要再跑一輪；N3 的題型四選一決定路線 | Jeong 等人，Adaptive-RAG（NAACL 2024） |
| CJK 字元 bigram 與詞典斷詞並用 | `cjk_bigram`、`cjk_word` 兩個欄位 | 中文資訊檢索的通用做法（例如 Lucene 的 CJKAnalyzer、NTCIR 的各屆結論）；斷詞用 jieba |
| Snowball（Porter2）詞幹 | `latin` 欄位 | Porter，Snowball: A language for stemming algorithms（2001） |
| 繁簡正規化後再比對 | 比對用的鍵值用 OpenCC 統一成同一種字體 | OpenCC 專案（BYVoid） |
| 配對 bootstrap | 所有比較的信賴區間（`evalkit`，Session A 交付） | Efron、Tibshirani，An Introduction to the Bootstrap（1993） |
| 讀第一個 token 的選項字母機率當判斷 | 所有判官呼叫 | Clarence 自己的 jevlike 專案（`clarencechien/jevlike`） |

| EmbeddingGemma 2 的非對稱檢索前綴 | N4 的 EG2 補充召回（查詢端 `task: search result \| query:`，文件端 `title: … \| text: …`） | 模型卡的建議用法，寫法取自 jevlike `bench/embed_route.py` |

S7b 之後沒有跑，所以沒有用到其他技術。
