const TOKEN_KEY = 'finance-rag-auth-token';
let user = null;

function token() { return localStorage.getItem(TOKEN_KEY); }
function headers() { return token() ? { Authorization: `Bearer ${token()}` } : {}; }

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || '요청을 처리하지 못했습니다.');
  return payload;
}

function updateBadge() {
  const badge = document.getElementById('auth-badge');
  if (!badge) return;
  badge.innerHTML = user
    ? `<i class="fa-solid fa-user-check"></i><span>${user.display_name}</span>`
    : '<i class="fa-solid fa-user"></i><span>회원가입/로그인</span>';
  badge.setAttribute('aria-label', user ? '내 계정과 사용 내역' : '회원가입 또는 로그인');
}

function modal() { return document.getElementById('auth-modal'); }
function closeModal() { modal()?.setAttribute('hidden', ''); document.body.classList.remove('modal-open'); }

async function renderActivity() {
  const target = document.getElementById('auth-activity');
  if (!target || !user) return;
  target.textContent = '사용 내역을 불러오는 중…';
  try {
    const items = await request('/auth/activity');
    if (!items.length) { target.textContent = '아직 저장된 사용 내역이 없습니다.'; return; }
    target.replaceChildren(...items.map((item) => {
      const row = document.createElement('li');
      const date = new Date(item.created_at).toLocaleString('ko-KR');
      row.textContent = `${item.view || item.action} · ${date}`;
      return row;
    }));
  } catch (error) { target.textContent = error.message; }
}

function showProfile() {
  const root = modal();
  root.querySelector('[data-auth-panel="form"]').hidden = true;
  root.querySelector('[data-auth-panel="profile"]').hidden = false;
  root.querySelector('#auth-profile-name').textContent = user.display_name;
  root.querySelector('#auth-profile-email').textContent = user.email;
  root.hidden = false;
  document.body.classList.add('modal-open');
  renderActivity();
}

function showForm(mode = 'login') {
  const root = modal();
  root.querySelector('[data-auth-panel="profile"]').hidden = true;
  root.querySelector('[data-auth-panel="form"]').hidden = false;
  root.querySelectorAll('[data-auth-mode]').forEach((button) => button.classList.toggle('active', button.dataset.authMode === mode));
  root.querySelector('#auth-username-field').hidden = mode !== 'signup';
  root.querySelector('#auth-username').required = mode === 'signup';
  root.querySelector('#auth-password').autocomplete = mode === 'signup' ? 'new-password' : 'current-password';
  root.querySelector('#auth-submit').textContent = mode === 'signup' ? '회원가입' : '로그인';
  root.querySelector('#auth-form').dataset.mode = mode;
  root.querySelector('#auth-error').textContent = '';
  root.hidden = false;
  document.body.classList.add('modal-open');
  root.querySelector('#auth-email').focus();
}

export function openAuthModal() { user ? showProfile() : showForm(); }

export async function recordUsage(view) {
  if (!user) return;
  try { await request('/auth/activity', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'view', view }) }); } catch { /* 로그 저장 실패는 화면 이용을 막지 않는다. */ }
}

export async function initAuth() {
  document.body.insertAdjacentHTML('beforeend', `
    <div id="auth-modal" class="auth-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="auth-modal-title" hidden>
      <section class="auth-modal"><button type="button" class="auth-modal-close" aria-label="닫기"><i class="fa-solid fa-xmark"></i></button>
        <div data-auth-panel="form"><h2 id="auth-modal-title">내 투자 학습 계정</h2><p>로그인하면 메뉴 이용 내역이 내 계정에 저장됩니다.</p>
          <div class="auth-tabs"><button type="button" data-auth-mode="login" class="active">로그인</button><button type="button" data-auth-mode="signup">회원가입</button></div>
          <form id="auth-form" data-mode="login"><label>이메일<input id="auth-email" type="email" required autocomplete="email"></label><label id="auth-username-field" hidden>이름<input id="auth-username" minlength="2" maxlength="30" autocomplete="name"></label><label>비밀번호<input id="auth-password" type="password" minlength="8" required autocomplete="current-password"></label><p id="auth-error" class="auth-error" aria-live="polite"></p><button id="auth-submit" class="auth-submit" type="submit">로그인</button></form>
        </div>
        <div data-auth-panel="profile" hidden><h2>내 계정</h2><p id="auth-profile-name"></p><small id="auth-profile-email"></small><h3>최근 사용 내역</h3><ul id="auth-activity" class="auth-activity"></ul><button type="button" id="auth-logout" class="auth-logout">로그아웃</button></div>
      </section>
    </div>`);
  document.getElementById('auth-badge')?.addEventListener('click', openAuthModal);
  modal().querySelector('.auth-modal-close').addEventListener('click', closeModal);
  modal().addEventListener('click', (event) => { if (event.target === modal()) closeModal(); });
  modal().querySelectorAll('[data-auth-mode]').forEach((button) => button.addEventListener('click', () => showForm(button.dataset.authMode)));
  modal().querySelector('#auth-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const mode = form.dataset.mode;
    const error = form.querySelector('#auth-error');
    const submit = form.querySelector('button[type="submit"]');
    const body = { email: form.querySelector('#auth-email').value, password: form.querySelector('#auth-password').value };
    if (mode === 'signup') body.display_name = form.querySelector('#auth-username').value;
    submit.disabled = true; error.textContent = '';
    try {
      const data = await request(`/auth/${mode === 'signup' ? 'signup' : 'login'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      localStorage.setItem(TOKEN_KEY, data.token); user = data.user; updateBadge(); closeModal(); recordUsage('로그인');
    } catch (err) { error.textContent = err.message; } finally { submit.disabled = false; }
  });
  modal().querySelector('#auth-logout').addEventListener('click', async () => { try { await request('/auth/logout', { method: 'POST' }); } catch {} localStorage.removeItem(TOKEN_KEY); user = null; updateBadge(); closeModal(); });
  if (token()) { try { user = await request('/auth/me'); } catch { localStorage.removeItem(TOKEN_KEY); } }
  updateBadge();
}
