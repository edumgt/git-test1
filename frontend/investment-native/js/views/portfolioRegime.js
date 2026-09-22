const REGIMES = [
  {
    id: 'r1', badge: 'R1', title: '극단적 안전선호', subtitle: 'Extreme Risk Aversion', color: '#b91c1c',
    regime: '국면 6 · 과열 및 고평가',
    market: '증시 밸류에이션 부담이 누적되고 경기 과열 우려가 커지면서 시장 급락 리스크가 극도로 고조된 구간입니다. (예: IT 테크 버블 시기)',
    strategy: '점진적으로 주식 비중을 축소하고, 현금 및 퀄리티(Quality) 주식 중심으로 포트폴리오를 보수적으로 재편합니다.',
  },
  {
    id: 'r2', badge: 'R2', title: '안전선호', subtitle: 'Risk Aversion', color: '#c2410c',
    regime: '국면 3 · 시스템 리스크',
    market: '금융시스템 전반에 충격이 발생해 시장에 공포(Risk-off)가 확산되는 시기입니다. 소비심리·기업 이익(EPS)이 둔화되고 크레딧 스프레드가 크게 확대됩니다. (예: 글로벌 금융위기, 코로나 초기)',
    strategy: '극단적인 방어막을 구축하는 단계입니다. 위험자산을 피하고 현금·단기채·달러 등 안전자산 비중을 적극적으로 늘립니다.',
  },
  {
    id: 'r3', badge: 'R3', title: '위험중립', subtitle: 'Risk Neutral', color: '#1d4ed8',
    regime: '국면 2 · 안정적 확장  /  국면 4 · 과도기(스태그플레이션)',
    market: '국면 2는 경제 펀더멘탈이 회복되고 지표가 양호한 안정기, 국면 4는 성장 둔화와 물가 상승이 겹치는 혼조세입니다.',
    strategy: '국면 2에서는 실적 주도주 중심 주식 비중 확대가, 국면 4에서는 고배당·인컴·단기채 중심 방어적 포트폴리오가 유리합니다. 기본적으로 전통적인 60(주식):40(채권) 구조를 축으로, 하방 리스크가 우려될 때는 단기채·투자등급 크레딧·퀄리티 주식으로 전술적 틸팅을 강화합니다.',
  },
  {
    id: 'r4', badge: 'R4', title: '위험선호', subtitle: 'Risk Seeking', color: '#15803d',
    regime: '국면 1 · 비펀더멘탈적 반등',
    market: '실물 경제·심리지표는 여전히 침체되어 있으나, 정책 지원이나 유동성 힘으로 주식시장이 먼저 바닥을 다지고 반등하는 국면입니다. (예: 금융위기 직후 양적완화 도입기)',
    strategy: '단기적인 리스크 온 전략을 구사합니다. 유동성 장세 흐름을 추종하며 신흥국 주식 비중을 확대하는 전술이 유효할 수 있습니다.',
  },
  {
    id: 'r5', badge: 'R5', title: '극단적 위험선호', subtitle: 'Extreme Risk Seeking', color: '#166534',
    regime: '국면 5 · 이상적 균형(골디락스)',
    market: '성장·물가·금리가 가장 안정적으로 조화를 이루는 장기 확장기입니다. 시장 전반에 자산 성장 확신과 위험선호 심리가 극대화됩니다.',
    strategy: '적극적인 수익 추구가 최우선입니다. 성장주 중심으로 포트폴리오를 강력하게 구성하고, 가치주 순환매 전략을 병행합니다.',
  },
];

const CURRENT_REGIME_ID = 'r3';

const ASSET_ROWS = [
  { key: 'globalEquity', name: '글로벌 주식', color: '#22c55e', weight: 59.3, expectedReturn: 7.0, volatility: 16.0 },
  { key: 'globalBond', name: '글로벌 채권', color: '#818cf8', weight: 32.1, expectedReturn: 3.5, volatility: 5.0 },
  { key: 'alternative', name: '대체자산', color: '#f59e0b', weight: 6.3, expectedReturn: 5.0, volatility: 10.0 },
  { key: 'cash', name: '현금성 자산', color: '#38bdf8', weight: 2.3, expectedReturn: 3.0, volatility: 0.5 },
];

