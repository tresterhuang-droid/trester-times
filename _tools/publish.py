#!/usr/bin/env python3
"""Trester Times 網站發布腳本。

把當日排程產出的 times.html（及同資料夾的圖片）轉成網頁版、加密後放進網站，
並更新首頁、歸檔，以及前後期之間的連結。

用法：
  TT_PASSWORD=... python3 _tools/publish.py --src /path/to/build_dir --date 20261108
  TT_PASSWORD=... python3 _tools/publish.py --pdf old.pdf --meta meta.json --date 20261030   # 補上線前的舊期

需要：Python 3 + beautifulsoup4、poppler（pdftoppm）；Node（第一次執行會自動 npm install staticrypt）。
"""
import argparse, base64, datetime as dt, html as H, json, mimetypes, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parent))
import today as T

ROOT = Path(__file__).resolve().parent.parent  # 網站根目錄（儲存庫根目錄）
TOOLS = ROOT / "_tools"
CONFIG = TOOLS / "staticrypt.json"
GATE = TOOLS / "gate.html"
MANIFEST_ENC = ROOT / "data" / "manifest.html"
WEEK = "一二三四五六日"
FONTS_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
              '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900'
              '&family=Noto+Serif+TC:wght@400;700;900&display=swap">')
HEAD_META = ('<meta name="viewport" content="width=device-width, initial-scale=1">'
             '<meta name="robots" content="noindex,nofollow">')

# 頭條類別：與 Notion 晨報歷史庫的選項一致；版面標籤的大類依此對應
CATEGORIES = ["台灣政治", "全球", "都市與地方", "社會與企業", "研究與觀察", "制度", "災害與城市"]
CAT_RULES = [("災", "災害與城市"), ("颱", "災害與城市"), ("全球", "全球"), ("國際", "全球"), ("世界", "全球"),
             ("台灣", "台灣政治"), ("政治", "台灣政治"), ("選", "台灣政治"), ("城市", "都市與地方"),
             ("都市", "都市與地方"), ("地方", "都市與地方"), ("社會", "社會與企業"), ("企業", "社會與企業"),
             ("ESG", "社會與企業"), ("研究", "研究與觀察"), ("觀察", "研究與觀察"), ("制度", "制度")]


def category_of(text):
    t = (text or "").strip()
    if t in CATEGORIES:
        return t
    head = re.split(r"[|｜]", t)[0]
    for key, cat in CAT_RULES:
        if key in head:
            return cat
    return ""


# ---------- 加密 ----------
def staticrypt_bin():
    b = TOOLS / "node_modules" / ".bin" / "staticrypt"
    if not b.exists():
        subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--prefix", str(TOOLS)], check=True)
    return str(b)


def encrypt(plain_path: Path, out_path: Path, password: str, title="Trester Times"):
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([staticrypt_bin(), str(plain_path), "-d", td, "-c", CONFIG.name, "--short",
                        "-t", str(GATE), "--template-title", title,
                        "--template-instructions", "每日晨報　發行人專用",
                        "--template-placeholder", "密碼", "--template-button", "閱讀",
                        "--template-remember", "在這台裝置記住我",
                        "--template-error", "密碼不正確",
                        "--template-toggle-show", "顯示密碼", "--template-toggle-hide", "隱藏密碼",
                        "--remember", "0"],
                       check=True, env={**os.environ, "STATICRYPT_PASSWORD": password}, cwd=TOOLS,
                       stdout=subprocess.DEVNULL)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(td) / plain_path.name, out_path)


