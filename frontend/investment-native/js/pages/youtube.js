/**
 * pages/youtube.js — 저장소 학습 주제별 유튜브 영상(사전 크롤링된 정적 데이터,
 * scripts/crawl_youtube_videos.py 로 생성)을 자체 iframe 플레이어로 재생하고,
 * 사용자별 시청 시작~종료 시각을 localStorage에 기록/표시한다.
 *
 * 외부 youtube.com으로 이동시키지 않고, 이 페이지의 콘텐츠 영역 안에서
 * YouTube IFrame Player API로 재생 + 상태 이벤트(재생/일시정지/종료)를 추적한다.
 */
const HISTORY_KEY = 'yt_watch_history_v1';
const DATA_URL = '../js/data/youtubeVideos.json';
const VIDEO_MODULES = [
  { title: '주식 1', subtitle: '경제와 산업을 살펴봐요', topics: ['산업·경쟁력 분석'] },
  { title: '주식 2', subtitle: '회사 성적표를 읽어요', topics: ['재무제표로 기업 분석', 'PER·PBR·ROE 가치평가', '현금흐름·기업가치'] },
  { title: '주식 3', subtitle: '차트와 시장을 읽어요', topics: ['이동평균·추세 분석', 'RSI·MACD 보조지표'] },
  { title: '주식 4', subtitle: '주식과 ETF를 알아봐요', topics: ['주식 투자 입문', 'ETF 투자 기초', '배당주·배당 ETF'] },
  { title: '주식 5', subtitle: '나누어 담고 지켜요', topics: ['분산투자와 리스크 관리'] },
];

let ytPlayer = null;
let ytApiPromise = null;
let currentVideo = null;   // {videoId, title, channel}
let openSession = null;    // 현재 진행 중(종료 시각 미확정)인 시청 기록
let playerResizeObserver = null;

function fitPlayerToContent() {
  if (!document.body.classList.contains('is-video-playing')) return;

  const main = document.querySelector('.content-main');
  const card = document.querySelector('.yt-player-card');
  const frame = document.getElementById('yt-player-frame');
  if (!main || !card || !frame) return;

  const mainStyle = getComputedStyle(main);
  const cardStyle = getComputedStyle(card);
  const horizontalSpace = main.clientWidth
    - parseFloat(mainStyle.paddingLeft) - parseFloat(mainStyle.paddingRight)
    - parseFloat(cardStyle.paddingLeft) - parseFloat(cardStyle.paddingRight);
  const cardChrome = parseFloat(cardStyle.paddingTop) + parseFloat(cardStyle.paddingBottom)
    + (card.querySelector('.card-title')?.getBoundingClientRect().height ?? 0)
    + (document.getElementById('now-playing-title')?.getBoundingClientRect().height ?? 0)
    + 28; // 제목·현재 영상명 사이의 여백
  const verticalSpace = main.clientHeight
    - parseFloat(mainStyle.paddingTop) - parseFloat(mainStyle.paddingBottom)
    - cardChrome;
  const width = Math.max(1, Math.min(horizontalSpace, Math.max(1, verticalSpace) * 16 / 9));
  const height = width * 9 / 16;

  frame.style.width = `${Math.floor(width)}px`;
  frame.style.height = `${Math.floor(height)}px`;
}

function enterPlayerMode() {
  document.body.classList.add('is-video-playing');
  const main = document.querySelector('.content-main');
  if (main && !playerResizeObserver) {
    playerResizeObserver = new ResizeObserver(fitPlayerToContent);
    playerResizeObserver.observe(main);
  }
  requestAnimationFrame(fitPlayerToContent);
}

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
  } catch {
    return [];
  }
}

function saveHistory(list) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, 200)));
}

function fmtTime(iso) {
  if (!iso) return '재생 중';
  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date(iso));
}

