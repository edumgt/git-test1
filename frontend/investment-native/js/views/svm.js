import { apiPost, withLoading, renderMetrics, renderImage, renderError } from '../api.js';
import { cloudResourceCard } from './cloudAiResources.js';

export function svmView(container) {
  container.innerHTML = `
    <section class="card">
      <h2>&#x2694;&#xFE0F; SVM Classifier</h2>
      <p class="desc">
        서포트 벡터 머신 분류기. 커널(rbf/linear/poly)과 C 값을 조절해 결과를 비교하세요.<br/>
        Support Vector Machine classifier. Adjust kernel and C parameter to compare results.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>커널 / Kernel</label>
          <select id="svmKernel">
            <option value="rbf" selected>RBF (Gaussian)</option>
            <option value="linear">Linear</option>
            <option value="poly">Polynomial</option>
          </select>
        </div>
        <div class="form-group">
          <label>C (Regularization)</label>
          <input id="svmC" type="number" step="0.1" value="1.0" min="0.01" max="100" />
        </div>
      </div>
      <button class="run" id="svmRun">&#x25B6; 학습 / Train</button>
      <div id="svmResult"></div>
    </section>
    ${cloudResourceCard('svm')}
  `;

  container.querySelector('#svmRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const resultEl = container.querySelector('#svmResult');
    const payload = {
      kernel: container.querySelector('#svmKernel').value,
      C: Number(container.querySelector('#svmC').value),
    };
    try {
      const result = await withLoading(btn, () => apiPost('/api/ml/svm', payload));
      resultEl.innerHTML =
        renderMetrics([
          ['Accuracy', result.accuracy.toFixed(4)],
          ['Support Vectors', result.n_support_vectors],
        ]) +
        renderImage(result.image_base64);
    } catch (err) {
      resultEl.innerHTML = renderError(err.message);
    }
  });
}
