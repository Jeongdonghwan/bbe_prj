// Community detail: like toggle (JSON), reply-to targeting.
(function () {
  var lb = document.getElementById('likeBtn');
  if (lb && window.LIKE_URL) lb.addEventListener('click', function () {
    fetch(window.LIKE_URL, { method: 'POST' }).then(function (r) { if (r.status === 302 || r.redirected) { location.href = '/auth/kakao?next=' + encodeURIComponent(location.pathname); return null; } return r.json(); })
      .then(function (j) { if (!j) return; document.getElementById('likeCnt').textContent = j.likes; lb.classList.toggle('on', j.liked); lb.style.color = j.liked ? 'var(--accent)' : ''; });
  });
  document.querySelectorAll('[data-reply]').forEach(function (b) {
    b.addEventListener('click', function () {
      document.getElementById('parentId').value = b.dataset.reply;
      document.getElementById('replyTo').innerHTML = '↳ <b>' + b.dataset.nick + '</b>님에게 답글 <button type="button" id="cancelReply" style="text-decoration:underline">취소</button>';
      document.getElementById('cancelReply').addEventListener('click', function () { document.getElementById('parentId').value = ''; document.getElementById('replyTo').innerHTML = ''; });
      document.querySelector('#commentForm textarea').focus();
    });
  });
})();
