// Channel campaign wizard (spec 2026-09-21): pane toggle, step guard, validation, live cost.
(function () {
  var W = window.WZ || {};
  var M = W.media || {}, MAX = W.steps || 5, BAL = W.balance || 0;
  var $ = function (id) { return document.getElementById(id); };
  var DAYS_KR = ['일', '월', '화', '수', '목', '금', '토'];
  var KEY = 'wz:' + W.channel;

  var step = 1, reached = 1, sel = null;
  var qty = $('qty'), daysVal = $('daysVal'), mediaId = $('mediaId');

  function fmt(n) { return (n || 0).toLocaleString() + '원'; }
  function err(id, msg) {
    var e = $(id), input = document.querySelector('[id="' + id.replace('e-', 'f-') + '"]');
    if (msg) { e.textContent = msg; e.hidden = false; if (input) input.classList.add('bad'); }
    else { e.hidden = true; if (input) input.classList.remove('bad'); }
    return !msg;
  }

  // ---------- step navigation ----------
  function paint() {
    document.querySelectorAll('.wz-pane').forEach(function (p) { p.hidden = +p.dataset.p !== step; });
    document.querySelectorAll('.wz-step').forEach(function (s) {
      var n = +s.dataset.go;
      s.classList.toggle('cur', n === step);
      s.classList.toggle('done', n < step || (n !== step && n <= reached));
      s.querySelector('.n').innerHTML = (n < step || (n !== step && n <= reached)) ? '✓' : n;
    });
    $('wPrev').disabled = step === 1;
    $('wNext').hidden = step === MAX;
    $('wSubmit').hidden = step !== MAX;
    if (step === 4) drawDates();
    if (step === MAX) summary();
    if (window.lucide) window.lucide.createIcons();
  }
  function go(n) {
    step = Math.min(MAX, Math.max(1, n));
    reached = Math.max(reached, step);
    paint();
    save();
    var body = document.querySelector('.wz-body');
    if (body && body.getBoundingClientRect().top < 0) body.scrollIntoView({ block: 'start' });
  }
  function validate(n) {
    if (n === 1) {
      var url = $('f-url').value.trim(), name = $('f-name').value.trim();
      var okUrl = err('e-url', url ? '' : '주소를 입력해주세요.');
      var okName = err('e-name', name.length >= 2 && name.length <= 60 ? '' : '이름을 2~60자로 입력해주세요.');
      return okUrl && okName;
    }
    if (n === 2) return err('e-media', mediaId.value ? '' : '광고 유형을 선택해주세요.');
    if (n === 3) {
      var kw = $('f-kw').value.trim();
      if (!kw) return err('e-kw', '메인 키워드를 입력해주세요.');
      if (/[,\s]/.test(kw)) return err('e-kw', '키워드는 한 개만 입력하세요.');
      return err('e-kw', '');
    }
    return true;
  }
  $('wNext').addEventListener('click', function () { if (validate(step)) go(step + 1); });
  $('wPrev').addEventListener('click', function () { go(step - 1); });
  document.querySelectorAll('.wz-step').forEach(function (b) {
    b.addEventListener('click', function () {
      var n = +b.dataset.go;
      if (n <= reached && n !== step) go(n);   // completed steps only
    });
  });

  // ---------- channel switch popover ----------
  var cb = $('chanBtn'), cp = $('chanPop');
  if (cb) {
    cb.addEventListener('click', function (e) { e.stopPropagation(); cp.hidden = !cp.hidden; });
    document.addEventListener('click', function () { cp.hidden = true; });
  }

  // ---------- step 2: ad type ----------
  function pick(card) {
    document.querySelectorAll('.msec .mcard').forEach(function (o) { o.classList.remove('sel'); });
    card.classList.add('sel');
    mediaId.value = card.dataset.id;
    sel = M[card.dataset.id];
    err('e-media', '');
    clampQty();
    save();
  }
  document.querySelectorAll('.msec .mcard').forEach(function (c) {
    c.addEventListener('click', function () { pick(c); });
  });

  // ---------- step 3: qty + memo ----------
  function clampQty() {
    var lo = 100, hi = 2000;
    if (sel) { lo = Math.max(100, Math.ceil(sel.min_daily / 100) * 100); hi = Math.max(lo, sel.max_daily || 2000); }
    var v = Math.min(hi, Math.max(lo, Math.round((+qty.value || lo) / 100) * 100));
    qty.value = v;
    $('qShow').textContent = v.toLocaleString();
  }
  $('qMinus').addEventListener('click', function () { qty.value = (+qty.value || 100) - 100; clampQty(); save(); });
  $('qPlus').addEventListener('click', function () { qty.value = (+qty.value || 100) + 100; clampQty(); save(); });
  var memo = $('f-memo');
  function memoCnt() { $('memoCnt').textContent = memo.value.length + '/500'; }
  memo.addEventListener('input', function () { memoCnt(); save(); });
  memoCnt();

  // ---------- step 4: schedule ----------
  function addDays(iso, n) { var d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + n); return d; }
  function fdate(d) {
    return d.getFullYear() + '.' + String(d.getMonth() + 1).padStart(2, '0') + '.' +
      String(d.getDate()).padStart(2, '0') + '(' + DAYS_KR[d.getDay()] + ')';
  }
  function drawDates() {
    var n = +daysVal.value;
    $('dateRange').textContent = fdate(addDays(W.startDate, 0)) + ' ~ ' + fdate(addDays(W.startDate, n - 1));
  }
  document.querySelectorAll('.dcard').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.dcard').forEach(function (o) { o.classList.remove('on'); });
      b.classList.add('on');
      daysVal.value = b.dataset.d;
      drawDates();
      save();
    });
  });

  // ---------- step 5: summary ----------
  function summary() {
    var n = +daysVal.value, q = +qty.value || 0, price = sel ? sel.price : 0;
    var daily = price * q, total = daily * n;
    $('cfName').textContent = $('f-name').value || '-';
    $('cfMedia').textContent = sel ? sel.name + ' (' + price.toLocaleString() + '원/회)' : '-';
    $('cfKw').textContent = $('f-kw').value || '-';
    $('cfQty').textContent = q.toLocaleString() + '회';
    $('cDaily').textContent = fmt(daily);
    $('cDays').textContent = n + '일 · ' + fdate(addDays(W.startDate, 0)) + ' ~ ' + fdate(addDays(W.startDate, n - 1));
    $('cTotal').textContent = fmt(total);
    var lack = total > BAL;
    $('costBox').classList.toggle('lack', lack);
    $('lackMsg').hidden = !lack;
    if (lack) $('lackAmt').textContent = fmt(total - BAL);
    $('cBal').textContent = fmt(BAL);
    $('chargeBtn').hidden = !lack;
    $('wSubmit').disabled = lack;
  }

  // ---------- draft (best effort) ----------
  function save() {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({
        url: $('f-url').value, name: $('f-name').value, media: mediaId.value,
        kw: $('f-kw').value, qty: qty.value, days: daysVal.value, memo: memo.value, step: step
      }));
    } catch (e) { /* private mode */ }
  }
  function restore() {
    var d;
    try { d = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) { return; }
    if (!d) return;
    if (!$('f-url').value && d.url) $('f-url').value = d.url;
    if (!$('f-name').value && d.name) $('f-name').value = d.name;
    if (!$('f-kw').value && d.kw) $('f-kw').value = d.kw;
    if (!mediaId.value && d.media) {
      var card = document.querySelector('.msec .mcard[data-id="' + d.media + '"]');
      if (card) pick(card);
    }
    if (d.qty) { qty.value = d.qty; }
    if (d.days) {
      var b = document.querySelector('.dcard[data-d="' + d.days + '"]');
      if (b) { document.querySelectorAll('.dcard').forEach(function (o) { o.classList.remove('on'); }); b.classList.add('on'); daysVal.value = d.days; }
    }
    if (d.memo) { memo.value = d.memo; memoCnt(); }
  }
  ['f-url', 'f-name', 'f-kw'].forEach(function (id) { $(id).addEventListener('input', save); });

  // ---------- submit ----------
  $('cwForm').addEventListener('submit', function (e) {
    for (var n = 1; n <= 3; n++) {
      if (!validate(n)) { e.preventDefault(); go(n); return; }
    }
    var total = (sel ? sel.price : 0) * (+qty.value || 0) * (+daysVal.value);
    if (total > BAL) { e.preventDefault(); go(MAX); return; }
    try { sessionStorage.removeItem(KEY); } catch (err2) { /* ignore */ }
  });

  // ---------- init ----------
  var preSel = document.querySelector('.msec .mcard.sel');
  if (preSel) pick(preSel);
  restore();
  clampQty();
  paint();
})();
