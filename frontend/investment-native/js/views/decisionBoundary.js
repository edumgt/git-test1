import { apiGet, withLoading, renderImage, renderError } from '../api.js';

export function decisionBoundaryView(container) {
  container.innerHTML = `
    <section class="card">
      <h2><i class="fa-solid fa-draw-polygon"></i> Decision Boundary</h2>
      <p class="desc">
        로지스틱 회귀 모델이 2D 공간을 어떻게 나누는지 시각화합니다.<br/>
        Visualizes how a Logistic Regression model partitions 2D feature space.
      </p>
      <button class="run" id="dbRun">▶ 이미지 생성 / Generate</button>
      <div id="dbArea"></div>
    </section>
  `;

  container.querySelector('#dbRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const area = container.querySelector('#dbArea');
    try {
      const result = await withLoading(btn, () => apiGet('/api/ml/decision-boundary'));
      area.innerHTML = renderImage(result.image_base64);
    } catch (err) {
      area.innerHTML = renderError(err.message);
    }
  });
}
