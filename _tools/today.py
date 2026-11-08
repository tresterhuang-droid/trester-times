"""今日報（方案A）與單則閱讀（方案B）。

parse_issue(soup)：把 template.py 產生的報紙 HTML 解析成結構化資料。
render_today(issue, ...)：產生網頁原生的「今日報」頁面，單則以 #s-NN 開啟。
"""
import difflib
import html as H
import re

WEEK = "一二三四五六日"


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def esc(s):
    return H.escape(s or "", quote=True)


def split_tag(el):
    """標籤「大類|細類　No.1103-09◆」→ (大類, 細類, 編號, 是否寫入週報候選)"""
    if not el:
        return "", "", "", False
    span = el.find("span")
    a = txt(el).split("|")[0].strip()
    b = txt(span) if span else ""
    m = re.search(r"No\.\s*(\d{4}-\d{2})\s*(◆?)", b)
    no, star = (m.group(1), bool(m.group(2))) if m else ("", False)
    b = re.sub(r"\s*No\.\s*\d{4}-\d{2}\s*◆?", "", b).strip()
    return a, b, no, star


def paras(el):
    out = {}
    for p in el.select("p"):
        lb = p.select_one(".lb")
        if not lb:
            continue
        k = txt(lb)
        v = txt(p)[len(k):].strip() if txt(p).startswith(k) else txt(p)
        out[k] = v
    return out


def fig_of(el):
    if not el:
        return None
    img = el.find("img")
    cap = el.find("figcaption")
    credit = txt(cap.find("i")) if cap and cap.find("i") else ""
    c = txt(cap)
    if credit and c.endswith(credit):
        c = c[: -len(credit)].strip()
    return {"src": img.get("src", "") if img else "", "cap": c, "credit": re.sub(r"^圖／", "", credit)}


def story_of(el, page, kind, fig=None):
    tagel = el.select_one(".tag")
    a, b, no, star = split_tag(tagel)
    ps = paras(el)
    src = txt(el.select_one(".src"))
    src = re.sub(r"^資料來源[:：]\s*", "", src)
    return {"cat": a, "sub": b, "no": no, "star": star, "title": txt(el.find("h2")), "deck": txt(el.select_one(".deck")),
            "dao": ps.get("導言", ""), "mai": ps.get("脈絡", ""), "hou": ps.get("後續觀察", ""), "src": src,
            "page": page, "kind": kind, "fig": fig}


