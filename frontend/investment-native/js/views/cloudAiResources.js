// ── 클라우드 AI 리소스 매핑 ──────────────────────────────────────────────────
// 각 ML/DL/기술적 분석 모듈을 AWS/Azure/GCP 관리형 AI 서비스로 구현한다면
// 어떤 리소스를 쓰게 되는지 설명하는 공용 카드. 실습은 로컬(scikit-learn/torch)로
// 진행하되, 실무에서는 아래 서비스들로 동일한 파이프라인을 대체/확장한다.

const CLOUD_RESOURCES = {
  'cross-validation': {
    aws:   'SageMaker Processing Job으로 K-Fold 분할·평가를 스크립트화해 실행하고, SageMaker Experiments로 폴드별 지표(정확도·표준편차)를 기록·비교합니다.',
    azure: 'Azure ML Pipelines에 K-Fold 단계를 구성하거나 AutoML의 내장 교차검증을 사용하고, Azure ML Experiments/MLflow 로깅으로 폴드별 성능을 추적합니다.',
    gcp:   'Vertex AI Pipelines(Kubeflow 기반)로 K-Fold 단계를 구성하고, Vertex AI Experiments로 폴드별 결과를 비교·시각화합니다.',
  },
  'random-forest': {
    aws:   'Amazon SageMaker의 내장 알고리즘 또는 scikit-learn 스크립트를 SageMaker Training Job(예: ml.m5.xlarge, CPU)으로 학습하고, 모델은 S3에 저장 후 SageMaker Endpoint로 배포합니다.',
    azure: 'Azure ML Designer의 Two-Class/Multiclass Decision Forest 모듈이나 Azure AutoML로 트리 앙상블을 자동 탐색하고, Compute Cluster에서 학습합니다.',
    gcp:   'Vertex AI AutoML Tables로 자동 트리 앙상블을 학습하거나, Vertex AI Training 커스텀 컨테이너에서 scikit-learn RandomForest를 실행합니다. 데이터는 BigQuery/Cloud Storage에서 로드합니다.',
  },
  'kmeans': {
    aws:   'SageMaker 내장 K-Means 알고리즘(대규모 데이터를 분산 처리하는 Web-scale K-Means)을 사용하고, 학습 결과는 S3에 저장합니다.',
    azure: 'Azure ML Designer의 K-Means Clustering 모듈, 또는 대용량 데이터라면 Azure Databricks(Spark MLlib KMeans)로 분산 군집화를 수행합니다.',
    gcp:   'BigQuery ML의 `CREATE MODEL ... OPTIONS(model_type="kmeans")` 구문으로 SQL만으로 서버리스 군집화를 실행하거나, Vertex AI Training으로 커스텀 학습합니다.',
  },
  'svm': {
    aws:   'SageMaker Linear Learner(선형 커널 근사) 또는 커스텀 스크립트(scikit-learn SVC)를 SageMaker Training Job에서 실행합니다.',
    azure: 'Azure ML Designer의 Two-Class Support Vector Machine 모듈로 노코드에 가깝게 학습·평가할 수 있습니다.',
    gcp:   'Vertex AI Training 커스텀 컨테이너로 scikit-learn SVM을 실행합니다(BigQuery ML은 SVM을 직접 지원하지 않아 AutoML Tables로 대체하는 경우가 많습니다).',
  },
  'mlp': {
    aws:   'SageMaker + PyTorch/TensorFlow Deep Learning Container를 GPU 인스턴스(예: ml.g4dn.xlarge)에서 학습하고, SageMaker Neo로 추론을 최적화할 수 있습니다.',
    azure: 'Azure ML Compute Cluster(GPU) + PyTorch/TensorFlow 환경에서 학습하거나, Azure ML Designer의 Neural Network Regression/Classification 모듈을 사용합니다.',
    gcp:   'Vertex AI Training의 TensorFlow/PyTorch 사전빌드 컨테이너를 GPU로 실행하고, Vertex AI Experiments로 하이퍼파라미터 튜닝(Vizier)을 병행합니다.',
  },
  'linear-regression': {
    aws:   'SageMaker 내장 알고리즘 Linear Learner로 학습하며, 대량의 특성·데이터에서도 분산 학습을 지원합니다.',
    azure: 'Azure ML Designer의 Linear Regression 모듈이나 Azure AutoML Regression으로 자동으로 최적 회귀 모델을 탐색합니다.',
    gcp:   'BigQuery ML의 `CREATE MODEL ... OPTIONS(model_type="linear_reg")`로 SQL 기반 서버리스 회귀 모델을 즉시 생성할 수 있습니다.',
  },
  'cnn-timeseries': {
    aws:   'SageMaker + TensorFlow/PyTorch Deep Learning Container를 GPU 인스턴스(ml.g5/ml.p3)로 학습하고, SageMaker Batch Transform으로 대량 추론을 실행합니다.',
    azure: 'Azure ML GPU Compute Cluster(NC/ND 시리즈 VM)에서 1D CNN을 학습하고, Azure ML Automated ML의 시계열 예측 기능과 결합할 수 있습니다.',
    gcp:   'Vertex AI Training의 GPU/TPU 리소스로 학습하고, 완전관리형 대안으로 Vertex AI Forecast(AutoML 기반 시계열 예측)를 검토할 수 있습니다.',
  },
  'lstm': {
    aws:   'SageMaker + TensorFlow/PyTorch DLC(GPU)로 직접 학습하거나, 완전관리형 시계열 예측 서비스인 Amazon Forecast(DeepAR+ 알고리즘 내장)로 대체할 수 있습니다.',
    azure: 'Azure ML GPU Compute Cluster에서 LSTM을 학습하거나, Azure Machine Learning Automated ML의 Forecasting(시계열 특화 AutoML)을 사용할 수 있습니다.',
    gcp:   'Vertex AI Training(GPU)으로 직접 학습하거나, 완전관리형 Vertex AI Forecast(AutoML 기반)로 시계열 예측 파이프라인을 단순화할 수 있습니다.',
  },
  'transformer': {
    aws:   'SageMaker JumpStart의 사전학습 Transformer 모델을 활용하거나, Hugging Face Deep Learning Container로 SageMaker에서 파인튜닝·분산학습(멀티 GPU, ml.p4d)합니다.',
    azure: 'Azure Machine Learning + Hugging Face 통합으로 파인튜닝하거나, 자체 학습 대신 Azure OpenAI Service의 사전학습 대형 모델 API를 호출하는 방식으로 대체할 수 있습니다.',
    gcp:   'Vertex AI Training의 TPU Pod로 대규모 Transformer를 학습하거나, Vertex AI Model Garden에서 사전학습 모델을 바로 배포·서빙할 수 있습니다.',
  },
  'technical-chart': {
    aws:   '이동평균·RSI·MACD 등은 학습 모델이 아닌 규칙 기반 계산이므로, 실시간 시세는 Amazon Kinesis Data Streams로 수집하고 지표 계산은 AWS Lambda(서버리스)에서 처리합니다. 캔들 패턴을 이미지로 다룬다면 SageMaker로 패턴 분류 모델을 추가할 수 있습니다.',
    azure: 'Azure Stream Analytics로 실시간 시세를 처리하고, Azure Functions(서버리스)로 지표를 계산합니다. 캔들 패턴 분류가 필요하면 Azure ML Designer로 이미지/시퀀스 분류 모델을 학습합니다.',
    gcp:   'Cloud Dataflow(Apache Beam)로 실시간 시세 스트리밍을 처리하고, Cloud Functions로 지표를 계산합니다. 패턴 분류 확장 시 Vertex AI로 이미지·시퀀스 분류 모델을 학습합니다.',
  },
  'backtest': {
    aws:   '다양한 파라미터 조합(단기/장기 이동평균 등)을 대량 병렬로 시뮬레이션해야 하므로 AWS Batch로 다수의 백테스트 잡을 동시 실행하고, 결과는 S3에 적재 후 Athena로 집계·조회합니다.',
    azure: 'Azure Batch 또는 Azure ML Pipelines의 병렬 Step으로 다중 파라미터 백테스트를 동시 실행하고, 결과는 Azure Data Lake + Synapse로 집계합니다.',
    gcp:   'Cloud Batch(또는 Dataflow)로 병렬 백테스트를 실행하고, BigQuery로 대량의 시뮬레이션 결과를 집계·분석합니다.',
  },
  'pipeline': {
    aws:   'SageMaker Pipelines로 전처리→피처 생성→학습→평가→배포까지 이어지는 MLOps 파이프라인을 자동화하고, SageMaker Feature Store로 팩터 데이터를 버전 관리합니다.',
    azure: 'Azure ML Pipelines로 데이터 준비→학습→모델 등록까지 자동화하고, Azure ML Feature Store로 퀀트 팩터를 재사용 가능한 형태로 관리합니다.',
    gcp:   'Vertex AI Pipelines(Kubeflow 기반)로 종단간 MLOps 파이프라인을 구성하고, Vertex AI Feature Store로 멀티팩터 데이터를 중앙 관리합니다.',
  },
};

