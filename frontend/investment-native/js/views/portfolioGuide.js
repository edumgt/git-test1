const PROFILES = {
  stable: {
    title: '안정 중심 구성', badge: '안정형', color: '#059669',
    intro: '큰 흔들림을 줄이는 데 우선순위를 둔 예시입니다. 수익 기회도 중요하지만, 예상보다 큰 변동을 견디기 어렵다면 이런 출발점이 편할 수 있습니다.',
    items: [
      ['현금성 자산', 35, '#38bdf8', '급한 상황이나 기회를 위한 여유 자금'],
      ['채권·안정형 자산', 35, '#818cf8', '포트폴리오의 흔들림을 완화하는 역할'],
      ['글로벌 주식', 20, '#22c55e', '장기 성장 기회를 위한 부분'],
      ['배당·방어형 주식', 10, '#f59e0b', '상대적으로 안정적인 현금흐름을 기대하는 부분'],
    ],
    note: '주가가 빠르게 오를 때에는 성장형 구성보다 수익이 더디게 느껴질 수 있습니다.',
  },
  balanced: {
    title: '균형 중심 구성', badge: '균형형', color: '#0078d4',
    intro: '성장 기회와 안정성을 함께 고려한 예시입니다. 한 가지 자산에 집중하기보다 서로 다른 역할을 가진 자산을 나누어 담는 데 초점을 둡니다.',
    items: [
      ['글로벌 주식', 45, '#22c55e', '여러 국가와 업종의 성장 기회'],
      ['채권·안정형 자산', 25, '#818cf8', '시장 변동을 완화하는 완충 역할'],
      ['국내 주식', 15, '#0078d4', '익숙한 시장의 성장 기회'],
      ['현금성 자산', 10, '#38bdf8', '예상치 못한 지출과 추가 투자 여유'],
      ['대체 자산', 5, '#f59e0b', '금 등 다른 성격의 자산을 소량 활용'],
    ],
    note: '시장 상황에 따라 주식과 안정형 자산이 모두 기대만큼 움직이지 않을 수 있습니다.',
  },
  growth: {
    title: '성장 중심 구성', badge: '성장형', color: '#7c3aed',
    intro: '장기 성장 가능성에 더 무게를 둔 예시입니다. 단기적인 등락을 감수할 수 있고, 투자 기간이 충분히 길 때 검토해 볼 수 있습니다.',
    items: [
      ['글로벌 주식', 60, '#22c55e', '폭넓은 성장 기회를 중심으로 구성'],
      ['국내 주식', 20, '#0078d4', '국내 시장과 관심 산업에 참여하는 부분'],
      ['테마·성장 자산', 10, '#a855f7', '높은 변동성을 감수하는 작은 비중'],
      ['채권·안정형 자산', 5, '#818cf8', '급격한 변동에 대비하는 완충 역할'],
      ['현금성 자산', 5, '#38bdf8', '기본적인 유동성 확보'],
    ],
    note: '짧은 기간에도 큰 손실이 발생할 수 있습니다. 생활에 필요한 돈은 별도로 두는 것이 좋습니다.',
  },
};

function suggestedProfile(risk, horizon) {
  if (risk === 'low' || horizon === 'short') return 'stable';
  if (risk === 'high' && horizon === 'long') return 'growth';
  return 'balanced';
}

function renderProfile(profile) {
  const config = PROFILES[profile];
  const blocks = config.items.map(([name, value, color]) => `<span style="width:${value}%;background:${color}" title="${name} ${value}%"></span>`).join('');
  const rows = config.items.map(([name, value, color, explanation]) => `
    <li><span class="guide-dot" style="background:${color}"></span><div><b>${name}</b><small>${explanation}</small></div><strong>${value}%</strong></li>`).join('');
  return `
    <section class="portfolio-guide-result">
      <div class="portfolio-guide-result-head">
        <div><p>추천 구성 예시</p><h2>${config.title} <span style="color:${config.color}">${config.badge}</span></h2></div>
        <i class="fa-solid fa-compass" style="color:${config.color}"></i>
      </div>
      <p class="portfolio-guide-intro">${config.intro}</p>
      <div class="guide-allocation-bar" aria-label="자산 구성 비중">${blocks}</div>
      <ul class="guide-allocation-list">${rows}</ul>
      <div class="portfolio-guide-note"><i class="fa-solid fa-circle-info"></i><span><b>미리 알아둘 점:</b> ${config.note}</span></div>
    </section>`;
}

