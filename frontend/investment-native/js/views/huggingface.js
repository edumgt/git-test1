import { apiPost, withLoading, renderError } from '../api.js';

export function huggingfaceView(container) {
  container.innerHTML = `
    <section class="card">
      <h2>&#x1F3A8; HuggingFace Diffusion (GPU)</h2>
      <p class="desc">
        텍스트 프롬프트에서 이미지를 생성합니다. CUDA GPU가 필요합니다.<br/>
        Generates images from text prompts using Stable Diffusion. Requires CUDA GPU.
      </p>
      <div class="form-row" style="flex-direction:column;">
        <div class="form-group">
          <label>Prompt</label>
          <textarea id="hfPrompt" rows="3">A futuristic city skyline at sunset</textarea>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Guidance Scale</label>
          <input id="hfGuidance" type="number" step="0.5" value="8.0" min="1" max="15" />
        </div>
        <div class="form-group">
          <label>Width</label>
          <input id="hfWidth" type="number" value="512" min="256" max="1024" step="64" />
        </div>
        <div class="form-group">
          <label>Height</label>
          <input id="hfHeight" type="number" value="512" min="256" max="1024" step="64" />
        </div>
      </div>
      <div class="alert alert-info">GPU 환경에서만 동작합니다. CPU에서는 503 오류가 반환됩니다.</div>
      <button class="run" id="hfRun">&#x25B6; 이미지 생성 / Generate</button>
      <div id="hfArea"></div>
    </section>
  `;

  container.querySelector('#hfRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const area = container.querySelector('#hfArea');
    const payload = {
      prompt: container.querySelector('#hfPrompt').value,
      guidance_scale: Number(container.querySelector('#hfGuidance').value),
      width: Number(container.querySelector('#hfWidth').value),
      height: Number(container.querySelector('#hfHeight').value),
    };
    try {
      const result = await withLoading(btn, () => apiPost('/api/genai/text-to-image', payload));
      area.innerHTML = '<img class="preview" src="' + result.image_url + '" alt="diffusion result" />';
    } catch (err) {
      area.innerHTML = renderError(err.message);
    }
  });
}
