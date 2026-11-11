"""Builds docs/report/taguri.html, a single-file report for the imitator host (style guide v3).

  python docs/report/build.py /path/to/imitator/style/report.css

The chassis CSS is pasted into the file (never linked). No third-party script, no storage API.
"""
import sys

CHASSIS = open(sys.argv[1], encoding="utf-8").read()
assert "imitator report chassis" in CHASSIS

VOICE = """
/* REGISTER:  收線的紀錄 — 一條線索怎麼一節一節拉回來，中間失手一次，後來怎麼改。讀者是要決定這東西值不值得往下做的人。
   REFERENCE: 《The Ashley Book of Knots》（1944）的圖版頁 — 編號的條目、線描、每條一段說明。
   PAPER:     放了八十年的未塗佈書頁紙 — 偏黃的奶油色，hsl(44 38% 93%)。
   VOICE:     焦油麻繩的深褐只給標題那個詞、條目編號和連結，明體標題，等寬體的條目編號。
   NOT:       儀表板。沒有互動元件，數字是證據。
   RECENT:    unavailable — 這個環境不能用 token 連到 host，沒有比對最近三份。 */
:root {
  --paper: hsl(44 38% 93%); --card: hsl(44 44% 96%);
  --ink: hsl(30 18% 13%); --ink-2: hsl(30 12% 28%); --mist: hsl(32 10% 38%);
  --rule: hsl(42 24% 82%); --rule-hard: hsl(40 20% 68%);
  --accent: hsl(22 62% 30%); --accent-soft: hsl(34 46% 85%);
  --disp: "Noto Serif TC", Georgia, serif;
  --sans: "Noto Sans TC", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    --paper: hsl(38 16% 8%); --card: hsl(38 14% 12%);
    --ink: hsl(42 28% 90%); --ink-2: hsl(40 16% 72%); --mist: hsl(38 10% 60%);
    --rule: hsl(38 10% 22%); --rule-hard: hsl(38 10% 32%);
    --accent: hsl(28 62% 68%); --accent-soft: hsl(28 26% 20%);
  }
}
:root[data-theme="dark"] {
  --paper: hsl(38 16% 8%); --card: hsl(38 14% 12%);
  --ink: hsl(42 28% 90%); --ink-2: hsl(40 16% 72%); --mist: hsl(38 10% 60%);
  --rule: hsl(38 10% 22%); --rule-hard: hsl(38 10% 32%);
  --accent: hsl(28 62% 68%); --accent-soft: hsl(28 26% 20%);
}
/* 條目：圖版頁的編號說明。一格編號、一格內文。 */
.entries { list-style: none; padding: 0; margin: var(--sp-5) 0; display: grid; gap: var(--sp-4); }
.entries > li { display: grid; grid-template-columns: 3.2rem minmax(0, 1fr); gap: var(--sp-3); align-items: baseline;
  border-top: 1px solid var(--rule); padding-top: var(--sp-3); }
.entries > li > .no { font-family: var(--mono); font-size: var(--fs-sm); color: var(--accent); letter-spacing: .04em; }
.entries > li > div { min-width: 0; }
.entries > li > div > strong { font-family: var(--disp); }
figure { margin-inline: 0; }
"""

def bars(rows, vmax, unit="", ref=None, label_w=150):
    """rows: [(label, value)]. One series -> --c1, no legend."""
    h = 16 + 36 * len(rows)
    x0, w = label_w + 10, 640 - label_w - 70
    out = [f'<svg viewBox="0 0 640 {h}" role="img" aria-label="{"；".join(f"{a} {b}" for a, b in rows)}">']
    if ref:
        xr = x0 + w * ref[1] / vmax
        out.append(f'<line class="grid" x1="{xr:.1f}" y1="6" x2="{xr:.1f}" y2="{h - 6}"/>')
        out.append(f'<text class="axis" x="{xr + 4:.1f}" y="12">{ref[0]}</text>')
    for i, (lab, v) in enumerate(rows):
        y = 16 + 36 * i
        out.append(f'<text class="axis" x="{label_w}" y="{y + 14}" text-anchor="end">{lab}</text>')
        out.append(f'<rect class="bar" x="{x0}" y="{y}" width="{w * v / vmax:.1f}" height="20" fill="var(--c1)"/>')
        out.append(f'<text class="label" x="{x0 + w * v / vmax + 8:.1f}" y="{y + 14}">{v:.1f}{unit}</text>')
    out.append("</svg>")
    return "\n".join(out)

