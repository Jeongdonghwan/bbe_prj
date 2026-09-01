// Admin screens: modals, reject flow, bulk select, row actions, toggles, badge tabs, content editor, countdown.
(function () {
  var $ = function (id) { return document.getElementById(id); };

  // ---- generic modals / checkboxes
  document.querySelectorAll('[data-modal]').forEach(function (el) { el.addEventListener('click', function (e) { e.preventDefault(); $(el.dataset.modal).classList.add('on'); }); });
  document.querySelectorAll('.modal').forEach(function (m) { m.addEventListener('click', function (e) { if (e.target === m || e.target.closest('[data-close]')) m.classList.remove('on'); }); });
  document.querySelectorAll('label.chk').forEach(function (c) { c.addEventListener('click', function () { setTimeout(function () { c.classList.toggle('on', c.querySelector('input').checked); }, 0); }); });

  // ---- 13:30 countdown
  var cd = $('cd2');
  if (cd) { (function t() { var n = new Date(), d = new Date(); d.setHours(13, 30, 0, 0); if (d < n) d.setDate(d.getDate() + 1); var s = Math.floor((d - n) / 1000); cd.textContent = String(Math.floor(s / 3600)).padStart(2, '0') + ':' + String(Math.floor(s % 3600 / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); setTimeout(t, 1000); })(); }

  // ---- reject modal (single + bulk)
  var rm = $('rejectModal');
  function openReject(ids, order, back) {
    if (!rm) return;
    var f = $('rejectForm'), box = $('rejectIds'); box.innerHTML = '';
    if (ids.length === 1 && !order.startsWith('bulk')) { f.action = '/admin/orders/' + ids[0] + '/action'; }
    else { f.action = '/admin/orders/bulk'; ids.forEach(function (id) { var i = document.createElement('input'); i.type = 'hidden'; i.name = 'ids'; i.value = id; box.appendChild(i); }); }
    $('rejectOrder').textContent = order; $('rejectBack').value = back || location.pathname + location.search;
    rm.classList.add('on'); rm.querySelector('textarea').focus();
  }
  document.querySelectorAll('[data-reject]').forEach(function (b) { b.addEventListener('click', function () { openReject([b.dataset.reject], b.dataset.order, b.dataset.back); }); });

  // ---- quick row actions (approve/start/stop/done/paid)
  document.querySelectorAll('[data-act]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.dataset.confirm && !confirm(b.dataset.confirm)) return;
      var f = $('actForm'); f.action = '/admin/orders/' + b.dataset.id + '/action'; $('actName').value = b.dataset.act; f.submit();
    });
  });
  // status select -> submit (reject asks reason)
  document.querySelectorAll('.statusForm select').forEach(function (s) {
    s.addEventListener('change', function () {
      var f = s.closest('form');
      if (s.value === 'rejected') { openReject([f.dataset.id], f.dataset.order); s.selectedIndex = 0; return; }
      if (s.value !== s.options[0].value) f.submit();
    });
  });
  // memo modal
  document.querySelectorAll('[data-memo]').forEach(function (b) {
    b.addEventListener('click', function () { $('memoForm').action = '/admin/orders/' + b.dataset.memo + '/action'; $('memoOrder').textContent = b.dataset.order; $('memoText').value = b.dataset.text; $('memoModal').classList.add('on'); });
  });

  // ---- bulk selection
  var chks = document.querySelectorAll('.rowchk'), bar = $('bulkBar');
  function refreshBulk() { var n = document.querySelectorAll('.rowchk:checked').length; if (bar) { bar.style.display = n ? 'flex' : 'none'; $('bulkCount').textContent = n; } }
  chks.forEach(function (c) { c.addEventListener('change', refreshBulk); });
  var all = $('chkAll'); if (all) all.addEventListener('change', function () { chks.forEach(function (c) { c.checked = all.checked; }); refreshBulk(); });
  var br = $('bulkReject'); if (br) br.addEventListener('click', function () { var ids = Array.prototype.map.call(document.querySelectorAll('.rowchk:checked'), function (c) { return c.value; }); if (ids.length) openReject(ids, 'bulk ' + ids.length + '건'); });

  // ---- fetch toggles (media / popular visibility)
  document.querySelectorAll('[data-toggle]').forEach(function (t) {
    t.addEventListener('click', function () {
      fetch(t.dataset.toggle, { method: 'POST', headers: { 'X-Requested-With': 'fetch' } }).then(function (r) { return r.json(); }).then(function (j) { t.classList.toggle('on', !!j.is_active); var row = t.closest('.mrow'); if (row) row.style.opacity = j.is_active ? '' : '.5'; });
    });
  });

  // ---- media badge tabs
  document.querySelectorAll('#badgeTabs button').forEach(function (b) { b.addEventListener('click', function () { document.querySelectorAll('#badgeTabs button').forEach(function (o) { o.classList.remove('on'); }); b.classList.add('on'); $('badgeVal').value = b.dataset.badge; }); });
  // logo file preview
  var logoIn = document.querySelector('input[name="logo"]');
  if (logoIn) logoIn.addEventListener('change', function () { var f = logoIn.files[0]; if (!f) return; var slot = logoIn.closest('.upl').querySelector('.logo-slot'); var img = slot.querySelector('img') || document.createElement('img'); img.src = URL.createObjectURL(f); slot.appendChild(img); });

  // ---- popular rank move
  document.querySelectorAll('[data-move]').forEach(function (b) {
    b.addEventListener('click', function () {
      var row = b.closest('.rankset'), other = b.dataset.move === 'up' ? row.previousElementSibling : row.nextElementSibling;
      if (!other || !other.classList.contains('rankset')) return;
      var a = row.querySelector('select'), bb = other.querySelector('select'), an = row.querySelector('input'), bn = other.querySelector('input');
      var v = a.value; a.value = bb.value; bb.value = v; v = an.value; an.value = bn.value; bn.value = v;
    });
  });

  // ---- content editor
  var area = $('editorArea');
  if (area) {
    var html = $('editorHtml'), form = $('contentForm');
    function exec(cmd, val) { area.focus(); document.execCommand(cmd, false, val || null); }
    document.querySelectorAll('.editor .tb button[data-cmd]').forEach(function (b) {
      b.addEventListener('click', function () {
        var c = b.dataset.cmd;
        if (c === 'bold' || c === 'italic') exec(c);
        else if (c === 'h2') exec('formatBlock', '<h2>');
        else if (c === 'ul') exec('insertUnorderedList');
        else if (c === 'ol') exec('insertOrderedList');
        else if (c === 'hr') exec('insertHorizontalRule');
        else if (c === 'table') exec('insertHTML', '<table><thead><tr><th>항목</th><th>값</th></tr></thead><tbody><tr><td>&nbsp;</td><td>&nbsp;</td></tr><tr><td>&nbsp;</td><td>&nbsp;</td></tr></tbody></table><p><br></p>');
        else if (c === 'link') { var u = prompt('링크 URL'); if (u) exec('createLink', u); }
        else if (c === 'image') $('imgFile').click();
        else if (c === 'html') { var on = html.style.display !== 'none'; if (on) { area.innerHTML = html.value; html.style.display = 'none'; area.style.display = ''; } else { html.value = area.innerHTML; html.style.display = 'block'; area.style.display = 'none'; } }
      });
    });
    $('imgFile').addEventListener('change', function () {
      var f = this.files[0]; if (!f) return; var fd = new FormData(); fd.append('image', f);
      fetch('/admin/content/upload', { method: 'POST', body: fd }).then(function (r) { return r.json(); }).then(function (j) { if (j.ok) exec('insertHTML', '<img src="' + j.url + '" alt=""><p><br></p>'); else alert(j.error || '업로드 실패'); });
    });
    // board -> category / preview
    var boardSel = $('boardSel');
    function syncBoard() {
      var b = boardSel.value;
      document.querySelectorAll('[data-for]').forEach(function (el) { el.style.display = el.dataset.for === b ? '' : 'none'; });
      var sel = document.querySelector('select[name="category_' + b + '"]');
      $('categoryField').value = sel ? sel.value : 'series';
      $('pvCat').textContent = sel ? sel.options[sel.selectedIndex].text : (b === 'series' ? '입문 시리즈' : '');
    }
    boardSel.addEventListener('change', syncBoard);
    document.querySelectorAll('select[name^="category_"]').forEach(function (s) { s.addEventListener('change', syncBoard); });
    syncBoard();
    document.querySelector('input[name="title"]').addEventListener('input', function (e) { $('pvTitle').textContent = e.target.value || '제목'; });
    document.querySelectorAll('[data-when]').forEach(function (b) { b.addEventListener('click', function () { document.querySelectorAll('[data-when]').forEach(function (o) { o.classList.remove('on'); }); b.classList.add('on'); $('whenField').value = b.dataset.when; $('publishAt').style.display = b.dataset.when === 'schedule' ? 'block' : 'none'; }); });
    if ($('publishAt').value) { document.querySelector('[data-when="schedule"]').click(); }
    $('draftBtn').addEventListener('click', function () { $('modeField').value = 'draft'; });
    form.addEventListener('submit', function () { if (html.style.display !== 'none') area.innerHTML = html.value; $('bodyField').value = area.innerHTML; syncBoard(); });
  }

  if (window.lucide) window.lucide.createIcons();
})();
