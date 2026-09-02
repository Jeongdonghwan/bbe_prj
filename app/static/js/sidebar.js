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

  var st = document.getElementById('sideToggle');
  if (st) st.addEventListener('click', function () {
    var r = document.documentElement;
    r.classList.toggle('side-min');
    try { localStorage.setItem('sideMin', r.classList.contains('side-min') ? '1' : '0'); } catch (e) {}
  });

  var sidebar = document.querySelector('.sidebar');
  var scrim = document.querySelector('.side-scrim');
  function closeSide() { if (sidebar) sidebar.classList.remove('open'); }
  document.querySelectorAll('[data-side-toggle]').forEach(function (el) {
    el.addEventListener('click', function (e) { e.preventDefault(); sidebar && sidebar.classList.toggle('open'); });
  });
  if (scrim) scrim.addEventListener('click', closeSide);

  if (window.lucide) window.lucide.createIcons();
})();
