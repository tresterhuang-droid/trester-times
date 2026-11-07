#!/usr/bin/env python3
"""Trester Times 網站發布腳本。

把當日排程產出的 times.html（及同資料夾的圖片）轉成網頁版、加密後放進網站，
並更新首頁與歸檔。

用法：
  TT_PASSWORD=... python3 _tools/publish.py --src /path/to/build_dir --date 20261108

需要：Python 3 + beautifulsoup4；Node（第一次執行會自動 npm install staticrypt）。
"""
import argparse, base64, datetime as dt, json, mimetypes, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from bs4 import BeautifulSoup

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
        subprocess.run([staticrypt_bin(), str(enc_path), "--decrypt", "-d", td, "-c", CONFIG.name, "--short"], cwd=TOOLS,
                       check=True, env={**os.environ, "STATICRYPT_PASSWORD": password},
                       stdout=subprocess.DEVNULL)
        return (Path(td) / enc_path.name).read_text(encoding="utf-8")


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
        p.write_text(f'<!doctype html><meta charset="utf-8"><script type="application/json" id="m">{data}</script>', encoding="utf-8")
        encrypt(p, MANIFEST_ENC, password)


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def date_zh(d: dt.date):
    return f"{d.year}年{d.month}月{d.day}日　星期{WEEK[d.weekday()]}"


def build_edition(src: Path, d: dt.date, prev_id):
    soup = BeautifulSoup((src / "times.html").read_text(encoding="utf-8"), "html.parser")

    # 1. 圖片內嵌成 data URI，讓圖片跟著頁面一起加密
    for img in soup.find_all("img"):
        s = img.get("src", "")
        if s.startswith(("data:", "http:", "https:")):
            continue
        f = (src / s)
        if f.exists():
            mime = mimetypes.guess_type(f.name)[0] or "image/png"
            img["src"] = f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
        else:
            img.decompose()

    # 2. 字型路徑改到網站共用資產；中文字型加上網頁字型後備
    for st in soup.find_all("style"):
        css = st.string or ""
        css = re.sub(r"url\((uni|pf9|pf7)\.woff2\)", r"url(/assets/fonts/\1.woff2)", css)
        css = css.replace('"Noto Serif CJK TC"', '"Noto Serif CJK TC","Noto Serif TC"')
        css = css.replace('"Noto Sans CJK TC"', '"Noto Sans CJK TC","Noto Sans TC"')
        st.string = css

    # 3. 擷取首頁與歸檔需要的資訊
    main = soup.select_one(".fgrid .main")
    headline = txt(main.find("h2")) if main else ""
    lead_tag = txt(main.select_one(".tag")) if main else ""
    deck = txt(main.select_one(".deck")) if main else ""
    teasers = [{"tag": txt(t.select_one(".tg")), "title": txt(t.select_one(".tt")), "where": txt(t.select_one(".tp"))}
               for t in soup.select(".teasers > div")]
    pages = len(soup.select(".page"))
    meta = {"id": d.strftime("%Y%m%d"), "date": d.isoformat(), "date_zh": date_zh(d),
            "headline": headline, "tag": lead_tag, "deck": deck, "teasers": teasers, "pages": pages}

    # 4. 網頁外框：工具列＋版面容器
    head = soup.head
    head.title.string = f"Trester Times｜{date_zh(d)}"
    head.insert(0, BeautifulSoup('<meta name="viewport" content="width=device-width, initial-scale=1">'
                                 '<meta name="robots" content="noindex,nofollow">' + FONTS_LINK, "html.parser"))
    head.append(BeautifulSoup('<link rel="stylesheet" href="/assets/web.css">', "html.parser"))
    prev = f'<a href="/e/{prev_id}/">‹ 前一期</a>' if prev_id else ""
    bar = BeautifulSoup(
        f'<nav class="tt-bar"><a class="home" href="/">Trester Times</a><span class="date">{date_zh(d)}</span>'
        f'<span class="sp"></span>{prev}<a href="/#archive">歸檔</a>'
        f'<span class="seg"><button data-mode="page">版面</button><button data-mode="read">閱讀</button></span>'
        f'<button data-print>列印</button></nav>', "html.parser")
    wrap = soup.new_tag("main", attrs={"class": "tt-sheets"})
    for pg in soup.select("section.page"):
        wrap.append(pg.extract())
    soup.body.clear()
    soup.body.append(bar)
    soup.body.append(wrap)
    soup.body.append(BeautifulSoup('<script src="/assets/web.js"></script>', "html.parser"))
    return str(soup), meta


