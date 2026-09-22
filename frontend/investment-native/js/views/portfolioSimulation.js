import { api } from '../api.js';

const PROFILE_COPY = {
  stable: '안정 중심', balanced: '균형 중심', growth: '성장 중심',
};

function won(value) {
  return `${Math.round(Number(value || 0)).toLocaleString('ko-KR')}원`;
}

function renderScenarioChart(points) {
  if (!points?.length) return '';
  const width = 760, height = 255, pad = { top: 15, right: 18, bottom: 35, left: 18 };
  const values = points.flatMap((point) => [point.cautious, point.middle, point.positive]);
  const min = Math.min(...values), max = Math.max(...values), range = Math.max(max - min, 1);
  const x = (index) => pad.left + (index / Math.max(points.length - 1, 1)) * (width - pad.left - pad.right);
  const y = (value) => pad.top + (1 - (value - min) / range) * (height - pad.top - pad.bottom);
  const line = (key) => points.map((point, index) => `${x(index).toFixed(1)},${y(point[key]).toFixed(1)}`).join(' ');
  const area = `${line('positive')} ${[...points].reverse().map((point, reverseIndex) => `${x(points.length - 1 - reverseIndex).toFixed(1)},${y(point.cautious).toFixed(1)}`).join(' ')}`;
  return `<div class="scenario-chart-wrap"><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="가상 시장 시나리오별 포트폴리오 가치 흐름"><polygon points="${area}" class="scenario-area"/><line x1="${pad.left}" x2="${width - pad.right}" y1="${height / 2}" y2="${height / 2}" class="scenario-grid"/><polyline points="${line('positive')}" class="scenario-line is-positive"/><polyline points="${line('middle')}" class="scenario-line is-middle"/><polyline points="${line('cautious')}" class="scenario-line is-cautious"/></svg><div class="scenario-years"><span>시작</span><span>${points[points.length - 1].year}년 후</span></div></div>`;
}

function renderResult(data) {
  return `<section class="scenario-result"><div class="scenario-result-head"><div><p>가상 시장 경로 5,000회</p><h2>${data.profile_label} 구성의 ${data.years}년 시뮬레이션</h2></div><i class="fa-solid fa-chart-area"></i></div><p class="scenario-intro">${data.explanation}</p><div class="scenario-legend"><span class="is-cautious">보수적 흐름</span><span class="is-middle">중간 흐름</span><span class="is-positive">긍정적 흐름</span></div>${renderScenarioChart(data.points)}<div class="scenario-summary"><article><span>보수적 흐름</span><strong>${won(data.summary.cautious)}</strong><small>상황이 기대보다 좋지 않을 때의 참고 범위</small></article><article class="is-main"><span>중간 흐름</span><strong>${won(data.summary.middle)}</strong><small>여러 가상 결과의 가운데에 가까운 흐름</small></article><article><span>긍정적 흐름</span><strong>${won(data.summary.positive)}</strong><small>상황이 비교적 좋게 이어질 때의 참고 범위</small></article></div><p class="scenario-paid">내가 넣은 돈의 합계: <b>${won(data.total_paid)}</b></p></section>`;
}

