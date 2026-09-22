import { apiPost, withLoading, renderMetrics, renderImage, renderError } from '../api.js';
import { cloudResourceCard } from './cloudAiResources.js';

export function kmeansView(container) {
  container.innerHTML = `
    <section class="card">
      <h2>&#x1F535; KMeans Clustering</h2>
      <p class="desc">
        비지도 학습으로 데이터를 K개 군집으로 나눕니다. Elbow 그래프로 최적 K를 찾을 수 있습니다.<br/>
        Unsupervised learning that groups data into K clusters. Use the elbow plot to find the optimal K.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label>샘플 수 / Samples</label>
          <input id="kmSamples" type="number" value="400" min="100" max="5000" />
        </div>
        <div class="form-group">
          <label>클러스터 수 K / Clusters</label>
          <input id="kmK" type="number" value="4" min="2" max="10" />
        </div>
        <div class="form-group">
          <label>분산 / Std</label>
          <input id="kmStd" type="number" step="0.1" value="0.8" min="0.1" max="3.0" />
        </div>
      </div>
      <button class="run" id="kmRun">&#x25B6; 클러스터링 / Cluster</button>
      <div id="kmResult"></div>
    </section>
    ${cloudResourceCard('kmeans')}
  `;

  container.querySelector('#kmRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const resultEl = container.querySelector('#kmResult');
    const payload = {
      n_samples: Number(container.querySelector('#kmSamples').value),
      n_clusters: Number(container.querySelector('#kmK').value),
      cluster_std: Number(container.querySelector('#kmStd').value),
    };
    try {
      const result = await withLoading(btn, () => apiPost('/api/ml/kmeans', payload));
      resultEl.innerHTML =
        renderMetrics([
          ['Silhouette', result.silhouette_score.toFixed(4)],
          ['Inertia', result.inertia.toFixed(1)],
        ]) +
        renderImage(result.image_base64);
    } catch (err) {
      resultEl.innerHTML = renderError(err.message);
    }
  });
}
