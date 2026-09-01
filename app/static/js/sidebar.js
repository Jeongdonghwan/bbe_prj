// Sidebar: accordion (only one channel open), mobile drawer toggle, Lucide icons.
(function () {
  document.querySelectorAll('.acc').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.acc').forEach(function (o) { if (o !== b) o.classList.remove('open'); });
      b.classList.toggle('open');
    });
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