def decrypt(enc_path: Path, password: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([staticrypt_bin(), str(enc_path), "--decrypt", "-d", td, "-c", CONFIG.name, "--short"],
                       cwd=TOOLS, check=True, env={**os.environ, "STATICRYPT_PASSWORD": password},
                       stdout=subprocess.DEVNULL)
        return (Path(td) / enc_path.name).read_text(encoding="utf-8")


def write_encrypted(text: str, out_path: Path, password: str, title="Trester Times"):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "index.html"
        p.write_text(text, encoding="utf-8")
        encrypt(p, out_path, password, title)


# ---------- 清單 ----------
def load_manifest(password):
    if not MANIFEST_ENC.exists():
        return []
    html = decrypt(MANIFEST_ENC, password)
    m = re.search(r'<script type="application/json" id="m">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else []


def save_manifest(entries, password):
    data = json.dumps(entries, ensure_ascii=False, indent=1).replace("</", "<\\/")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "manifest.html"
        p.write_text(f'<!doctype html><meta charset="utf-8"><script type="application/json" id="m">{data}</script>',
                     encoding="utf-8")
        encrypt(p, MANIFEST_ENC, password)


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def date_zh(d: dt.date):
    return f"{d.year}年{d.month}月{d.day}日　星期{WEEK[d.weekday()]}"


def short_date(eid):
    d = dt.datetime.strptime(eid, "%Y%m%d").date()
    return f"{d.month}/{d.day}"


# ---------- 工具列（前後期連結以註記包住，之後可替換） ----------
HEADLINES = {}


def nav_link(kind, target):
    label = "前一期" if kind == "prev" else "下一期"
    arrow_l, arrow_r = ("‹ ", "") if kind == "prev" else ("", " ›")
    if target:
        return (f'<!--{kind.upper()}--><a class="pn {kind}" data-nav="{kind}" href="/e/{target}/" '
                f'title="{label}：{short_date(target)}" data-h="{esc(HEADLINES.get(target, ""))}">{arrow_l}<span>{label}</span>{arrow_r}</a><!--/{kind.upper()}-->')
    return f'<!--{kind.upper()}--><span class="pn {kind} off">{arrow_l}<span>{label}</span>{arrow_r}</span><!--/{kind.upper()}-->'


def toolbar_today(eid, d, prev_id, next_id):
    return (f'<nav class="tt-bar" data-id="{eid}"><a class="home" href="/">Trester Times</a>'
            f'<span class="seg"><span class="on">今日報</span><a href="paper/">報紙版</a></span>'
            f'<span class="date">{date_zh(d)}</span><span class="sp"></span>'
            f'{nav_link("prev", prev_id)}{nav_link("next", next_id)}'
            f'<a class="arc" href="/archive/"><span class="hide-m">回</span>歷史資料庫</a></nav>')


def toolbar(eid, d, prev_id, next_id, pages, modes):
    opts = "".join(f'<option value="{pid}">{H.escape(lbl)}</option>' for pid, lbl in pages)
    seg = ('<span class="seg"><button data-mode="page">版面</button><button data-mode="read">閱讀</button></span>'
           if modes else "")
    return (f'<nav class="tt-bar" data-id="{eid}"><a class="home" href="/">Trester Times</a>'
            f'<span class="date">{date_zh(d)}</span><span class="sp"></span>'
            f'<select class="jump" aria-label="跳到版次"><option value="">版次</option>{opts}</select>'
            f'<a class="arc" href="../">‹ 今日報</a><a class="arc" href="/archive/">回歷史資料庫</a>'
            f'{seg}<button class="prt" data-print>列印</button></nav>')


def set_nav(eid, kind, target, password):
    """改寫某一期工具列中的前一期／下一期連結。"""
    f = ROOT / "e" / eid / "index.html"
    if not f.exists():
        return
    page = decrypt(f, password)
    tag = kind.upper()
    new, n = re.subn(rf"<!--{tag}-->.*?<!--/{tag}-->", nav_link(kind, target).replace("\\", "\\\\"), page, flags=re.S)
    if n and new != page:
        write_encrypted(new, f, password)


# ---------- 每期頁面 ----------
def build_edition(src: Path, d: dt.date, prev_id, next_id):
    eid = d.strftime("%Y%m%d")
    soup = BeautifulSoup((src / "times.html").read_text(encoding="utf-8"), "html.parser")

    # 圖片內嵌成 data URI，讓圖片跟著頁面一起加密
    for img in soup.find_all("img"):
        s = img.get("src", "")
        if s.startswith(("data:", "http:", "https:")):
            continue
        f = src / s
        if f.exists():
            mime = mimetypes.guess_type(f.name)[0] or "image/png"
            img["src"] = f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
        else:
            img.decompose()

    # 字型路徑改到網站共用資產；中文字型加上網頁字型後備
    for st in soup.find_all("style"):
        css = st.string or ""
        css = re.sub(r"url\((uni|pf9|pf7)\.woff2\)", r"url(/assets/fonts/\1.woff2)", css)
        css = css.replace('"Noto Serif CJK TC"', '"Noto Serif CJK TC","Noto Serif TC"')
        css = css.replace('"Noto Sans CJK TC"', '"Noto Sans CJK TC","Noto Sans TC"')
        st.string = css

    issue = T.parse_issue(BeautifulSoup(str(soup), "html.parser"))
    # 首頁與歸檔需要的資訊
    main = soup.select_one(".fgrid .main")
    headline = txt(main.find("h2")) if main else ""
    lead_tag = txt(main.select_one(".tag")) if main else ""
    deck = txt(main.select_one(".deck")) if main else ""
    teasers = [{"tag": txt(t.select_one(".tg")), "title": txt(t.select_one(".tt")), "where": txt(t.select_one(".tp"))}
               for t in soup.select(".teasers > div")]

    # 各版加上錨點，供「版次」選單跳轉
    pages = []
    for i, pg in enumerate(soup.select("section.page"), 1):
        b = pg.select_one(".rh .c b")
        if b:
            code = re.match(r"[A-Z]\d+", txt(b))
            code = code.group(0) if code else f"A{i}"
            zh = txt(b.find("em")) if b.find("em") else ""
        else:
            code, zh = "A1", "要聞"
        pg["id"] = code
        pages.append((code, f"{code} {zh}".strip()))

    meta = {"id": eid, "date": d.isoformat(), "date_zh": date_zh(d), "headline": headline, "tag": lead_tag,
            "cat": category_of(lead_tag), "deck": deck, "teasers": teasers, "pages": len(pages), "source": "html",
            "stories": [{"id": x["id"], "t": x["title"], "c": x["cat"]} for x in issue["stories"]]}

    head = soup.head
    head.title.string = f"Trester Times｜{date_zh(d)}"
    head.insert(0, BeautifulSoup(HEAD_META + FONTS_LINK, "html.parser"))
    head.append(BeautifulSoup('<link rel="stylesheet" href="/assets/web.css">', "html.parser"))
    wrap = soup.new_tag("main", attrs={"class": "tt-sheets"})
    for pg in soup.select("section.page"):
        wrap.append(pg.extract())
    soup.body.clear()
    soup.body["class"] = "tt-html"
    soup.body.append(BeautifulSoup(toolbar(eid, d, prev_id, next_id, pages, True), "html.parser"))
    soup.body.append(wrap)
    soup.body.append(BeautifulSoup('<script src="/assets/web.js"></script>', "html.parser"))
    today_page = T.render_today(issue, eid, date_zh(d), toolbar_today(eid, d, prev_id, next_id), len(pages))
    return str(soup), meta, today_page


def build_pdf_edition(pdf: Path, d: dt.date, prev_id, next_id, meta_in: dict):
    """由過去的 PDF 建立網頁版：每頁轉成圖片內嵌。"""
    eid = d.strftime("%Y%m%d")
    with tempfile.TemporaryDirectory() as td:
        from PIL import Image
        subprocess.run(["pdftoppm", "-r", "150", "-png", str(pdf), f"{td}/p"], check=True)
        imgs = sorted(Path(td).glob("p-*.png"), key=lambda f: int(f.stem.split("-")[1]))
        figs, pages = [], []
        for i, f in enumerate(imgs, 1):
            code = f"A{i}"
            pages.append((code, code))
            w = f.with_suffix(".webp")
            Image.open(f).convert("RGB").save(w, "WEBP", quality=60, method=6)
            figs.append(f'<figure class="pg" id="{code}"><img alt="{code}" loading="lazy" '
                        f'src="data:image/webp;base64,{base64.b64encode(w.read_bytes()).decode()}"></figure>')
    page = (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">{HEAD_META}'
            f'<title>Trester Times｜{date_zh(d)}</title>{FONTS_LINK}<link rel="stylesheet" href="/assets/web.css"></head>'
            f'<body class="tt-pdf">{toolbar(eid, d, prev_id, next_id, pages, False)}'
            f'<main class="pdfpages"><p class="note">本期為網站上線前的存檔，以原版面呈現。'
            f'<span class="m">點一下版面可放大，再點一下還原。</span></p>{"".join(figs)}</main>'
            f'<script src="/assets/web.js"></script></body></html>')
    tag = meta_in.get("tag", "")
    meta = {"id": eid, "date": d.isoformat(), "date_zh": date_zh(d), "headline": meta_in.get("headline", ""),
            "tag": tag, "cat": category_of(meta_in.get("cat") or tag), "deck": meta_in.get("deck", ""),
            "teasers": meta_in.get("teasers", []), "pages": len(pages), "source": "pdf"}
    return page, meta


# ---------- 首頁與歸檔 ----------
INDEX_CSS = """
@font-face{font-family:Uni;src:url(/assets/fonts/uni.woff2)}
*{box-sizing:border-box;margin:0;padding:0}
:root{--paper:#f3efe3;--ink:#1a1814;--red:#8a1c1c;--box:#e9e1cf;--mute:#5d574b;--rule:#8f8877}
body{background:var(--paper);color:var(--ink);font:400 16px/1.7 "Noto Serif TC","Noto Serif CJK TC","Songti TC","PMingLiU",serif;padding:0 18px 64px}
.sans{font-family:"Noto Sans TC","Noto Sans CJK TC","PingFang TC",sans-serif}
a{color:inherit;text-decoration:none}
.wrap{max-width:780px;margin:0 auto}
header{text-align:center;padding:34px 0 0}
header h1{font:400 clamp(44px,11vw,84px)/1 Uni,serif}
header .sub{font:400 12px "Noto Sans TC",sans-serif;letter-spacing:.5em;color:#3c382f;margin:10px 0 6px}
header .pub{font:400 12px "Noto Sans TC",sans-serif;letter-spacing:.25em;color:var(--mute)}
.bar{border-top:3px solid var(--ink);border-bottom:1px solid var(--ink);margin:18px 0 26px;padding:6px 2px;display:flex;justify-content:space-between;gap:12px;font:400 13px "Noto Sans TC",sans-serif}
.bar b{color:var(--red)}
.resume{display:none;margin:-12px 0 22px;padding:9px 12px;background:var(--box);font:400 14px "Noto Sans TC",sans-serif}
.resume a{color:var(--red);font-weight:700;margin-left:6px}
.latest{display:block;border-bottom:1px solid var(--ink);padding-bottom:24px}
.kicker{display:flex;gap:10px;align-items:center;font:700 13px "Noto Sans TC",sans-serif;color:var(--red);letter-spacing:.04em}
.kicker .today{background:var(--red);color:var(--paper);padding:1px 7px;letter-spacing:.2em}
.latest h2{font:900 clamp(26px,5vw,38px)/1.3 "Noto Serif TC",serif;margin:8px 0 10px}
.latest:hover h2{color:var(--red)}
.latest p{color:#2f2b24}
.latest .go{display:inline-block;margin-top:14px;background:var(--red);color:var(--paper);font:700 14px "Noto Sans TC",sans-serif;letter-spacing:.2em;padding:9px 18px}
.teasers{list-style:none;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin:20px 0 0;border-top:1px solid var(--rule)}
.teasers li{padding:12px 14px 0 0;font:700 15px/1.45 "Noto Serif TC",serif}
.teasers .tg{display:block;font:700 12px "Noto Sans TC",sans-serif;color:var(--red)}
.teasers em{display:block;font:400 12px "Noto Sans TC",sans-serif;color:var(--mute);font-style:normal;margin-top:3px}
#archive{margin-top:40px;scroll-margin-top:12px}
#archive>h2{font:900 13px "Noto Sans TC",sans-serif;letter-spacing:.2em;color:var(--red);border-top:3px solid var(--ink);border-bottom:1px solid var(--ink);padding:6px 0;margin-bottom:14px;display:flex;justify-content:space-between}
#archive>h2 small{font-weight:400;letter-spacing:.05em;color:var(--mute)}
.tools{display:flex;flex-direction:column;gap:10px;margin-bottom:6px}
.search{display:flex;align-items:center;border-bottom:1.5px solid var(--ink);padding:4px 2px}
.search input{flex:1;border:0;background:none;font:400 16px "Noto Sans TC",sans-serif;color:var(--ink);outline:0;padding:6px 4px}
.search svg{flex:none;opacity:.6}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips button{font:500 13px "Noto Sans TC",sans-serif;border:1px solid var(--rule);background:none;color:var(--ink);padding:4px 10px;border-radius:2px;cursor:pointer}
.chips button[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:var(--paper)}
.chips button i{font-style:normal;opacity:.6;margin-left:4px;font-size:12px}
.month h3{font:900 18px "Noto Serif TC",serif;margin:22px 0 4px;display:flex;justify-content:space-between;align-items:baseline}
.month h3 small{font:400 12px "Noto Sans TC",sans-serif;color:var(--mute)}
.month ol{list-style:none}
.row a{display:grid;grid-template-columns:62px 1fr;gap:4px 14px;padding:10px 0;border-bottom:1px dotted var(--rule)}
.row a:hover .h{color:var(--red)}
.row .d{grid-row:span 2;font:700 15px "Noto Sans TC",sans-serif;position:relative}
.row .d i{display:block;font:400 12px "Noto Sans TC",sans-serif;font-style:normal;color:var(--mute)}
.row .h{font:700 16px/1.5 "Noto Serif TC",serif}
.row .c{font:400 12px "Noto Sans TC",sans-serif;color:var(--mute)}
.row .c b{color:var(--red);font-weight:500;margin-right:8px}
.row .c b:empty{display:none}
.row.unread .d:after{content:"";position:absolute;left:-12px;top:8px;width:6px;height:6px;border-radius:50%;background:var(--red)}
.row.read .h{color:#4a453b;font-weight:500}
.hits{display:none;list-style:none;margin:0 0 6px 76px;padding:0;font:15px/1.5 "Noto Serif TC",serif}
.hits li{display:none;padding:5px 0 5px 12px;border-left:2px solid var(--red)}
.hits li.on{display:block}
.hits a{color:var(--ink)}.hits a:hover{color:var(--red)}
.searching .hits{display:block}
.empty{display:none;padding:28px 0;text-align:center;font:400 14px "Noto Sans TC",sans-serif;color:var(--mute)}
footer{margin-top:40px;border-top:1px solid var(--ink);padding-top:8px;font:400 12px "Noto Sans TC",sans-serif;color:var(--mute);display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px}
@media (max-width:600px){.row.unread .d:after{left:-9px}.bar{flex-direction:column;gap:2px}}
"""

INDEX_JS = r"""
(function(){
  function get(k){try{return localStorage.getItem(k)}catch(e){return null}}
  var read={};try{read=JSON.parse(get('tt-read')||'{}')}catch(e){}
  var rows=[].slice.call(document.querySelectorAll('.row'));
  var seen=Object.keys(read).length>0;
  rows.forEach(function(r){ if(read[r.dataset.id]) r.classList.add('read'); else if(seen) r.classList.add('unread'); });
  // 今日／最新
  var t=new Date(),pad=function(n){return(n<10?'0':'')+n};
  var today=t.getFullYear()+pad(t.getMonth()+1)+pad(t.getDate());
  var lat=document.querySelector('.latest');
  if(lat&&lat.dataset.id===today){document.querySelector('.kicker .today').style.display='inline';document.querySelector('.latest .go').textContent='閱讀今日晨報';}
  // 上次讀到
  var last=get('tt-last');
  if(last&&lat&&last!==lat.dataset.id){var row=document.querySelector('.row[data-id="'+last+'"]');
    if(row){var box=document.querySelector('.resume');box.querySelector('a').href='/e/'+last+'/';
      box.querySelector('a').textContent=row.querySelector('.h').textContent.slice(0,28)+'…（'+row.dataset.md+'）';box.style.display='block';}}
  // 搜尋與分類
  var q=document.querySelector('.search input'),cat='',chips=[].slice.call(document.querySelectorAll('.chips button'));
  function apply(){var s=(q.value||'').trim().toLowerCase(),n=0;
    document.getElementById('archive').classList.toggle('searching',!!s);
    rows.forEach(function(r){var hit=0;r.querySelectorAll('.hits li').forEach(function(li){var m=!!s&&li.dataset.q.indexOf(s)>-1;li.classList.toggle('on',m);if(m)hit++;});
      var ok=(!cat||r.dataset.cat===cat)&&(!s||r.dataset.q.indexOf(s)>-1);r.style.display=ok?'':'none';if(ok)n++;});
    document.querySelectorAll('.month').forEach(function(m){var v=[].some.call(m.querySelectorAll('.row'),function(r){return r.style.display!=='none'});m.style.display=v?'':'none';});
    document.querySelector('.empty').style.display=n?'none':'block';document.querySelector('#archive h2 small').textContent=(s||cat)?('符合 '+n+' 期'):('共 '+rows.length+' 期');}
  q.addEventListener('input',apply);
  chips.forEach(function(b){b.addEventListener('click',function(){cat=(cat===b.dataset.cat)?'':b.dataset.cat;
    chips.forEach(function(x){x.setAttribute('aria-pressed',x.dataset.cat===cat&&cat!==''?'true':'false')});
    if(!cat)chips[0].setAttribute('aria-pressed','true');apply();});});
  document.addEventListener('keydown',function(e){if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus();}});
})();
"""


def esc(s):
    return H.escape(s or "", quote=True)


def build_index(entries):
    entries = sorted(entries, key=lambda e: e["id"], reverse=True)
    latest = entries[0]
    teas = "".join(f'<li><span class="tg">{esc(t["tag"])}</span>{esc(t["title"])}<em>{esc(t["where"])}</em></li>'
                   for t in latest.get("teasers", []))
    teas_html = f'<ul class="teasers">{teas}</ul>' if teas else ""
    counts = {}
    for e in entries:
        c = e.get("cat") or category_of(e.get("tag"))
        e["_cat"] = c
        if c:
            counts[c] = counts.get(c, 0) + 1
    chips = '<button data-cat="" aria-pressed="true">全部</button>' + "".join(
        f'<button data-cat="{c}" aria-pressed="false">{c}<i>{counts[c]}</i></button>' for c in CATEGORIES if c in counts)
    groups = {}
    for e in entries:
        groups.setdefault(e["id"][:6], []).append(e)
    months = []
    for ym, es in groups.items():
        rows = []
        for e in es:
            d = dt.date.fromisoformat(e["date"])
            sts = e.get("stories", [])
            q = (e["headline"] + " " + e.get("tag", "") + " " + e["_cat"] + " " + e.get("deck", "") + " "
                 + " ".join(x["t"] for x in sts)).lower()
            hits = "".join(f'<li data-q="{esc(x["t"].lower())}"><a href="/e/{e["id"]}/#s-{x["id"]}">{esc(x["t"])}</a></li>'
                           for x in sts)
            src = "原版面" if e.get("source") == "pdf" else "網頁版"
            rows.append(f'<li class="row" data-id="{e["id"]}" data-md="{d.month}/{d.day}" data-cat="{esc(e["_cat"])}" '
                        f'data-q="{esc(q)}"><a href="/e/{e["id"]}/"><span class="d">{d.month}/{d.day}<i>週{WEEK[d.weekday()]}</i></span>'
                        f'<span class="h">{esc(e["headline"])}</span>'
                        f'<span class="c"><b>{esc(e["_cat"])}</b>{len(sts) or ""}{" 則　" if sts else ""}{e.get("pages", "")} 版</span></a>'
                        f'<ul class="hits">{hits}</ul></li>')
        months.append(f'<section class="month"><h3>{int(ym[:4])} 年 {int(ym[4:])} 月<small>{len(es)} 期</small></h3>'
                      f'<ol>{"".join(rows)}</ol></section>')
    ld = dt.date.fromisoformat(latest["date"])
    kick_tag = esc(latest.get("_cat") or latest.get("tag"))
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">{HEAD_META}
<title>Trester Times</title>{FONTS_LINK}<style>{INDEX_CSS}</style></head><body><div class="wrap">
<header><h1>Trester Times</h1><div class="sub">每日晨報　·　城市／地方／制度／世界</div><div class="pub">發行人　Cho-Yun, Huang</div></header>
<div class="bar"><span><b>最新一期</b>　{esc(latest["date_zh"])}</span><span><a href="/e/{latest["id"]}/">回今日報 →</a></span></div>
<div class="resume">上次讀到<a href="#"></a></div>
<a class="latest" href="/e/{latest["id"]}/" data-id="{latest["id"]}"><div class="kicker"><span class="today" style="display:none">今日</span>{kick_tag}</div>
<h2>{esc(latest["headline"])}</h2><p>{esc(latest.get("deck"))}</p><span class="go">閱讀 {ld.month}/{ld.day} 晨報</span></a>
{teas_html}
<section id="archive"><h2>歷史資料庫<small>共 {len(entries)} 期</small></h2>
<div class="tools"><label class="search"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
<input type="search" placeholder="搜尋所有報導標題，例如：都更、碳費、地方創生" aria-label="搜尋報導"></label><div class="chips">{chips}</div></div>
{"".join(months)}<p class="empty">沒有符合的期數</p></section>
<footer><span>Trester Times　發行人 Cho-Yun, Huang　每日 09:00 出刊</span><span>本報內容為新聞彙整與編輯觀察，事實以原始來源為準</span></footer>
</div><script>{INDEX_JS}</script></body></html>'''


# ---------- 主程序 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="含 times.html 與圖片的資料夾")
    ap.add_argument("--pdf", help="改用過去的 PDF 建立當期（補上線前的舊期）")
    ap.add_argument("--meta", help="搭配 --pdf：JSON 檔，含 headline/tag/cat/deck/teasers")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--category", help="頭條類別（與 Notion 晨報歷史庫相同的選項）")
    a = ap.parse_args()
    pw = os.environ.get("TT_PASSWORD")
    if not pw:
        sys.exit("缺少環境變數 TT_PASSWORD")
    if not (a.src or a.pdf):
        sys.exit("需要 --src 或 --pdf")
    d = dt.datetime.strptime(a.date, "%Y%m%d").date()

    entries = [e for e in load_manifest(pw) if e["id"] != a.date]
    ids = sorted(e["id"] for e in entries)
    older = [i for i in ids if i < a.date]
    newer = [i for i in ids if i > a.date]
    HEADLINES.update({e["id"]: e["headline"] for e in entries})
    prev_id = older[-1] if older else None
    next_id = newer[0] if newer else None

    if a.pdf:
        meta_in = json.loads(Path(a.meta).read_text(encoding="utf-8")) if a.meta else {}
        page, meta = build_pdf_edition(Path(a.pdf).resolve(), d, prev_id, next_id, meta_in)
    else:
        page, meta, today_page = build_edition(Path(a.src).resolve(), d, prev_id, next_id)
    if a.category:
        meta["cat"] = a.category
    entries.append(meta)

    HEADLINES[a.date] = meta["headline"]
    if a.pdf:
        write_encrypted(page, ROOT / "e" / a.date / "index.html", pw)
    else:
        write_encrypted(today_page, ROOT / "e" / a.date / "index.html", pw)
        write_encrypted(page, ROOT / "e" / a.date / "paper" / "index.html", pw)
    # 讓相鄰兩期指向這一期
    if prev_id:
        set_nav(prev_id, "next", a.date, pw)
    if next_id:
        set_nav(next_id, "prev", a.date, pw)
    write_encrypted(build_index(entries), ROOT / "archive" / "index.html", pw)
    latest = max(e["id"] for e in entries)
    (ROOT / "index.html").write_text(
        f'<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex,nofollow">'
        f'<title>Trester Times</title><meta http-equiv="refresh" content="0;url=/e/{latest}/">'
        f'<script>location.replace("/e/{latest}/"+location.hash)</script><a href="/e/{latest}/">Trester Times</a>',
        encoding="utf-8")
    for e in entries:
        e.pop("_cat", None)
    save_manifest(entries, pw)
    print(json.dumps({"published": a.date, "headline": meta["headline"], "cat": meta["cat"], "pages": meta["pages"],
                      "editions": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
