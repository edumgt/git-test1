import { apiPost, withLoading, renderMetrics, renderImage, renderError } from '../api.js';
import { cloudResourceCard } from './cloudAiResources.js';

export function linearRegressionView(container) {
  container.innerHTML = `
    <section class="card">
      <h2>&#x1F4C8; Linear &amp; Polynomial Regression</h2>
      <p class="desc">
        선형 및 다항 회귀 분석. degree=1이 선형, 2+ 이면 다항 회귀입니다.<br/>
        Linear and polynomial regression. degree=1 is linear; higher degree fits curved data.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>다항 차수 / Poly Degree</label>
          <input id="regDegree" type="number" value="1" min="1" max="5" />
        </div>
        <div class="form-group">
          <label>샘플 수 / Samples</label>
          <input id="regSamples" type="number" value="200" min="50" max="2000" />
        </div>
        <div class="form-group">
          <label>노이즈 / Noise</label>
          <input id="regNoise" type="number" step="0.5" value="3.0" min="0" max="20" />
        </div>
      </div>
      <button class="run" id="regRun">&#x25B6; 학습 / Fit</button>
      <div id="regResult"></div>
    </section>
    ${cloudResourceCard('linear-regression')}
  `;

  container.querySelector('#regRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const resultEl = container.querySelector('#regResult');
    const payload = {
      degree: Number(container.querySelector('#regDegree').value),
      n_samples: Number(container.querySelector('#regSamples').value),
      noise: Number(container.querySelector('#regNoise').value),
    };
    try {
      const result = await withLoading(btn, () => apiPost('/api/ml/linear-regression', payload));
      resultEl.innerHTML =
        renderMetrics([
          ['R²', result.r2_score.toFixed(4)],
          ['MSE', result.mse.toFixed(4)],
          ['Degree', result.degree],
        ]) +
        renderImage(result.image_base64);
    } catch (err) {
      resultEl.innerHTML = renderError(err.message);
    }
  });
}
