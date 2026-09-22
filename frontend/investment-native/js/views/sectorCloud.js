import { api } from '../api.js';

const MARKET_LABELS = { kospi: 'KOSPI', kosdaq: 'KOSDAQ' };

function formatEok(value) {
  const eok = Number(value) / 100_000_000;
  if (!Number.isFinite(eok)) return '--';
  return `${eok.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}억 원`;
}

function colorForChange(changePct) {
  if (changePct > 0) return '#ef476f';
  if (changePct < 0) return '#3b82f6';
  return '#94a3b8';
}

function chartOptions(sectors) {
  return {
    chart: { type: 'treemap', height: 500, toolbar: { show: false }, animations: { enabled: false }, background: 'transparent', fontFamily: 'Pretendard, -apple-system, "Malgun Gothic", sans-serif' },
    series: [{
      name: '섹터 거래대금',
      data: sectors.map((sector) => ({
        x: sector.sector,
        y: Math.max(1, Number(sector.trade_value) || 1),
        fillColor: colorForChange(Number(sector.change_pct)),
        sector,
      })),
    }],
    plotOptions: { treemap: { distributed: false, enableShades: true, shadeIntensity: 0.22, useFillColorAsStroke: true } },
    stroke: { width: 2, colors: ['#111827'] },
    dataLabels: {
      enabled: true,
      formatter: (value, options) => {
        const sector = options.w.config.series[options.seriesIndex].data[options.dataPointIndex].sector;
        const sign = Number(sector.change_pct) >= 0 ? '+' : '';
        return [value, `${sign}${Number(sector.change_pct).toFixed(2)}%`];
      },
      style: { colors: ['#fff'], fontSize: '12px', fontWeight: 750 },
      background: { enabled: false },
    },
    legend: { show: false },
    grid: { show: false, padding: { top: 0, bottom: 0, left: 0, right: 0 } },
    tooltip: {
      theme: 'dark',
      custom: ({ seriesIndex, dataPointIndex, w }) => {
        const sector = w.config.series[seriesIndex].data[dataPointIndex].sector;
        const change = Number(sector.change_pct) || 0;
        const leaderChange = Number(sector.leader_change_pct) || 0;
        return `<div class="sector-cloud-tooltip"><strong>${sector.sector}</strong><b>${formatEok(sector.trade_value)}</b><em class="${change >= 0 ? 'is-up' : 'is-down'}">${change >= 0 ? '▲' : '▼'} 평균 ${Math.abs(change).toFixed(2)}%</em><p>표본 ${sector.stock_count}종목 · 거래대금 합계</p><p>거래대금 상위: ${sector.leader_name} (${leaderChange >= 0 ? '+' : ''}${leaderChange.toFixed(2)}%)</p></div>`;
      },
    },
  };
}

export function sectorCloudView(container) {
  container.innerHTML = `
    <section class="sector-cloud-page">
      <header class="sector-cloud-head">
        <div>
          <h1><i class="fa-solid fa-cloud"></i> 섹터별 클라우드</h1>
          <p>대표 종목을 섹터별로 묶었습니다. 타일이 클수록 거래대금 합계가 크고, 빨강은 상승·파랑은 하락입니다.</p>
        </div>
        <div class="sector-cloud-actions"><span id="sector-cloud-stamp">조회 전</span><button type="button" id="sector-cloud-refresh"><i class="fa-solid fa-rotate-right"></i> 새로고침</button></div>
      </header>
      <div class="sector-cloud-tabs" role="tablist" aria-label="시장 선택">
        <button type="button" role="tab" data-sector-market="kospi" class="active" aria-selected="true">KOSPI</button>
        <button type="button" role="tab" data-sector-market="kosdaq" aria-selected="false">KOSDAQ</button>
      </div>
      <section class="sector-cloud-stage">
        <div class="sector-cloud-stage-head"><strong id="sector-cloud-title">KOSPI 섹터별 클라우드</strong><span><i class="fa-solid fa-circle is-up"></i> 상승 <i class="fa-solid fa-circle is-down"></i> 하락</span></div>
        <div id="sector-cloud-chart"></div>
      </section>
      <div class="sector-cloud-summary" id="sector-cloud-summary">섹터 집계 데이터를 불러오는 중…</div>
      <p class="sector-cloud-note">거래소 전체 업종지수가 아닌 대표 종목 표본 집계입니다. 타일 면적은 종가 × 당일 거래량으로 계산한 거래대금 합계이며, 색은 거래대금 가중 평균 등락률입니다.</p>
    </section>`;

  let market = 'kospi';
  let chart = null;
  let disposed = false;

  const destroyChart = () => {
    if (!chart) return;
    try { chart.destroy(); } catch {}
    chart = null;
  };

  async function loadCloud() {
    const button = container.querySelector('#sector-cloud-refresh');
    const stamp = container.querySelector('#sector-cloud-stamp');
    const summary = container.querySelector('#sector-cloud-summary');
    button.disabled = true;
    button.classList.add('is-loading');
    summary.textContent = '섹터 집계 데이터를 불러오는 중…';
    try {
      const data = await api.marketSectorCloud(market);
      if (disposed) return;
      const sectors = data.sectors || [];
      destroyChart();
      chart = new ApexCharts(container.querySelector('#sector-cloud-chart'), chartOptions(sectors));
      await chart.render();
      const leader = sectors[0];
      summary.innerHTML = leader
        ? `<strong>${data.sample_size}개 대표 종목 · ${sectors.length}개 섹터</strong> · 거래대금이 가장 큰 섹터: <b>${leader.sector}</b> <span>${formatEok(leader.trade_value)}</span>`
        : '표시할 섹터 데이터가 없습니다.';
      const latest = data.latest_data_at ? new Date(data.latest_data_at) : null;
      stamp.textContent = latest && !Number.isNaN(latest.valueOf())
        ? `기준일 ${latest.toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit' })}`
        : '조회 완료';
    } catch (error) {
      if (!disposed) summary.textContent = `조회 실패: ${error.message}`;
    } finally {
      if (!disposed) {
        button.disabled = false;
        button.classList.remove('is-loading');
      }
    }
  }

  container.querySelectorAll('[data-sector-market]').forEach((tab) => {
    tab.addEventListener('click', () => {
      market = tab.dataset.sectorMarket;
      container.querySelectorAll('[data-sector-market]').forEach((item) => {
        const active = item === tab;
        item.classList.toggle('active', active);
        item.setAttribute('aria-selected', String(active));
      });
      container.querySelector('#sector-cloud-title').textContent = `${MARKET_LABELS[market]} 섹터별 클라우드`;
      loadCloud();
    });
  });
  container.querySelector('#sector-cloud-refresh').addEventListener('click', loadCloud);
  loadCloud();
  const refreshTimer = window.setInterval(loadCloud, 60_000);
  window._viewCleanup = () => {
    disposed = true;
    window.clearInterval(refreshTimer);
    destroyChart();
  };
}
