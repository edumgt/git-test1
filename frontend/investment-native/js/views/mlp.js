import { apiPost, withLoading, renderMetrics, renderImage, renderError } from '../api.js';
import { cloudResourceCard } from './cloudAiResources.js';

export function mlpView(container) {
  container.innerHTML = `
    <section class="card">
      <h2>&#x1F9E0; MLP Neural Network</h2>
      <p class="desc">
        다층 퍼셉트론(MLP) 신경망 분류기. 은닉층 크기와 반복 횟수를 조절하세요.<br/>
        Multi-Layer Perceptron classifier. Adjust hidden layer sizes and max iterations.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>은닉층 / Hidden Layers (쉼표 구분)</label>
          <input id="mlpLayers" type="text" value="128,64,32" />
        </div>
        <div class="form-group">
          <label>최대 반복 / Max Iter</label>
          <input id="mlpIter" type="number" value="300" min="50" max="1000" />
        </div>
        <div class="form-group">
          <label>샘플 수 / Samples</label>
          <input id="mlpSamples" type="number" value="1000" min="200" max="10000" />
        </div>
      </div>
      <button class="run" id="mlpRun">&#x25B6; 학습 / Train</button>
      <div id="mlpResult"></div>
    </section>
    ${cloudResourceCard('mlp')}
  `;

  container.querySelector('#mlpRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const resultEl = container.querySelector('#mlpResult');
    const payload = {
      hidden_layers: container.querySelector('#mlpLayers').value,
      max_iter: Number(container.querySelector('#mlpIter').value),
      n_samples: Number(container.querySelector('#mlpSamples').value),
    };
    try {
      const result = await withLoading(btn, () => apiPost('/api/ml/mlp', payload));
      resultEl.innerHTML =
        renderMetrics([
          ['Accuracy', result.accuracy.toFixed(4)],
          ['Iterations', result.n_iterations],
        ]) +
        renderImage(result.image_base64);
    } catch (err) {
      resultEl.innerHTML = renderError(err.message);
    }
  });
}
