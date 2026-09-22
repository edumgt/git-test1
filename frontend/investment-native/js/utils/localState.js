const PREFIX = 'investment-analysis:';

function keyFor(view, suffix) {
  return `${PREFIX}${suffix}:${view}`;
}

function safely(fn, fallback = null) {
  try {
    return fn();
  } catch (error) {
    // 저장 공간이 부족하거나 브라우저 정책으로 막힌 경우에도 화면 기능은 유지한다.
    console.warn('로컬 저장소 처리 실패:', error);
    return fallback;
  }
}

function controlKey(control) {
  return control.id || control.name || null;
}

function storableControls(root) {
  return [...root.querySelectorAll('input, select, textarea')].filter((control) => {
    const type = (control.type || '').toLowerCase();
    return controlKey(control)
      && !control.disabled
      && !control.closest('[data-local-state="off"]')
      && !['button', 'submit', 'reset', 'file', 'hidden', 'password'].includes(type);
  });
}

export function saveFormState(view, root = document) {
  if (!view || view.startsWith('quiz-')) return;
  const values = {};
  for (const control of storableControls(root)) {
    const key = controlKey(control);
    const type = (control.type || '').toLowerCase();
    if (type === 'radio') {
      if (control.checked) values[key] = { type, value: control.value };
    } else if (type === 'checkbox') {
      values[key] = { type, checked: control.checked };
    } else {
      values[key] = { type, value: control.value };
    }
  }
  safely(() => localStorage.setItem(keyFor(view, 'form'), JSON.stringify(values)));
}

export function restoreFormState(view, root = document) {
  if (!view || view.startsWith('quiz-')) return;
  const values = safely(() => JSON.parse(localStorage.getItem(keyFor(view, 'form')) || '{}'), {});
  for (const control of storableControls(root)) {
    const saved = values[controlKey(control)];
    if (!saved) continue;
    const type = (control.type || '').toLowerCase();
    if (type === 'radio') {
      control.checked = saved.value === control.value;
    } else if (type === 'checkbox') {
      control.checked = Boolean(saved.checked);
    } else {
      control.value = saved.value ?? control.value;
    }
  }
}

export function saveViewPayload(view, payload) {
  safely(() => localStorage.setItem(keyFor(view, 'payload'), JSON.stringify(payload)));
}

export function loadViewPayload(view) {
  return safely(() => JSON.parse(localStorage.getItem(keyFor(view, 'payload')) || 'null'));
}
