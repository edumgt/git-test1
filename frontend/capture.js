(() => {
  function loadHtml2Canvas() {
    if (window.html2canvas) return Promise.resolve(window.html2canvas);
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
      script.onload = () => resolve(window.html2canvas);
      script.onerror = () => reject(new Error('캡처 도구를 불러오지 못했습니다. 네트워크 상태를 확인하세요.'));
      document.head.appendChild(script);
    });
  }

  const fab = document.querySelector('#screenCaptureFab');
  const panel = document.querySelector('#screenCapturePanel');
  if (!fab || !panel) return;
  const preview = panel.querySelector('[data-capture-preview]');
  const status = panel.querySelector('[data-capture-status]');
  const service = panel.querySelector('[data-capture-service]');
  let blob; let previewUrl;
  const copy = async () => {
    if (!blob || !navigator.clipboard?.write || !window.ClipboardItem) throw new Error('이 브라우저에서는 이미지 클립보드 복사를 지원하지 않습니다. PNG 저장을 이용하세요.');
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
  };
  fab.addEventListener('click', async () => {
    fab.disabled = true; fab.classList.add('is-capturing'); panel.hidden = false;
    status.textContent = '현재 보이는 화면을 캡처하고 있습니다…';
    try {
      const html2canvas = await loadHtml2Canvas();
      const canvas = await html2canvas(document.body, {
        backgroundColor: '#f5f5f5', scale: Math.min(window.devicePixelRatio || 1, 2),
        x: window.scrollX, y: window.scrollY, width: window.innerWidth, height: window.innerHeight,
        windowWidth: window.innerWidth, windowHeight: window.innerHeight,
        ignoreElements: (element) => element.dataset?.html2canvasIgnore === 'true',
      });
      blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
      if (!blob) throw new Error('PNG 이미지를 만들지 못했습니다.');
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(blob); preview.src = previewUrl;
      try { await copy(); status.textContent = 'PNG를 클립보드에 복사했습니다. GPT 창에서 Ctrl/⌘+V로 붙여넣으세요.'; }
      catch { status.textContent = '캡처가 준비되었습니다. PNG 저장 또는 이미지 다시 복사를 이용하세요.'; }
    } catch (error) { status.textContent = error.message || '화면 캡처에 실패했습니다.'; }
    finally { fab.disabled = false; fab.classList.remove('is-capturing'); }
  });
  panel.querySelector('[data-capture-close]').addEventListener('click', () => { panel.hidden = true; });
  panel.querySelector('[data-capture-copy]').addEventListener('click', async () => { try { await copy(); status.textContent = 'PNG를 클립보드에 다시 복사했습니다.'; } catch (error) { status.textContent = error.message; } });
  panel.querySelector('[data-capture-download]').addEventListener('click', () => {
    if (!previewUrl) { status.textContent = '먼저 캡처하기 버튼을 눌러 이미지를 준비하세요.'; return; }
    const link = document.createElement('a'); link.href = previewUrl;
    link.download = `investment-learning-${new Date().toISOString().slice(0, 10)}.png`; link.click();
  });
  panel.querySelector('[data-capture-open]').addEventListener('click', () => {
    if (!blob) { status.textContent = '먼저 캡처하기 버튼을 눌러 이미지를 준비하세요.'; return; }
    window.open(service.value, '_blank', 'noopener,noreferrer');
    status.textContent = 'GPT 웹을 열었습니다. 새 창에서 Ctrl/⌘+V로 이미지를 붙여넣고 질문하세요.';
  });
})();
