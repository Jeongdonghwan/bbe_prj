// Community detail: like toggle (JSON), reply-to targeting.
(function () {
  var lb = document.getElementById('likeBtn');
  if (lb) lb.addEventListener('click', function () {
    fetch(lb.dataset.url, { method: 'POST', credentials: 'same-origin' }).then(function (r) {
      if (r.redirected || !r.ok) { location.href = '/auth/login?next=' + encodeURIComponent(location.pathname); return null; }
      return r.json();
    }).then(function (j) {
      if (!j) return;
      document.getElementById('likeCnt').textContent = j.likes;
      lb.classList.toggle('on', j.liked); lb.setAttribute('aria-pressed', j.liked ? 'true' : 'false');
    });
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