export function portfolioSimulationView(container) {
  container.innerHTML = `<section class="portfolio-simulation-page"><div class="page-heading"><div><h1><i class="fa-solid fa-chart-area"></i> 포트폴리오 시뮬레이션</h1><p>여러 가상의 시장 상황을 통해 내 포트폴리오가 어떻게 달라질 수 있는지 살펴보세요.</p></div></div><aside class="simulation-explainer"><i class="fa-solid fa-dice"></i><div><strong>몬테카를로 시뮬레이션이란?</strong><p>한 번의 미래를 단정하지 않고, 다양한 시장 흐름을 많이 만들어 보는 방법입니다. 이 화면은 세 가지 결과 범위를 통해 “좋지 않은 경우에도 계속 투자할 수 있을까?”를 생각해 보는 데 도움을 줍니다.</p><div class="simulation-steps"><span><b>1</b>시장이 오르내리는 여러 미래를 만듭니다</span><span><b>2</b>같은 투자 계획을 각 미래에 적용합니다</span><span><b>3</b>결과를 모아 가능한 범위를 보여줍니다</span></div><button type="button" class="monte-carlo-help-button" id="monte-carlo-help" aria-haspopup="dialog" aria-expanded="false"><i class="fa-solid fa-circle-question" aria-hidden="true"></i> 몬테카를로 자세히 알아보기</button></div></aside><div class="monte-carlo-modal-backdrop" id="monte-carlo-modal" hidden><section class="monte-carlo-modal" role="dialog" aria-modal="true" aria-labelledby="monte-carlo-modal-title" tabindex="-1"><header class="monte-carlo-modal-header"><div><span class="monte-carlo-modal-icon"><i class="fa-solid fa-dice"></i></span><div><p class="monte-carlo-kicker">Monte Carlo Simulation <span aria-label="몬테 카를로 시뮬레이션">(몬테 카를로 시뮬레이션)</span></p><h2 id="monte-carlo-modal-title">많은 가상 미래로 가능성 살펴보기</h2><p>한 가지 예측 대신 수천 번의 서로 다른 시장 경로를 만들어 결과의 범위를 봅니다.</p></div></div><button type="button" class="monte-carlo-modal-close" aria-label="몬테카를로 설명 닫기"><i class="fa-solid fa-xmark"></i></button></header><div class="monte-carlo-modal-body"><div class="monte-carlo-plain-language"><span><i class="fa-solid fa-language"></i> 이름의 유래</span><p>몬테카를로는 카지노로 유명한 모나코의 도시 이름입니다. 제2차 세계대전 무렵 과학자들이 무작위 표본을 반복해서 뽑아 복잡한 문제를 푸는 방법을 발전시키며, 주사위·룰렛 같은 확률 게임을 떠올리게 하는 이 이름이 붙었습니다.</p></div><div class="monte-carlo-steps"><div><b>1</b><strong>가정 정하기</strong><span>기대수익률과 변동성 같은 출발 조건을 정합니다.</span></div><div><b>2</b><strong>무작위 경로 만들기</strong><span>매달 오르내릴 수익률을 여러 번 생성합니다.</span></div><div><b>3</b><strong>결과 모아 보기</strong><span>수천 개 결과의 가운데·낮은 쪽·높은 쪽을 비교합니다.</span></div></div><div class="monte-carlo-example"><h3><i class="fa-solid fa-bullseye"></i> 이 화면에서는 이렇게 읽으세요</h3><p>같은 투자금과 월 납입액이라도 매달 시장 흐름은 달라질 수 있습니다. 그래서 한 개의 ‘정답 금액’ 대신 5,000개 가상 결과 중 <b>10% 지점(보수적)</b>, <b>50% 지점(중간)</b>, <b>90% 지점(긍정적)</b>을 보여줍니다. 이는 확정된 미래가 아니라 가능한 범위를 이해하기 위한 참고값입니다.</p></div><div class="monte-carlo-code-head"><h3><i class="fa-brands fa-python"></i> 이 프로젝트에서 실제 쓰는 코드</h3><span>app/backend/routers/quant.py 일부</span></div><pre class="monte-carlo-code"><code>paths = 5_000
balances = np.full(paths, float(req.initial_amount))
monthly_return = (1 + config["return"]) ** (1 / 12) - 1
monthly_volatility = config["volatility"] / np.sqrt(12)

# 5,000개 경로마다 다른 월간 수익률을 만듭니다.
changes = rng.normal(monthly_return, monthly_volatility, paths)
balances = np.maximum(0, (balances + req.monthly_amount) * (1 + changes))

# 결과 분포에서 보수적·중간·긍정적 범위를 뽑습니다.
cautious, middle, positive = np.percentile(balances, [10, 50, 90])</code></pre><p class="monte-carlo-note"><i class="fa-solid fa-circle-info"></i> 결과는 수익률과 변동성에 관한 가정에 크게 좌우됩니다. 세금·수수료·물가·예상 밖의 시장 충격은 반영하지 않은 교육용 시뮬레이션입니다.</p></div></section></div><div class="simulation-layout"><section class="simulation-form"><h2>내 투자 계획</h2><label><span>구성 성향</span><select class="param-input" id="simulation-profile"><option value="stable">안정 중심</option><option value="balanced" selected>균형 중심</option><option value="growth">성장 중심</option></select></label><label><span>처음 투자할 금액</span><input class="param-input" id="simulation-initial" type="number" min="0" step="100000" value="10000000" /></label><label><span>매달 더할 금액</span><input class="param-input" id="simulation-monthly" type="number" min="0" step="10000" value="500000" /></label><label><span>투자 기간</span><select class="param-input" id="simulation-years"><option value="3">3년</option><option value="5">5년</option><option value="10" selected>10년</option><option value="20">20년</option></select></label><button class="run-btn" id="simulation-run"><i class="fa-solid fa-play"></i> 가상 시나리오 보기</button></section><div id="simulation-result" class="simulation-result"><div class="simulation-empty"><i class="fa-solid fa-chart-area"></i><p>투자 계획을 입력하고 시나리오를 확인해 보세요.</p></div></div></div><p class="simulation-disclaimer">이 시뮬레이션은 교육용 가정으로 만든 가상 결과입니다. 실제 시장 수익률, 세금·수수료·물가 및 개인 상황을 반영하지 않으며 미래 성과를 보장하지 않습니다.</p></section>`;
  const result = container.querySelector('#simulation-result');
  const run = container.querySelector('#simulation-run');
  const monteCarloHelp = container.querySelector('#monte-carlo-help');
  const monteCarloModal = container.querySelector('#monte-carlo-modal');
  const monteCarloPanel = monteCarloModal.querySelector('.monte-carlo-modal');
  const closeMonteCarloModal = () => { monteCarloModal.hidden = true; monteCarloHelp.setAttribute('aria-expanded', 'false'); monteCarloHelp.focus(); };
  monteCarloHelp.addEventListener('click', () => { monteCarloModal.hidden = false; monteCarloHelp.setAttribute('aria-expanded', 'true'); monteCarloPanel.focus(); });
  monteCarloModal.querySelector('.monte-carlo-modal-close').addEventListener('click', closeMonteCarloModal);
  monteCarloModal.addEventListener('click', (event) => { if (event.target === monteCarloModal) closeMonteCarloModal(); });
  monteCarloPanel.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMonteCarloModal(); });
  async function simulate() {
    const profile = container.querySelector('#simulation-profile').value;
    const initial_amount = Number(container.querySelector('#simulation-initial').value);
    const monthly_amount = Number(container.querySelector('#simulation-monthly').value);
    const years = Number(container.querySelector('#simulation-years').value);
    if (!Number.isFinite(initial_amount) || !Number.isFinite(monthly_amount) || initial_amount < 0 || monthly_amount < 0) { result.innerHTML = '<p class="combination-error">투자 금액은 0원 이상의 숫자로 입력해 주세요.</p>'; return; }
    run.disabled = true; run.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 가상 경로 생성 중...'; result.innerHTML = '<div class="simulation-loading"><i class="fa-solid fa-spinner fa-spin"></i> 다양한 시장 상황을 만들어 보고 있습니다.</div>';
    try { result.innerHTML = renderResult(await api.portfolioScenario({ profile, initial_amount, monthly_amount, years })); }
    catch (error) { result.innerHTML = `<p class="combination-error">${error.message || '시뮬레이션을 실행하지 못했습니다.'}</p>`; }
    finally { run.disabled = false; run.innerHTML = '<i class="fa-solid fa-play"></i> 가상 시나리오 보기'; }
  }
  run.addEventListener('click', simulate);
  simulate();
}
