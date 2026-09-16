// Campaign create wizard (2026-09-16 credit model): 4 steps, media tiles, qty stepper,
// period presets, cost summary against credit balance.
(function () {
  var M = window.MEDIA, BAL = window.BALANCE || 0;
  var $ = function (id) { return document.getElementById(id); };
  var DAYS_KR = ['일', '월', '화', '수', '목', '금', '토'];
  var step = 1, MAX = 4;
  var sel = null;
  var qty = $('qty'), daysVal = $('daysVal'), mediaId = $('mediaId');

  function fmt(n) { return (n || 0).toLocaleString() + '원'; }

  // ---- step nav
  function show() {
    document.querySelectorAll('.wpane').forEach(function (p) { p.hidden = +p.dataset.p !== step; });
    document.querySelectorAll('.wstep').forEach(function (s) {
      var n = +s.dataset.s;
      s.classList.toggle('cur', n === step);
      s.classList.toggle('done', n < step);
      s.querySelector('.no').innerHTML = n < step ? '✓' : n;
    });
    $('wPrev').disabled = step === 1;
    $('wNext').hidden = step === MAX;
    $('wSubmit').hidden = step !== MAX;
    if (step === 3) drawDates();
    if (step === MAX) summary();
    if (window.lucide) window.lucide.createIcons();
  }
  function valid(s) {
    if (s === 1) {
      if (!$('pUrl').value.trim()) { alert('URL을 입력해주세요.'); $('pUrl').focus(); return false; }
      if (!$('pName').value.trim()) { alert('이름을 입력해주세요.'); $('pName').focus(); return false; }
    }
    if (s === 2) {
      if (!mediaId.value) { alert('광고 유형(매체)을 선택해주세요.'); return false; }
      if (!$('kw').value.trim()) { alert('메인 키워드를 입력해주세요.'); $('kw').focus(); return false; }
    }
    return true;
  }
  $('wNext').addEventListener('click', function () { if (valid(step)) { step = Math.min(MAX, step + 1); show(); } });
  $('wPrev').addEventListener('click', function () { step = Math.max(1, step - 1); show(); });

  // ---- step1: preview card
  function preview() {
    var n = $('pName').value.trim(), u = $('pUrl').value.trim();
    $('prodCard').hidden = !(n || u);
    $('pcName').textContent = n || '-';
    $('pcUrl').textContent = u || '-';
  }
  $('pName').addEventListener('input', preview);
  $('pUrl').addEventListener('input', preview);

  // ---- step2: media tiles
  function pick(card) {
    document.querySelectorAll('.msec .mcard').forEach(function (o) { o.classList.remove('sel'); });
    card.classList.add('sel');
    mediaId.value = card.dataset.id;
    sel = M[card.dataset.id];
    clampQty();
  }
  document.querySelectorAll('.msec .mcard').forEach(function (c) { c.addEventListener('click', function () { pick(c); }); });

  // ---- step2: qty stepper (100 단위)
  function clampQty() {
    var lo = 100, hi = 2000;
    if (sel) { lo = Math.max(100, Math.ceil(sel.min_daily / 100) * 100); hi = Math.max(lo, sel.max_daily); }
    var v = Math.min(hi, Math.max(lo, Math.round((+qty.value || lo) / 100) * 100));
    qty.value = v;
    $('qShow').textContent = v.toLocaleString();
  }
  $('qMinus').addEventListener('click', function () { qty.value = (+qty.value || 100) - 100; clampQty(); });
  $('qPlus').addEventListener('click', function () { qty.value = (+qty.value || 100) + 100; clampQty(); });

  // ---- step2: request note
  var noteBox = $('noteBox'), noteTa = noteBox.querySelector('textarea');
  $('noteToggle').addEventListener('click', function () { noteBox.hidden = !noteBox.hidden; });
  if (noteTa.value) noteBox.hidden = false;
  noteTa.addEventListener('input', function () { $('noteCnt').textContent = noteTa.value.length + '/200'; });
  $('noteCnt').textContent = noteTa.value.length + '/200';

  // ---- step3: period presets
  function addDays(iso, n) {
    var d = new Date(iso + 'T00:00:00');
    d.setDate(d.getDate() + n);
    return d;
  }
  function fdate(d) {
    return d.getFullYear() + '.' + String(d.getMonth() + 1).padStart(2, '0') + '.' + String(d.getDate()).padStart(2, '0') +
      '(' + DAYS_KR[d.getDay()] + ')';
  }
  function drawDates() {
    var n = +daysVal.value;
    var s = addDays(window.START_DATE, 0), e = addDays(window.START_DATE, n - 1);
    $('dateRange').textContent = fdate(s) + ' ~ ' + fdate(e);
  }
  document.querySelectorAll('.dcard').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.dcard').forEach(function (o) { o.classList.remove('on'); });
      b.classList.add('on');
      daysVal.value = b.dataset.d;
      drawDates();
    });
  });

  // ---- step4: summary + credit check
  function summary() {
    var n = +daysVal.value, q = +qty.value || 0, price = sel ? sel.price : 0;
    var daily = price * q, total = daily * n;
    $('cfName').textContent = $('pName').value || '-';
    $('cfUrl').textContent = $('pUrl').value || '-';
    $('cfMedia').textContent = sel ? sel.name + ' (' + price.toLocaleString() + '원/회)' : '-';
    $('cfKw').textContent = $('kw').value || '-';
    var s = addDays(window.START_DATE, 0), e = addDays(window.START_DATE, n - 1);
    $('cfDays').textContent = n + '일 · ' + fdate(s) + ' ~ ' + fdate(e);
    $('cfQty').textContent = q.toLocaleString() + '회';
    $('cDaily').textContent = fmt(daily);
    $('cDays').textContent = n + '일';
    $('cTotal').textContent = fmt(total);
    var lack = total > BAL;
    $('costBox').classList.toggle('lack', lack);
    $('lackMsg').hidden = !lack;
    if (lack) $('lackAmt').textContent = fmt(total - BAL);
    $('cBal').textContent = fmt(BAL);
    $('chargeBtn').hidden = !lack;
    $('wSubmit').disabled = lack;
    if (window.lucide) window.lucide.createIcons();
  }

  // ---- submit guard
  $('campForm').addEventListener('submit', function (e) {
    if (!valid(1) || !valid(2)) { e.preventDefault(); return; }
    var n = +daysVal.value, q = +qty.value || 0, price = sel ? sel.price : 0;
    if (price * q * n > BAL) { e.preventDefault(); alert('크레딧이 부족합니다. 충전 후 다시 시도해주세요.'); }
  });

  // ---- init
  var preSel = document.querySelector('.msec .mcard.sel');
  if (preSel) pick(preSel);
  clampQty();
  preview();
  show();
})();