export function portfolioGuideView(container) {
  container.innerHTML = `
    <section class="portfolio-guide-page">
      <div class="page-heading"><div><h1><i class="fa-solid fa-compass"></i> 포트폴리오 추천</h1><p>몇 가지 질문으로 나에게 맞는 자산 구성의 출발점을 찾아보세요.</p></div></div>
      <aside class="portfolio-guide-explainer"><i class="fa-solid fa-map"></i><div><strong>추천은 ‘정답’보다 ‘출발점’입니다</strong><p>투자 목적, 필요한 시점, 감당할 수 있는 흔들림은 사람마다 다릅니다. 이 메뉴는 그 차이를 반영해 자산을 어떻게 나누어 볼지 쉽게 보여주는 학습용 가이드입니다.</p><button type="button" class="sharpe-help-button" id="sharpe-help" aria-haspopup="dialog" aria-expanded="false"><i class="fa-solid fa-circle-question" aria-hidden="true"></i> 샤프지수(Sharpe Ratio) 알아보기</button></div></aside>
      <div class="sharpe-modal-backdrop" id="sharpe-modal" hidden>
        <section class="sharpe-modal" role="dialog" aria-modal="true" aria-labelledby="sharpe-modal-title" tabindex="-1">
          <header class="sharpe-modal-header"><div><span class="sharpe-modal-icon"><i class="fa-solid fa-scale-balanced"></i></span><div><p class="sharpe-kicker">Sharpe Ratio <span aria-label="샤프 레이시오">(샤프 레이시오)</span></p><h2 id="sharpe-modal-title">샤프지수, 위험 대비 수익의 효율</h2><p>얼마나 많이 벌었는지뿐 아니라, 그 수익을 얻기 위해 얼마나 흔들렸는지도 함께 봅니다.</p></div></div><button type="button" class="sharpe-modal-close" aria-label="샤프지수 설명 닫기"><i class="fa-solid fa-xmark"></i></button></header>
          <div class="sharpe-modal-body">
            <div class="sharpe-plain-language"><span><i class="fa-solid fa-language"></i> 쉽게 말하면</span><p><b>샤프지수</b>는 영어로 <b>Sharpe Ratio</b>, 한국어식으로 <b>샤프 레이시오</b>라고 읽습니다. 위험을 감수하고 얻은 <b>초과수익의 효율</b>을 숫자로 나타낸 지표입니다. 같은 수익이라면 덜 흔들린 투자의 샤프지수가 더 높습니다.</p></div>
            <div class="sharpe-formula" aria-label="샤프지수 수식"><span>Sharpe Ratio</span> = <span>(포트폴리오 수익률 − 무위험수익률)</span> / <span>포트폴리오 변동성</span></div>
            <div class="sharpe-parts"><div><b>초과수익</b><span>예금·국채처럼 위험이 낮은 투자보다 얼마나 더 벌었는지</span></div><div><b>변동성</b><span>수익률이 위아래로 흔들린 정도, 즉 감수한 위험</span></div><div><b>결과</b><span>값이 높을수록 같은 위험 대비 수익의 효율이 높은 편</span></div></div>
            <div class="sharpe-example"><h3><i class="fa-solid fa-calculator"></i> 짧은 예시</h3><p>연 수익률이 10%, 무위험수익률이 3%, 변동성이 14%라면 <b>(10% − 3%) ÷ 14% = 0.50</b>입니다. 수익률이 같아도 변동성이 7%라면 샤프지수는 <b>1.00</b>이 됩니다. 그래서 수익률만 비교할 때 놓치기 쉬운 ‘흔들림’을 함께 고려할 수 있습니다.</p></div>
            <div class="sharpe-caution"><i class="fa-solid fa-triangle-exclamation"></i><p><b>이 추천 화면은 샤프지수를 계산하지 않습니다.</b> 투자 기간·목적·위험 성향에 따라 정해진 학습용 자산배분 예시를 보여줍니다. 샤프지수는 별도의 포트폴리오 최적화 화면에서 여러 조합을 비교할 때 사용합니다.</p></div>
            <div class="sharpe-code-head"><h3><i class="fa-brands fa-python"></i> 이 프로젝트의 최적화 코드</h3><span>app/backend/routers/quant.py 일부</span></div>
            <pre class="sharpe-code"><code># r: 포트폴리오 기대수익률
# v: 공분산을 반영한 포트폴리오 변동성
r = float(w @ mu_ann)
v = float(np.sqrt(w @ cov @ w))

# rf: 무위험수익률 (기본값 3%)
sharpe = (r - rf) / v

# 여러 비중 조합 중 샤프지수가 가장 높은 조합을 선택
best_i = int(np.argmax(port_sharpes))</code></pre>
            <p class="sharpe-note"><i class="fa-solid fa-circle-info"></i> 샤프지수는 과거 데이터와 가정한 수익률·변동성에 따라 달라집니다. 미래 성과나 손실 가능성을 보장하지 않습니다.</p>
          </div>
        </section>
      </div>
      <div class="portfolio-guide-layout">
        <section class="portfolio-guide-form">
          <h2>내 상황에 가까운 선택</h2>
          <label><span>투자 목적</span><select class="param-input" id="guide-goal"><option value="growth">장기적으로 자산을 키우고 싶어요</option><option value="balance">성장과 안정의 균형이 필요해요</option><option value="protect">원금의 큰 흔들림이 걱정돼요</option></select></label>
          <label><span>투자 기간</span><select class="param-input" id="guide-horizon"><option value="short">3년 이내</option><option value="medium" selected>3년 ~ 7년</option><option value="long">7년 이상</option></select></label>
          <label><span>가격이 내려갈 때 내 마음은?</span><select class="param-input" id="guide-risk"><option value="low">불안해서 빠르게 줄이고 싶어요</option><option value="medium" selected>상황을 보며 유지할 수 있어요</option><option value="high">길게 보고 기다릴 수 있어요</option></select></label>
          <button class="run-btn" id="guide-run"><i class="fa-solid fa-wand-magic-sparkles"></i> 구성 예시 보기</button>
        </section>
        <div id="guide-result">${renderProfile('balanced')}</div>
      </div>
      <section class="portfolio-guide-check"><h2><i class="fa-solid fa-list-check"></i> 구성 전에 확인해 보세요</h2><div><p><b>생활비와 비상금</b><span>가까운 시일에 쓸 돈은 투자금과 분리했나요?</span></p><p><b>한 종목 쏠림</b><span>좋아하는 종목이나 같은 업종에 너무 많이 담기지 않았나요?</span></p><p><b>정기 점검</b><span>정한 목적과 비중이 지금도 내 상황에 맞는지 살펴보세요.</span></p></div></section>
      <p class="portfolio-guide-disclaimer">이 내용은 금융 교육을 위한 일반적인 구성 예시이며, 개인별 투자 조언이나 수익을 보장하는 추천이 아닙니다.</p>
    </section>`;

  const result = container.querySelector('#guide-result');
  const sharpeHelp = container.querySelector('#sharpe-help');
  const sharpeModal = container.querySelector('#sharpe-modal');
  const sharpePanel = sharpeModal.querySelector('.sharpe-modal');

  const closeSharpeModal = () => {
    sharpeModal.hidden = true;
    sharpeHelp.setAttribute('aria-expanded', 'false');
    sharpeHelp.focus();
  };
  sharpeHelp.addEventListener('click', () => {
    sharpeModal.hidden = false;
    sharpeHelp.setAttribute('aria-expanded', 'true');
    sharpePanel.focus();
  });
  sharpeModal.querySelector('.sharpe-modal-close').addEventListener('click', closeSharpeModal);
  sharpeModal.addEventListener('click', (event) => {
    if (event.target === sharpeModal) closeSharpeModal();
  });
  sharpePanel.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeSharpeModal();
  });

  container.querySelector('#guide-run').addEventListener('click', () => {
    const risk = container.querySelector('#guide-risk').value;
    const horizon = container.querySelector('#guide-horizon').value;
    const goal = container.querySelector('#guide-goal').value;
    const profile = goal === 'protect' ? 'stable' : goal === 'growth' && horizon === 'long' && risk !== 'low' ? 'growth' : suggestedProfile(risk, horizon);
    result.innerHTML = renderProfile(profile);
  });
}
