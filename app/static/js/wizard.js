// Channel campaign wizard (spec 2026-09-21): pane toggle, step guard, validation, live cost.
(function () {
  var W = window.WZ || {};
  var MAX = W.steps || 5, BAL = W.balance || 0;
  var $ = function (id) { return document.getElementById(id); };
  var DAY = ['일', '월', '화', '수', '목', '금', '토'];
  var KEY = 'wz:' + W.channel;

  var step = 1, reached = 1;
  var qty = $('qty'), daysVal = $('daysVal'), startIn = $('f-start');
  var QMIN = +qty.dataset.min || 100, QSTEP = +qty.dataset.step || 100;

  function fmt(n) { return (n || 0).toLocaleString() + '원'; }
  function num(v) { return parseInt(String(v).replace(/[^0-9]/g, ''), 10) || 0; }
  function err(id, msg) {
    var e = $(id), input = $(id.replace('e-', 'f-'));
    if (msg) { e.textContent = msg; e.hidden = false; if (input) input.classList.add('bad'); }
    else { e.hidden = true; if (input) input.classList.remove('bad'); }
    return !msg;
  }
  function picked() { return document.querySelector('.adt input[type=radio]:checked'); }
  function price() { var r = picked(); return r ? +r.dataset.price : 0; }
  function qmax() { var r = picked(); var m = r ? +r.dataset.max : 0; return m > 0 ? m : Infinity; }
  function qmin() { var r = picked(); return Math.max(QMIN, r ? (+r.dataset.min || QMIN) : QMIN); }

  // ---------- dates ----------
  function d(iso) { return new Date(iso + 'T00:00:00'); }
  function addDays(date, n) { var x = new Date(date); x.setDate(x.getDate() + n); return x; }
  function iso(date) {
    return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
  }
  function fshort(date) { return (date.getMonth() + 1) + '.' + date.getDate() + '(' + DAY[date.getDay()] + ')'; }
  function flong(date) {
    return date.getFullYear() + '.' + String(date.getMonth() + 1).padStart(2, '0') + '.' +
      String(date.getDate()).padStart(2, '0') + '(' + DAY[date.getDay()] + ')';
  }
  function startDate() { return d(startIn.value || W.minStart); }
  function endDate() { return addDays(startDate(), (+daysVal.value) - 1); }

  function drawDates() {
    var s = startDate();
    document.querySelectorAll('.dcard-range').forEach(function (el) {
      el.textContent = fshort(s) + ' – ' + fshort(addDays(s, (+el.dataset.range) - 1));
    });
    $('dateRange').textContent = flong(s) + ' ~ ' + flong(endDate());
    var wk = s.getDay() === 0 || s.getDay() === 6;
    err('e-start', startIn.value < W.minStart
      ? '시작일은 ' + flong(d(W.minStart)) + ' 이후로 선택해주세요.'
      : (wk ? '' : ''));
    var warn = $('e-start');
    if (wk && startIn.value >= W.minStart) {
      warn.textContent = '주말 시작입니다. 구동 물량이 평일보다 적을 수 있습니다.';
      warn.hidden = false;
      warn.classList.add('soft');
    } else { warn.classList.remove('soft'); }
  }

  // ---------- cost ----------
  function cost() {
    var q = num(qty.value), n = +daysVal.value, p = price();
    return { q: q, n: n, p: p, daily: p * q, total: p * q * n };
  }
  function paintCost() {
    var c = cost();
    var calc = c.q.toLocaleString() + '회 × ' + c.p.toLocaleString() + '원';
    if ($('dcCalc')) { $('dcCalc').textContent = calc; $('dcTotal').textContent = fmt(c.daily); }
    if ($('cDaily')) {
      $('cDaily').textContent = fmt(c.daily);
      $('cCalc').textContent = calc + ' × ' + c.n + '일';
      $('cTotal').textContent = fmt(c.total);
      var lack = c.total > BAL;
      $('costBox').classList.toggle('lack', lack);
      $('costNote').hidden = lack;
      $('costLack').hidden = !lack;
      if (lack) $('lackAmt').textContent = fmt(c.total - BAL);
    }
    $('clientTotal').value = c.total;
    return c;
  }

  // ---------- steps ----------
  function paint() {
    document.querySelectorAll('.wz-pane').forEach(function (p) { p.hidden = +p.dataset.p !== step; });
    document.querySelectorAll('.wz-step').forEach(function (s) {
      var n = +s.dataset.go, done = n !== step && n <= reached;
      s.classList.toggle('cur', n === step);
      s.classList.toggle('done', done);
      s.querySelector('.n').innerHTML = done ? '✓' : n;
    });
    $('wPrev').disabled = step === 1;
    $('wNext').hidden = step === MAX;
    $('wSubmit').hidden = step !== MAX;
    if (step === 3 || step === 4) { drawDates(); paintCost(); }
    if (step === 4) $('wNext').disabled = cost().total > BAL;
    else $('wNext').disabled = false;
    if (step === MAX) summary();
    if (window.lucide) window.lucide.createIcons();
  }
  function go(n) {
    step = Math.min(MAX, Math.max(1, n));
    reached = Math.max(reached, step);
    paint(); save();
    var top = document.querySelector('.wz');
    if (top && top.getBoundingClientRect().top < 0) top.scrollIntoView({ block: 'start' });
  }
  function validate(n) {
    if (n === 1) {
      var url = $('f-url').value.trim(), name = $('f-name').value.trim();
      var a = err('e-url', url ? '' : '주소를 입력해주세요.');
      var b = err('e-name', name.length >= 2 && name.length <= 60 ? '' : '이름을 2~60자로 입력해주세요.');
      return a && b;
    }
    if (n === 2) return err('e-media', picked() ? '' : '광고 유형을 선택해주세요.');
    if (n === 3) {
      var kw = $('f-kw').value.trim();
      if (!kw) return err('e-kw', '메인 키워드를 입력해주세요.');
      if (/[,\s]/.test(kw)) return err('e-kw', '키워드는 한 개만 입력하세요.');
      err('e-kw', '');
      var v = num(qty.value), hi = qmax();
      if (v < qmin()) return err('e-qty', '일일 목표 유입수는 ' + qmin().toLocaleString() + '회 이상으로 입력하세요.');
      if (v > hi) return err('e-qty', '이 유형의 일일 목표 유입수는 ' + hi.toLocaleString() + '회까지 가능합니다.');
      return err('e-qty', '');
    }
    if (n === 4) {
      if (!startIn.value || startIn.value < W.minStart) {
        return err('e-start', '시작일은 ' + flong(d(W.minStart)) + ' 이후로 선택해주세요.');
      }
      if (cost().total > BAL) return false;
    }
    return true;
  }
  $('wNext').addEventListener('click', function () { if (validate(step)) go(step + 1); });
  $('wPrev').addEventListener('click', function () { go(step - 1); });
  document.querySelectorAll('.wz-step').forEach(function (b) {
    b.addEventListener('click', function () {
      var n = +b.dataset.go;
      if (n <= reached && n !== step) go(n);      // completed steps only
    });
  });
  document.querySelectorAll('[data-edit]').forEach(function (b) {
    b.addEventListener('click', function () { go(+b.dataset.edit); });
  });

  // ---------- channel popover ----------
  var cb = $('chanBtn'), cp = $('chanPop');
  if (cb) {
    cb.addEventListener('click', function (e) { e.stopPropagation(); cp.hidden = !cp.hidden; });
    document.addEventListener('click', function () { cp.hidden = true; });
  }

  // ---------- step 2 ----------
  function paintPicked() {
    var r = picked();
    document.querySelectorAll('.adt').forEach(function (l) { l.classList.toggle('on', l.contains(r)); });
    $('adtPicked').hidden = !r;
    if (r) {
      $('adtPickedName').textContent = r.dataset.name;
      $('adtPickedPrice').textContent = fmt(+r.dataset.price);
      err('e-media', '');
      clampQty(0);
    }
    showRange();
  }
  document.querySelectorAll('.adt input[type=radio]').forEach(function (r) {
    r.addEventListener('change', function () { paintPicked(); paintCost(); save(); });
  });

  // ---------- step 3 ----------
  function showRange() {
    var hi = qmax();
    $('qRange').textContent = '버튼으로 ' + QSTEP + '회씩 조절하거나 직접 입력할 수 있습니다. (최소 ' +
      qmin().toLocaleString() + '회' + (hi === Infinity ? ', 상한 없음' : ', 최대 ' + hi.toLocaleString() + '회') + ')';
  }
  function clampQty(stepBy) {
    var v = num(qty.value);
    if (stepBy) v = Math.round(v / QSTEP) * QSTEP + stepBy;
    v = Math.max(qmin(), Math.min(qmax(), v || qmin()));
    qty.value = v;
    err('e-qty', '');
    paintCost();
  }
  qty.addEventListener('input', function () {
    qty.value = String(qty.value).replace(/[^0-9]/g, '');
    paintCost(); save();
  });
  qty.addEventListener('blur', function () { clampQty(0); save(); });
  $('qMinus').addEventListener('click', function () { clampQty(-QSTEP); save(); });
  $('qPlus').addEventListener('click', function () { clampQty(QSTEP); save(); });

  var memo = $('f-memo');
  function memoCnt() { $('memoCnt').textContent = memo.value.length + '/500'; }
  memo.addEventListener('input', function () { memoCnt(); save(); });
  memoCnt();

  // ---------- step 4 ----------
  startIn.addEventListener('change', function () { drawDates(); paintCost(); paint(); save(); });
  document.querySelectorAll('.dcard').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.dcard').forEach(function (o) { o.classList.remove('on'); });
      b.classList.add('on');
      daysVal.value = b.dataset.d;
      drawDates(); paintCost(); paint(); save();
    });
  });

  // ---------- step 5 ----------
  function hostPath(u) {
    try {
      var x = new URL(u);
      return (x.host + x.pathname).replace(/\/$/, '');
    } catch (e) { return u; }
  }
  function summary() {
    var c = paintCost(), r = picked();
    $('sName').textContent = $('f-name').value || '-';
    var u = $('f-url').value.trim();
    $('sUrl').textContent = u ? hostPath(u) : '';
    $('sUrl').title = u;
    $('sMedia').textContent = r ? r.dataset.name + ' (' + (+r.dataset.price).toLocaleString() + '원/회)' : '-';
    $('sKw').textContent = $('f-kw').value || '-';
    $('sQty').textContent = c.q.toLocaleString() + '회';
    $('sDays').innerHTML = '<b>' + c.n + '일</b> ' + flong(startDate()) + ' ~ ' + flong(endDate());
    $('fDaily').textContent = fmt(c.daily);
    $('fDays').textContent = c.n + '일';
    $('fTotal').textContent = fmt(c.total);
    var lack = c.total > BAL;
    $('costBox2').classList.toggle('lack', lack);
    $('fNote').hidden = lack;
    $('fLack').hidden = !lack;
    if (lack) $('fLackAmt').textContent = fmt(c.total - BAL);
    else $('fAfter').textContent = '→ 만든 후 ' + fmt(BAL - c.total);
    $('wSubmit').disabled = lack;
  }

  // ---------- draft ----------
  function save() {
    try {
      var r = picked();
      sessionStorage.setItem(KEY, JSON.stringify({
        url: $('f-url').value, name: $('f-name').value, media: r ? r.value : '',
        kw: $('f-kw').value, qty: qty.value, days: daysVal.value, start: startIn.value, memo: memo.value
      }));
    } catch (e) { /* private mode */ }
  }
  function restore() {
    var v;
    try { v = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) { return; }
    if (!v) return;
    if (!$('f-url').value && v.url) $('f-url').value = v.url;
    if (!$('f-name').value && v.name) $('f-name').value = v.name;
    if (!$('f-kw').value && v.kw) $('f-kw').value = v.kw;
    if (!picked() && v.media) {
      var r = document.querySelector('.adt input[value="' + v.media + '"]');
      if (r) r.checked = true;
    }
    if (v.qty) qty.value = v.qty;
    if (v.start && v.start >= W.minStart) startIn.value = v.start;
    if (v.days) {
      var b = document.querySelector('.dcard[data-d="' + v.days + '"]');
      if (b) { document.querySelectorAll('.dcard').forEach(function (o) { o.classList.remove('on'); }); b.classList.add('on'); daysVal.value = v.days; }
    }
    if (v.memo) { memo.value = v.memo; memoCnt(); }
  }
  ['f-url', 'f-name', 'f-kw'].forEach(function (id) { $(id).addEventListener('input', save); });

  // ---------- submit ----------
  $('cwForm').addEventListener('submit', function (e) {
    for (var n = 1; n <= 4; n++) {
      if (!validate(n)) { e.preventDefault(); go(n); return; }
    }
    paintCost();
    try { sessionStorage.removeItem(KEY); } catch (x) { /* ignore */ }
  });

  // ---------- init ----------
  restore();
  paintPicked();
  clampQty(0);
  drawDates();
  paint();
})();
