// Trester Times 網頁版：版面模式自動填版、縮放；閱讀模式切換
(function () {
  var KEY = 'tt-mode';
  var sheets = document.querySelector('.tt-sheets');
  var PAGE_W = 793.7; // 210mm in CSS px

  function store(k, v) { try { v === undefined ? (v = localStorage.getItem(k)) : localStorage.setItem(k, v); return v; } catch (e) { return null; } }

  // 與 render.js 同一套演算法：逐頁放大內容直到剛好填滿版面
  function fitPages() {
    document.querySelectorAll('.page').forEach(function (pg) {
      var body = pg.querySelector('.body') || pg.querySelector('.fgrid');
      if (!body) return;
      var kids = Array.prototype.slice.call(body.children), best = 1;
      for (var z = 1; z <= 1.6; z += 0.01) {
        kids.forEach(function (k) { k.style.zoom = z; });
        if (body.scrollHeight - body.clientHeight > 1) break;
        best = z;
      }
      kids.forEach(function (k) { k.style.zoom = best; });
    });
  }

  function scaleSheets() {
    if (document.body.classList.contains('tt-read')) { sheets.style.zoom = 1; return; }
    var avail = document.documentElement.clientWidth - 32;
    sheets.style.zoom = Math.min(1, avail / PAGE_W);
  }

  function setMode(mode, save) {
    document.body.classList.toggle('tt-read', mode === 'read');
    document.querySelectorAll('[data-mode]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-mode') === mode ? 'true' : 'false');
    });
    if (save) store(KEY, mode);
    scaleSheets();
  }

  document.querySelectorAll('[data-mode]').forEach(function (b) {
    b.addEventListener('click', function () { setMode(b.getAttribute('data-mode'), true); });
  });
  var pr = document.querySelector('[data-print]');
  if (pr) pr.addEventListener('click', function () { setMode('page'); window.print(); });

  var saved = store(KEY);
  var initial = saved || (document.documentElement.clientWidth < 760 ? 'read' : 'page');
  setMode('page');
  var ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
  ready.then(function () { fitPages(); setMode(initial); });
  window.addEventListener('resize', scaleSheets);
})();
