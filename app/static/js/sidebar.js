// Sidebar: accordion (only one channel open), mobile drawer toggle, Lucide icons.
(function () {
  document.querySelectorAll('.acc').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.acc').forEach(function (o) { if (o !== b) o.classList.remove('open'); });
      b.classList.toggle('open');
    });
  });

  var ts = document.getElementById('topstrip'), tx = document.getElementById('stripX');
  try { if (ts && sessionStorage.getItem('stripHide')) ts.style.display = 'none'; } catch (e) {}
  if (tx) tx.addEventListener('click', function (e) {
    e.preventDefault(); e.stopPropagation();
    ts.style.display = 'none';
    try { sessionStorage.setItem('stripHide', '1'); } catch (e2) {}
  });

  var sidebar = document.querySelector('.sidebar');
  var scrim = document.querySelector('.side-scrim');
  function closeSide() { if (sidebar) sidebar.classList.remove('open'); }
  document.querySelectorAll('[data-side-toggle]').forEach(function (el) {
    el.addEventListener('click', function (e) { e.preventDefault(); sidebar && sidebar.classList.toggle('open'); });
  });
  if (scrim) scrim.addEventListener('click', closeSide);

  // 제출하면 응답이 올 때까지 페이지가 통째로 바뀌는 폼은 그동안 아무 반응이 없다.
  // 버튼을 "조회중…" 으로 바꿔 지금 뭔가 돌고 있다는 걸 보여준다.
  //   data-busy="문구"  문구 바꾸기 / data-busy="off"  적용 안 함
  // 버블 단계에서 듣는다 — 캡처로 들으면 폼 자신의 핸들러가 preventDefault 하기 전에 돌아서
  // 취소된 제출까지 잠긴다 (위저드의 "최종 확인 화면에서만 제출" 가드가 그렇다).
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || e.defaultPrevented) { return; }
    if (form.dataset.busy === 'off' || form.dataset.busyOn === '1') { return; }
    var btn = e.submitter || form.querySelector('button[type="submit"], button:not([type])');
    if (!btn || btn.disabled || btn.dataset.busy === 'off') { return; }
    // 새 탭·다운로드로 빠지는 제출은 이 페이지가 그대로 남는다 → 잠그면 영영 안 풀린다.
    if (form.target || btn.getAttribute('formtarget')) { return; }
    form.dataset.busyOn = '1';
    var label = btn.textContent;
    btn.classList.add('is-busy');
    btn.textContent = btn.dataset.busy || form.dataset.busy || '조회중…';
    btn.addEventListener('click', function (ev) { ev.preventDefault(); });   // 두 번째 클릭 차단
    // 안전망: 페이지가 안 바뀌는 경우(서버 오류 등)에 버튼이 영영 잠겨 있지 않게.
    setTimeout(function () {
      form.dataset.busyOn = '';
      btn.classList.remove('is-busy');
      btn.textContent = label;
    }, 20000);
  });

  // 연락처 · 사업자등록번호 칸은 입력하는 대로 하이픈을 넣는다 (2026-10-07). 서버도 다시 정규화한다.
  function hyphen(v, kind) {
    var d = v.replace(/\D/g, '');
    if (kind === 'biz') { d = d.slice(0, 10); return d.length > 5 ? d.slice(0, 3) + '-' + d.slice(3, 5) + '-' + d.slice(5) : d.length > 3 ? d.slice(0, 3) + '-' + d.slice(3) : d; }
    d = d.slice(0, 11);
    if (d.length < 4) return d;
    if (d.length < 8) return d.slice(0, 3) + '-' + d.slice(3);
    var mid = d.length === 11 ? 4 : 3;               // 010-1234-5678 / 011-123-4567
    return d.slice(0, 3) + '-' + d.slice(3, 3 + mid) + '-' + d.slice(3 + mid);
  }
  document.addEventListener('input', function (e) {
    if (e.target.hasAttribute && e.target.hasAttribute('data-money')) {   // 금액 칸: 천 단위 쉼표 (서버가 숫자만 읽는다)
      var d = e.target.value.replace(/\D/g, '').replace(/^0+(?=\d)/, '');
      e.target.value = d ? Number(d).toLocaleString('ko-KR') : '';
      return;
    }
    var t = e.target, kind = t.name === 'phone' ? 'phone' : (t.name === 'biz_no' ? 'biz' : null);
    if (!kind || e.isComposing) return;
    var v = hyphen(t.value, kind);
    if (v !== t.value) { t.value = v; t.dispatchEvent(new Event('input', { bubbles: false })); }
  });

  if (window.lucide) window.lucide.createIcons();
})();