function renderRegimeCards() {
  return REGIMES.map((regime) => `
    <article class="regime-card${regime.id === CURRENT_REGIME_ID ? ' is-current' : ''}">
      ${regime.id === CURRENT_REGIME_ID ? '<span class="regime-current-tag">현재 국면</span>' : ''}
      <div class="regime-card-head"><span class="regime-badge" style="background:${regime.color}">${regime.badge}</span><div><b>${regime.title}</b><small>${regime.subtitle}</small></div></div>
      <p class="regime-mapping"><i class="fa-solid fa-diagram-project"></i> ${regime.regime}</p>
      <p class="regime-market">${regime.market}</p>
      <p class="regime-strategy"><b>전략</b> ${regime.strategy}</p>
    </article>`).join('');
}

function renderAssetRows() {
  return ASSET_ROWS.map((asset) => `
    <div class="risk-sim-row" data-risk-row="${asset.key}">
      <span class="risk-sim-dot" style="background:${asset.color}"></span>
      <span class="risk-sim-name">${asset.name}</span>
      <input type="number" aria-label="${asset.name} 비중(%)" data-risk-input="weight" data-asset="${asset.key}" value="${asset.weight}" min="0" max="100" step="0.1">
      <input type="number" aria-label="${asset.name} 기대수익률(%)" data-risk-input="return" data-asset="${asset.key}" value="${asset.expectedReturn}" min="-20" max="30" step="0.1">
      <input type="number" aria-label="${asset.name} 변동성(%)" data-risk-input="volatility" data-asset="${asset.key}" value="${asset.volatility}" min="0" max="60" step="0.1">
    </div>`).join('');
}

