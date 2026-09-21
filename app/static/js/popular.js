// 인기 트래픽 — prototype_popular_traffic.html 의 openD/closeD/setSort/renderWidget 이식.
// 페이지와 대시보드 위젯이 같은 드로어를 쓴다.
(function () {
  var scrim = document.getElementById('p-scrim');
  var drawer = document.getElementById('p-drawer');
  if (!scrim || !drawer) { return; }

  /* ── 드로어 ── */
  function mark(id) {
    document.querySelectorAll('.p-card').forEach(function (c) {
      c.classList.toggle('p-on', id !== null && c.dataset.type === String(id));
    });
  }
  function close() {
    scrim.classList.remove('p-on');
    drawer.classList.remove('p-on');
    drawer.innerHTML = '';
    mark(null);
  }
  function open(id) {
    fetch('/popular/drawer/' + id, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (!html) { return; }
        drawer.innerHTML = html;
        scrim.classList.add('p-on');
        drawer.classList.add('p-on');
        mark(id);
        drawer.querySelector('.p-db').scrollTop = 0;
      });
  }
  document.addEventListener('click', function (e) {
    var row = e.target.closest('[data-type]');
    if (row) { open(row.dataset.type); return; }
    if (e.target.closest('[data-close]') || e.target === scrim) { close(); }
    var star = e.target.closest('.p-stars [data-star]');
    if (star) {
      var n = +star.dataset.star;
      document.getElementById('p-stars-val').value = n;
      drawer.querySelectorAll('.p-stars button').forEach(function (b, i) { b.classList.toggle('p-on', i < n); });
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' || e.keyCode === 27) { close(); }
  });

  /* ── 정렬 (추천순 = 순위 → 후기수) ── */
  document.querySelectorAll('[data-sort]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var mode = btn.dataset.sort;
      document.querySelectorAll('[data-sort]').forEach(function (b) { b.classList.toggle('p-on', b.dataset.sort === mode); });
      document.querySelectorAll('.p-grid').forEach(function (grid) {
        var cards = Array.prototype.slice.call(grid.children);
        cards.sort(function (a, b) {
          if (mode === 'rev') { return +b.dataset.cnt - +a.dataset.cnt; }
          if (mode === 'price') { return +a.dataset.price - +b.dataset.price; }
          return (+a.dataset.rank - +b.dataset.rank) || (+b.dataset.cnt - +a.dataset.cnt);
        });
        cards.forEach(function (c) { grid.appendChild(c); });
      });
    });
  });

  /* ── 채널 탭 (세 채널 모두 렌더돼 있어 이동 없이 전환) ── */
  document.querySelectorAll('[data-ch]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      var ch = a.dataset.ch;
      document.querySelectorAll('[data-ch]').forEach(function (b) { b.classList.toggle('p-on', b === a); });
      document.querySelectorAll('[data-chview]').forEach(function (v) { v.hidden = v.dataset.chview !== ch; });
      // 새로고침·공유 시 유지. file:// 등 일부 환경에서는 막히므로 탭 전환을 깨지 않게 감싼다.
      try { history.replaceState(null, '', '?ch=' + ch); } catch (err) { /* ignore */ }
      close();
    });
  });

  /* ── 위젯 채널 탭 ── */
  document.querySelectorAll('[data-wch]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('[data-wch]').forEach(function (b) { b.classList.toggle('p-on', b === btn); });
      document.querySelectorAll('[data-wlist]').forEach(function (l) {
        l.hidden = l.dataset.wlist !== btn.dataset.wch;
      });
    });
  });
}());
