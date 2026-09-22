import { api } from '../api.js';

const MARKET_LABELS = { us: '미국', kr: '한국 KOSPI 20' };

function formatNumber(value) {
  return Number(value).toLocaleString('ko-KR');
}

function formatPrice(value, market) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '--';
  return market === 'kr'
    ? `${Math.round(numeric).toLocaleString('ko-KR')}원`
    : `$${numeric.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function bubbleColor(changePct) {
  if (changePct > 0) return '#fb4b5c';
  if (changePct < 0) return '#3b82f6';
  return '#94a3b8';
}

function chartOptions(items, market) {
  const validItems = items.filter((item) => item.status === 'ok');
  return {
    chart: { type: 'treemap', height: 450, toolbar: { show: false }, animations: { enabled: false }, background: 'transparent', fontFamily: 'Pretendard, -apple-system, "Malgun Gothic", sans-serif' },
    series: [{
      name: '거래량 비중',
      data: validItems.map((item) => ({
        x: item.name,
        y: Math.max(0.15, Number(item.volume_ratio) || 0.15),
        fillColor: bubbleColor(Number(item.change_pct)),
        item,
      })),
    }],
    plotOptions: {
      treemap: {
        distributed: false,
        enableShades: true,
        shadeIntensity: 0.22,
        useFillColorAsStroke: true,
      },
    },
    stroke: { width: 2, colors: ['#111827'] },
    dataLabels: {
      enabled: true,
      formatter: (value, options) => {
        const item = options.w.config.series[options.seriesIndex].data[options.dataPointIndex].item;
        return [value, `${Number(item.volume_ratio).toFixed(2)}×`];
      },
      style: { colors: ['#ffffff'], fontSize: '12px', fontWeight: 750 },
      background: { enabled: false },
    },
    legend: { show: false },
    grid: { show: false, padding: { top: 0, bottom: 0, left: 0, right: 0 } },
    tooltip: {
      theme: 'dark',
      custom: ({ seriesIndex, dataPointIndex, w }) => {
        const item = w.config.series[seriesIndex].data[dataPointIndex].item;
        const change = Number(item.change_pct) || 0;
        return `<div class="volume-cloud-tooltip"><strong>${item.name} <span>${item.ticker}</span></strong><b>${formatPrice(item.price, market)}</b><em class="${change >= 0 ? 'is-up' : 'is-down'}">${change >= 0 ? '▲' : '▼'} ${Math.abs(change).toFixed(2)}%</em><p>거래량 ${formatNumber(item.volume)}주</p><p>20일 평균 대비 ${Number(item.volume_ratio).toFixed(2)}배</p></div>`;
      },
    },
  };
}

export function volumeCloudView(container) {
  container.innerHTML = `
    <section class="volume-cloud-page">
      <header class="volume-cloud-head">
        <div>
          <h1><i class="fa-solid fa-cloud"></i> 거래량 클라우드</h1>
          <p>타일이 클수록 최근 거래량이 20거래일 평균보다 많이 늘어난 종목입니다. 빨강은 상승, 파랑은 하락을 뜻합니다.</p>
        </div>
        <div class="volume-cloud-actions"><span id="volume-cloud-stamp">조회 전</span><button type="button" id="volume-cloud-refresh"><i class="fa-solid fa-rotate-right"></i> 새로고침</button></div>
      </header>
      <div class="volume-cloud-tabs" role="tablist" aria-label="시장 선택">
        <button type="button" role="tab" data-market="us" class="active" aria-selected="true">미국 · Magnificent Seven</button>
        <button type="button" role="tab" data-market="kr" aria-selected="false">한국 · KOSPI 20</button>
      </div>
      <section class="volume-cloud-stage">
        <div class="volume-cloud-stage-head"><strong id="volume-cloud-title">미국 거래량 클라우드</strong><span><i class="fa-solid fa-circle is-up"></i> 상승 <i class="fa-solid fa-circle is-down"></i> 하락</span></div>
        <div id="volume-cloud-chart"></div>
      </section>
      <div class="volume-cloud-summary" id="volume-cloud-summary">거래량을 불러오는 중…</div>
      <p class="volume-cloud-note">한국과 미국은 거래량 단위와 가격 통화가 다르므로 서로 비교하지 않습니다. 타일 면적은 각 시장 안에서의 최근 거래량 ÷ 직전 20거래일 평균 거래량입니다.</p>
    </section>`;

  let market = 'us';
  let chart = null;
  let disposed = false;

  function destroyChart() {
    if (chart) {
      try { chart.destroy(); } catch {}
      chart = null;
    }
  }

  async function loadCloud() {
    const button = container.querySelector('#volume-cloud-refresh');
    const stamp = container.querySelector('#volume-cloud-stamp');
    const summary = container.querySelector('#volume-cloud-summary');
    button.disabled = true;
    button.classList.add('is-loading');
    summary.textContent = '거래량을 불러오는 중…';
    try {
      const data = await api.marketVolumeCloud(market);
      if (disposed) return;
      const items = data.items || [];
      destroyChart();
      chart = new ApexCharts(container.querySelector('#volume-cloud-chart'), chartOptions(items, market));
      await chart.render();
      const activeCount = items.filter((item) => item.status === 'ok').length;
      const maxItem = items.filter((item) => item.status === 'ok').sort((a, b) => b.volume_ratio - a.volume_ratio)[0];
      summary.innerHTML = maxItem
        ? `<strong>${activeCount}종목</strong> 조회 · 평균 대비 거래량이 가장 큰 종목: <b>${maxItem.name}</b> <span>${Number(maxItem.volume_ratio).toFixed(2)}배</span>`
        : '표시할 거래량 데이터가 없습니다.';
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

  container.querySelectorAll('[data-market]').forEach((tab) => {
    tab.addEventListener('click', () => {
      market = tab.dataset.market;
      container.querySelectorAll('[data-market]').forEach((item) => {
        const isActive = item === tab;
        item.classList.toggle('active', isActive);
        item.setAttribute('aria-selected', String(isActive));
      });
      container.querySelector('#volume-cloud-title').textContent = `${MARKET_LABELS[market]} 거래량 클라우드`;
      loadCloud();
    });
  });
  container.querySelector('#volume-cloud-refresh').addEventListener('click', loadCloud);
  loadCloud();
  const refreshTimer = window.setInterval(loadCloud, 60_000);
  window._viewCleanup = () => {
    disposed = true;
    window.clearInterval(refreshTimer);
    destroyChart();
  };
}
