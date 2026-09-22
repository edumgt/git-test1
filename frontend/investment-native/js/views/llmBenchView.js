import { api } from '../api.js';

const PROVIDERS = [
  {
    id: 'ec2',
    icon: 'fa-server',
    color: '#16a34a',
    title: 'EC2/ECS + vLLM · Ollama',
    desc: '로컬 Ollama와 동일한 엔진 구조입니다. GPU 인스턴스(g4dn/g5)에 vLLM 또는 Ollama를 직접 올려 OpenAI 호환 API로 서빙합니다.',
  },
  {
    id: 'bedrock',
    icon: 'fa-cloud',
    color: '#ff9900',
    title: 'Amazon Bedrock',
    desc: '완전 관리형. 인프라 없이 API 호출만으로 Llama·Mistral 등 오픈모델과 상용 모델을 사용합니다.',
  },
  {
    id: 'sagemaker',
    icon: 'fa-diagram-project',
    color: '#0ea5e9',
    title: 'SageMaker JumpStart',
    desc: '오픈소스 모델을 내 VPC의 전용 엔드포인트로 배포합니다. 파인튜닝이 필요할 때 적합합니다.',
  },
];

const EXAMPLES = ['삼성전자의 최근 실적 흐름을 3문장으로 요약해줘', 'PER과 PBR의 차이를 알려줘', '분산투자를 하는 이유는 무엇인가요?'];

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}

export function llmBenchView(app) {
  let active = 'ec2';
  let status = null;
  const results = { ec2: null, bedrock: null, sagemaker: null }; // { loading, error, response, model, latency_ms }

  function configuredBadge(id) {
    if (!status) return '<span class="badge badge-gray">확인 중</span>';
    const configured = status[id]?.configured;
    return configured
      ? '<span class="badge badge-green">설정됨</span>'
      : '<span class="badge badge-gray">미설정</span>';
  }

  function providerDetail(id) {
    if (!status) return '';
    const s = status[id];
    if (id === 'ec2') return s.base_url ? `엔드포인트: ${escapeHtml(s.base_url)} · 모델: ${escapeHtml(s.model || '-')}` : 'LLM_EC2_BASE_URL / LLM_EC2_MODEL 미설정';
    if (id === 'bedrock') return s.model ? `리전: ${escapeHtml(s.region || '-')} · 모델: ${escapeHtml(s.model)}` : 'AWS_REGION / BEDROCK_MODEL_ID 미설정';
    return s.endpoint ? `리전: ${escapeHtml(s.region || '-')} · 엔드포인트: ${escapeHtml(s.endpoint)}` : 'AWS_REGION / SAGEMAKER_ENDPOINT_NAME 미설정';
  }

  function resultPanel(id) {
    const r = results[id];
    if (!r) return '<p class="text-muted" style="font-size:.85rem;">프롬프트를 입력하고 실행 버튼을 누르면 결과가 여기 표시됩니다.</p>';
    if (r.loading) return '<p style="font-size:.85rem;"><i class="fa-solid fa-spinner fa-spin"></i> 요청 중...</p>';
    if (r.error) return `<p style="color:#ef4444;font-size:.85rem;"><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(r.error)}</p>`;
    return `
      <div style="display:flex;gap:8px;margin-bottom:8px;">
        <span class="badge badge-green">${r.latency_ms}ms</span>
        <span class="badge badge-gray">${escapeHtml(r.model || '')}</span>
      </div>
      <p style="white-space:pre-wrap;font-size:.85rem;line-height:1.6;">${escapeHtml(r.response)}</p>`;
  }

  function render() {
    const provider = PROVIDERS.find((p) => p.id === active);
    app.innerHTML = `
      <section class="card" style="margin-bottom:16px;">
        <h2><i class="fa-solid fa-cloud-bolt"></i> LLM 서빙 방식 비교 (AWS)</h2>
        <p style="color:var(--text-muted,#666);font-size:.85rem;">로컬 Ollama를 대체할 AWS 서빙 방식 3가지를 같은 화면에서 테스트합니다. 각 방식은 환경변수를 설정해야 사용할 수 있습니다 (백엔드 .env.example 참고).</p>
      </section>
      <div class="llm-bench-gnb" style="display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--border,#e0e0e0);margin-bottom:16px;">
        ${PROVIDERS.map((p) => `
          <button type="button" class="llm-bench-tab" data-tab="${p.id}" style="
            display:flex;align-items:center;gap:8px;padding:10px 16px;border:none;background:none;cursor:pointer;
            font-weight:700;font-size:.85rem;color:${active === p.id ? p.color : 'var(--text-muted,#888)'};
            border-bottom:3px solid ${active === p.id ? p.color : 'transparent'};">
            <i class="fa-solid ${p.icon}"></i>${p.title}
          </button>`).join('')}
      </div>
      <section class="card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
          <div>
            <h3 style="margin:0 0 4px;font-size:.95rem;color:${provider.color};"><i class="fa-solid ${provider.icon}"></i> ${provider.title}</h3>
            <p style="margin:0;font-size:.82rem;color:var(--text-muted,#666);">${provider.desc}</p>
          </div>
          ${configuredBadge(active)}
        </div>
        <p style="font-size:.78rem;color:var(--text-muted,#888);margin-bottom:14px;">${providerDetail(active)}</p>

        <div class="llm-bench-examples" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
          ${EXAMPLES.map((ex) => `<button type="button" class="btn btn-secondary btn-sm llm-bench-example" data-query="${escapeHtml(ex)}">${escapeHtml(ex)}</button>`).join('')}
        </div>
        <form id="llm-bench-form" style="display:flex;gap:8px;">
          <input id="llm-bench-input" placeholder="테스트할 프롬프트를 입력하세요" maxlength="2000"
            style="flex:1;padding:10px 12px;border:1px solid var(--border,#ccc);border-radius:8px;font-size:.85rem;" />
          <button class="btn btn-primary" type="submit"><i class="fa-solid fa-play"></i> 실행</button>
        </form>

        <div id="llm-bench-result" style="margin-top:16px;padding:12px 14px;background:rgba(127,127,127,.06);border-radius:8px;min-height:48px;">
          ${resultPanel(active)}
        </div>
      </section>`;

    app.querySelectorAll('.llm-bench-tab').forEach((btn) => btn.addEventListener('click', () => { active = btn.dataset.tab; render(); }));
    app.querySelectorAll('.llm-bench-example').forEach((btn) => btn.addEventListener('click', () => runTest(btn.dataset.query)));
    app.querySelector('#llm-bench-form').addEventListener('submit', (event) => {
      event.preventDefault();
      const input = app.querySelector('#llm-bench-input');
      runTest(input.value.trim());
    });
  }

  async function runTest(prompt) {
    if (!prompt) return;
    results[active] = { loading: true };
    render();
    try {
      const data = await api.llmBenchChat({ provider: active, prompt });
      results[active] = { response: data.response, model: data.model, latency_ms: data.latency_ms };
    } catch (error) {
      results[active] = { error: error.message || '요청에 실패했습니다.' };
    }
    render();
  }

  async function loadStatus() {
    try {
      status = await api.llmBenchStatus();
    } catch {
      status = { ec2: {}, bedrock: {}, sagemaker: {} };
    }
    render();
  }

  render();
  loadStatus();
}
