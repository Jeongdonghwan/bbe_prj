// Campaign create: media select, progress, quote calc, presets/warnings, keyword toggle, pay method, paybar.
(function () {
  var M = window.MEDIA, CH = window.CHANNEL, DAYS = ['일', '월', '화', '수', '목', '금', '토'];
  var $ = function (id) { return document.getElementById(id); };
  var sel = null, price = 0;
  var mediaId = $('mediaId'), qty = $('qty'), d1 = $('d1'), d2 = $('d2');

  function fmt(n) { return n.toLocaleString() + '원'; }
  function el(id, v) { $(id).textContent = v; }

  // ---- filters
  document.querySelectorAll('.mfilter button').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.mfilter button').forEach(function (o) { o.classList.remove('on'); });
      b.classList.add('on');
      var f = b.dataset.filter;
      document.querySelectorAll('.msec').forEach(function (secEl) {
        var grid = secEl.querySelector('.mtiles'), cards = Array.prototype.slice.call(grid.querySelectorAll('.mcard'));
        var visible = 0;
        cards.forEach(function (c) {
          var show = f === 'all' || f === 'price' || c.dataset.badge === f;
          c.style.display = show ? '' : 'none'; if (show) visible++;
        });
        if (f === 'price') { cards.sort(function (a, b) { return (+a.dataset.p) - (+b.dataset.p); }); cards.forEach(function (c) { grid.appendChild(c); }); }
        secEl.style.display = visible ? '' : 'none';
      });
    });
  });

  // ---- select media
  function select(card) {
    document.querySelectorAll('.msec .mcard').forEach(function (o) { o.classList.remove('sel'); });
    card.classList.add('sel');
    var id = card.dataset.id; sel = M[id]; price = sel.price; mediaId.value = id;
    $('col1').classList.add('done'); ['col2', 'col3'].forEach(function (i) { $(i).classList.remove('dim'); });
    $('cols').classList.add('picked'); el('ssName', sel.name); el('ssPrice', fmt(price));
    var effMap = { normal: ['보통', '45%'], good: ['좋음', '72%'], best: ['매우 좋음', '100%'] };
    var lv = effMap[sel.eff] || effMap.good, ef = $('effFill');
    ef.className = 'eff-fill ' + (effMap[sel.eff] ? sel.eff : 'good');
    $('effLabel').textContent = lv[0];
    ef.style.width = '0';
    requestAnimationFrame(function () { requestAnimationFrame(function () { ef.style.width = lv[1]; }); });
    var en = $('effNote');
    if (sel.eff_note) { en.textContent = sel.eff_note; en.style.display = 'block'; } else { en.style.display = 'none'; }
    $('c2empty').style.display = 'none'; $('c2body').style.display = 'block';
    el('selName', sel.name); el('selTag', sel.tagline || '100% 실사용자 리워드'); el('selPrice', fmt(price));
    el('selMin', sel.min_days + '일'); el('selRange', sel.min_daily + ' ~ ' + sel.max_daily + '건');
    el('selCutoff', sel.cutoff); var same = $('selSame'); same.textContent = sel.same_day ? '가능' : '익일'; same.className = sel.same_day ? 'ok' : '';
    var desc = $('selDesc'), dw = $('selDescWrap');
    if (sel.desc) { desc.textContent = sel.desc; dw.style.display = 'block'; } else { dw.style.display = 'none'; }
    qty.min = sel.min_daily; qty.max = sel.max_daily;
    if (+qty.value < sel.min_daily) qty.value = sel.min_daily; if (+qty.value > sel.max_daily) qty.value = sel.max_daily;
    $('pg1').className = 'p ok'; el('pg1s', sel.name + ' · ' + fmt(price));
    $('pg2').className = 'p ok'; $('pg3').className = 'p cur';
    $('paybar').classList.add('on'); calc();
  }
  document.querySelectorAll('.msec .mcard').forEach(function (c) { c.addEventListener('click', function () { select(c); }); });

  // ---- dates / qty
  function clearPreset() { document.querySelectorAll('.presets button').forEach(function (b) { b.classList.remove('on'); }); }
  function isoDate(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  document.querySelectorAll('.presets button').forEach(function (b) {
    b.addEventListener('click', function () { clearPreset(); b.classList.add('on'); var a = new Date(d1.value + 'T00:00:00'); a.setDate(a.getDate() + (+b.dataset.n) - 1); d2.value = isoDate(a); calc(); });
  });
  d1.addEventListener('change', function () { clearPreset(); calc(); }); d2.addEventListener('change', function () { clearPreset(); calc(); });
  $('qm').addEventListener('click', function () { qty.value = Math.max(+qty.min || 50, (+qty.value || 0) - 10); calc(); });
  $('qp').addEventListener('click', function () { qty.value = Math.min(+qty.max || 500, (+qty.value || 0) + 10); calc(); });
  qty.addEventListener('input', calc);

  function calc() {
    var a = new Date(d1.value + 'T00:00:00'), b = new Date(d2.value + 'T00:00:00');
    var n = Math.max(0, Math.round((b - a) / 864e5) + 1), wd = a.getDay(), h = $('dhint'), minDays = sel ? sel.min_days : 3;
    if (isNaN(n)) { h.textContent = ''; n = 0; }
    else if (wd === 0 || wd === 6) { h.className = 'hint warn'; h.textContent = n + '일 · ' + DAYS[wd] + '요일 시작 — 주말 시작은 다음 평일부터 구동됩니다. 시작일을 평일로 바꿔주세요.'; }
    else if (n < minDays) { h.className = 'hint warn'; h.textContent = n + '일 — 최소 ' + minDays + '일 이상 설정해주세요.'; }
    else { h.className = 'hint'; h.textContent = n + '일 · ' + DAYS[wd] + '요일 시작'; }
    var q = +qty.value || 0, order = price * q * n, vat = Math.round(order * 0.1), total = order + vat;
    el('calc', price ? fmt(price) + ' × ' + q + '건 × ' + n + '일' : '');
    el('order', fmt(order)); el('vat', fmt(vat)); el('total', fmt(total));
    el('pbM', sel ? sel.name : '—'); el('pbD', price ? n + '일' : '—'); el('pbQ', price ? q + '건' : '—'); el('pbT', fmt(total));
    if (price) $('pg4').className = 'p cur';
  }

  // ---- back to media list (step accordion)
  var chg = $('ssChange');
  if (chg) chg.addEventListener('click', function () { $('cols').classList.remove('picked'); });

  // ---- checkbox visual
  document.querySelectorAll('.chk').forEach(function (c) { c.addEventListener('click', function () { setTimeout(function () { c.classList.toggle('on', c.querySelector('input').checked); }, 0); }); });

  // ---- pay method
  document.querySelectorAll('#payTabs button').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('#payTabs button').forEach(function (o) { o.classList.remove('on'); }); b.classList.add('on');
      var pm = b.dataset.pm; $('payMethod').value = pm; $('depositorRow').style.display = pm === 'bank' ? 'block' : 'none';
      el('pg4s', pm === 'bank' ? '무통장입금' : '카드 결제');
      if (!window.EDITING) $('submit').textContent = pm === 'bank' ? '입금 정보 받고 등록' : '결제하고 등록';
    });
  });

  // ---- submit guard
  $('campForm').addEventListener('submit', function (e) {
    if (!mediaId.value) { e.preventDefault(); alert('매체사를 먼저 선택해주세요.'); window.scrollTo(0, 0); }
  });

  // ---- store hub: live volume lookup
  var skw = $('skw'), svol = $('svol'), vt;
  if (skw) skw.addEventListener('input', function () {
    clearTimeout(vt); var v = skw.value.trim(); if (!v) { svol.value = ''; return; }
    vt = setTimeout(function () {
      fetch('/api/campaign/volume?kw=' + encodeURIComponent(v)).then(function (r) { return r.json(); }).then(function (j) {
        if (j.ok) svol.value = j.total.toLocaleString() + '  → 추천 ' + j.reco + '건/일';
      });
    }, 300);
  });

  // ---- init from prefill
  var pre = document.querySelector('.msec .mcard.sel');
  if (pre) select(pre); else calc();
  if (window.lucide) window.lucide.createIcons();
})();
