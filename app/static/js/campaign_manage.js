// Campaign manage: row click -> fetch drawer partial; close; deep link via ?open=.
(function () {
  var drawer = document.getElementById('drawer');
  function close() { drawer.classList.remove('on'); document.querySelectorAll('tr[data-open]').forEach(function (o) { o.classList.remove('sel'); }); }
  function open(id, tr) {
    document.querySelectorAll('tr[data-open]').forEach(function (o) { o.classList.remove('sel'); });
    if (tr) tr.classList.add('sel');
    fetch(window.DRAWER_BASE + id + '/drawer').then(function (r) { return r.text(); }).then(function (html) {
      drawer.innerHTML = html; drawer.classList.add('on');
      drawer.querySelector('#dclose').addEventListener('click', close);
      if (window.lucide) window.lucide.createIcons();
    });
  }
  var rm = document.getElementById('rankModal'), rb = document.getElementById('rankBody');
  function closeRanks() { rm.classList.remove('on'); }
  rm.addEventListener('click', function (e) { if (e.target === rm) closeRanks(); });
  document.querySelectorAll('[data-ranks]').forEach(function (b) {
    b.addEventListener('click', function (e) {
      e.stopPropagation();
      fetch(window.DRAWER_BASE + b.dataset.ranks + '/ranks').then(function (r) { return r.text(); }).then(function (html) {
        rb.innerHTML = html;
        rm.classList.add('on');
        var x = document.getElementById('rkclose');
        if (x) x.addEventListener('click', closeRanks);
        if (window.lucide) window.lucide.createIcons();
      });
    });
  });
  document.querySelectorAll('tr[data-open]').forEach(function (tr) {
    tr.addEventListener('click', function (e) { if (e.target.closest('.rowact') || e.target.closest('a,button,form')) return; open(tr.dataset.open, tr); });
  });
  var dc = document.getElementById('dclose'); if (dc) dc.addEventListener('click', close);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
  if (window.OPEN_ID) open(window.OPEN_ID, document.querySelector('tr[data-open="' + window.OPEN_ID + '"]'));
})();