def parse_issue(soup):
    issue = {"pages": [], "stories": [], "teasers": [], "papers": [], "side": [], "stats": [], "boxes": []}
    for i, pg in enumerate(soup.select("section.page")):
        if i == 0:
            code, zh, en = "A1", "要聞", "FRONT PAGE"
            issue["pages"].append({"code": code, "zh": zh, "en": en, "items": []})
            for t in pg.select(".teasers > div"):
                a, b, _, _ = split_tag(t.select_one(".tg"))
                issue["teasers"].append({"cat": a, "sub": b, "title": txt(t.select_one(".tt")), "where": txt(t.select_one(".tp"))})
            bar = pg.select_one(".bar")
            issue["date_line"] = txt(bar.select("span")[1]) if bar and len(bar.select("span")) > 1 else ""
            main = pg.select_one(".fgrid .main")
            if main:
                second = main.select_one(".story")
                lead_el = soup.new_tag("div")
                for ch in list(main.children):
                    if ch is second:
                        break
                    lead_el.append(ch.__copy__() if hasattr(ch, "__copy__") else ch)
                lead = story_of(lead_el, code, "lead", fig_of(lead_el.select_one("figure")))
                for s in lead_el.select(".stats > div"):
                    b_ = s.find("b")
                    small = b_.find("small") if b_ else None
                    unit = txt(small)
                    num = txt(b_)[: -len(unit)].strip() if unit and txt(b_).endswith(unit) else txt(b_)
                    issue["stats"].append({"num": num, "unit": unit, "desc": txt(s.find("span"))})
                issue["stories"].append(lead)
                issue["pages"][0]["items"].append(("story", len(issue["stories"]) - 1))
                if second:
                    issue["stories"].append(story_of(second, code, "second"))
                    issue["pages"][0]["items"].append(("story", len(issue["stories"]) - 1))
            side = pg.select_one(".fgrid .side")
            if side:
                cur = None
                for ch in side.find_all(recursive=False):
                    cls = ch.get("class") or []
                    if ch.name == "h5":
                        cur = {"title": txt(ch), "papers": [], "paras": []}
                        issue["side"].append(cur)
                    elif "paper" in cls:
                        sp = ch.select_one(".sidep")
                        issue["papers"].append({"name": txt(ch.select_one(".n")), "title": txt(ch.select_one(".t")),
                                                "note": txt(sp) if sp else ""})
                        if cur is not None:
                            cur["papers"].append(len(issue["papers"]) - 1)
                    elif "sidep" in cls and cur is not None:
                        cur["paras"].append({"text": txt(ch), "note": "note" in cls})
            continue
        b = pg.select_one(".rh .c b")
        m = re.match(r"([A-Z]\d+)", txt(b)) if b else None
        code = m.group(1) if m else f"A{i + 1}"
        zh = txt(b.find("em")) if b and b.find("em") else ""
        en = txt(pg.select_one(".rh .c small"))
        page = {"code": code, "zh": zh, "en": en, "items": []}
        issue["pages"].append(page)
        body = pg.select_one(".body")
        pending_fig = None
        for ch in (body.find_all(recursive=False) if body else []):
            cls = ch.get("class") or []
            if ch.name == "figure":
                pending_fig = fig_of(ch)
            elif "secbar" in cls:
                page["items"].append(("secbar", txt(ch)))
            elif "box" in cls:
                rows = []
                for p in ch.select("p"):
                    k = p.select_one("b.k")
                    rows.append({"k": txt(k), "v": txt(p)[len(txt(k)):].strip() if k else txt(p)})
                issue["boxes"].append({"title": txt(ch.find("h4")), "rows": rows, "page": code})
                page["items"].append(("box", len(issue["boxes"]) - 1))
            elif "halfrow" in cls:
                for h in ch.select(".half"):
                    s = story_of(h, code, "half", pending_fig)
                    pending_fig = None
                    if s["title"] or s["dao"]:
                        issue["stories"].append(s)
                        page["items"].append(("story", len(issue["stories"]) - 1))
                    else:  # 短訊、編按
                        issue["boxes"].append({"title": f'{s["cat"]}｜{s["sub"]}', "rows": [{"k": "", "v": s["deck"]}], "page": code})
                        page["items"].append(("box", len(issue["boxes"]) - 1))
            elif "story" in cls:
                issue["stories"].append(story_of(ch, code, "story", pending_fig))
                pending_fig = None
                page["items"].append(("story", len(issue["stories"]) - 1))
    # 每則的 id：取晨報編號的序號；沒有編號者依序補上
    used = set()
    for k, s in enumerate(issue["stories"]):
        sid = s["no"].split("-")[1] if s["no"] else ""
        if not sid or sid in used:
            sid = f"x{k + 1:02d}"
        used.add(sid)
        s["id"] = sid
    return issue


def five_things(issue):
    st = issue["stories"]
    out = []
    for s in st[:2]:
        out.append((s["title"], s["id"]))
    titles = [s["title"] for s in st]
    for t in issue["teasers"]:
        best, score = None, 0
        for k, tt in enumerate(titles):
            r = difflib.SequenceMatcher(None, t["title"], tt).ratio()
            if r > score:
                best, score = k, r
        sid = st[best]["id"] if best is not None and score > .3 else ""
        if sid and any(sid == o[1] for o in out):
            continue
        out.append((t["title"], sid))
    # 不足五則時，依序補上寫入週報候選的報導，再補其他報導
    have = {o[1] for o in out}
    for s in sorted(st[2:], key=lambda x: not x["star"]):
        if len(out) >= 5:
            break
        if s["id"] not in have:
            out.append((s["title"], s["id"]))
            have.add(s["id"])
    return out[:5]


CSS = """
@font-face{font-family:Uni;src:url(/assets/fonts/uni.woff2)}
@font-face{font-family:PF;font-weight:900;src:url(/assets/fonts/pf9.woff2)}
@font-face{font-family:PF;font-weight:700;src:url(/assets/fonts/pf7.woff2)}
"""


def page_label(issue, code):
    for p in issue["pages"]:
        if p["code"] == code:
            return f'{code} {p["zh"]}'.strip()
    return code


def meta_line(s, with_star=True):
    bits = [esc(s["sub"] or s["cat"])]
    if s["no"]:
        bits.append(f'<span class="no">No.{esc(s["no"])}</span>')
    if with_star and s["star"]:
        bits.append('<span class="star" title="已寫入週報候選庫">◆ 週報候選</span>')
    return "　".join(bits)