function fmtDuration(sec) {
  if (!sec || sec <= 0) return '0초';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}분 ${s}초` : `${s}초`;
}

function renderHistory() {
  const el = document.getElementById('watch-history');
  if (!el) return;
  const history = loadHistory();

  if (!history.length) {
    el.innerHTML = `<p style="color:var(--text-muted);font-size:.85rem;">아직 시청 기록이 없습니다. 영상을 재생하면 여기에 시작~종료 시각이 기록됩니다.</p>`;
    return;
  }

  const rows = history.map((h) => `
    <tr>
      <td class="wh-title">${h.title}</td>
      <td>${fmtTime(h.startedAt)}</td>
      <td>${fmtTime(h.endedAt)}</td>
      <td>${h.endedAt ? fmtDuration(h.durationSec) : '-'}</td>
    </tr>
  `).join('');

  el.innerHTML = `
    <table class="watch-history-table">
      <thead><tr><th>영상</th><th>시작 시각</th><th>종료 시각</th><th>시청 시간</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function finalizeOpenSession() {
  if (!openSession) return;
  const now = new Date().toISOString();
  openSession.endedAt = now;
  openSession.durationSec = Math.max(
    0, Math.round((new Date(now) - new Date(openSession.startedAt)) / 1000),
  );
  const history = loadHistory();
  const idx = history.findIndex((h) => h.sessionId === openSession.sessionId);
  if (idx >= 0) history[idx] = openSession;
  saveHistory(history);
  openSession = null;
  renderHistory();
}

function startSession(video) {
  finalizeOpenSession();
  openSession = {
    sessionId: `${video.videoId}-${Date.now()}`,
    videoId: video.videoId,
    title: video.title,
    channel: video.channel,
    startedAt: new Date().toISOString(),
    endedAt: null,
    durationSec: 0,
  };
  const history = loadHistory();
  history.unshift(openSession);
  saveHistory(history);
  renderHistory();
}

function ensureYouTubeApi() {
  if (ytApiPromise) return ytApiPromise;
  ytApiPromise = new Promise((resolve) => {
    if (window.YT && window.YT.Player) return resolve(window.YT);
    const prevReady = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      if (typeof prevReady === 'function') prevReady();
      resolve(window.YT);
    };
    const s = document.createElement('script');
    s.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(s);
  });
  return ytApiPromise;
}

function onPlayerStateChange(event) {
  if (!currentVideo) return;
  const YT = window.YT;
  if (event.data === YT.PlayerState.PLAYING) {
    if (!openSession || openSession.videoId !== currentVideo.videoId) {
      startSession(currentVideo);
    }
  } else if (event.data === YT.PlayerState.PAUSED || event.data === YT.PlayerState.ENDED) {
    finalizeOpenSession();
  }
}

async function playVideo(video) {
  currentVideo = video;
  enterPlayerMode();
  document.querySelectorAll('.video-card').forEach((c) => c.classList.toggle('now-playing', c.dataset.videoId === video.videoId));
  document.getElementById('yt-player-empty')?.classList.add('hidden');

  // 영상을 고르면 목록 패널을 닫아 재생 화면이 바로 보이게 한다
  document.getElementById('video-list-panel')?.classList.remove('open');
  document.getElementById('video-list-overlay')?.classList.remove('show');

  const nowPlayingEl = document.getElementById('now-playing-title');
  if (nowPlayingEl) nowPlayingEl.textContent = `${video.title} · ${video.channel}`;

  const YT = await ensureYouTubeApi();
  if (!ytPlayer) {
    ytPlayer = new YT.Player('yt-player', {
      videoId: video.videoId,
      width: '100%',
      height: '100%',
      playerVars: { rel: 0, autoplay: 1 },
      events: {
        onReady: (e) => e.target.playVideo(),
        onStateChange: onPlayerStateChange,
      },
    });
  } else {
    ytPlayer.loadVideoById(video.videoId);
  }

  document.getElementById('yt-player-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 탭을 벗어나거나 페이지를 떠날 때 열려 있는 시청 세션을 종료 시각으로 마감
window.addEventListener('beforeunload', finalizeOpenSession);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') finalizeOpenSession();
});

function videoCard(video) {
  return `
    <div class="card video-card" data-video-id="${video.videoId}">
      <div class="video-thumb-wrap">
        <img class="video-thumb" src="${video.thumbnail}" alt="${video.title}" loading="lazy" />
        <span class="video-length">${video.length || ''}</span>
      </div>
      <h3 class="video-title" title="${video.title}">${video.title}</h3>
      <p class="video-channel"><i class="fa-solid fa-user"></i> ${video.channel}</p>
      <button class="resource-cta video-play-btn" type="button">
        <i class="fa-solid fa-play"></i> 이 페이지에서 재생
      </button>
    </div>
  `;
}

