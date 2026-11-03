// Campaign manage: row click -> fetch drawer partial; close; deep link via ?open=.
(function () {
  var drawer = document.getElementById('drawer');
  // 전체 캠페인 관리는 여러 채널이 섞여 있어 행마다 채널(data-ch)로 주소를 만든다
  function base(id) {
    var tr = document.querySelector('tr[data-open="' + id + '"]');
    return tr && tr.dataset.ch ? '/campaign/' + tr.dataset.ch + '/' : window.DRAWER_BASE;
  }
  function close() { drawer.classList.remove('on'); document.querySelectorAll('tr[data-open]').forEach(function (o) { o.classList.remove('sel'); }); }
  function open(id, tr) {
    document.querySelectorAll('tr[data-open]').forEach(function (o) { o.classList.remove('sel'); });
    if (tr) tr.classList.add('sel');
    fetch(base(id) + id + '/drawer').then(function (r) { return r.text(); }).then(function (html) {
      drawer.innerHTML = html; drawer.classList.add('on');
      drawer.querySelector('#dclose').addEventListener('click', close);
      if (window.lucide) window.lucide.createIcons();
    });
  }
  // 취소·중단 — 확인 팝업을 한 번 더 띄운다. 구동 시작일부터 3일 안이면 막고 안내 (서버도 같은 규칙, refund_rule)
  function popup(msg, onOk) {
    var m = document.createElement('div');
    m.className = 'modal on';
    m.setAttribute('role', 'alertdialog');
    m.innerHTML = '<div class="modal-box" style="max-width:420px;text-align:center">' +
      '<p style="font-size:15px;line-height:1.7;margin:4px 0 18px;white-space:pre-line"></p>' +
      '<div style="display:flex;gap:8px;justify-content:center">' +
      (onOk ? '<button class="btn sec" type="button" data-no style="min-width:110px">아니요</button>' : '') +
      '<button class="btn pri" type="button" data-yes style="min-width:110px">' + (onOk ? '네, 진행할게요' : '확인') + '</button></div></div>';
    m.querySelector('p').textContent = msg;
    document.body.appendChild(m);
    function close() { m.remove(); }
    m.querySelector('[data-yes]').addEventListener('click', function () { close(); if (onOk) onOk(); });
    var no = m.querySelector('[data-no]'); if (no) no.addEventListener('click', close);
    m.addEventListener('click', function (e) { if (e.target === m) close(); });
    m.querySelector('[data-yes]').focus();
  }
  document.addEventListener('submit', function (e) {
    var f = e.target.closest('form[data-refund]'); if (!f || f.dataset.ok === '1') return;
    e.preventDefault();
    if (f.dataset.refund === 'locked') {
      popup('최소 작업일수는 3일입니다. 환불은 불가합니다.' + (f.dataset.unlock ? '\n' + f.dataset.unlock + '부터 중단할 수 있습니다.' : ''));
      return;
    }
    popup(f.dataset.ask, function () { f.dataset.ok = '1'; f.submit(); });
  }, true);
  var rm = document.getElementById('rankModal'), rb = document.getElementById('rankBody');
  function closeRanks() { if (rm) rm.classList.remove('on'); }
  // 회원 목록(어드민)처럼 순위 모달이 없는 화면도 이 파일을 쓴다 — 없으면 여기서 멈춰 행 클릭이 안 붙었다
  if (rm) rm.addEventListener('click', function (e) { if (e.target === rm) closeRanks(); });
  // 드로어는 fetch 로 나중에 들어오므로 문서에 위임한다 (그때 붙이면 버튼이 안 먹는다).
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-ranks]');
    if (!b || !rm) { return; }
    e.stopPropagation();
    fetch(base(b.dataset.ranks) + b.dataset.ranks + '/ranks').then(function (r) { return r.text(); }).then(function (html) {
      rb.innerHTML = html;
      rm.classList.add('on');
      var x = document.getElementById('rkclose');
      if (x) x.addEventListener('click', closeRanks);
      if (window.lucide) window.lucide.createIcons();
    });
  });
  document.querySelectorAll('tr[data-open]').forEach(function (tr) {
    tr.addEventListener('click', function (e) { if (e.target.closest('.rowact') || e.target.closest('a,button,form')) return; open(tr.dataset.open, tr); });
  });
  var dc = document.getElementById('dclose'); if (dc) dc.addEventListener('click', close);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
  // 팝업(.drawer.pop) 바깥을 누르면 닫는다 — 행·순위 버튼·다른 모달 클릭은 제외
  document.addEventListener('click', function (e) {
    if (drawer.classList.contains('on') && drawer.classList.contains('pop') && !drawer.contains(e.target) &&
        !e.target.closest('tr[data-open], [data-ranks], .modal')) close();
  });
  if (window.OPEN_ID) open(window.OPEN_ID, document.querySelector('tr[data-open="' + window.OPEN_ID + '"]'));
})();