def render_story(issue, s, k, date_zh):
    st = issue["stories"]
    same = [x for x in st if x["page"] == s["page"] and x is not s][:3]
    prev_s = st[k - 1] if k > 0 else None
    next_s = st[k + 1] if k + 1 < len(st) else None
    hou = re.sub(r"^[（(]編輯觀察[）)]\s*", "", s["hou"])
    fig = ""
    if s.get("fig") and s["fig"]["src"]:
        f = s["fig"]
        fig = (f'<figure class="sfig"><img src="{f["src"]}" alt="{esc(f["cap"])}" loading="lazy">'
               f'<figcaption>{esc(f["cap"])}<i>圖／{esc(f["credit"])}</i></figcaption></figure>')
    rel = "".join(f'<a class="li" href="#s-{x["id"]}"><span class="m">{meta_line(x)}</span><span class="t">{esc(x["title"])}</span></a>' for x in same)
    pn = ""
    if prev_s:
        pn += f'<a class="pv" href="#s-{prev_s["id"]}"><small>‹ 上一則</small>{esc(prev_s["title"])}</a>'
    else:
        pn += '<span></span>'
    if next_s:
        pn += f'<a class="nx" href="#s-{next_s["id"]}"><small>下一則 ›</small>{esc(next_s["title"])}</a>'
    srcs = [x.strip() for x in re.split(r"[；;]\s*", s["src"]) if x.strip()]
    src_html = "".join(f"<li>{esc(x)}</li>" for x in srcs) or "<li>未註明</li>"
    blocks = ""
    if s["dao"]:
        blocks += f'<section class="blk"><h2><span></span>導言　發生什麼</h2><p>{esc(s["dao"])}</p></section>'
    if s["mai"]:
        blocks += f'<section class="blk"><h2><span></span>脈絡　為什麼重要</h2><p>{esc(s["mai"])}</p></section>'
    if hou:
        blocks += f'<section class="hou"><h2>後續觀察　編輯觀點</h2><p>{esc(hou)}</p></section>'
    return f'''<article class="story" id="s-{s["id"]}" data-sid="{s["id"]}" hidden>
<div class="sbar"><a class="back" href="#{esc(s["page"])}" aria-label="回今日報">‹ 今日報</a><span>{esc(page_label(issue, s["page"]))}</span></div>
<div class="sin">
<div class="kick">{esc(s["cat"])}｜{meta_line(s)}</div>
<h1>{esc(s["title"])}</h1>
{f'<p class="deck">{esc(s["deck"])}</p>' if s["deck"] else ""}
<div class="chips"><span>{esc(date_zh)}</span><span>{esc(page_label(issue, s["page"]))}</span>{"<span>資料來源 " + str(len(srcs)) + " 則</span>" if srcs else ""}</div>
{fig}{blocks}
<details class="srcs"><summary>資料來源（{len(srcs)}）<span>展開</span></summary><ul>{src_html}</ul></details>
{f'<div class="rel"><h3>{esc(page_label(issue, s["page"]))}　·　同版其他報導</h3>{rel}</div>' if rel else ""}
<nav class="pn" aria-label="上一則與下一則">{pn}</nav>
</div></article>'''


