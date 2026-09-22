import { apiPost, withLoading, renderError } from '../api.js';

export function sentimentView(container) {
  container.innerHTML = `
    <section class="card">
      <h2>&#x1F4AC; NLP Text Classification</h2>
      <p class="desc">
        TF-IDF 벡터화 + 로지스틱 회귀로 텍스트를 스포츠 / 정치 카테고리로 분류합니다.<br/>
        Classifies text into Sports vs. Politics using TF-IDF + Logistic Regression.
      </p>
      <div class="form-group" style="margin-bottom:10px;">
        <label>분류할 텍스트 / Texts to Classify (한 줄에 하나 / one per line)</label>
        <textarea id="nlpTexts" rows="5">The team scored a goal in overtime to win the championship!
The government proposed a new budget policy for healthcare.
Ice hockey season is starting next month with exciting matchups.
Political debates are heating up ahead of the election.</textarea>
      </div>
      <button class="run" id="nlpRun">&#x25B6; 분류 / Classify</button>
      <div id="nlpResult"></div>
    </section>
  `;

  container.querySelector('#nlpRun').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const resultEl = container.querySelector('#nlpResult');
    const texts = container.querySelector('#nlpTexts').value
      .split('\n')
      .map(t => t.trim())
      .filter(t => t.length > 0);

    if (texts.length === 0) {
      resultEl.innerHTML = renderError('텍스트를 입력하세요.');
      return;
    }

    try {
      const result = await withLoading(btn, () => apiPost('/api/nlp/text-classify', { texts }));
      const rows = result.predictions.map(p => `
        <tr>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;max-width:400px;word-break:break-word;">${p.text}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-weight:600;color:var(--primary)">${p.label}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;">${(p.confidence * 100).toFixed(1)}%</td>
        </tr>
      `).join('');
      resultEl.innerHTML = `
        <table style="width:100%;border-collapse:collapse;margin-top:12px;font-size:0.85rem;">
          <thead>
            <tr style="background:var(--bg);">
              <th style="padding:8px;text-align:left;">Text</th>
              <th style="padding:8px;text-align:left;">Label</th>
              <th style="padding:8px;text-align:left;">Confidence</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    } catch (err) {
      resultEl.innerHTML = renderError(err.message);
    }
  });
}
