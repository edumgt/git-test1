(() => {
  const API_BASE = window.API_BASE || '';
  const tokenKey = 'finance-rag-auth-token';
  let signup = false;
  let user = null;
  const button = document.querySelector('#authButton');
  const modal = document.querySelector('#authModal');
  const form = document.querySelector('#authForm');
  const status = document.querySelector('#authStatus');
  const switcher = document.querySelector('#authSwitch');
  const nameField = document.querySelector('#authNameField');
  const formPanel = document.querySelector('#authFormPanel');
  const profilePanel = document.querySelector('#authProfilePanel');
  const activity = document.querySelector('#authActivity');
  if (!button || !modal || !form || !status || !switcher || !nameField) return;

  const token = () => localStorage.getItem(tokenKey);
  const headers = () => ({ 'Content-Type': 'application/json', ...(token() ? { Authorization: `Bearer ${token()}` } : {}) });
  const request = async (path, options = {}) => {
    const response = await fetch(`${API_BASE}${path}`, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
    const data = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || '요청을 처리하지 못했습니다.');
    return data;
  };
  function show(open) { modal.hidden = !open; document.body.classList.toggle('modal-open', open); }
  function updateButton() {
    button.innerHTML = user ? `<i class="fa-solid fa-user-check"></i> ${escapeHtml(user.display_name)}` : '<i class="fa-solid fa-user"></i> 회원가입/로그인';
    button.title = user ? `${user.display_name}님 계정과 사용 내역` : '회원가입 또는 로그인';
    button.dataset.loggedIn = user ? 'true' : '';
  }
  function escapeHtml(value) { const el = document.createElement('span'); el.textContent = value || ''; return el.innerHTML; }
  function showForm() { formPanel.hidden = false; profilePanel.hidden = true; show(true); document.querySelector('#authEmail').focus(); }
  async function showProfile() {
    formPanel.hidden = true; profilePanel.hidden = false;
    document.querySelector('#authProfileName').textContent = user.display_name;
    document.querySelector('#authProfileEmail').textContent = user.email;
    activity.textContent = '사용 내역을 불러오는 중…'; show(true);
    try {
      const items = await request('/auth/activity');
      activity.replaceChildren(...(items.length ? items.map((item) => {
        const row = document.createElement('li');
        row.textContent = `${item.view || item.action} · ${new Date(item.created_at).toLocaleString('ko-KR')}`;
        return row;
      }) : [Object.assign(document.createElement('li'), { textContent: '아직 저장된 사용 내역이 없습니다.' })]));
    } catch (error) { activity.textContent = error.message; }
  }
  function setMode(isSignup) {
    signup = isSignup; nameField.hidden = !signup;
    document.querySelector('#authName').required = signup;
    status.textContent = '';
    document.querySelector('#authTitle').textContent = signup ? '회원가입' : '로그인';
    form.querySelector('button').textContent = signup ? '가입하고 시작하기' : '로그인';
    switcher.textContent = signup ? '이미 계정이 있어요' : '회원가입';
    document.querySelector('#authPassword').autocomplete = signup ? 'new-password' : 'current-password';
  }
  button.addEventListener('click', () => user ? showProfile() : showForm());
  document.querySelectorAll('[data-auth-close]').forEach((item) => item.addEventListener('click', () => show(false)));
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !modal.hidden) show(false); });
  switcher.addEventListener('click', () => setMode(!signup));
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); status.textContent = '';
    const email = form.querySelector('#authEmail').value;
    const password = form.querySelector('#authPassword').value;
    const displayName = form.querySelector('#authName').value;
    const body = { email, password, ...(signup ? { display_name: displayName } : {}) };
    try {
      const data = await request(`/auth/${signup ? 'signup' : 'login'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      localStorage.setItem(tokenKey, data.token); user = data.user; updateButton(); show(false); form.reset();
      window.dispatchEvent(new CustomEvent('finance:auth-changed', { detail: user }));
    } catch (error) { status.textContent = error.message; }
  });
  document.querySelector('#authLogout').addEventListener('click', async () => {
    try { await request('/auth/logout', { method: 'POST' }); } catch { /* local logout remains available */ }
    localStorage.removeItem(tokenKey); user = null; updateButton(); show(false);
    window.dispatchEvent(new CustomEvent('finance:auth-changed', { detail: null }));
  });
  window.addEventListener('finance:view', async (event) => {
    if (!user) return;
    try { await request('/auth/activity', { method: 'POST', body: JSON.stringify({ action: 'view', view: event.detail || '' }) }); } catch { /* usage logging never blocks navigation */ }
  });
  async function restore() {
    if (!token()) return;
    try { user = await request('/auth/me'); } catch { localStorage.removeItem(tokenKey); user = null; }
    updateButton();
  }
  setMode(false); restore();
})();
