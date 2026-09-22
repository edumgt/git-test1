import { api } from '../api.js';

const EXAMPLES = [
  ['AAPL', 'JNJ'],
  ['NVDA', 'KO'],
  ['005930.KS', '000660.KS'],
];

const SIGNALS = {
  green: { icon: 'fa-circle-check', label: '분산 효과 기대', className: 'is-green' },
  yellow: { icon: 'fa-triangle-exclamation', label: '보통', className: 'is-yellow' },
  red: { icon: 'fa-circle-exclamation', label: '함께 움직이는 편', className: 'is-red' },
};

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[char]));
}

function formatChartDate(value) {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric' }).format(date);
}

function renderFlowChart(points, tickerA, tickerB, signal) {
  if (!Array.isArray(points) || points.length < 2) return '';

  const width = 760;
  const height = 250;
  const padding = { top: 20, right: 22, bottom: 34, left: 22 };
  const values = points.flatMap((point) => [Number(point.a), Number(point.b)]).filter(Number.isFinite);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const x = (index) => padding.left + (index / (points.length - 1)) * (width - padding.left - padding.right);
  const y = (value) => padding.top + (1 - (value - min) / range) * (height - padding.top - padding.bottom);
  const line = (key) => points.map((point, index) => `${x(index).toFixed(1)},${y(Number(point[key])).toFixed(1)}`).join(' ');
  const mid = points[Math.floor(points.length / 2)];
  const why = {
    green: '두 선이 같은 방향으로만 움직이지 않고 갈라지는 구간이 보입니다. 한 종목의 변화가 포트폴리오 전체에 그대로 이어질 가능성을 낮추는 데 도움이 될 수 있습니다.',
    yellow: '두 선이 함께 움직이는 구간과 다른 방향을 보이는 구간이 섞여 있습니다. 분산 효과는 있지만, 시장 상황에 따라 두 종목이 동시에 흔들릴 수도 있습니다.',
    red: '두 선이 비슷한 시점에 오르내리는 구간이 많이 보입니다. 한 종목이 흔들릴 때 다른 종목도 함께 영향을 받을 가능성이 있어 분산 효과가 제한적일 수 있습니다.',
  }[signal] || '';

  return `
    <article class="combination-chart-card">
      <div class="combination-chart-head">
        <div>
          <h3><i class="fa-solid fa-chart-line"></i> 같은 출발선에서 본 가격 흐름</h3>
          <p>종목별 가격 단위는 달라도, 어느 쪽이 더 오르내렸는지는 한눈에 비교할 수 있도록 그렸습니다.</p>
        </div>
        <div class="chart-legend"><span class="line-a"><i></i>${escapeHtml(tickerA)}</span><span class="line-b"><i></i>${escapeHtml(tickerB)}</span></div>
      </div>
      <div class="flow-chart-wrap" role="img" aria-label="${escapeHtml(tickerA)}와 ${escapeHtml(tickerB)}의 기간별 가격 흐름 비교 차트">
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
          <line x1="${padding.left}" x2="${width - padding.right}" y1="${height / 2}" y2="${height / 2}" class="flow-grid" />
          <polyline points="${line('a')}" class="flow-line flow-line-a" />
          <polyline points="${line('b')}" class="flow-line flow-line-b" />
        </svg>
        <div class="flow-chart-dates"><span>${formatChartDate(points[0].date)}</span><span>${formatChartDate(mid.date)}</span><span>${formatChartDate(points[points.length - 1].date)}</span></div>
      </div>
      <p class="chart-why"><i class="fa-solid fa-lightbulb"></i> <b>차트 읽기:</b> ${why}</p>
    </article>`;
}