export function portfolioRegimeView(container) {
  container.innerHTML = `
    <section class="regime-page">
      <div class="page-heading"><h1><i class="fa-solid fa-chart-diagram"></i> IBKS 자산배분 정량 모델 (K-클러스터링) · 위험선호도</h1><p>K-클러스터링으로 나눈 경제 국면(Regime)에 따라 R1~R5 위험선호도가 포트폴리오의 기본 뼈대를 결정합니다.</p></div>

      <aside class="regime-explainer"><i class="fa-solid fa-circle-info"></i><div><strong>R1~R5는 시장 국면에 대응하는 기준선입니다</strong><p>IBKS의 'IBK'는 Industrial Bank of Korea(중소기업은행)의 약자로, IBK투자증권 리서치센터의 자산배분 전략 자료를 가리킵니다. 각 단계는 자산군별 위험 대비 수익률과 변동성 흐름에 따라 서로 다른 자산배분 전략을 제시하는 학습용 프레임워크입니다. 실제 투자 조언이나 수익 보장이 아닙니다.</p></div></aside>

      <div class="regime-cards">${renderRegimeCards()}</div>

      <section class="risk-sim-section">
        <div class="risk-sim-head">
          <div><h2><i class="fa-solid fa-scale-balanced"></i> 리스크 시뮬레이션</h2><p>현재 자산배분 보고서가 가리키는 <b>'과도기(R3, 위험중립)'</b> 국면의 예시 비중에서 시작해, 비중·기대수익률·변동성을 직접 조정해 보세요.</p></div>
          <button type="button" class="run-btn" id="risk-sim-reset"><i class="fa-solid fa-rotate-left"></i> 예시값으로 초기화</button>
        </div>

        <div class="guide-allocation-bar" id="risk-sim-bar" aria-label="자산 구성 비중"></div>

        <div class="risk-sim-table">
          <div class="risk-sim-row risk-sim-row-head"><span></span><span class="risk-sim-name">자산군</span><span>비중(%)</span><span>기대수익률(%)</span><span>변동성(%)</span></div>
          ${renderAssetRows()}
        </div>

        <label class="risk-sim-correlation">자산 간 평균 상관계수(가정)<input type="range" id="risk-sim-corr" min="-0.3" max="1" step="0.05" value="0.3"><output id="risk-sim-corr-output">0.30</output></label>

        <div class="risk-sim-summary" id="risk-sim-summary"></div>

        <p class="portfolio-guide-disclaimer">이 시뮬레이션은 학습용 근사 계산입니다. 포트폴리오 변동성은 입력한 자산 간 평균 상관계수를 하나의 값으로 단순화해 추정한 것이며, 실제로는 자산 쌍마다 상관관계가 다르고 시간에 따라서도 달라집니다. 기대수익률·변동성 입력값은 직접 조정한 가정치일 뿐 실제 시장 전망이나 수익을 보장하지 않습니다.</p>
      </section>
    </section>`;

  const bar = container.querySelector('#risk-sim-bar');
  const summary = container.querySelector('#risk-sim-summary');
  const corrInput = container.querySelector('#risk-sim-corr');
  const corrOutput = container.querySelector('#risk-sim-corr-output');

  const readAssets = () => ASSET_ROWS.map((asset) => ({
    ...asset,
    weight: Number(container.querySelector(`[data-risk-input="weight"][data-asset="${asset.key}"]`).value) || 0,
    expectedReturn: Number(container.querySelector(`[data-risk-input="return"][data-asset="${asset.key}"]`).value) || 0,
    volatility: Number(container.querySelector(`[data-risk-input="volatility"][data-asset="${asset.key}"]`).value) || 0,
  }));

  const update = () => {
    const assets = readAssets();
    const totalWeight = assets.reduce((sum, asset) => sum + asset.weight, 0);
    const norm = totalWeight > 0 ? 100 / totalWeight : 0;
    const correlation = Number(corrInput.value);
    corrOutput.textContent = correlation.toFixed(2);

    bar.innerHTML = assets.map((asset) => `<span style="width:${Math.max(asset.weight, 0)}%;background:${asset.color}" title="${asset.name} ${asset.weight}%"></span>`).join('');

    const weightedReturn = assets.reduce((sum, asset) => sum + (asset.weight / 100) * asset.expectedReturn, 0);
    const simpleSumVol = assets.reduce((sum, asset) => sum + (asset.weight / 100) * asset.volatility, 0);
    let variance = 0;
    for (const a of assets) {
      for (const b of assets) {
        const rho = a.key === b.key ? 1 : correlation;
        variance += (a.weight / 100) * (b.weight / 100) * (a.volatility / 100) * (b.volatility / 100) * rho;
      }
    }
    const diversifiedVol = Math.sqrt(Math.max(variance, 0)) * 100;

    summary.innerHTML = `
      <article><span>총 비중 합계</span><strong style="color:${Math.abs(totalWeight - 100) < 0.05 ? '#0f172a' : '#dc2626'}">${totalWeight.toFixed(1)}%</strong>${Math.abs(totalWeight - 100) >= 0.05 ? `<small>100%가 아닙니다. 정규화 기준 ×${norm.toFixed(3)}</small>` : ''}</article>
      <article><span>가중평균 기대수익률</span><strong>${weightedReturn.toFixed(2)}%</strong></article>
      <article><span>단순 합산 변동성(상한 추정)</span><strong>${simpleSumVol.toFixed(2)}%</strong><small>자산 간 상관관계를 고려하지 않은 값</small></article>
      <article><span>분산효과 반영 변동성(근사)</span><strong>${diversifiedVol.toFixed(2)}%</strong><small>평균 상관계수 ${correlation.toFixed(2)} 가정 시</small></article>`;
  };

  container.querySelectorAll('[data-risk-input]').forEach((input) => input.addEventListener('input', update));
  corrInput.addEventListener('input', update);
  container.querySelector('#risk-sim-reset').addEventListener('click', () => {
    container.querySelectorAll('[data-risk-input]').forEach((input) => { input.value = input.defaultValue; });
    corrInput.value = 0.3;
    update();
  });

  update();
}
