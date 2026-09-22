/**
 * includeSidebar.js — 정적 MPA 페이지(pages/*.html)에서 공통 사이드바 내비게이션을
 * partials/sidebar-nav.html로부터 fetch 하여 주입한다. 해당 파일은 index.html(SPA)
 * 쪽 사이드바를 생성할 때 자동으로 만들어지므로 직접 수정하지 말 것
 * (readme.md 참고 / scripts/build-sidebar-partial.py 로 재생성).
 */
(async function includeSidebar() {
  const slot = document.getElementById('sidebar-nav-slot');
  if (!slot) return;

  try {
    const res = await fetch('partials/sidebar-nav.html');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    slot.outerHTML = await res.text();
  } catch (err) {
    slot.innerHTML = `<p style="padding:16px;color:var(--text-muted);font-size:.82rem;">
      메뉴를 불러오지 못했습니다. <a href="../index.html">대시보드로 이동</a>
    </p>`;
    console.error('사이드바 로드 실패:', err);
    return;
  }

  if (typeof window._orderSidebarSections === 'function') window._orderSidebarSections();
  if (typeof window._ensureSidebarChatbot === 'function') window._ensureSidebarChatbot();

  // 현재 정적 페이지에 해당하는 메뉴 링크를 활성 표시
  const page = document.body.dataset.page;
  if (page) {
    const link = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (link) {
      link.classList.add('active');
    }
  }
})();