FIG1 = bars([("只用關鍵字", 48.9), ("上游迴圈＋reranker", 66.2), ("Taguri", 80.2), ("上游迴圈＋商用判官", 81.0)], 100)
FIG2 = bars([("照原規格", 64.3), ("加上每輪重判", 74.9), ("再加暫定證據", 78.7), ("再換問法", 80.6)], 100, ref=("基線 77.1", 77.1), label_w=130)

BODY = f"""
<div class="progress"></div>
<button class="theme-toggle" id="theme-toggle" type="button" aria-pressed="false">theme · auto</button>

<main class="report">

  <p class="eyebrow">收線紀錄 · TAGURI · 2026-11</p>
  <h1 class="display">線索要<br><em>一節一節</em><br>拉回來</h1>
  <p class="lede">有些問題的答案散在好幾份文件裡。讀到第一份，才知道第二份該找什麼。這份紀錄講一個只靠本機模型的檢索做法，它第一次試的時候輸了十二分，後來怎麼追回來，以及現在還不知道的事。</p>
  <p class="byline">Taguri POC · 數字出自 github.com/clarencechien/taguri 的 results/</p>

  <p class="eyebrow">№ 1 · 第二段在哪裡</p>
  <h2>搜尋找不到的那一段</h2>

  <p>拿一個真的測試題來看。問題是「Erik Hort 的出生地屬於哪個郡」。資料庫裡有兩段文字跟它有關。</p>

  <ul class="entries">
    <li><span class="no">第一段</span><div>Erik Hort 生於 Montebello。</div></li>
    <li><span class="no">第二段</span><div>Montebello 是 Rockland County 的一個村。</div></li>
  </ul>

  <p>第一段很好找，問題裡就有他的名字。第二段跟問題幾乎沒有共同的字。用關鍵字找不到它，用語意相似度也排不到前面，因為問題裡根本沒提 Montebello。</p>

  <p><span class="mark">要先讀懂第一段，才知道下一步該查 Montebello。</span>這種題目叫多跳題。企業裡的問題常常長這樣，例如「這個警報上次換的零件，供應商是哪一家」。</p>

  <p class="eyebrow">№ 2 · 手繰り</p>
  <h2>讓模型只做選擇題</h2>

  <p>Taguri 這個名字是日文的「手繰り」，意思是把線一把一把收回來。做法分兩種角色。程式負責找候選和排順序。模型當判官，只回答選擇題，而且只讀它回答的第一個字的機率，不讓它寫字。</p>

  <ul class="entries">
    <li><span class="no">一</span><div><strong>先撈。</strong>用關鍵字從資料庫取出五十段可能相關的內容。</div></li>
    <li><span class="no">二</span><div><strong>逐段判。</strong>判官看每一段，回答這段對問題有沒有用。</div></li>
    <li><span class="no">三</span><div><strong>挑線索。</strong>程式從有用的段落裡列出幾個詞，判官選下一步該查哪一個。</div></li>
    <li><span class="no">四</span><div><strong>再撈一次。</strong>把選到的詞加進查詢，回到第二步。這樣走兩輪。</div></li>
    <li><span class="no">五</span><div><strong>交出十段。</strong>依判官的把握程度排序。</div></li>
  </ul>

  <p>整件事不呼叫任何外部服務。索引是一個 SQLite 檔案，判官是一顆開源的 Gemma 4。建索引的時候完全不用模型。</p>

  <p class="eyebrow">№ 3 · 失手</p>
  <h2>省掉的那一步，剛好是最需要的</h2>

  <p>第一版的規格有一條省錢的規定，判過的段落不再重判。照這條做出來，在四百題的開發集上比基線低了 11.9 分，離事先訂的及格線很遠。照計畫這裡就該停下來。</p>

  <p>停下來之後做的是拆帳。把每一個該找到卻沒找到的段落，歸到它卡住的那一步。</p>

  <div class="tiles wide stagger">
    <div class="stat"><p class="label">第一輪就撈到的證據</p><div class="value">67%</div><div class="delta">當時還沒有任何上下文</div></div>
    <div class="stat"><p class="label">沒有上下文時判「有用」</p><div class="value">43%</div><div class="delta">一半以上被判錯</div></div>
    <div class="stat"><p class="label">換成完美的判官</p><div class="value">91</div><div class="delta">流程本身撐得住</div></div>
  </div>

  <p>原因很直白。第二跳的段落，在還不知道橋接的那個詞之前，本來就看不出跟問題有關。判官在第一輪說「沒用」是合理的。問題出在後來找到第一段了，卻不回頭再看一次。</p>

  <p class="pull">便宜是靠少判換來的，少掉的偏偏是帶著新證據回頭看的那幾次。</p>

  <p>改法有兩個，都很小。每一輪結束，把分數最高的二十段帶著目前的證據再判一次。另外，如果沒有任何段落過關，就先拿分數最高的兩段當暫定證據，讓後面有東西可以接。</p>

  <figure class="reveal">
    <p class="title">一步一步追回來</p>
    <p class="subtitle">校準用的 150 題，前五段撈到的證據比例。直線是同一批題目上的基線。</p>
    <div class="chart">
{FIG2}
    </div>
    <details class="datatable">
      <summary>看數字</summary>
      <div class="table-scroll">
        <table>
          <thead><tr><th>做法</th><th class="num">前五段撈到的比例</th><th class="num">每題判斷次數</th></tr></thead>
          <tbody>
            <tr><td>照原規格</td><td class="num">64.3</td><td class="num">111</td></tr>
            <tr><td>加上每輪重判</td><td class="num">74.9</td><td class="num">140</td></tr>
            <tr><td>再加暫定證據</td><td class="num">78.7</td><td class="num">147</td></tr>
            <tr><td>再換問法</td><td class="num">80.6</td><td class="num">143</td></tr>
            <tr><td>基線（上游迴圈配同一顆模型）</td><td class="num">77.1</td><td class="num">334</td></tr>
          </tbody>
        </table>
      </div>
    </details>
    <figcaption>這 150 題只用來調整。正式的成績在下一節，用的是沒碰過的 700 題。</figcaption>
  </figure>

  <p class="eyebrow">№ 4 · 收上來的東西</p>
  <h2>跟商用判官打平</h2>

  <div class="hero reveal">80.2</div>
  <p class="byline">沒碰過的 700 題，前五段撈到的證據比例。上游做法配商用判官是 81.0。</p>

  <p>兩者差 0.8 分，統計上分不出高低（95% 信賴區間從負 2.6 到正 1.0）。測試題只跑一次，中途沒有調整。開發時的成績是 80.2，測試也是 80.2，沒有只在自己調過的題目上好看。</p>

  <figure class="reveal">
    <p class="title">四種做法，同一批 700 題</p>
    <p class="subtitle">MuSiQue 測試集，前五段撈到的證據比例。</p>
    <div class="chart">
{FIG1}
    </div>
    <details class="datatable">
      <summary>看數字</summary>
      <div class="table-scroll">
        <table>
          <thead><tr><th>做法</th><th class="num">前五段</th><th class="num">前十段全部找齊的題目</th></tr></thead>
          <tbody>
            <tr><td>只用關鍵字</td><td class="num">48.9</td><td class="num">18.7%</td></tr>
            <tr><td>上游迴圈＋reranker</td><td class="num">66.2</td><td class="num">44.1%</td></tr>
            <tr><td>Taguri</td><td class="num">80.2</td><td class="num">71.9%</td></tr>
            <tr><td>上游迴圈＋商用判官</td><td class="num">81.0</td><td class="num">69.9%</td></tr>
          </tbody>
        </table>
      </div>
    </details>
  </figure>

  <p>成績一樣，花的力氣不一樣。</p>

  <div class="tiles wide stagger">
    <div class="stat"><p class="label">每題判斷次數</p><div class="value">143</div><div class="delta">基線是 334 次</div></div>
    <div class="stat"><p class="label">每千題運算成本</p><div class="value">$1</div><div class="delta">商用判官約 $4.3</div></div>
    <div class="stat"><p class="label">外部服務</p><div class="value">0</div><div class="delta">模型和資料都在本機</div></div>
  </div>

  <p>判官挑線索這件事本身也量過。把它換成「直接取最罕見的兩個詞」，成績掉 2.2 分，全部找齊的題目少 6 個百分點。</p>

  <p class="eyebrow">№ 5 · 換一片海</p>
  <h2>沒看過的資料上還成立嗎</h2>

  <p>在自己調過的題組上好看不算數。下面三個題組都沒有拿來調過任何參數。</p>

  <div class="table-scroll wide">
    <table>
      <thead><tr><th>題組</th><th class="num">只用關鍵字</th><th class="num">Taguri</th><th class="wrap">結果</th></tr></thead>
      <tbody>
        <tr><td>新聞<span class="sub">MultiHop-RAG · 300 題</span></td><td class="num">52.4</td><td class="num">72.2</td><td class="wrap">和基線的 70.9 持平</td></tr>
        <tr><td>企業文件<span class="sub">EnterpriseRAG · 51 萬份</span></td><td class="num">69.0</td><td class="num">74.5</td><td class="wrap">比關鍵字高 5.5 分，比上游做法配商用判官低 6.6 分。加上向量模型補撈後是 80.7，和商用判官的 81.1 打平</td></tr>
        <tr><td>企業文件，問法跟文件用詞不同<span class="sub">同上 · 125 題</span></td><td class="num">42.4</td><td class="num">52.8</td><td class="wrap">加上一個向量模型補撈後到 62.4，商用判官是 58.4</td></tr>
      </tbody>
    </table>
  </div>

  <p>企業文件那一組還接上了回答。同一顆模型讀找出來的十份文件作答，抽一百題。只用關鍵字時答對 47 題，用 Taguri 答對 64 題，直接把標準文件給它是 83 題。這個評分是模型自己打的，沒有人工核對，只能看方向。</p>

  <div class="note warn">
    <p class="head">有一類題目沒有進步</p>
    <p>「把某個專案的相關文件全部找齊」這種題目，Taguri 跟關鍵字一樣差，比商用判官低 19 分。它的設計是往下一跳走，沒有設計成把同一件事的文件收齊。</p>
  </div>

  <p>這 19 分後來拆過一次。把上游的迴圈接上同一顆本機判官，跑同樣的六十題，就能分出判官和流程各占多少。換判官掉 12 分，換流程再掉 7 分。<span class="mark">比較大的一塊在判官。</span>同一個專案的文件彼此都相關，本機判官分不出題目指定的是哪幾份。</p>

  <p>向量模型補撈的效果後來在全部 470 題上量過。加了之後，整體和商用判官打平。打平的組成不一樣。最基本的查找題和問法跟文件用詞不同的題目，Taguri 各高 4 分。要把同一件事的文件找齊的題目，仍然低 13 到 31 分，向量模型在這裡沒有幫上忙。</p>

  <p class="eyebrow">№ 6 · 中文</p>
  <h2>搬到中文掉了二十一分，其中八分是資料的問題</h2>

  <p>把一百題和它的資料庫翻成繁體中文，再轉一份簡體，三種語言跑同一套流程。英文 80.3，繁中 58.6，簡中 59.4。繁簡之間沒有差別，字體的正規化沒有問題。</p>

  <p>差距拆開來看，有一塊是翻譯自己造成的。二十九題的問題裡留著英文名字，資料庫那邊的標題卻翻成了中文，兩邊對不起來。重翻問題之後，繁中回到 64.8。</p>

  <p>另一塊是線索的品質。英文靠大寫字找專有名詞，中文沒有大寫，程式列給判官選的詞變成「現況」「領銜」這種斷詞碎片。改成只列人名地名和機構名之後，繁中到 66.3，離英文還差 14 分。</p>

  <p>這 14 分不全是 Taguri 的。上游的迴圈接上同一顆判官，在同一份中文資料上也掉 7 到 10 分。兩套做法在中文上分不出高低。共同掉的那一塊在判官，它讀中文時變得保守，該說「有用」的段落比較常說「沒用」。提示詞用英文寫還是中文寫，結果一樣。</p>

  <p>順手測了一件事。中文問題直接查英文資料庫，不加向量模型時前五段只撈到 16.6，加上之後是 65.4，跟先把文件翻成中文再查一樣好。第一輪靠向量模型找到入口，之後的線索是從英文證據裡抽出來的英文詞，後面幾輪就回到英文查英文。</p>

  <p class="eyebrow">№ 7 · 補撈</p>
  <h2>什麼時候要多帶一個向量模型</h2>

  <p>一開始的設計是完全不用向量，只靠關鍵字和判官。做到後來，結論變成看資料。<span class="mark">問題和文件的用詞常常對不上的時候要帶，對得上的時候不用。</span></p>

  <ul class="entries">
    <li><span class="no">不用</span><div><strong>問題會直接講出名字。</strong>人名、作品名、產品名、編號都算。維基百科那類多跳題加了只多半分，在雜訊裡。</div></li>
    <li><span class="no">要</span><div><strong>企業文件和會議記錄。</strong>問的人和寫的人用詞不同。五十一萬份文件上，不加時比商用判官低 6.6 分，加了打平。</div></li>
    <li><span class="no">要</span><div><strong>一個問題問兩件事。</strong>各在一份文件裡，關鍵字常常只撈到前半段那一份。加了之後這類題目從 85 分到 97 分。</div></li>
    <li><span class="no">一定要</span><div><strong>中文問、英文文件。</strong>不加幾乎找不到，前五段只有 16.6。加了是 65.4。</div></li>
    <li><span class="no">沒用</span><div><strong>要把同一件事的文件找齊。</strong>加了之後帶進來的反而是更多看起來相關的干擾。</div></li>
  </ul>

  <p>代價不大。向量只要建一次，五十一萬份文件在一張 GPU 上花了 132 分鐘、4.3 美元，存下來是一個 2.4 GB 的檔案。查詢時每題多一成七的判斷次數。它不需要向量資料庫，也不參與排序。它只負責多撈幾段進來，誰是證據仍然由判官決定。</p>

  <p class="eyebrow">№ 8 · 帳面</p>
  <h2>最後的成績</h2>

  <div class="table-scroll wide">
    <table>
      <thead><tr><th>題組</th><th class="num">只用關鍵字</th><th class="num">上游迴圈＋商用判官</th><th class="num">Taguri</th><th class="num">加向量補撈</th></tr></thead>
      <tbody>
        <tr><td>英文多跳<span class="sub">MuSiQue · 沒碰過的 700 題 · 前 5 段</span></td><td class="num">48.9</td><td class="num">81.0</td><td class="num">80.2</td><td class="num">沒跑</td></tr>
        <tr><td>新聞<span class="sub">MultiHop-RAG · 300 題 · 前 10 段</span></td><td class="num">52.4</td><td class="num">沒有紀錄</td><td class="num">72.2</td><td class="num">沒跑</td></tr>
        <tr><td>企業文件<span class="sub">EnterpriseRAG · 470 題 · 前 10 份</span></td><td class="num">67.8</td><td class="num">81.1</td><td class="num">74.5</td><td class="num">80.7</td></tr>
        <tr><td>其中要找齊多份文件的<span class="sub">60 題</span></td><td class="num">58.8</td><td class="num">81.1</td><td class="num">61.9</td><td class="num">62.3</td></tr>
        <tr><td>繁體中文<span class="sub">機器翻譯 · 100 題 · 前 5 段</span></td><td class="num">38.4</td><td class="num">沒有</td><td class="num">66.3</td><td class="num">66.4</td></tr>
        <tr><td>中文問、英文文件<span class="sub">100 題 · 前 5 段</span></td><td class="num"></td><td class="num"></td><td class="num">16.6</td><td class="num">65.4</td></tr>
      </tbody>
    </table>
  </div>

  <p>兩個打平的地方，差距都在統計的雜訊裡。英文多跳差 0.8 分，企業文件加了向量之後差 0.4 分。花的力氣不一樣。英文多跳每題 143 次判斷，上游迴圈配同一顆判官要 334 次。企業文件上讀進去的字是它的三成。</p>

  <p>另外量過能不能再省。把每輪回頭重看的段數減半、證據留五段，判斷次數少一成，讀的字少一成七，分數不變。再往下省就得拿分數換，砍掉一輪會讓「全部找齊」的題目少掉三到七個百分點。</p>

  <p class="eyebrow">№ 9 · 還沒收完的線</p>
  <h2>這是一件資產，還稱不上產品</h2>

  <p>現在有的是一個能重複使用的檢索元件，加上證明它有效的紀錄。它沒有畫面，沒有權限控管，不會自己寫答案。下面四件事還不知道。</p>

  <ul class="entries">
    <li><span class="no">a</span><div><strong>一個問題要等多久。</strong>所有實驗都是十六題一起跑，量到的是吞吐量。單獨一題的等待時間沒有量過。</div></li>
    <li><span class="no">b</span><div><strong>在公司的機器上是什麼樣子。</strong>實驗在雲端的 GPU 上做，模型權重和伺服器都跟地端不同。</div></li>
    <li><span class="no">c</span><div><strong>自己的文件。</strong>會議記錄只有間接的數字，工廠記錄完全沒有，真實的繁中文件也沒有。</div></li>
    <li><span class="no">d</span><div><strong>更大的資料庫。</strong>一百五十萬段的時候，關鍵字那一層原本每題要四十幾秒，查到原因之後降到四秒左右，找出來的東西一樣。再大十倍會怎樣，沒有試過。</div></li>
  </ul>

  <p>這四件事裡，前三件不用再花雲端的錢。把它搬到不連外網的機器上，照著接手文件跑一遍就知道了。</p>

  <p>知道之後，還有三件事可以做。</p>

  <ul class="entries">
    <li><span class="no">e</span><div><strong>把同一件事的文件找齊。</strong>這是現在唯一明顯輸的地方。要另外做一條依專案展開的路線，而且要先準備一批沒看過的題目來調。</div></li>
    <li><span class="no">f</span><div><strong>換一顆判官。</strong>中文掉的分數和找齊文件掉的分數，大半都在判官。往上換更強的可以補分數，往下讓小模型先判可以省成本。兩個都還沒試。</div></li>
    <li><span class="no">g</span><div><strong>回答的品質。</strong>現在只量了找得到找不到。接上回答之後對不對，只做過一次模型自己評分的抽測，要有獨立的評分者。</div></li>
  </ul>

  <p>整個實驗到這裡花了大約三十九美元。</p>

  <p class="byline">程式、每一段的報告與接手文件：github.com/clarencechien/taguri</p>

</main>

<script>
(() => {{
  const root = document.documentElement, btn = document.getElementById('theme-toggle');
  let dark = matchMedia('(prefers-color-scheme: dark)').matches;
  btn.textContent = 'theme · ' + (dark ? 'dark' : 'light');
  btn.addEventListener('click', () => {{
    dark = !dark; root.dataset.theme = dark ? 'dark' : 'light';
    btn.textContent = 'theme · ' + (dark ? 'dark' : 'light'); btn.setAttribute('aria-pressed', 'true');
  }});
}})();
</script>
"""