export function portfolioCombinationView(container) {
  container.innerHTML = `
    <section class="portfolio-combination">
      <div class="page-heading">
        <div>
          <h1><i class="fa-solid fa-traffic-light"></i> 포트폴리오 조합</h1>
          <p>두 종목을 골라 함께 담았을 때의 분산 효과를 신호등으로 확인하세요.</p>
        </div>
      </div>

      <aside class="composition-guide" aria-label="포트폴리오 조합 안내">
        <div class="composition-guide-icon"><i class="fa-solid fa-seedling"></i></div>
        <div>
          <strong>포트폴리오를 나누어 담는 이유</strong>
          <p>한 종목에만 투자하면 그 회사의 좋은 일과 나쁜 일이 내 투자금에 크게 영향을 줍니다. 서로 다른 흐름을 보이는 종목을 함께 담으면, 한쪽이 흔들릴 때 다른 한쪽이 전체 변동을 덜어 줄 수 있습니다.</p>
          <p><button type="button" class="term-help-button" id="covariance-help" aria-haspopup="dialog" aria-expanded="false">공분산 <i class="fa-solid fa-circle-question" aria-hidden="true"></i></button>은 두 종목이 같은 시기에 함께 움직이는 경향을 살펴보는 방법입니다. 이 화면에서는 어려운 숫자 대신, 차트의 두 선과 신호등으로 “두 종목이 얼마나 비슷하게 움직였는지”를 쉽게 보여드립니다.</p>
          <p><button type="button" class="term-help-button" id="correlation-help" aria-haspopup="dialog" aria-expanded="false">수익률 상관관계 <i class="fa-solid fa-circle-question" aria-hidden="true"></i></button>는 두 종목이 오르거나 내린 날에 얼마나 자주 비슷한 방향을 보였는지 살펴보는 기준입니다. 함께 움직이는 날이 많으면 빨간 신호에 가까워지고, 서로 다른 흐름을 보이는 구간이 많으면 초록 신호에 가까워집니다.</p>
        </div>
        <div class="signal-legend" aria-label="신호등 의미">
          <span class="legend-green"><i class="fa-solid fa-circle"></i> 함께 담기 좋은 편</span>
          <span class="legend-yellow"><i class="fa-solid fa-circle"></i> 보통</span>
          <span class="legend-red"><i class="fa-solid fa-circle"></i> 비슷하게 움직이는 편</span>
        </div>
      </aside>

      <div class="covariance-modal-backdrop" id="covariance-modal" hidden>
        <section class="covariance-modal" role="dialog" aria-modal="true" aria-labelledby="covariance-modal-title" tabindex="-1">
          <header class="covariance-modal-header">
            <div><span class="covariance-modal-icon"><i class="fa-solid fa-arrows-left-right-to-line"></i></span><div><p class="covariance-kicker">Covariance <span aria-label="코베리언스">(코베리언스)</span></p><h2 id="covariance-modal-title">공분산, 함께 움직임의 방향</h2><p>두 종목의 수익률이 평균에서 얼마나 같이 벗어나는지 보는 값입니다.</p></div></div>
            <button type="button" class="covariance-modal-close" aria-label="공분산 설명 닫기"><i class="fa-solid fa-xmark"></i></button>
          </header>
          <div class="covariance-modal-body">
            <div class="covariance-plain-language"><span><i class="fa-solid fa-language"></i> 용어 한눈에 보기</span><p><b>공분산</b>은 영어로 <b>Covariance</b>라고 쓰고, 한국어식으로는 <b>코베리언스</b>라고 읽습니다. ‘공동으로(共) 흩어진 정도(分散)’를 본다는 뜻으로, 두 종목이 평균 수익률에서 함께 멀어지는지를 살펴봅니다.</p></div>
            <p class="covariance-intro">둘 다 평균보다 높은 날이나 낮은 날이 자주 겹치면 <b>양수</b>, 한쪽이 높을 때 다른 쪽이 낮은 날이 많으면 <b>음수</b>에 가까워집니다. 0에 가까우면 함께 움직이는 뚜렷한 방향이 약하다는 뜻입니다.</p>
            <div class="covariance-sign-grid" aria-label="공분산 값의 의미"><div><i class="fa-solid fa-arrow-trend-up"></i><b>양수 (+)</b><span>두 종목이 같은 방향으로 움직이는 날이 많은 편</span></div><div><i class="fa-solid fa-arrows-left-right"></i><b>0에 가까움</b><span>함께 움직이는 일정한 방향이 뚜렷하지 않음</span></div><div><i class="fa-solid fa-arrow-right-arrow-left"></i><b>음수 (−)</b><span>한쪽이 오를 때 다른 쪽이 내리는 날이 많은 편</span></div></div>
            <div class="covariance-formula" aria-label="공분산 수식"><span>Cov(X, Y)</span> = <span>Σ (Xᵢ − X̄)(Yᵢ − Ȳ)</span> / <span>(n − 1)</span></div>
            <ul class="covariance-meaning"><li><b>Xᵢ, Yᵢ</b>: 같은 날의 두 종목 수익률</li><li><b>X̄, Ȳ</b>: 각 종목의 평균 수익률</li><li>각 날의 ‘평균에서 벗어난 정도’를 곱해 평균 낸 값입니다.</li></ul>
            <div class="covariance-mini-example"><h3><i class="fa-solid fa-calendar-day"></i> 아주 짧은 예시</h3><p>A와 B가 모두 평균보다 <b>높았던 날</b>에는 두 값의 차이가 모두 +여서 곱한 값도 +입니다. 반대로 A는 높고 B는 <b>낮았던 날</b>에는 +와 −를 곱하므로 −가 됩니다. 이런 값을 여러 날에 걸쳐 평균 내면 공분산이 됩니다.</p></div>
            <div class="covariance-example"><h3><i class="fa-solid fa-chart-pie"></i> 포트폴리오에 어떻게 쓰나요?</h3><p>두 종목의 공분산이 낮거나 음수이면 한 종목의 움직임이 다른 종목과 덜 겹칠 수 있어, 함께 담았을 때 전체 흔들림을 줄이는 데 도움이 될 수 있습니다. 다만 공분산은 단위 영향을 받으므로 종목 간 비교에는 상관계수도 함께 확인하세요.</p></div>
            <div class="covariance-code-head"><h3><i class="fa-brands fa-python"></i> 이 프로젝트에서 쓰는 코드</h3><span>app/src/RiskManager.py 일부</span></div>
            <pre class="covariance-code"><code># returns_df: 종목별 일간 수익률 DataFrame
# 예) 열: AAPL, JNJ, 005930.KS
vol = returns_df.std() * np.sqrt(252)  # 각 종목의 연환산 변동성

# 일간 수익률의 공분산 행렬을 연 단위로 환산합니다.
cov = returns_df.cov() * 252

# 동일 비중으로 담았을 때의 포트폴리오 변동성
weights = np.ones(len(returns_df.columns)) / len(returns_df.columns)
port_vol = float(np.sqrt(weights @ cov.values @ weights))</code></pre>
            <p class="covariance-code-explanation"><b>핵심:</b> <code>returns_df.cov()</code>가 종목 쌍마다 공분산을 계산합니다. 그 결과를 <code>weights @ cov.values @ weights</code>에 넣어, 종목들이 함께 움직이는 정도까지 반영한 포트폴리오 전체 변동성을 구합니다.</p>
            <p class="covariance-note"><i class="fa-solid fa-circle-info"></i> 과거 공분산은 미래를 보장하지 않습니다. 시장 급변 시에는 서로 다른 종목도 함께 움직일 수 있습니다.</p>
          </div>
        </section>
      </div>

      <div class="correlation-modal-backdrop" id="correlation-modal" hidden>
        <section class="correlation-modal" role="dialog" aria-modal="true" aria-labelledby="correlation-modal-title" tabindex="-1">
          <header class="correlation-modal-header">
            <div><span class="correlation-modal-icon"><i class="fa-solid fa-link"></i></span><div><p class="correlation-kicker">Correlation <span aria-label="코릴레이션">(코릴레이션)</span></p><h2 id="correlation-modal-title">수익률 상관관계, 방향의 닮은 정도</h2><p>가격 자체가 아니라, 매일의 수익률이 같은 방향으로 움직이는 정도를 −1부터 +1로 나타냅니다.</p></div></div>
            <button type="button" class="correlation-modal-close" aria-label="수익률 상관관계 설명 닫기"><i class="fa-solid fa-xmark"></i></button>
          </header>
          <div class="correlation-modal-body">
            <div class="correlation-plain-language"><span><i class="fa-solid fa-language"></i> 용어 한눈에 보기</span><p><b>상관관계</b>는 영어로 <b>Correlation</b>, 한국어식으로 <b>코릴레이션</b>이라고 읽습니다. 두 종목이 같은 날 오르고 내리는 <b>방향의 닮은 정도</b>를 비교하기 쉬운 숫자로 바꾼 값입니다.</p></div>
            <div class="correlation-scale" aria-label="상관계수 범위"><div class="negative"><b>−1</b><span>반대 방향</span></div><div class="neutral"><b>0</b><span>뚜렷한 관계 없음</span></div><div class="positive"><b>+1</b><span>같은 방향</span></div></div>
            <p class="correlation-intro"><b>+1에 가까울수록</b> 함께 오르내리는 경향이 강하고, <b>−1에 가까울수록</b> 반대 방향으로 움직이는 경향이 강합니다. 0 근처라면 두 수익률의 직선적인 관계가 약한 편입니다.</p>
            <div class="correlation-formula" aria-label="상관계수 수식"><span>Corr(X, Y)</span> = <span>Cov(X, Y)</span> / <span>(σₓ × σᵧ)</span></div>
            <ul class="correlation-meaning"><li><b>Cov(X, Y)</b>: 앞에서 본 공분산</li><li><b>σₓ, σᵧ</b>: 각 종목 수익률의 변동성(표준편차)</li><li>공분산을 각 종목의 변동성으로 나눠, 종목의 가격 단위와 관계없이 −1~+1 범위에서 비교할 수 있게 합니다.</li></ul>
            <div class="correlation-example"><h3><i class="fa-solid fa-traffic-light"></i> 이 화면의 신호등 기준</h3><p>상관계수가 <b>0.30 미만</b>이면 초록, <b>0.30 이상 0.70 미만</b>이면 노랑, <b>0.70 이상</b>이면 빨강 신호로 보여줍니다. 이는 최근 흐름을 쉽게 읽기 위한 안내 기준입니다.</p></div>
            <div class="correlation-code-head"><h3><i class="fa-brands fa-python"></i> 이 화면에서 실제 쓰는 코드</h3><span>app/backend/main.py 일부</span></div>
            <pre class="correlation-code"><code># 두 종목의 같은 거래일 종가를 맞춘 뒤
aligned_prices = pd.concat(prices, axis=1, join="inner").dropna()

# 가격 변화율(일간 수익률)을 계산합니다.
daily_moves = aligned_prices.pct_change(fill_method=None).dropna()

# 두 종목 수익률의 상관계수(−1 ~ +1)
relationship = float(daily_moves.corr().iloc[0, 1])</code></pre>
            <p class="correlation-code-explanation"><b>핵심:</b> <code>pct_change()</code>로 종가를 수익률로 바꾼 뒤, <code>corr()</code>로 두 종목의 상관계수를 구합니다. 이 값이 현재 조합 화면의 신호등 색을 결정합니다.</p>
            <p class="correlation-note"><i class="fa-solid fa-circle-info"></i> 상관관계는 과거 구간과 시장 상황에 따라 달라집니다. 낮은 상관관계가 미래의 분산 효과를 보장하지는 않습니다.</p>
          </div>
        </section>
      </div>

      <div class="combination-card">
        <div class="combination-form">
          <label>
            <span>첫 번째 종목</span>
            <input id="combination-ticker-a" class="param-input" value="AAPL" maxlength="15" autocomplete="off" placeholder="예: AAPL 또는 005930.KS" />
          </label>
          <div class="combination-plus" aria-hidden="true"><i class="fa-solid fa-plus"></i></div>
          <label>
            <span>두 번째 종목</span>
            <input id="combination-ticker-b" class="param-input" value="JNJ" maxlength="15" autocomplete="off" placeholder="예: JNJ 또는 000660.KS" />
          </label>
          <label>
            <span>분석 기간</span>
            <select id="combination-period" class="param-input">
              <option value="3mo">최근 3개월</option>
              <option value="6mo">최근 6개월</option>
              <option value="1y" selected>최근 1년</option>
              <option value="2y">최근 2년</option>
            </select>
          </label>
        </div>
        <div class="combination-actions">
          <button class="run-btn" id="combination-run"><i class="fa-solid fa-chart-simple"></i> 조합 확인하기</button>
          <div class="combination-examples">빠른 선택: ${EXAMPLES.map(([a, b]) => `<button type="button" data-a="${a}" data-b="${b}">${a} + ${b}</button>`).join('')}</div>
        </div>
        <p class="combination-help">미국 종목은 <b>AAPL</b>, 국내 종목은 <b>005930.KS</b>처럼 입력하세요.</p>
      </div>

      <div id="combination-result" class="combination-result" aria-live="polite">
        <div class="combination-empty"><i class="fa-solid fa-traffic-light"></i><p>두 종목을 선택하고 조합을 확인해 보세요.</p></div>
      </div>
    </section>`;

  const tickerA = container.querySelector('#combination-ticker-a');
  const tickerB = container.querySelector('#combination-ticker-b');
  const period = container.querySelector('#combination-period');
  const run = container.querySelector('#combination-run');
  const result = container.querySelector('#combination-result');
  const covarianceHelp = container.querySelector('#covariance-help');
  const covarianceModal = container.querySelector('#covariance-modal');
  const covarianceClose = covarianceModal.querySelector('.covariance-modal-close');
  const covariancePanel = covarianceModal.querySelector('.covariance-modal');
  const correlationHelp = container.querySelector('#correlation-help');
  const correlationModal = container.querySelector('#correlation-modal');
  const correlationClose = correlationModal.querySelector('.correlation-modal-close');
  const correlationPanel = correlationModal.querySelector('.correlation-modal');

  const closeCovarianceModal = () => {
    covarianceModal.hidden = true;
    covarianceHelp.setAttribute('aria-expanded', 'false');
    covarianceHelp.focus();
  };
  covarianceHelp.addEventListener('click', () => {
    covarianceModal.hidden = false;
    covarianceHelp.setAttribute('aria-expanded', 'true');
    covariancePanel.focus();
  });
  covarianceClose.addEventListener('click', closeCovarianceModal);
  covarianceModal.addEventListener('click', (event) => {
    if (event.target === covarianceModal) closeCovarianceModal();
  });
  covariancePanel.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeCovarianceModal();
  });

  const closeCorrelationModal = () => {
    correlationModal.hidden = true;
    correlationHelp.setAttribute('aria-expanded', 'false');
    correlationHelp.focus();
  };
  correlationHelp.addEventListener('click', () => {
    correlationModal.hidden = false;
    correlationHelp.setAttribute('aria-expanded', 'true');
    correlationPanel.focus();
  });
  correlationClose.addEventListener('click', closeCorrelationModal);
  correlationModal.addEventListener('click', (event) => {
    if (event.target === correlationModal) closeCorrelationModal();
  });
  correlationPanel.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeCorrelationModal();
  });

  container.querySelectorAll('.combination-examples button').forEach((button) => {
    button.addEventListener('click', () => {
      tickerA.value = button.dataset.a;
      tickerB.value = button.dataset.b;
    });
  });

  async function analyse() {
    const a = tickerA.value.trim().toUpperCase();
    const b = tickerB.value.trim().toUpperCase();
    if (!a || !b) {
      result.innerHTML = '<p class="combination-error">두 종목 코드를 모두 입력해 주세요.</p>';
      return;
    }
    if (a === b) {
      result.innerHTML = '<p class="combination-error">서로 다른 두 종목을 선택해 주세요.</p>';
      return;
    }

    run.disabled = true;
    run.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 데이터 확인 중...';
    result.innerHTML = '<div class="combination-loading"><i class="fa-solid fa-spinner fa-spin"></i> 최근 가격 흐름을 불러오는 중입니다.</div>';
    try {
      const data = await api.portfolioCombination({ ticker_a: a, ticker_b: b, period: period.value });
      const signal = SIGNALS[data.signal] || SIGNALS.yellow;
      const latest = data.latest_data_at ? new Intl.DateTimeFormat('ko-KR', { month: 'long', day: 'numeric' }).format(new Date(data.latest_data_at)) : '최근 거래일';
      result.innerHTML = `
        <article class="signal-card ${signal.className}">
          <div class="signal-light"><i class="fa-solid ${signal.icon}"></i></div>
          <div class="signal-copy">
            <p class="signal-eyebrow">${escapeHtml(data.ticker_a)} + ${escapeHtml(data.ticker_b)}</p>
            <h2>${signal.label}</h2>
            <p>${escapeHtml(data.summary)}</p>
          </div>
        </article>
        ${renderFlowChart(data.chart_points, data.ticker_a, data.ticker_b, data.signal)}
        <div class="combination-detail-grid">
          <article class="combination-detail-card">
            <h3><i class="fa-solid fa-calendar-days"></i> 분석 기준</h3>
            <p>${escapeHtml(data.period_label)} 동안 두 종목이 함께 움직인 흐름을 확인했습니다.</p>
            <small>최근 데이터: ${latest} · 공휴일 등으로 실제 거래일 수는 달라질 수 있습니다.</small>
          </article>
          <article class="combination-detail-card">
            <h3><i class="fa-solid fa-compass"></i> 포트폴리오 힌트</h3>
            <p>${escapeHtml(data.portfolio_hint)}</p>
            <small>이 결과는 과거 가격 흐름을 바탕으로 한 참고 정보이며, 미래 성과를 보장하지 않습니다.</small>
          </article>
        </div>`;
    } catch (error) {
      result.innerHTML = `<p class="combination-error">${escapeHtml(error.message || '데이터를 불러오지 못했습니다.')} 종목 코드를 확인한 뒤 다시 시도해 주세요.</p>`;
    } finally {
      run.disabled = false;
      run.innerHTML = '<i class="fa-solid fa-chart-simple"></i> 조합 확인하기';
    }
  }

  run.addEventListener('click', analyse);
}
