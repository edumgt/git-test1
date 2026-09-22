/**
 * 드로잉 차트 — 사이드바에서 여는 오프캔버스(우측 슬라이드) 패널.
 * 원래 학습 문서(주식 2)의 인라인 버튼으로 열리던 모달을 분리해,
 * 어느 화면에서든 사이드바 메뉴로 열 수 있게 만든 전역 위젯이다.
 */
export function initChartDrawingOffcanvas() {
  const trigger = document.querySelector('.nav-item[data-view="chart-drawing"]');
  if (!trigger) return;

  const panel = document.createElement('div');
  panel.className = 'chart-drawing-offcanvas-backdrop';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true');
  panel.setAttribute('aria-labelledby', 'chart-drawing-offcanvas-title');
  panel.innerHTML = `
    <section class="chart-drawing-offcanvas">
      <header class="chart-drawing-offcanvas-header">
        <div><span class="chart-drawing-offcanvas-icon"><i class="fa-solid fa-chart-line"></i></span><div><h2 id="chart-drawing-offcanvas-title">드로잉 차트</h2><p>왼쪽에 가격 흐름을 그리면 오른쪽에서 주식 차트 형태와 읽는 순서를 확인합니다.</p></div></div>
        <button type="button" class="chart-drawing-offcanvas-close" aria-label="드로잉 차트 닫기"><i class="fa-solid fa-xmark"></i></button>
      </header>
      <div class="chart-drawing-split">
        <section class="chart-drawing-panel"><header><b>1. 내가 그린 가격 흐름</b><small>왼쪽 → 오른쪽은 시간, 위 → 아래는 가격</small></header><div class="chart-drawing-canvas-wrap"><canvas data-chart-drawing-input aria-label="가격 흐름을 직접 그리는 캔버스"></canvas></div></section>
        <section class="chart-drawing-panel"><header><b>2. 주식 차트에서 읽는 상태</b><small>분홍색·노란색 캔들을 클릭해 계산식을 확인하세요.</small></header><div class="chart-drawing-canvas-wrap"><canvas data-chart-drawing-output aria-label="그린 흐름을 주식 차트 형태로 나타낸 캔버스"></canvas></div><div class="chart-drawing-insight" data-chart-drawing-insight aria-live="polite"></div></section>
        <section class="chart-drawing-similar" aria-live="polite"><header><b><i class="fa-solid fa-magnifying-glass-chart"></i> 3. 흐름이 비슷한 종목</b><small>최근 1개월 · KOSPI·KOSDAQ 대표 종목의 일별 종가 흐름과 비교</small></header>
          <div class="chart-drawing-stats" data-chart-drawing-stats>
            <div><span><i class="fa-solid fa-plus" aria-hidden="true"></i> 전체 몸통 높이 합</span><strong data-chart-drawing-stat-sum>-</strong><small data-chart-drawing-stat-sum-formula>캔들을 그려 계산합니다</small></div>
            <div><span><i class="fa-solid fa-superscript" aria-hidden="true"></i> 편차 제곱의 합</span><strong data-chart-drawing-stat-square-sum>-</strong><small data-chart-drawing-stat-square-sum-formula>캔들을 그려 계산합니다</small></div>
            <div><span><i class="fa-solid fa-calculator" aria-hidden="true"></i> 평균 몸통 높이</span><strong data-chart-drawing-stat-mean>-</strong><small data-chart-drawing-stat-mean-formula>합계 ÷ 캔들 수</small></div>
            <div><span><i class="fa-solid fa-square-root-variable" aria-hidden="true"></i> 모표준편차</span><strong data-chart-drawing-stat-population-std>-</strong><small data-chart-drawing-stat-population-std-formula>√(편차 제곱합 ÷ n)</small></div>
            <div><span><i class="fa-solid fa-square-root-variable" aria-hidden="true"></i> 표본표준편차</span><strong data-chart-drawing-stat-sample-std>-</strong><small data-chart-drawing-stat-sample-std-formula>√(편차 제곱합 ÷ n−1)</small></div>
            <div><span><i class="fa-solid fa-xmark" aria-hidden="true"></i> 모표준편차 2배 기준</span><strong data-chart-drawing-stat-threshold>-</strong><small data-chart-drawing-stat-threshold-formula>모표준편차 × 2</small></div>
            <div><span><i class="fa-solid fa-highlighter" aria-hidden="true"></i> 노란 캔들</span><strong data-chart-drawing-stat-outliers>-</strong><small data-chart-drawing-stat-outliers-formula>높이 &gt; 모표준편차 × 2</small></div>
          </div>
          <div class="chart-drawing-similar-body"><p data-chart-drawing-similar>선을 충분히 그리면 최근 1개월 실제 흐름과 비교합니다.</p><div class="chart-drawing-similar-cards" data-chart-drawing-similar-cards></div></div></section>
      </div>
      <p class="chart-drawing-note"><i class="fa-solid fa-circle-info"></i> 이 도구는 모양을 읽는 연습입니다. 추세·지지·저항은 미래 가격을 확정하거나 매수·매도 신호를 주지 않습니다.</p>
      <div class="chart-drawing-candle-popup" data-chart-drawing-candle-popup hidden>
        <section role="dialog" aria-modal="true" aria-labelledby="chart-drawing-candle-popup-title">
          <header><div><span><i class="fa-solid fa-calculator"></i></span><div><h3 id="chart-drawing-candle-popup-title">캔들 계산 상세</h3><p>그린 흐름에서 계산한 값입니다.</p></div></div><button type="button" data-chart-drawing-candle-popup-close aria-label="캔들 계산 상세 닫기"><i class="fa-solid fa-xmark"></i></button></header>
          <div data-chart-drawing-candle-popup-content></div>
        </section>
      </div>
    </section>`;
  document.body.appendChild(panel);

  const inputCanvas = panel.querySelector('[data-chart-drawing-input]');
  const outputCanvas = panel.querySelector('[data-chart-drawing-output]');
  const insight = panel.querySelector('[data-chart-drawing-insight]');
  const similarText = panel.querySelector('[data-chart-drawing-similar]');
  const similarCards = panel.querySelector('[data-chart-drawing-similar-cards]');
  const closeButton = panel.querySelector('.chart-drawing-offcanvas-close');
  const statMean = panel.querySelector('[data-chart-drawing-stat-mean]');
  const statSum = panel.querySelector('[data-chart-drawing-stat-sum]');
  const statSquareSum = panel.querySelector('[data-chart-drawing-stat-square-sum]');
  const statPopulationStd = panel.querySelector('[data-chart-drawing-stat-population-std]');
  const statSampleStd = panel.querySelector('[data-chart-drawing-stat-sample-std]');
  const statThreshold = panel.querySelector('[data-chart-drawing-stat-threshold]');
  const statOutliers = panel.querySelector('[data-chart-drawing-stat-outliers]');
  const statSumFormula = panel.querySelector('[data-chart-drawing-stat-sum-formula]');
  const statSquareSumFormula = panel.querySelector('[data-chart-drawing-stat-square-sum-formula]');
  const statMeanFormula = panel.querySelector('[data-chart-drawing-stat-mean-formula]');
  const statPopulationStdFormula = panel.querySelector('[data-chart-drawing-stat-population-std-formula]');
  const statSampleStdFormula = panel.querySelector('[data-chart-drawing-stat-sample-std-formula]');
  const statThresholdFormula = panel.querySelector('[data-chart-drawing-stat-threshold-formula]');
  const statOutliersFormula = panel.querySelector('[data-chart-drawing-stat-outliers-formula]');
  const candlePopup = panel.querySelector('[data-chart-drawing-candle-popup]');
  const candlePopupContent = panel.querySelector('[data-chart-drawing-candle-popup-content]');
  const candlePopupClose = panel.querySelector('[data-chart-drawing-candle-popup-close]');
  // 변환된 오프캔버스의 overflow에 가려지지 않도록 팝업은 최상위에 둔다.
  document.body.appendChild(candlePopup);
  let points = [];
  let drawing = false;
  let lastFocused = null;
  let patternItemsPromise = null;
  let candleHitAreas = [];

  const decimal = (value) => value.toFixed(2);
  const closeCandlePopup = () => { candlePopup.hidden = true; };
  const candleAt = (event) => {
    if (!candleHitAreas.length) return null;
    const rect = outputCanvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    return candleHitAreas.reduce((nearest, candle) => (
      Math.abs((candle.x + candle.width / 2) - x) < Math.abs((nearest.x + nearest.width / 2) - x) ? candle : nearest
    ));
  };
  const showCandlePopup = (candle) => {
    const { index, open, close, height, heightSum, mean, std, threshold, squaredDeviationSum, count, isOutlier } = candle;
    const sampleStd = count > 1 ? Math.sqrt(squaredDeviationSum / (count - 1)) : null;
    candlePopupContent.innerHTML = `<div class="chart-drawing-candle-values"><div><span>캔들</span><strong>${index + 1}번째</strong></div><div><span>시가</span><strong>${decimal(open)}</strong></div><div><span>종가</span><strong>${decimal(close)}</strong></div><div><span>몸통 높이</span><strong>${decimal(height)}</strong></div></div><div class="chart-drawing-candle-formula"><p><b>캔들 높이</b><code>|${decimal(close)} − ${decimal(open)}| = ${decimal(height)}</code></p><p><b>전체 높이 합</b><code>Σ 몸통 높이 = ${decimal(heightSum)}</code></p><p><b>평균 높이</b><code>${decimal(heightSum)} ÷ ${count} = ${decimal(mean)}</code></p><p><b>편차 제곱합</b><code>Σ(높이 − ${decimal(mean)})² = ${decimal(squaredDeviationSum)}</code></p><p><b>모표준편차</b><code>√(${decimal(squaredDeviationSum)} ÷ ${count}) = ${decimal(std)}</code></p><p><b>표본표준편차</b><code>${sampleStd === null ? '캔들이 2개 이상 필요합니다' : `√(${decimal(squaredDeviationSum)} ÷ ${count - 1}) = ${decimal(sampleStd)}`}</code></p><p><b>노란색 기준</b><code>${decimal(std)} × 2 = ${decimal(threshold)}</code></p><p class="${isOutlier ? 'is-warning' : 'is-normal'}">${decimal(height)} ${isOutlier ? '&gt;' : '≤'} ${decimal(threshold)} → ${isOutlier ? '노란색 캔들' : '기본 색상 캔들'}</p></div>`;
    candlePopup.hidden = false;
    candlePopupClose.focus();
  };

  const sizeCanvas = (canvas) => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(320, canvas.parentElement.clientWidth - 2);
    const height = Math.max(300, Math.min(520, window.innerHeight * .55));
    canvas.width = width * dpr; canvas.height = height * dpr;
    canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
    const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, width, height };
  };
  const grid = (ctx, width, height, label) => {
    ctx.fillStyle = '#fbfdff'; ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1;
    for (let x = 38; x < width; x += (width - 54) / 6) { ctx.beginPath(); ctx.moveTo(x, 20); ctx.lineTo(x, height - 30); ctx.stroke(); }
    for (let y = 28; y < height - 20; y += (height - 58) / 5) { ctx.beginPath(); ctx.moveTo(38, y); ctx.lineTo(width - 16, y); ctx.stroke(); }
    ctx.fillStyle = '#94a3b8'; ctx.font = '600 11px Pretendard, sans-serif'; ctx.fillText(label, 12, 17);
  };
  const drawInput = () => {
    const { ctx, width, height } = sizeCanvas(inputCanvas); grid(ctx, width, height, '가격');
    if (!points.length) {
      ctx.fillStyle = '#64748b'; ctx.font = '700 15px Pretendard, sans-serif'; ctx.textAlign = 'center'; ctx.fillText('이 영역에 가격선을 그려 보세요', width / 2, height / 2 - 6);
      ctx.font = '500 12px Pretendard, sans-serif'; ctx.fillText('예: 계단식 상승 · 박스권 · 고점 후 하락', width / 2, height / 2 + 20); ctx.textAlign = 'start'; return;
    }
    ctx.strokeStyle = '#2563eb'; ctx.lineWidth = 3; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.beginPath();
    points.forEach((point, index) => { const x = 38 + point.x * (width - 54); const y = 20 + point.y * (height - 50); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke();
  };
  const analyze = () => {
    if (points.length < 8) return { title: '선을 더 그려 보세요', text: '시간에 따른 움직임을 읽으려면 왼쪽에서 오른쪽으로 조금 더 길게 선을 그려 주세요.', type: 'neutral', slope: 0, volatility: 0 };
    const values = points.map((point) => 1 - point.y);
    const first = values.slice(0, Math.max(2, Math.floor(values.length * .25))).reduce((a, b) => a + b, 0) / Math.max(2, Math.floor(values.length * .25));
    const last = values.slice(-Math.max(2, Math.floor(values.length * .25))).reduce((a, b) => a + b, 0) / Math.max(2, Math.floor(values.length * .25));
    const slope = last - first;
    const changes = values.slice(1).map((value, index) => Math.abs(value - values[index]));
    const volatility = changes.reduce((a, b) => a + b, 0) / changes.length;
    const range = Math.max(...values) - Math.min(...values);
    if (Math.abs(slope) < .1 && range < .28) return { title: '횡보 · 박스권 후보', text: '가격이 비슷한 범위 안에서 움직이는 모습입니다. 여러 번 멈춘 위·아래 구간을 저항·지지 후보로 표시해 볼 수 있습니다.', type: 'flat', slope, volatility };
    if (slope > .12) return { title: '상승 추세 후보', text: `왼쪽보다 오른쪽 가격대가 높습니다. 고점·저점이 함께 높아지는지와 상승에 거래량이 실렸는지를 차례로 확인합니다.${volatility > .06 ? ' 다만 흔들림이 커 조정 구간도 함께 보입니다.' : ''}`, type: 'up', slope, volatility };
    return { title: '하락 추세 후보', text: `왼쪽보다 오른쪽 가격대가 낮습니다. 고점·저점이 낮아지는지, 이전 지지 구간에서 멈추는지를 확인합니다.${volatility > .06 ? ' 중간 반등이 있어도 큰 흐름과 구분해 봅니다.' : ''}`, type: 'down', slope, volatility };
  };
  const drawOutput = () => {
    const { ctx, width, height } = sizeCanvas(outputCanvas); grid(ctx, width, height, '주가');
    candleHitAreas = [];
    const result = analyze();
    if (points.length >= 2) {
      const sampled = Array.from({ length: Math.min(28, points.length) }, (_, index) => points[Math.round(index * (points.length - 1) / (Math.min(28, points.length) - 1))]);
      const chartWidth = width - 58; const chartHeight = height - 54;
      const closes = sampled.map((point) => 60 + (1 - point.y) * 80);
      const min = Math.min(...closes) - 8; const max = Math.max(...closes) + 8;
      const candles = closes.map((close, index) => ({ close, open: index ? closes[index - 1] : close - 2 }));
      const heights = candles.map(({ open, close }) => Math.abs(open - close));
      const heightSum = heights.reduce((sum, value) => sum + value, 0);
      const mean = heightSum / heights.length;
      const squaredDeviationSum = heights.reduce((sum, value) => sum + (value - mean) ** 2, 0);
      const std = Math.sqrt(squaredDeviationSum / heights.length);
      const sampleStd = heights.length > 1 ? Math.sqrt(squaredDeviationSum / (heights.length - 1)) : null;
      const threshold = std * 2;
      let outlierCount = 0;
      candles.forEach(({ open, close }, index) => {
        const isOutlier = threshold > 0 && heights[index] > threshold;
        if (isOutlier) outlierCount += 1;
        const x = 42 + index * chartWidth / sampled.length; const y = 20 + (max - Math.max(open, close)) / (max - min) * chartHeight; const body = Math.max(3, Math.abs(open - close) / (max - min) * chartHeight); const candleWidth = Math.max(3, chartWidth / sampled.length * .56);
        ctx.strokeStyle = isOutlier ? '#eab308' : (close >= open ? '#ef476f' : '#3b82f6'); ctx.beginPath(); ctx.moveTo(x + candleWidth / 2, y - 5); ctx.lineTo(x + candleWidth / 2, y + body + 5); ctx.stroke(); ctx.fillStyle = ctx.strokeStyle; ctx.fillRect(x, y, candleWidth, body);
        ctx.fillStyle = isOutlier ? '#b45309' : '#475569'; ctx.font = '700 8px Pretendard, sans-serif'; ctx.textAlign = 'center'; ctx.fillText(heights[index].toFixed(2), x + candleWidth / 2, y - 9); ctx.textAlign = 'start';
        candleHitAreas.push({ index, open, close, height: heights[index], heightSum, mean, std, threshold, squaredDeviationSum, count: candles.length, isOutlier, x, y, width: candleWidth, bottom: y + body + 5 });
      });
      const movingAverages = [
        { period: 5, color: '#f59e0b', label: 'MA5' },
        { period: 12, color: '#7c3aed', label: 'MA12' },
        { period: 20, color: '#0891b2', label: 'MA20' },
      ];
      const maSeries = movingAverages.map(({ period, color, label }) => ({
        period, color, label,
        values: closes.map((_, index) => closes.slice(Math.max(0, index - period + 1), index + 1).reduce((sum, value) => sum + value, 0) / Math.min(period, index + 1)),
      }));
      maSeries.forEach(({ color, label, values: ma }, seriesIndex) => {
        ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
        ma.forEach((value, index) => { const x = 42 + index * chartWidth / sampled.length + chartWidth / sampled.length * .28; const y = 20 + (max - value) / (max - min) * chartHeight; index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
        ctx.stroke();
        ctx.fillStyle = color; ctx.font = '700 10px Pretendard, sans-serif'; ctx.fillText(label, width - 150 + seriesIndex * 49, 17);
      });
      const shortMa = maSeries[0].values; const longMa = maSeries[2].values;
      for (let index = 1; index < closes.length; index += 1) {
        const wasBelow = shortMa[index - 1] <= longMa[index - 1]; const isAbove = shortMa[index] > longMa[index];
        const wasAbove = shortMa[index - 1] >= longMa[index - 1]; const isBelow = shortMa[index] < longMa[index];
        if (!((wasBelow && isAbove) || (wasAbove && isBelow))) continue;
        const isGolden = wasBelow && isAbove;
        const x = 42 + index * chartWidth / sampled.length + chartWidth / sampled.length * .28;
        const value = (shortMa[index] + longMa[index]) / 2; const y = 20 + (max - value) / (max - min) * chartHeight;
        ctx.fillStyle = isGolden ? '#d97706' : '#2563eb'; ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#fff'; ctx.font = '800 9px Pretendard, sans-serif'; ctx.textAlign = 'center'; ctx.fillText(isGolden ? 'G' : 'D', x, y + 3); ctx.textAlign = 'start';
      }
      statSum.textContent = heightSum.toFixed(2); statSquareSum.textContent = squaredDeviationSum.toFixed(2); statMean.textContent = mean.toFixed(2); statPopulationStd.textContent = std.toFixed(2); statSampleStd.textContent = sampleStd === null ? '-' : sampleStd.toFixed(2); statThreshold.textContent = threshold.toFixed(2); statOutliers.textContent = `${outlierCount}개`;
      statSumFormula.textContent = `Σ 몸통 높이 = ${heightSum.toFixed(2)}`; statSquareSumFormula.textContent = `Σ(높이 − ${mean.toFixed(2)})² = ${squaredDeviationSum.toFixed(2)}`; statMeanFormula.textContent = `${heightSum.toFixed(2)} ÷ ${heights.length} = ${mean.toFixed(2)}`; statPopulationStdFormula.textContent = `√(${squaredDeviationSum.toFixed(2)} ÷ ${heights.length}) = ${std.toFixed(2)}`; statSampleStdFormula.textContent = sampleStd === null ? '캔들이 2개 이상 필요합니다' : `√(${squaredDeviationSum.toFixed(2)} ÷ ${heights.length - 1}) = ${sampleStd.toFixed(2)}`; statThresholdFormula.textContent = `${std.toFixed(2)} × 2 = ${threshold.toFixed(2)}`; statOutliersFormula.textContent = `높이 > ${threshold.toFixed(2)} → ${outlierCount}개`;
      statOutliers.parentElement.classList.toggle('has-outliers', outlierCount > 0);
    } else {
      statSum.textContent = '-'; statSquareSum.textContent = '-'; statMean.textContent = '-'; statPopulationStd.textContent = '-'; statSampleStd.textContent = '-'; statThreshold.textContent = '-'; statOutliers.textContent = '-';
      statSumFormula.textContent = '캔들을 그려 계산합니다'; statSquareSumFormula.textContent = '캔들을 그려 계산합니다'; statMeanFormula.textContent = '합계 ÷ 캔들 수'; statPopulationStdFormula.textContent = '√(편차 제곱합 ÷ n)'; statSampleStdFormula.textContent = '√(편차 제곱합 ÷ n−1)'; statThresholdFormula.textContent = '모표준편차 × 2'; statOutliersFormula.textContent = '높이 > 모표준편차 × 2';
      statOutliers.parentElement.classList.remove('has-outliers');
    }
    insight.className = `chart-drawing-insight is-${result.type}`;
    insight.innerHTML = `<strong>${result.title}</strong><p>${result.text}</p>`;
  };
  const resampleSketch = (count) => {
    const sorted = [...points].sort((a, b) => a.x - b.x);
    return Array.from({ length: count }, (_, index) => {
      const x = index / (count - 1); const rightIndex = sorted.findIndex((point) => point.x >= x);
      if (rightIndex < 0) return 1 - sorted.at(-1).y;
      if (rightIndex === 0) return 1 - sorted[0].y;
      const left = sorted[rightIndex - 1]; const right = sorted[rightIndex];
      return 1 - (left.y + (right.y - left.y) * (x - left.x) / Math.max(.0001, right.x - left.x));
    });
  };
  const correlation = (first, second) => {
    const firstMean = first.reduce((sum, value) => sum + value, 0) / first.length; const secondMean = second.reduce((sum, value) => sum + value, 0) / second.length;
    const numerator = first.reduce((sum, value, index) => sum + (value - firstMean) * (second[index] - secondMean), 0);
    const firstScale = Math.sqrt(first.reduce((sum, value) => sum + (value - firstMean) ** 2, 0)); const secondScale = Math.sqrt(second.reduce((sum, value) => sum + (value - secondMean) ** 2, 0));
    return firstScale && secondScale ? numerator / (firstScale * secondScale) : 0;
  };
  const updateSimilarStocks = async () => {
    if (points.length < 8) { similarText.textContent = '선을 왼쪽에서 오른쪽까지 충분히 그리면 최근 1개월 실제 흐름과 비교합니다.'; similarCards.replaceChildren(); return; }
    similarText.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 최근 1개월 종가 흐름을 비교하는 중…'; similarCards.replaceChildren();
    try {
      patternItemsPromise ||= fetch('/api/market/chart-patterns').then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
        return response.json();
      });
      const data = await patternItemsPromise; const sketch = resampleSketch(22);
      const ranked = data.items.map((item) => ({ ...item, similarity: correlation(sketch, item.returns.map((value) => value - item.returns[0])) })).sort((a, b) => b.similarity - a.similarity).slice(0, 4);
      const date = data.latest_data_at ? new Date(data.latest_data_at).toLocaleDateString('ko-KR') : '최근 거래일';
      similarText.textContent = `${date} 기준 · 모양의 상관도가 높은 대표 종목 표본입니다. 수익률 크기나 향후 방향이 같다는 뜻은 아닙니다.`;
      similarCards.innerHTML = ranked.map((item) => `<article><span>${item.sector}</span><strong>${item.name}</strong><small>${item.ticker.replace(/\.(KS|KQ)$/, '')} · 1개월 ${item.one_month_change_pct >= 0 ? '+' : ''}${item.one_month_change_pct}%</small><em>흐름 유사도 ${Math.round(Math.max(0, item.similarity) * 100)}%</em></article>`).join('');
    } catch (error) { patternItemsPromise = null; similarText.textContent = `최근 차트 데이터를 불러오지 못했습니다: ${error.message || '잠시 후 다시 시도해 주세요.'}`; }
  };
  const redraw = () => { drawInput(); drawOutput(); };
  const pointFromEvent = (event) => {
    const rect = inputCanvas.getBoundingClientRect();
    return { x: Math.max(0, Math.min(1, (event.clientX - rect.left - 38) / Math.max(1, rect.width - 54))), y: Math.max(0, Math.min(1, (event.clientY - rect.top - 20) / Math.max(1, rect.height - 50))) };
  };
  inputCanvas.addEventListener('pointerdown', (event) => { drawing = true; points = [pointFromEvent(event)]; inputCanvas.setPointerCapture(event.pointerId); redraw(); });
  inputCanvas.addEventListener('pointermove', (event) => { if (!drawing) return; const point = pointFromEvent(event); const previous = points.at(-1); if (!previous || point.x - previous.x > .004) { points.push(point); redraw(); } });
  inputCanvas.addEventListener('pointerup', () => { drawing = false; updateSimilarStocks(); });
  outputCanvas.addEventListener('pointermove', (event) => {
    outputCanvas.style.cursor = candleAt(event) ? 'pointer' : 'default';
  });
  outputCanvas.addEventListener('click', (event) => {
    const candle = candleAt(event);
    if (candle) showCandlePopup(candle);
  });
  candlePopupClose.addEventListener('click', closeCandlePopup);
  candlePopup.addEventListener('click', (event) => { if (event.target === candlePopup) closeCandlePopup(); });
  const closePanel = () => { closeCandlePopup(); panel.classList.remove('show'); document.body.classList.remove('modal-open'); lastFocused?.focus(); };
  const onKeydown = (event) => { if (event.key === 'Escape' && !candlePopup.hidden) closeCandlePopup(); else if (event.key === 'Escape' && panel.classList.contains('show')) closePanel(); };
  trigger.addEventListener('click', (event) => {
    event.preventDefault();
    lastFocused = trigger;
    panel.classList.add('show');
    document.body.classList.add('modal-open');
    redraw();
    closeButton.focus();
  });
  closeButton.addEventListener('click', closePanel);
  panel.addEventListener('click', (event) => { if (event.target === panel) closePanel(); });
  window.addEventListener('resize', () => { if (panel.classList.contains('show')) redraw(); });
  document.addEventListener('keydown', onKeydown);
}
