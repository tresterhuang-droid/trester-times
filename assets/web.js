// Trester Times 網頁版：版面填版與縮放、閱讀模式、版次跳轉、前後期、已讀紀錄
(function () {
  var KEY = 'tt-mode';
  var PAGE_W = 793.7; // 210mm in CSS px
  var body = document.body;
  var bar = document.querySelector('.tt-bar');
  var id = bar && bar.getAttribute('data-id');
  var sheets = document.querySelector('.tt-sheets');

  function getS(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function setS(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  // 已讀與上次讀到
  if (id) {
    var read = {};
    try { read = JSON.parse(getS('tt-read') || '{}'); } catch (e) {}
    read[id] = 1; setS('tt-read', JSON.stringify(read)); setS('tt-last', id);
  }

  // 版面模式：與 render.js 同一套演算法，逐頁放大內容直到剛好填滿
  function fitPages() {
    document.querySelectorAll('.page').forEach(function (pg) {
      var b = pg.querySelector('.body') || pg.querySelector('.fgrid');
      if (!b) return;
      var kids = Array.prototype.slice.call(b.children), best = 1;
      for (var z = 1; z <= 1.6; z += 0.01) {
        kids.forEach(function (k) { k.style.zoom = z; });
        if (b.scrollHeight - b.clientHeight > 1) break;
        best = z;
      }
      kids.forEach(function (k) { k.style.zoom = best; });
    });
  }
  function scaleSheets() {
    if (!sheets) return;
    if (body.classList.contains('tt-read')) { sheets.style.zoom = 1; return; }
    sheets.style.zoom = Math.min(1, (document.documentElement.clientWidth - 32) / PAGE_W);
  }
  function setMode(mode, save) {
    body.classList.toggle('tt-read', mode === 'read');
    document.querySelectorAll('[data-mode]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-mode') === mode ? 'true' : 'false');
    });
    if (save) setS(KEY, mode);
    scaleSheets();
  }
  document.querySelectorAll('[data-mode]').forEach(function (b) {
    b.addEventListener('click', function () { setMode(b.getAttribute('data-mode'), true); });
  });
  var pr = document.querySelector('[data-print]');
  if (pr) pr.addEventListener('click', function () { if (sheets) setMode('page'); window.print(); });

  if (sheets) {
    var initial = getS(KEY) || (document.documentElement.clientWidth < 760 ? 'read' : 'page');
    setMode('page');
    var ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    ready.then(function () { fitPages(); setMode(initial); });
    window.addEventListener('resize', scaleSheets);
  }

  // 舊期：手機上點版面放大
  document.querySelectorAll('.pg').forEach(function (f) {
    f.addEventListener('click', function () {
      if (document.documentElement.clientWidth > 640) return;
      f.classList.toggle('zoom');
      if (f.classList.contains('zoom')) f.scrollLeft = 0;
    });
  });

  // 版次跳轉，並隨捲動標示目前所在版次
  var jump = document.querySelector('.jump');
  var anchors = Array.prototype.slice.call(document.querySelectorAll('section.page[id], .pg[id]'));
  if (jump) jump.addEventListener('change', function () {
    var t = document.getElementById(jump.value);
    if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  var prog = document.createElement('div'); prog.className = 'tt-progress'; body.appendChild(prog);
  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return; ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      var h = document.documentElement.scrollHeight - window.innerHeight;
      prog.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + '%';
      if (!jump) return;
      var cur = '';
      anchors.forEach(function (a) { if (a.getBoundingClientRect().top < 120) cur = a.id; });
      if (jump.value !== cur) jump.value = cur;
    });
  }, { passive: true });

  // 文章底部的前後期
  var prev = document.querySelector('a[data-nav=prev]'), next = document.querySelector('a[data-nav=next]');
  var main = sheets || document.querySelector('.pdfpages');
  if (main && (prev || next)) {
    var end = document.createElement('nav'); end.className = 'tt-end';
    var card = function (a, cls, label) {
      var el = document.createElement('a'); el.className = cls; el.href = a.getAttribute('href');
      var s = document.createElement('small'); s.textContent = label + '　' + a.title.split('：')[1];
      el.appendChild(s); el.appendChild(document.createTextNode(a.getAttribute('data-h') || ''));
      end.appendChild(el);
    };
    if (prev) card(prev, 'prev', '‹ 前一期');
    if (next) card(next, 'next', '下一期 ›');
    main.parentNode.insertBefore(end, main.nextSibling);
  }

  // 鍵盤：← → 換期
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'ArrowLeft' && prev) location.href = prev.getAttribute('href');
    if (e.key === 'ArrowRight' && next) location.href = next.getAttribute('href');
  });
})();
