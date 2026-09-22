const BASE = '';

// Backward-compat helpers used by legacy views
export async function apiGet(path) { return apiFetch(path); }
export async function apiPost(path, body) { return apiFetch(path, { method: 'POST', body: JSON.stringify(body) }); }
export async function withLoading(btn, fn) {
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = '실행 중...';
  try { return await fn(); } finally { btn.disabled = false; btn.textContent = orig; }
}
export function renderError(msg) { return `<p style="color:#ef4444; margin-top:12px;">오류: ${msg}</p>`; }
export function renderImage(src) { return src ? `<img src="${src}" style="width:100%; border-radius:8px; margin-top:16px;"/>` : ''; }
export function renderMetrics(m) {
  if (!m) return '';
  return `<div style="display:flex; flex-wrap:wrap; gap:12px; margin-top:16px;">
    ${Object.entries(m).map(([k, v]) => `
      <div class="metric-box">
        <div style="font-size:0.7rem; color:#64748b; text-transform:uppercase; margin-bottom:4px;">${k.replace(/_/g,' ')}</div>
        <div style="font-size:1rem; font-weight:700; color:#3b82f6;">${typeof v === 'number' ? v.toFixed(4) : v}</div>
      </div>`).join('')}
  </div>`;
}

export async function apiFetch(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  health:           ()      => apiFetch('/api/health'),
  systemResources:  ()      => apiFetch('/api/system/resources'),
  visitorHeartbeat: (body)  => apiFetch('/api/visitors/heartbeat',         { method: 'POST', body: JSON.stringify(body) }),
  crossValidation:  (body)  => apiFetch('/api/ml/cross-validation',        { method: 'POST', body: JSON.stringify(body) }),
  decisionBoundary: ()      => apiFetch('/api/ml/decision-boundary'),
  randomForest:     (body)  => apiFetch('/api/ml/random-forest',           { method: 'POST', body: JSON.stringify(body) }),
  kmeans:           (body)  => apiFetch('/api/ml/kmeans',                  { method: 'POST', body: JSON.stringify(body) }),
  svm:              (body)  => apiFetch('/api/ml/svm',                     { method: 'POST', body: JSON.stringify(body) }),
  mlp:              (body)  => apiFetch('/api/ml/mlp',                     { method: 'POST', body: JSON.stringify(body) }),
  linearRegression: (body)  => apiFetch('/api/ml/linear-regression',       { method: 'POST', body: JSON.stringify(body) }),
  textClassify:     (body)  => apiFetch('/api/nlp/text-classify',          { method: 'POST', body: JSON.stringify(body) }),
  opencv:           (body)  => apiFetch('/api/cv/circle-animation',        { method: 'POST', body: JSON.stringify(body) }),
  huggingface:      (body)  => apiFetch('/api/genai/text-to-image',        { method: 'POST', body: JSON.stringify(body) }),
  cnnTimeseries:    (body)  => apiFetch('/api/dl/cnn-timeseries',          { method: 'POST', body: JSON.stringify(body) }),
  lstm:             (body)  => apiFetch('/api/dl/lstm-predictor',          { method: 'POST', body: JSON.stringify(body) }),
  transformer:      (body)  => apiFetch('/api/dl/transformer-timeseries',  { method: 'POST', body: JSON.stringify(body) }),
  backtest:         (body)  => apiFetch('/api/quant/backtest',             { method: 'POST', body: JSON.stringify(body) }),
  portfolio:        (body)  => apiFetch('/api/quant/portfolio',            { method: 'POST', body: JSON.stringify(body) }),
  portfolioScenario:(body)  => apiFetch('/api/quant/portfolio-scenario',   { method: 'POST', body: JSON.stringify(body) }),
  portfolioCombination: (body) => apiFetch('/api/market/portfolio-combination', { method: 'POST', body: JSON.stringify(body) }),
  risk:             (body)  => apiFetch('/api/quant/risk',                 { method: 'POST', body: JSON.stringify(body) }),
  pipeline:         (body)  => apiFetch('/api/quant/pipeline',             { method: 'POST', body: JSON.stringify(body) }),
  financialKnowledge:(body) => apiFetch('/api/quant/financial-knowledge',   { method: 'POST', body: JSON.stringify(body) }),
  marketSnapshot:   (body)  => apiFetch('/api/market/snapshot',             { method: 'POST', body: JSON.stringify(body) }),
  marketVolumeCloud:(market) => apiFetch(`/api/market/volume-cloud?market=${encodeURIComponent(market)}`),
  marketSectorCloud:(market) => apiFetch(`/api/market/sector-cloud?market=${encodeURIComponent(market)}`),
  macroRealtime:    (body)  => apiFetch('/api/macro/realtime',              { method: 'POST', body: JSON.stringify(body) }),
  macroSimulation:  (body)  => apiFetch('/api/macro/simulation',            { method: 'POST', body: JSON.stringify(body) }),
  dartCompanySearch:(body)  => apiFetch('/api/dart/company-search',         { method: 'POST', body: JSON.stringify(body) }),
  dartCompanyList:  (body)  => apiFetch('/api/dart/company-list',            { method: 'POST', body: JSON.stringify(body) }),
  groupNetwork:     (body)  => apiFetch('/api/dart/group-network',           { method: 'POST', body: JSON.stringify(body) }),
  industryPorter:   (body)  => apiFetch('/api/industry/porter',             { method: 'POST', body: JSON.stringify(body) }),
  industrySector:   (body)  => apiFetch('/api/industry/sector',             { method: 'POST', body: JSON.stringify(body) }),
  industryPeer:     (body)  => apiFetch('/api/industry/peer',               { method: 'POST', body: JSON.stringify(body) }),
  industryLifecycle:(body)  => apiFetch('/api/industry/lifecycle',          { method: 'POST', body: JSON.stringify(body) }),
  companyFinancials:(body)  => apiFetch('/api/finance/company-financials',  { method: 'POST', body: JSON.stringify(body) }),
  kospiExMeta:      ()      => apiFetch('/api/macro/kospi-ex/meta'),
  kospiEx:          (body)  => apiFetch('/api/macro/kospi-ex',              { method: 'POST', body: JSON.stringify(body) }),
  dartFinancialAnalysis: (body) => apiFetch('/api/dart/financial-analysis', { method: 'POST', body: JSON.stringify(body) }),
  taxSample:        ()      => apiFetch('/api/tax/sample'),
  taxSimulate:      (body)  => apiFetch('/api/tax/simulate',               { method: 'POST', body: JSON.stringify(body) }),
  quantLeanList:    ()      => apiFetch('/api/quant/lean'),
  quantLean:        (symbol) => apiFetch(`/api/quant/lean/${encodeURIComponent(symbol)}`),
  llmBenchStatus:   ()      => apiFetch('/api/llm-bench/status'),
  llmBenchChat:     (body)  => apiFetch('/api/llm-bench/chat',              { method: 'POST', body: JSON.stringify(body) }),
};