const PROVIDER_META = [
  ['AWS',   'aws',   '#ff9900'],
  ['Azure', 'azure', '#0078d4'],
  ['GCP',   'gcp',   '#4285f4'],
];

/**
 * @param {keyof typeof CLOUD_RESOURCES} key
 * @returns {string} HTML — 해당 모듈을 AWS/Azure/GCP 관리형 AI 리소스로 구현할 때의 매핑 카드
 */
export function cloudResourceCard(key) {
  const r = CLOUD_RESOURCES[key];
  if (!r) return '';
  return `
    <section style="margin-top:20px;background:var(--surface,#fff);border:1px solid var(--border,#e0e0e0);
                     border-left:3px solid #7c3aed;border-radius:10px;padding:16px 18px;">
      <h3 style="font-size:.88rem;font-weight:800;color:var(--text,#111);margin:0 0 10px;display:flex;align-items:center;gap:6px;">
        <i class="fa-solid fa-cloud" style="color:#7c3aed;"></i>
        클라우드 AI 리소스로 구현한다면?
      </h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;">
        ${PROVIDER_META.map(([name, prop, color]) => `
          <div style="background:rgba(127,127,127,.06);border:1px solid var(--border,#e0e0e0);border-radius:8px;padding:11px 12px;">
            <div style="font-size:.72rem;font-weight:800;color:${color};margin-bottom:5px;">${name}</div>
            <div style="font-size:.78rem;color:var(--text-muted,#555);line-height:1.55;">${r[prop]}</div>
          </div>`).join('')}
      </div>
    </section>`;
}
