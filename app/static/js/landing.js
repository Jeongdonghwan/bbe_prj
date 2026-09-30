/* 홍보 랜딩 효과 (templates/landing.html). 전부 장식이라 실패해도 내용은 그대로 보인다.
   - .rv 요소는 뷰포트에 들어오면 .in (등장 애니메이션, 한 번만)
   - [data-count] 는 0 → 목표값으로 세어 올림
   - 히어로 카드는 마우스 위치에 따라 살짝 기울고, 헤드라인 단어가 돌아가며 바뀜
   - 헤더는 스크롤 80px 뒤 축소
   모션 최소화 설정(prefers-reduced-motion)이면 애니메이션 없이 최종 상태만. */
(function () {
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 등장
  var rv = document.querySelectorAll('.rv');
  if (reduce || !('IntersectionObserver' in window)) {
    rv.forEach(function (el) { el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { threshold: 0.15, rootMargin: '0px 0px -8% 0px' });
    rv.forEach(function (el) { io.observe(el); });
  }

  // 숫자 세어 올리기
  function ease(t) { return 1 - Math.pow(1 - t, 3); }
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var target = +el.getAttribute('data-count'), suffix = el.getAttribute('data-suffix') || '';
    var fmt = function (n) { return n.toLocaleString('ko-KR') + suffix; };
    if (reduce || !('IntersectionObserver' in window)) { el.textContent = fmt(target); return; }
    el.textContent = fmt(0);
    var o = new IntersectionObserver(function (es) {
      if (!es[0].isIntersecting) return;
      o.disconnect();
      var start = performance.now(), dur = 1400;
      (function tick(now) {
        var p = Math.min((now - start) / dur, 1);
        el.textContent = fmt(Math.round(target * ease(p)));
        if (p < 1) requestAnimationFrame(tick);
      })(start);
    }, { threshold: 0.4 });
    o.observe(el);
  });

  // 헤드라인 단어 회전
  var rot = document.querySelector('.ld-rotate');
  if (rot && !reduce) {
    // 첫 <span> 이 보이는 단어, 나머지는 폭만 잡아 두는 숨은 사본 (CSS inline-grid)
    var words = rot.getAttribute('data-words').split('|'), i = 0, cur = rot.querySelector('span:not([aria-hidden])');
    setInterval(function () {
      rot.classList.add('out');
      setTimeout(function () {
        i = (i + 1) % words.length;
        cur.textContent = words[i];
        rot.classList.remove('out');
      }, 260);
    }, 2400);
  }

  // 히어로 카드 — 마우스 따라 기울기 (데스크톱만)
  var stage = document.querySelector('.ld-stage');
  if (stage && !reduce && window.matchMedia('(pointer:fine)').matches) {
    var cards = stage.querySelectorAll('.ld-fc');
    stage.parentElement.addEventListener('mousemove', function (e) {
      var r = stage.getBoundingClientRect();
      var dx = (e.clientX - (r.left + r.width / 2)) / r.width, dy = (e.clientY - (r.top + r.height / 2)) / r.height;
      cards.forEach(function (c, k) {
        var depth = (k + 1) * 6;
        c.style.transform = 'translate3d(' + (dx * depth).toFixed(1) + 'px,' + (dy * depth).toFixed(1) + 'px,0)';
      });
    });
    stage.parentElement.addEventListener('mouseleave', function () {
      cards.forEach(function (c) { c.style.transform = ''; });
    });
  }

  // 헤더 축소
  var nav = document.querySelector('.ld-nav'), ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { nav.classList.toggle('shrink', window.scrollY > 80); ticking = false; });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // FAQ — 하나 열면 나머지 닫기
  var faqs = document.querySelectorAll('.ld-faq details');
  faqs.forEach(function (d) {
    d.addEventListener('toggle', function () {
      if (d.open) faqs.forEach(function (o) { if (o !== d) o.open = false; });
    });
  });
})();