PDF_CSS = """
@font-face{font-family:Uni;src:url(/assets/fonts/uni.woff2)}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#cfc8b8}
.pdfpages{padding:24px 12px 40px}
.pdfpages img{display:block;width:100%;max-width:794px;margin:0 auto 20px;box-shadow:0 1px 2px rgba(0,0,0,.18),0 6px 24px rgba(0,0,0,.14);background:#f3efe3}
.note{max-width:794px;margin:0 auto 14px;font:400 13px/1.6 "Noto Sans TC","Noto Sans CJK TC",sans-serif;color:#3b372e}
@media (max-width:600px){.pdfpages{padding:12px 0 30px}.pdfpages img{margin-bottom:10px}.note{padding:0 12px}}
@media print{body{background:none;padding:0}.tt-bar,.note{display:none}.pdfpages{padding:0}.pdfpages img{margin:0;box-shadow:none;max-width:none;page-break-after:always}}
"""


def build_pdf_edition(pdf: Path, d: dt.date, prev_id, meta_in: dict):
    """由過去的 PDF 建立網頁版：每頁轉成圖片內嵌（無法切換閱讀模式）。"""
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", "120", "-jpeg", "-jpegopt", "quality=74", str(pdf), f"{td}/p"], check=True)
        imgs = sorted(Path(td).glob("p-*.jpg"), key=lambda f: int(f.stem.split("-")[1]))
        tags = "".join(f'<img alt="第{i}版" src="data:image/jpeg;base64,{base64.b64encode(f.read_bytes()).decode()}">'
                       for i, f in enumerate(imgs, 1))
    prev = f'<a href="/e/{prev_id}/">‹ 前一期</a>' if prev_id else ""
    html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Trester Times｜{date_zh(d)}</title>{FONTS_LINK}<style>{PDF_CSS}</style>