def render_today(issue, eid, date_zh, toolbar_html, count_pages):
    st = issue["stories"]
    lead = st[0] if st else None
    second = st[1] if len(st) > 1 and st[1]["kind"] == "second" else None
    n = len(st)
    # 今日五件事
    five = "".join(
        f'<li><span class="n">{k}</span>' + (f'<a href="#s-{sid}">{esc(t)}</a>' if sid else f'<span>{esc(t)}</span>') + "</li>"
        for k, (t, sid) in enumerate(five_things(issue), 1))
    # 頭條
    stats = "".join(f'<div><b>{esc(x["num"])}<small>{esc(x["unit"])}</small></b><span>{esc(x["desc"])}</span></div>' for x in issue["stats"])
    lead_html = ""
    if lead:
        hou = re.sub(r"^[（(]編輯觀察[）)]\s*", "", lead["hou"])
        lead_html = f'''<article class="lead"><div class="kick">頭條　{esc(lead["cat"])}｜{meta_line(lead)}</div>
<h1><a href="#s-{lead["id"]}">{esc(lead["title"])}</a></h1><p class="deck">{esc(lead["deck"])}</p>
{f'<div class="stats">{stats}</div>' if stats else ""}
{f'<div class="houbox"><h3>後續觀察（編輯觀察）</h3><p>{esc(hou)}</p></div>' if hou else ""}
<a class="more" href="#s-{lead["id"]}">讀全文：導言、脈絡與資料來源 →</a></article>'''
        if second:
            lead_html += (f'<a class="second" href="#s-{second["id"]}"><div class="kick">第二則要聞　{esc(second["cat"])}｜{meta_line(second)}</div>'
                          f'<h2>{esc(second["title"])}</h2><p>{esc(second["deck"])}</p></a>')
    # 側欄：三報頭版對照、編輯按、本週待追
    side = ""
    for blk in issue["side"]:
        inner = ""
        for pi in blk["papers"]:
            p = issue["papers"][pi]
            note = f'<p>{esc(p["note"])}</p>' if p["note"] else ""
            inner += f'<div class="paper"><div class="n">{esc(p["name"])}</div><div class="t">{esc(p["title"])}</div>{note}</div>'
        for pp in blk["paras"]:
            inner += f'<p class="{"note" if pp["note"] else ""}">{esc(pp["text"])}</p>'
        side += f'<div class="sideblk"><h2>{esc(blk["title"])}</h2>{inner}</div>'
    watch = next((b for b in issue["boxes"] if "待追" in b["title"]), None)
    if watch:
        rows = "".join(f'<li><b>{esc(r["k"])}</b>　{esc(r["v"])}</li>' if r["k"] else f"<li>{esc(r['v'])}</li>" for r in watch["rows"])
        side += f'<div class="watch"><h2>{esc(watch["title"])}</h2><ul>{rows}</ul></div>'
    # 各版
    secs = ""
    tabs = ['<a href="#top" data-tab="top">今日</a>']
    for p in issue["pages"][1:]:
        items = ""
        cnt = 0
        for kind, val in p["items"]:
            if kind == "story":
                s = st[val]
                cnt += 1
                items += (f'<a class="li" href="#s-{s["id"]}"><span class="m">{meta_line(s)}</span>'
                          f'<span class="t">{esc(s["title"])}</span></a>')
            elif kind == "secbar":
                items += f'<div class="secbar">{esc(val)}</div>'
            elif kind == "box":
                b = issue["boxes"][val]
                if b is watch:
                    continue
                note = "編輯手記" in b["title"]
                rows = "".join((f'<p><b>{esc(r["k"])}</b>　{esc(r["v"])}</p>' if r["k"] else f'<p>{esc(r["v"])}</p>') for r in b["rows"])
                if note:
                    items += f'<div class="notebox"><h3>{esc(b["title"])}</h3>{rows}</div>'
                else:
                    items += f'<details class="minibox"><summary>{esc(b["title"])}<span>展開</span></summary>{rows}</details>'
        secs += (f'<section class="sec" id="{esc(p["code"])}" aria-label="{esc(p["code"])} {esc(p["zh"])}"><h2><span class="c">{esc(p["code"])}</span>'
                 f'<span class="z">{esc(p["zh"])}</span><span class="k">{cnt} 則</span></h2>{items}</section>')
        tabs.append(f'<a href="#{esc(p["code"])}" data-tab="{esc(p["code"])}">{esc(p["zh"] or p["code"])}</a>')
    stories = "".join(render_story(issue, s, k, date_zh) for k, s in enumerate(st))
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Trester Times｜{esc(date_zh)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@400;700;900&display=swap">
<link rel="stylesheet" href="/assets/today.css"></head>
<body class="today" data-id="{eid}">{toolbar_html}
<nav class="tabs" aria-label="版次">{"".join(tabs)}</nav>
<main id="front">
<header class="mast" id="top"><div class="logo">Trester Times</div><div class="sub">每日晨報　·　城市／地方／制度／世界</div>
<div class="bar"><span><b>本期</b>　{esc(date_zh)}</span><span>共 {n} 則報導　·　{count_pages} 版</span><span>發行人　Cho-Yun, Huang</span></div></header>
<section class="five" aria-labelledby="five"><div><h2 id="five">今日五件事</h2><p>一分鐘掌握今天的報紙；點任一則直接讀全文。</p></div><ol>{five}</ol></section>
<div class="top"><div class="main">{lead_html}</div><aside class="side">{side}</aside></div>
<div class="secs">{secs}</div>
<a class="paperlink" href="paper/">改看報紙版（A4 原版面）</a>
<footer><span>Trester Times　發行人 Cho-Yun, Huang　每日 09:00 出刊</span><span>本報內容為新聞彙整與編輯觀察，事實以原始來源為準</span></footer>
</main>
<div id="reader">{stories}</div>
<script src="/assets/today.js"></script></body></html>'''
