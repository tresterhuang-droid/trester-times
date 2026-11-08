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
    if (!sheets || body.classList.contains('tt-read')) return;
    document.querySelectorAll('.page').forEach(function (pg) {
      pg.classList.remove('grow');
      var b = pg.querySelector('.body') || pg.querySelector('.fgrid');
      if (!b) return;
      var kids = Array.prototype.slice.call(b.children), best = 1, z;
      var over = function (v) { kids.forEach(function (k) { k.style.zoom = v; }); return b.scrollHeight - b.clientHeight > 1; };
      if (over(1)) {            // 內容超出一頁：縮小到剛好放得下
        for (z = 0.99; z >= 0.6; z -= 0.01) { best = z; if (!over(z)) break; }
      } else {                  // 內容不足一頁：放大到剛好填滿
        for (z = 1.01; z <= 1.6; z += 0.01) { if (over(z)) break; best = z; }
      }
      kids.forEach(function (k) { k.style.zoom = best; });
      // 縮到下限仍放不下：讓這一版往下延伸，避免文字壓到頁尾
      if (b.scrollHeight - b.clientHeight > 1) pg.classList.add('grow');
    });
  }
  // 字型分批載入（iPhone 等沒有內建思源字型的裝置）時，每載完一批就重新填版
  var refitTimer;
  function refit() { clearTimeout(refitTimer); refitTimer = setTimeout(function () { fitPages(); scaleSheets(); }, 120); }
  // 整體縮放改用 transform：文字以原尺寸排版後再等比縮小，
  // 不會觸發 Safari 的最小字級限制（以 zoom 縮小時，小字會被放大回來而溢出）。
  function scaleSheets() {
    if (!sheets) return;
    var st = sheets.style;
    st.zoom = '';
    if (body.classList.contains('tt-read')) { st.transform = st.width = st.marginBottom = ''; return; }
    var full = PAGE_W + 32, vw = document.documentElement.clientWidth;
    var s = Math.min(1, vw / full);
    if (s >= 1) { st.transform = st.width = st.marginBottom = ''; return; }
    st.width = full + 'px';
    st.transformOrigin = '0 0';
    st.transform = 'scale(' + s + ')';
    st.marginBottom = (-(sheets.offsetHeight * (1 - s))) + 'px';
  }
  function setMode(mode, save) {
    body.classList.toggle('tt-read', mode === 'read');
    document.querySelectorAll('[data-mode]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-mode') === mode ? 'true' : 'false');
    });
    if (save) setS(KEY, mode);
    if (mode === 'page' && fitted) refit(); else scaleSheets();
  }
  var fitted = false;
  document.querySelectorAll('[data-mode]').forEach(function (b) {
    b.addEventListener('click', function () { setMode(b.getAttribute('data-mode'), true); });
  });
  var pr = document.querySelector('[data-print]');
  if (pr) pr.addEventListener('click', function () { if (sheets) setMode('page'); window.print(); });

  if (sheets) {
    var initial = getS(KEY) || (document.documentElement.clientWidth < 760 ? 'read' : 'page');
    setMode(initial);
    var ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    ready.then(function () { fitted = true; fitPages(); scaleSheets(); });
    if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener('loadingdone', refit);
    window.addEventListener('load', refit);
    setTimeout(refit, 1500); setTimeout(refit, 4000);
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