HTML = f"""<!doctype html>
<html lang="zh-Hant">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="imitator-style" content="v3">
<meta name="imitator-register" content="收線的紀錄 — 一條線索怎麼一節一節拉回來，中間失手一次，後來怎麼改">
<meta name="imitator-reference" content="《The Ashley Book of Knots》（1944）的圖版頁">
<meta name="imitator-paper" content="hsl(44 38% 93%)">
<meta name="imitator-accent" content="hsl(22 62% 30%)">
<title>線索要一節一節拉回來 — Taguri 收線紀錄</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@500;700&family=Noto+Sans+TC:wght@400;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
{CHASSIS}
{VOICE}
</style>
<body>
{BODY}
</body>
</html>
"""
open("docs/report/taguri.html", "w", encoding="utf-8").write(HTML)

# plain-text copy of the prose for twtone
import re
text = re.sub(r"<svg.*?</svg>", "", BODY, flags=re.S)
text = re.sub(r"<script.*?</script>", "", text, flags=re.S)
text = re.sub(r"<(h1|h2)[^>]*>", "\n## ", text)
text = re.sub(r"<br>", "", text)
text = re.sub(r"</(p|h1|h2|li|div|tr|figcaption|summary)>", "\n", text)
text = re.sub(r"<[^>]+>", "", text)
text = re.sub(r"\n\s*\n+", "\n\n", text)
open("docs/report/taguri.txt.md", "w", encoding="utf-8").write(text.strip() + "\n")
print(len(HTML), "bytes")
