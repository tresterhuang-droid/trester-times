// Trester Times 今日報：以網址 #s-NN 開啟單則，# 加版次代碼跳到該版；已讀紀錄
(function () {
  var body = document.body;
  var id = body.getAttribute('data-id');
  var front = document.getElementById('front');
  var frontY = 0;

  function getS(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function setS(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  var read = {};
  try { read = JSON.parse(getS('tt-read-s') || '{}'); } catch (e) {}
  var issues = {};
  try { issues = JSON.parse(getS('tt-read') || '{}'); } catch (e) {}
  if (id) { issues[id] = 1; setS('tt-read', JSON.stringify(issues)); setS('tt-last', id); }

  function markRead() {
    document.querySelectorAll('#front a.li').forEach(function (a) {
      var sid = (a.getAttribute('href') || '').replace('#s-', '');
      if (read[id + '-' + sid]) a.classList.add('read');
    });
  }

  function show() {
    var h = decodeURIComponent(location.hash || '');
    var m = h.match(/^#s-([\w-]+)$/);
    document.querySelectorAll('article.story').forEach(function (a) { a.hidden = true; });
    if (m) {
      var art = document.getElementById('s-' + m[1]);
      if (art) {
        if (!body.classList.contains('reading')) frontY = window.scrollY;
        body.classList.add('reading');
        art.hidden = false;
        window.scrollTo(0, 0);
        read[id + '-' + m[1]] = 1; setS('tt-read-s', JSON.stringify(read));
        var t = art.querySelector('h1');
        document.title = 'Trester Times｜' + (t ? t.textContent : '');
        return;
      }
    }
    var wasReading = body.classList.contains('reading');
    body.classList.remove('reading');
    document.title = document.title.replace(/｜.*$/, '') + '｜' + (body.getAttribute('data-date') || '');
    markRead();
    var target = h.length > 1 ? document.getElementById(h.slice(1)) : null;
    if (target && front.contains(target)) target.scrollIntoView();
    else if (wasReading) window.scrollTo(0, frontY);
  }
  window.addEventListener('hashchange', show);
  show();

  // 版次分頁列：隨捲動標示目前所在的版
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tabs a'));
  var secs = tabs.map(function (a) { return document.getElementById(a.getAttribute('data-tab')); });
  var ticking = false;
  function onScroll() {
    if (ticking || body.classList.contains('reading')) return;
    ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      var cur = 0;
      secs.forEach(function (s, i) { if (s && s.getBoundingClientRect().top < 130) cur = i; });
      tabs.forEach(function (a, i) { a.classList.toggle('on', i === cur); });
      var on = tabs[cur];
      if (on && on.parentNode.scrollWidth > on.parentNode.clientWidth) {
        var p = on.parentNode, l = on.offsetLeft - p.clientWidth / 2 + on.clientWidth / 2;
        if (Math.abs(p.scrollLeft - l) > 40) p.scrollLeft = l;
      }
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // 鍵盤：單則閱讀時 ← → 換則，Esc 回今日報
  document.addEventListener('keydown', function (e) {
    if (!body.classList.contains('reading') || e.metaKey || e.ctrlKey || e.altKey) return;
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    var art = document.querySelector('article.story:not([hidden])');
    if (!art) return;
    var pv = art.querySelector('.pn .pv'), nx = art.querySelector('.pn .nx'), bk = art.querySelector('.back');
    if (e.key === 'ArrowLeft' && pv) location.hash = pv.getAttribute('href');
    if (e.key === 'ArrowRight' && nx) location.hash = nx.getAttribute('href');
    if (e.key === 'Escape' && bk) location.hash = bk.getAttribute('href');
  });
})();
