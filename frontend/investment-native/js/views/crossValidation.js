import { apiPost, withLoading, renderMetrics, renderImage, renderError } from '../api.js';
import { cloudResourceCard } from './cloudAiResources.js';

export function crossValidationView(container) {
  container.innerHTML = `
    <section class="card">
      <h2><i class="fa-solid fa-table-cells"></i> Cross Validation</h2>
      <p class="desc">
        K-Fold 교차 검증으로 모델의 안정적인 성능을 측정합니다.<br/>
        K-Fold cross-validation measures stable model performance by averaging across multiple folds.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>샘플 수 / Samples</label>
          <input id="cvSamples" type="number" value="1000" min="200" max="20000" />
        </div>
        <div class="form-group">
          <label>특성 수 / Features</label>
          <input id="cvFeatures" type="number" value="10" min="2" max="100" />
        </div>
        <div class="form-group">
          <label>Fold 수 / Folds</label>
          <input id="cvFold" type="number" value="5" min="3" max="10" />
        </div>
      </div>
      <button class="run" id="cvRun">▶ 실행 / Run</button>
      <div id="cvResult"></div>
    </section>
    ${cloudResourceCard('cross-validation')}
  `;

  container.querySelector('#cvRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const resultEl = container.querySelector('#cvResult');
    const payload = {
      n_samples: Number(container.querySelector('#cvSamples').value),
      n_features: Number(container.querySelector('#cvFeatures').value),
      cv: Number(container.querySelector('#cvFold').value),
    };
    try {
      const result = await withLoading(btn, () => apiPost('/api/ml/cross-validation', payload));
      resultEl.innerHTML =
        renderMetrics([
          ['Mean Acc', result.mean_accuracy.toFixed(4)],
          ['Std', result.std_accuracy.toFixed(4)],
          ['Folds', result.fold_scores.length],
        ]) +
        `<pre>${JSON.stringify(result, null, 2)}</pre>`;
    } catch (err) {
      resultEl.innerHTML = renderError(err.message);
    }
  });
}