async function render() {
  const el = document.getElementById('page-content');
  if (!el) return;
  el.innerHTML = `<div class="loading-wrap"><div class="spinner"></div><div class="loading-text">영상 목록 불러오는 중…</div></div>`;

  let data;
  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (err) {
    el.innerHTML = `<div class="card"><p style="color:var(--red)">영상 목록을 불러오지 못했습니다: ${err.message}</p></div>`;
    return;
  }

  const topicSections = VIDEO_MODULES.map((module) => {
    const topics = module.topics
      .map((label) => ({ label, info: data[label] }))
      .filter(({ info }) => info);
    return `
      <section class="video-module-block">
        <div class="resource-module-head">
          <div><span class="resource-module-kicker">${module.title}</span><h2>${module.subtitle}</h2></div>
          <p>영상은 뜻을 이해하는 데만 사용하고, ‘수익 보장’ 같은 말은 믿지 않아요.</p>
        </div>
        ${topics.map(({ label, info }) => `
          <div class="video-topic-block">
            <div class="resource-category">${info.category}</div>
            <h3 class="video-topic-label">${label}</h3>
            <div class="grid-3">${info.videos.map(videoCard).join('')}</div>
          </div>`).join('')}
      </section>`;
  }).join('');

  el.innerHTML = `
    <div class="resource-hero">
      <h1><i class="fa-brands fa-youtube" style="color:#ff0000"></i> 주식 1~5 영상 자료</h1>
      <p>주식 1부터 순서대로, 모르는 말을 이해하는 데 도움이 되는 영상만 골라 보세요.</p>
    </div>

    <div id="yt-player-wrap" class="card yt-player-card">
      <div class="card-title"><i class="fa-solid fa-tv"></i>재생 영역</div>
      <div id="yt-player-frame">
        <div id="yt-player"></div>
        <p id="yt-player-empty" class="yt-player-empty">아래 목록에서 영상을 선택하면 여기에서 재생됩니다.</p>
      </div>
      <p id="now-playing-title" class="now-playing-title"></p>
    </div>

    <section class="card yt-watch-history" style="margin:20px 0;">
      <div class="card-title"><i class="fa-solid fa-clock-rotate-left"></i>내 시청 기록 (이 브라우저에 저장됨)</div>
      <div id="watch-history"></div>
      <button id="clear-history-btn" class="ghost-btn" type="button" style="margin-top:12px;">
        <i class="fa-solid fa-trash"></i> 기록 전체 삭제
      </button>
    </section>

    <button class="video-list-toggle" id="video-list-toggle" type="button">
      <i class="fa-solid fa-list"></i> 영상 목록
    </button>
    <div class="video-list-overlay" id="video-list-overlay"></div>
    <aside class="video-list-panel" id="video-list-panel">
      <div class="video-list-hdr">
        <div class="video-list-title"><i class="fa-brands fa-youtube" style="color:#ff0000"></i> 영상 목록</div>
        <button class="video-list-close" id="video-list-close" type="button" aria-label="영상 목록 닫기">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
      ${topicSections}
    </aside>
  `;

  // 영상 목록 offcanvas 열기/닫기
  function openVideoList() {
    document.getElementById('video-list-panel')?.classList.add('open');
    document.getElementById('video-list-overlay')?.classList.add('show');
  }
  function closeVideoList() {
    document.getElementById('video-list-panel')?.classList.remove('open');
    document.getElementById('video-list-overlay')?.classList.remove('show');
  }
  document.getElementById('video-list-toggle')?.addEventListener('click', openVideoList);
  document.getElementById('video-list-overlay')?.addEventListener('click', closeVideoList);
  document.getElementById('video-list-close')?.addEventListener('click', closeVideoList);

  el.querySelectorAll('.video-card').forEach((card) => {
    const videoId = card.dataset.videoId;
    let video = null;
    for (const info of Object.values(data)) {
      const found = info.videos.find((v) => v.videoId === videoId);
      if (found) { video = found; break; }
    }
    card.querySelector('.video-play-btn')?.addEventListener('click', () => video && playVideo(video));
  });

  document.getElementById('clear-history-btn')?.addEventListener('click', () => {
    if (!confirm('시청 기록을 모두 삭제할까요?')) return;
    saveHistory([]);
    openSession = null;
    renderHistory();
  });

  renderHistory();
}

render();
