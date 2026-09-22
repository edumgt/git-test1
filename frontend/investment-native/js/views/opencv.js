import { apiPost, withLoading, renderError } from '../api.js';

export function opencvView(container) {
  container.innerHTML = `
    <section class="card">
      <h2>&#x1F3A5; OpenCV Circle Animation</h2>
      <p class="desc">
        OpenCV로 동심원 애니메이션 MP4를 서버에서 생성합니다.<br/>
        Generates a pulsing circle animation video using OpenCV on the server.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>너비 / Width</label>
          <input id="cvWidth" type="number" value="512" min="128" max="1920" />
        </div>
        <div class="form-group">
          <label>높이 / Height</label>
          <input id="cvHeight" type="number" value="512" min="128" max="1080" />
        </div>
        <div class="form-group">
          <label>FPS</label>
          <input id="cvFps" type="number" value="30" min="10" max="60" />
        </div>
      </div>
      <button class="run" id="ocvRun">&#x25B6; 영상 생성 / Generate</button>
      <div id="ocvArea"></div>
    </section>
  `;

  container.querySelector('#ocvRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const area = container.querySelector('#ocvArea');
    const payload = {
      width: Number(container.querySelector('#cvWidth').value),
      height: Number(container.querySelector('#cvHeight').value),
      fps: Number(container.querySelector('#cvFps').value),
    };
    try {
      const result = await withLoading(btn, () => apiPost('/api/cv/circle-animation', payload));
      area.innerHTML = '<video class="preview" controls src="' + result.video_url + '"></video>';
    } catch (err) {
      area.innerHTML = renderError(err.message);
    }
  });
}