<link rel="stylesheet" href="/assets/web.css"></head><body>
<nav class="tt-bar"><a class="home" href="/">Trester Times</a><span class="date">{date_zh(d)}</span><span class="sp"></span>{prev}<a href="/#archive">歸檔</a><button onclick="print()" data-print>列印</button></nav>
<main class="pdfpages"><p class="note">本期為網站上線前的存檔，以 PDF 版面呈現。</p>{tags}</main></body></html>'''
    meta = {"id": d.strftime("%Y%m%d"), "date": d.isoformat(), "date_zh": date_zh(d),
            "headline": meta_in.get("headline", ""), "tag": meta_in.get("tag", ""), "deck": meta_in.get("deck", ""),
            "teasers": meta_in.get("teasers", []), "pages": len(imgs), "source": "pdf"}
    return html, meta


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_index(entries):
    entries = sorted(entries, key=lambda e: e["id"], reverse=True)
    latest = entries[0]
    teas = "".join(f'<li><span class="tg">{esc(t["tag"])}</span>{esc(t["title"])}<em>{esc(t["where"])}</em></li>'
                   for t in latest.get("teasers", []))
    groups, rows = {}, []
    for e in entries:
        groups.setdefault(e["id"][:6], []).append(e)
    for ym, es in groups.items():
        rows.append(f'<h3>{int(ym[:4])} 年 {int(ym[4:])} 月<small>{len(es)} 期</small></h3><ol>')
        for e in es:
            d = dt.date.fromisoformat(e["date"])
            rows.append(f'<li><a href="/e/{e["id"]}/"><span class="d">{d.month}/{d.day}<i>週{WEEK[d.weekday()]}</i></span>'
                        f'<span class="h">{esc(e["headline"])}</span></a></li>')
        rows.append('</ol>')
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Trester Times</title>{FONTS_LINK}
<style>
@font-face{{font-family:Uni;src:url(/assets/fonts/uni.woff2)}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f3efe3;color:#1a1814;font:400 16px/1.7 "Noto Serif TC","Noto Serif CJK TC","Songti TC","PMingLiU",serif;padding:0 18px 64px}}
a{{color:inherit;text-decoration:none}}
.wrap{{max-width:760px;margin:0 auto}}
header{{text-align:center;padding:36px 0 0}}
header h1{{font:400 clamp(44px,11vw,84px)/1 Uni,serif}}
header .sub{{font:400 12px "Noto Sans TC",sans-serif;letter-spacing:.5em;color:#3c382f;margin:10px 0 6px}}
header .pub{{font:400 12px "Noto Sans TC",sans-serif;letter-spacing:.25em;color:#5d574b}}
.bar{{border-top:3px solid #1a1814;border-bottom:1px solid #1a1814;margin:18px 0 28px;padding:6px 2px;display:flex;justify-content:space-between;font:400 13px "Noto Sans TC",sans-serif}}
.bar b{{color:#8a1c1c}}
.latest{{display:block;border-bottom:1px solid #1a1814;padding-bottom:24px}}
.tag{{font:700 13px "Noto Sans TC",sans-serif;color:#8a1c1c;letter-spacing:.04em}}
.latest h2{{font:900 clamp(26px,5vw,38px)/1.3 "Noto Serif TC",serif;margin:6px 0 10px}}
.latest p{{color:#2f2b24}}
.latest .go{{display:inline-block;margin-top:14px;background:#8a1c1c;color:#f3efe3;font:700 14px "Noto Sans TC",sans-serif;letter-spacing:.2em;padding:9px 18px}}
.teasers{{list-style:none;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0;margin:22px 0 0;border-top:1px solid #8f8877}}
.teasers li{{padding:12px 14px 0 0;font:700 15px/1.45 "Noto Serif TC",serif}}
.teasers .tg{{display:block;font:700 12px "Noto Sans TC",sans-serif;color:#8a1c1c}}
.teasers em{{display:block;font:400 12px "Noto Sans TC",sans-serif;color:#5d574b;font-style:normal;margin-top:3px}}
#archive{{margin-top:40px}}
#archive>h2{{font:900 13px "Noto Sans TC",sans-serif;letter-spacing:.4em;color:#8a1c1c;border-top:3px solid #1a1814;border-bottom:1px solid #1a1814;padding:6px 0;margin-bottom:8px}}
#archive h3{{font:900 18px "Noto Serif TC",serif;margin:22px 0 4px;display:flex;justify-content:space-between;align-items:baseline}}
#archive h3 small{{font:400 12px "Noto Sans TC",sans-serif;color:#5d574b}}
#archive ol{{list-style:none}}
#archive li a{{display:flex;gap:16px;padding:9px 0;border-bottom:1px dotted #8f8877}}
#archive li a:hover .h{{color:#8a1c1c}}
#archive .d{{flex:none;width:64px;font:700 15px "Noto Sans TC",sans-serif}}
#archive .d i{{display:block;font:400 12px "Noto Sans TC",sans-serif;font-style:normal;color:#5d574b}}
#archive .h{{font:700 16px/1.5 "Noto Serif TC",serif}}
footer{{margin-top:40px;border-top:1px solid #1a1814;padding-top:8px;font:400 12px "Noto Sans TC",sans-serif;color:#5d574b;display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px}}
</style></head><body><div class="wrap">
<header><h1>Trester Times</h1><div class="sub">每日晨報　·　城市／地方／制度／世界</div><div class="pub">發行人　Cho-Yun, Huang</div></header>
<div class="bar"><span><b>最新一期</b>　{esc(latest["date_zh"])}</span><span>共 {len(entries)} 期</span></div>
<a class="latest" href="/e/{latest["id"]}/"><div class="tag">{esc(latest.get("tag"))}</div><h2>{esc(latest["headline"])}</h2>
<p>{esc(latest.get("deck"))}</p><span class="go">閱讀今日晨報</span></a>
<ul class="teasers">{teas}</ul>
<section id="archive"><h2>歸　檔</h2>{"".join(rows)}</section>
<footer><span>Trester Times　發行人 Cho-Yun, Huang　每日 09:00 出刊</span><span>本報內容為新聞彙整與編輯觀察，事實以原始來源為準</span></footer>
</div></body></html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="含 times.html 與圖片的資料夾")
    ap.add_argument("--pdf", help="改用過去的 PDF 建立當期（補上線前的舊期）")
    ap.add_argument("--meta", help="搭配 --pdf：JSON 檔，含 headline/tag/deck/teasers")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    a = ap.parse_args()
    pw = os.environ.get("TT_PASSWORD")
    if not pw:
        sys.exit("缺少環境變數 TT_PASSWORD")
    d = dt.datetime.strptime(a.date, "%Y%m%d").date()

    entries = [e for e in load_manifest(pw) if e["id"] != a.date]
    older = sorted(e["id"] for e in entries if e["id"] < a.date)
    prev_id = older[-1] if older else None
    if a.pdf:
        meta_in = json.loads(Path(a.meta).read_text(encoding="utf-8")) if a.meta else {}
        html, meta = build_pdf_edition(Path(a.pdf).resolve(), d, prev_id, meta_in)
    else:
        html, meta = build_edition(Path(a.src).resolve(), d, prev_id)
    entries.append(meta)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "index.html"
        p.write_text(html, encoding="utf-8")
        encrypt(p, ROOT / "e" / a.date / "index.html", pw, title="Trester Times")
        p.write_text(build_index(entries), encoding="utf-8")
        encrypt(p, ROOT / "index.html", pw, title="Trester Times")
    save_manifest(entries, pw)
    print(json.dumps({"published": a.date, "headline": meta["headline"], "pages": meta["pages"],
                      "editions": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
