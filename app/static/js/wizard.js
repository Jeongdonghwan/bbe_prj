// Campaign wizard v3 — behaviour ported from prototype_wizard_v3.html, wired to the server form.
(function () {
  var W = window.WZ || {}, T = W.types || {}, GROUPS = W.groups || [], SPANS = W.spans || [10, 20, 30];
  var BAL = W.balance || 0, LAST = 5, KEY = 'wz:' + W.channel;
  var $ = function (id) { return document.getElementById(id); };
  var cur = 1, reached = 1, tab = -1;
  var qty = $('qty'), daysVal = $('daysVal'), mediaId = $('mediaId'), startIn = $('f-start');

  function won(n) { return (n || 0).toLocaleString('ko-KR') + '원'; }
  function num(n) { return (n || 0).toLocaleString('ko-KR'); }
  function digits(v) { return parseInt(String(v).replace(/[^0-9]/g, ''), 10) || 0; }
  function cnt() { return digits(qty.value); }
  function span() { return +daysVal.value || SPANS[0]; }
  function sel() { return T[mediaId.value] || null; }
  function day(d) { return (d.getMonth() + 1) + '.' + String(d.getDate()).padStart(2, '0') + '(' + '일월화수목금토'[d.getDay()] + ')'; }
  function longDay(d) {
    return d.getFullYear() + '.' + String(d.getMonth() + 1).padStart(2, '0') + '.' + String(d.getDate()).padStart(2, '0') +
      '(' + '일월화수목금토'[d.getDay()] + ')';
  }
  function startAt() { return new Date((startIn.value || W.minStart) + 'T00:00:00'); }
  function err(id, msg) {
    var e = $(id), input = $(id.replace('e-', 'f-'));
    if (id === 'e-qty') input = qty;
    if (msg) { e.textContent = msg; e.hidden = false; if (input) input.classList.add('w-bad'); }
    else { e.hidden = true; if (input) input.classList.remove('w-bad'); }
    return !msg;
  }

  /* ── Step 1: URL preview ── */
  function urlLooksOk(u) { return /^https?:\/\/[^\s]+\.[^\s]+/.test(u); }
  function tidyUrl(u) { return u.replace(/^https?:\/\//, '').split('?')[0]; }

  function preview() {
    var u = $('f-url').value.trim(), n = $('f-name').value.trim();
    var chip = $('urlOk');
    if (chip) {                                    // 쿠팡·플레이스: 확인 표시만
      chip.hidden = !(u && urlLooksOk(u));
      if (!chip.hidden) $('urlOkTxt').textContent = tidyUrl(u);
      return;
    }
    $('preview').hidden = !u;
    if (!u) { $('pvImg').hidden = true; $('pvIcon').hidden = false; $('pvWarn').hidden = true; return; }
    var pn = $('pvName');
    pn.textContent = n;
    pn.hidden = !n;
    $('pvUrl').textContent = tidyUrl(u);
    $('pvOk').hidden = !urlLooksOk(u);
  }

  /* ── Step 1: product lookup (proxy to the rank server; best-effort) ── */
  var lookupSeq = 0, lookupDone = {}, lookupTimer = null;

  function showLookup(url, d) {
    var img = $('pvImg'), icon = $('pvIcon'), ok = $('pvOk'), warn = $('pvWarn');
    warn.hidden = true;
    if (!d || !d.ok) return;                       // could not ask — stay quiet
    if (d.valid === false) {
      img.hidden = true; icon.hidden = false; ok.hidden = true;
      warn.textContent = d.note || '이 주소에서 상품 번호를 찾지 못했습니다. 상품 페이지 주소가 맞는지 확인해주세요.';
      warn.hidden = false;
      return;
    }
    // 썸네일은 자주 없다. 네이버가 데이터센터 IP의 상품 페이지 열람을 막아서, 순위 서버가
    // 수집 캐시(source:"serp")로 답할 때는 이미지가 아예 포함되지 않는다.
    if (d.imageUrl) {
      img.src = d.imageUrl;
      img.hidden = false;
      icon.hidden = true;
      img.onerror = function () { img.hidden = true; icon.hidden = false; };
    }
    var nameIn = $('f-name');
    if ($('nvMid')) $('nvMid').value = /^\d{1,20}$/.test(String(d.nvMid || '')) ? String(d.nvMid) : '';
    if (d.prodNm) {
      ok.textContent = (d.mallName ? d.mallName + ' · ' : '') + '상품을 확인했습니다';
      if (!nameIn.value.trim()) {                  // never overwrite what the user typed
        nameIn.value = String(d.prodNm).slice(0, 60);
        preview();
        save();
      }
    } else {
      ok.textContent = '주소는 확인했습니다. 상품명은 직접 입력해주세요';
    }
    ok.hidden = false;
  }

  function lookup() {
    var url = $('f-url').value.trim();
    if (!urlLooksOk(url)) return;
    if (lookupDone[url]) { showLookup(url, lookupDone[url]); return; }
    var seq = ++lookupSeq;
    fetch('/api/product/preview?url=' + encodeURIComponent(url), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : { ok: false }; })
      .catch(function () { return { ok: false }; })
      .then(function (d) {
        lookupDone[url] = d;
        if (seq !== lookupSeq) return;             // a newer URL was typed meanwhile
        if ($('f-url').value.trim() === url) showLookup(url, d);
      });
  }

  /* ── Step 2: master-detail ── */
  function setTab(i) {
    tab = i;
    document.querySelectorAll('#tabs button').forEach(function (b) { b.classList.toggle('w-on', +b.dataset.tab === i); });
    document.querySelectorAll('#typegrid [data-g]').forEach(function (el) {
      el.style.display = (i === -1 || +el.dataset.g === i) ? '' : 'none';
    });
  }
  document.querySelectorAll('#tabs button').forEach(function (b) {
    b.addEventListener('click', function () { setTab(+b.dataset.tab); });
  });
  function pick(id) {
    mediaId.value = id;
    document.querySelectorAll('#typegrid .w-card').forEach(function (c) { c.classList.toggle('w-on', c.dataset.id === String(id)); });
    err('e-media', '');
    renderDetail(); sync(); save();
  }
  document.querySelectorAll('#typegrid .w-card').forEach(function (c) {
    c.addEventListener('click', function () { pick(c.dataset.id); });
  });
  function renderDetail() {
    var t = sel(), el = $('detail');
    if (!t) { el.innerHTML = '<div class="w-db"><p class="w-ds">왼쪽에서 광고 유형을 선택하세요.</p></div>'; return; }
    var badge = t.badge ? '<span class="w-bd w-' + t.badge + '">' + t.badge_label + '</span>' : '';
    var desc = t.desc ? t.desc : '설명이 아직 등록되지 않았습니다.';
    var fit = (t.fit || []).length
      ? '<div><div class="w-dk">이런 상품에 맞아요</div><div class="w-chips">' +
        t.fit.map(function (f) { return '<span>' + f + '</span>'; }).join('') + '</div></div>' : '';
    var flow = (t.flow || []).length
      ? '<div><div class="w-dk">진행 방식</div><div class="w-flow">' +
        t.flow.map(function (f, i) { return '<div><i>' + (i + 1) + '</i>' + f + '</div>'; }).join('') + '</div></div>' : '';
    el.innerHTML =
      '<div class="w-dh"><div class="w-dg">' + (GROUPS[t.g] || '') + '</div>' +
      '<div class="w-dn">' + t.n + badge + '</div>' +
      '<div class="w-dp w-num"><b>' + num(t.p) + '원</b><span>/ 유입 1회</span></div></div>' +
      '<div class="w-db"><p class="w-ds">' + desc + '</p>' + fit + flow +
      '<div class="w-est w-num"><span>100회 × 10일 기준</span><b>' + won(t.p * 100 * 10) + '</b></div></div>';
  }

  /* ── Step 3 ── */
  function sync() {
    var t = sel();
    if (!t) { $('lede3').textContent = '광고 유형을 먼저 선택하세요.'; return; }
    var d = cnt() * t.p;
    $('lede3').textContent = t.n + ' 기준 · 유입 1회당 ' + num(t.p) + '원';
    $('s3-day').textContent = won(d);
    $('s3-f').textContent = num(cnt()) + '회 × ' + num(t.p) + '원';
    $('s3-type').textContent = t.n;
    $('s3-price').textContent = num(t.p) + '원';
    $('s3-10').textContent = won(d * 10);
    if (cur >= 4) calc();
  }
  function clearBands() { document.querySelectorAll('.w-bands button').forEach(function (b) { b.classList.remove('w-on'); }); }
  function setCnt(v, btn) {
    qty.value = Math.max(100, v);
    clearBands();
    if (btn) btn.classList.add('w-on');
    err('e-qty', '');
    sync(); save();
  }
  $('qMinus').addEventListener('click', function () { setCnt(Math.max(100, Math.round(cnt() / 100) * 100 - 100)); });
  $('qPlus').addEventListener('click', function () { setCnt(Math.round(cnt() / 100) * 100 + 100); });
  qty.addEventListener('input', function () {
    qty.value = String(qty.value).replace(/[^0-9]/g, '');
    clearBands(); sync(); save();
  });
  qty.addEventListener('blur', function () { if (cnt() < 100) setCnt(100); });
  document.querySelectorAll('.w-bands button').forEach(function (b) {
    b.addEventListener('click', function () { setCnt(+b.dataset.band, b); });
  });
  $('f-memo').addEventListener('input', save);

  /* ── Step 4 ── */
  function calc() {
    var t = sel();
    if (!t) return;
    var from = startAt(), perDay = cnt() * t.p, html = '';
    SPANS.forEach(function (d, i) {
      var to = new Date(from); to.setDate(to.getDate() + d - 1);
      html += '<button type="button" class="w-span' + (d === span() ? ' w-on' : '') + '" data-d="' + d + '">' +
        (i === 0 ? '<span class="w-bd w-hot">많이 선택</span>' : '') +
        '<div class="w-d w-num">' + d + '일</div><div class="w-r w-num">' + day(from) + ' – ' + day(to) + '</div>' +
        '<div class="w-tt w-num"><span>총 광고비</span><b>' + won(perDay * d) + '</b></div></button>';
    });
    $('spans').innerHTML = html;
    document.querySelectorAll('#spans .w-span').forEach(function (b) {
      b.addEventListener('click', function () { daysVal.value = b.dataset.d; calc(); save(); });
    });
    var total = perDay * span();
    $('c-day').textContent = won(perDay);
    $('c-formula').textContent = num(cnt()) + '회 × ' + num(t.p) + '원 × ' + span() + '일';
    $('c-total').textContent = won(total);
    var m = $('c-msg');
    if (total > BAL) {
      m.className = 'w-msg w-over';
      m.innerHTML = '보유 크레딧 ' + won(BAL) + '보다 ' + won(total - BAL) +
        ' 부족합니다. 기간이나 목표 유입수를 줄이거나 <a href="/credit/charge">크레딧을 충전</a>하세요.';
    } else {
      m.className = 'w-msg';
      m.textContent = '보유 크레딧 ' + won(BAL) + ' · 광고 시작 시 총 광고비가 한 번에 차감됩니다.';
    }
    $('clientTotal').value = total;
    if (cur === 4) $('btn-next').disabled = total > BAL;
  }
  startIn.addEventListener('change', function () { err('e-start', ''); calc(); save(); });

  /* ── Step 5 ── */
  function recap() {
    var t = sel();
    if (!t) return;
    var from = startAt(), to = new Date(from); to.setDate(to.getDate() + span() - 1);
    var perDay = cnt() * t.p, total = perDay * span();
    var raw = $('f-url').value.trim();
    var url = raw.replace(/^https?:\/\//, '').split('?')[0];
    $('v-prod').innerHTML = ($('f-name').value.trim() || $('f-kw').value.trim() || '-') + '<span class="w-s" title="' + raw + '">' + url + '</span>';
    $('v-kind').textContent = t.n + ' · 회당 ' + num(t.p) + '원';
    $('v-kw').textContent = $('f-kw').value || '-';
    $('v-cnt').textContent = num(cnt()) + '회';
    $('v-span').textContent = span() + '일 · ' + day(from) + ' – ' + day(to);
    $('t-day').textContent = won(perDay);
    $('t-span').textContent = span() + '일';
    $('t-total').textContent = won(total);
    $('t-after').textContent = total > BAL ? won(total - BAL) + ' 부족' : '만든 후 ' + won(BAL - total);
    $('btn-submit').disabled = total > BAL;
    $('clientTotal').value = total;
  }

  /* ── navigation ── */
  function go(n) {
    cur = Math.min(LAST, Math.max(1, n));
    reached = Math.max(reached, cur);
    document.querySelectorAll('.w-pane').forEach(function (p) { p.classList.toggle('w-on', +p.dataset.p === cur); });
    document.querySelectorAll('#steps li').forEach(function (li) {
      var i = +li.dataset.n;
      li.classList.toggle('w-cur', i === cur);
      li.classList.toggle('w-done', i !== cur && i <= reached);
      li.querySelector('.w-dot').textContent = (i !== cur && i <= reached) ? '✓' : i;
    });
    $('steps').style.setProperty('--fill', ((cur - 1) / (LAST - 1) * 100) + '%');
    $('bar').style.width = (cur / LAST * 100) + '%';
    $('ghost').innerHTML = '0' + cur + '<small>/0' + LAST + '</small>';
    $('btn-prev').style.visibility = cur === 1 ? 'hidden' : 'visible';
    $('btn-next').hidden = cur === LAST;
    $('btn-submit').hidden = cur !== LAST;
    $('btn-next').disabled = false;
    sync();
    if (cur >= 4) calc();
    if (cur === LAST) recap();
    save();
    var top = document.querySelector('.wiz');
    if (top && top.getBoundingClientRect().top < 0) top.scrollIntoView({ block: 'start' });
  }
  function validate(n) {
    if (n === 1) {
      var u = $('f-url').value.trim(), nm = $('f-name').value.trim();
      var a = err('e-url', u ? '' : '주소를 입력해주세요.');
      var opt = $('f-name').dataset.opt === '1';
      var b = err('e-name', (opt && !nm) || (nm.length >= 2 && nm.length <= 60) ? '' : '이름을 2~60자로 입력해주세요.');
      return a && b;
    }
    if (n === 2) return err('e-media', sel() ? '' : '광고 유형을 선택해주세요.');
    if (n === 3) {
      var kw = $('f-kw').value.trim();
      if (!kw) return err('e-kw', '메인 키워드를 입력해주세요.');
      if (/[,\s]/.test(kw)) return err('e-kw', '키워드는 한 개만 입력하세요.');
      err('e-kw', '');
      var t = sel(), v = cnt();
      if (v < 100) return err('e-qty', '일일 목표 유입수는 100회 이상으로 입력하세요.');
      if (t && t.max && v > t.max) return err('e-qty', '이 유형은 하루 ' + num(t.max) + '회까지 가능합니다.');
      return err('e-qty', '');
    }
    if (n === 4) {
      if (!startIn.value || startIn.value < W.minStart) {
        return err('e-start', '시작일은 ' + longDay(new Date(W.minStart + 'T00:00:00')) + ' 이후로 선택해주세요.');
      }
      err('e-start', '');
      var tt = sel();
      return !(tt && cnt() * tt.p * span() > BAL);
    }
    return true;
  }
  $('btn-next').addEventListener('click', function () { if (validate(cur)) go(cur + 1); });
  $('btn-prev').addEventListener('click', function () { go(cur - 1); });
  document.querySelectorAll('#steps li').forEach(function (li) {
    li.addEventListener('click', function () {
      var n = +li.dataset.n;
      if (n <= reached && n !== cur) go(n);
    });
  });
  document.querySelectorAll('.w-fix').forEach(function (b) {
    b.addEventListener('click', function () { go(+b.dataset.go); });
  });

  /* ── channel popover ── */
  var cb = $('chanBtn'), cp = $('chanPop');
  function shutChan() { cp.hidden = true; cb.setAttribute('aria-expanded', 'false'); }
  cb.addEventListener('click', function (e) {
    e.stopPropagation();
    cp.hidden = !cp.hidden;
    cb.setAttribute('aria-expanded', cp.hidden ? 'false' : 'true');
  });
  document.addEventListener('click', shutChan);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' || e.keyCode === 27) shutChan();
  });

  /* ── draft ── */
  function save() {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({
        url: $('f-url').value, name: $('f-name').value, media: mediaId.value, kw: $('f-kw').value,
        qty: qty.value, days: daysVal.value, start: startIn.value, memo: $('f-memo').value
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
    if (!mediaId.value && v.media && T[v.media]) mediaId.value = v.media;
    if (v.qty) qty.value = v.qty;
    if (v.days && SPANS.indexOf(+v.days) >= 0) daysVal.value = v.days;
    if (v.start && v.start >= W.minStart) startIn.value = v.start;
    if (v.memo) $('f-memo').value = v.memo;
  }
  ['f-url', 'f-name', 'f-kw'].forEach(function (id) {
    $(id).addEventListener('input', function () { preview(); save(); });
  });
  if (W.preview && $('preview')) {
    var pvOkDefault = $('pvOk').textContent;
    $('f-url').addEventListener('input', function () {
      $('pvWarn').hidden = true;
      $('pvOk').textContent = pvOkDefault;        // drop the previous product's mall line
      $('pvImg').hidden = true;
      $('pvIcon').hidden = false;
      if ($('nvMid')) $('nvMid').value = '';            // 주소가 바뀌면 이전 상품의 nvMid 를 버린다
      clearTimeout(lookupTimer);
      lookupTimer = setTimeout(lookup, 600);
    });
    $('f-url').addEventListener('blur', function () { clearTimeout(lookupTimer); lookup(); });
  }

  /* ── submit ── */
  $('cwForm').addEventListener('submit', function (e) {
    for (var n = 1; n <= 4; n++) {
      if (!validate(n)) { e.preventDefault(); go(n); return; }
    }
    recap();
    try { sessionStorage.removeItem(KEY); } catch (x) { /* ignore */ }
  });

  /* ── init ── */
  restore();
  if (mediaId.value) {
    document.querySelectorAll('#typegrid .w-card').forEach(function (c) { c.classList.toggle('w-on', c.dataset.id === mediaId.value); });
  }
  preview();
  renderDetail();
  setTab(-1);
  go(1);
})();
