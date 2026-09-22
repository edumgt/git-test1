from __future__ import annotations

import base64
import io
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[3]
GENERATED_DIR = ROOT_DIR / "app" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
router = APIRouter()
_matplotlib_font_configured = False


def configure_matplotlib_korean_font(plt) -> None:
    global _matplotlib_font_configured
    if _matplotlib_font_configured:
        return
    import matplotlib.font_manager as fm

    for font_path in (
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ):
        if font_path.exists():
            fm.fontManager.addfont(str(font_path))
            plt.rcParams["font.family"] = fm.FontProperties(fname=str(font_path)).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False
    _matplotlib_font_configured = True


class CrossValidationRequest(BaseModel):
    n_samples: int = Field(default=1000, ge=200, le=20000)
    n_features: int = Field(default=10, ge=2, le=100)
    cv: int = Field(default=5, ge=3, le=10)


class RandomForestRequest(BaseModel):
    test_size: float = Field(default=0.3, ge=0.1, le=0.5)


class CircleAnimationRequest(BaseModel):
    width: int = Field(default=512, ge=128, le=1920)
    height: int = Field(default=512, ge=128, le=1080)
    fps: int = Field(default=30, ge=10, le=60)


class KMeansRequest(BaseModel):
    n_samples: int = Field(default=400, ge=100, le=5000)
    n_clusters: int = Field(default=4, ge=2, le=10)
    cluster_std: float = Field(default=0.8, ge=0.1, le=3.0)


class SVMRequest(BaseModel):
    kernel: str = Field(default="rbf", pattern="^(rbf|linear|poly)$")
    C: float = Field(default=1.0, ge=0.01, le=100.0)


class MLPRequest(BaseModel):
    hidden_layers: str = Field(default="128,64,32", pattern=r"^\d+(,\d+)*$")
    max_iter: int = Field(default=300, ge=50, le=1000)
    n_samples: int = Field(default=1000, ge=200, le=10000)


class LinearRegressionRequest(BaseModel):
    degree: int = Field(default=1, ge=1, le=5)
    n_samples: int = Field(default=200, ge=50, le=2000)
    noise: float = Field(default=3.0, ge=0.0, le=20.0)


class TextClassifyRequest(BaseModel):
    texts: list[str] = Field(default=["The team played amazing hockey tonight!"])
    max_features: int = Field(default=5000, ge=500, le=20000)


class DiffusionRequest(BaseModel):
    prompt: str = Field(default="A futuristic city skyline at sunset")
    height: int = Field(default=512, ge=256, le=1024)
    width: int = Field(default=512, ge=256, le=1024)
    guidance_scale: float = Field(default=8.0, ge=1.0, le=15.0)


class BacktestRequest(BaseModel):
    fast: int = Field(default=5, ge=2, le=50, description="단기 이동평균 기간")
    slow: int = Field(default=20, ge=5, le=200, description="장기 이동평균 기간")
    n_days: int = Field(default=1260, ge=252, le=3780, description="시뮬레이션 일수 (252=1년)")
    annual_return: float = Field(default=0.08, ge=-0.2, le=0.5)
    annual_vol: float = Field(default=0.20, ge=0.05, le=1.0)
    risk_free: float = Field(default=0.03, ge=0.0, le=0.1)


class PortfolioRequest(BaseModel):
    n_portfolios: int = Field(default=3000, ge=500, le=10000)
    risk_free: float = Field(default=0.03, ge=0.0, le=0.1)


class RiskRequest(BaseModel):
    annual_vol: float = Field(default=0.25, ge=0.05, le=1.0)
    capital: float = Field(default=10_000_000, ge=1_000_000, le=1_000_000_000)
    risk_pct: float = Field(default=0.01, ge=0.001, le=0.05)
    confidence: float = Field(default=0.95, ge=0.90, le=0.99)
    atr_multiplier: float = Field(default=2.0, ge=1.0, le=5.0)


class TVAlertRequest(BaseModel):
    action: str = Field(default="buy", pattern="^(buy|sell)$")
    ticker: str = Field(default="AAPL", max_length=20)
    price: float = Field(default=0.0, ge=0.0)
    rsi: float | None = Field(default=None)


class CNNTimeSeriesRequest(BaseModel):
    window: int = Field(default=20, ge=10, le=60, description="입력 창 길이 (거래일)")
    n_samples: int = Field(default=2000, ge=500, le=10000, description="합성 데이터 샘플 수")
    epochs: int = Field(default=20, ge=5, le=50, description="학습 에폭 수")


class LSTMRequest(BaseModel):
    seq_len: int = Field(default=30, ge=10, le=60, description="LSTM 입력 시퀀스 길이")
    n_days: int = Field(default=2000, ge=500, le=5000, description="시뮬레이션 일수")
    hidden_size: int = Field(default=64, ge=16, le=256, description="LSTM 은닉 유닛 수")
    epochs: int = Field(default=30, ge=10, le=80, description="학습 에폭 수")


class TransformerTSRequest(BaseModel):
    seq_len: int = Field(default=40, ge=20, le=80, description="인코더 입력 창 길이")
    pred_steps: int = Field(default=5, ge=1, le=10, description="예측 스텝 수")
    d_model: int = Field(default=32, ge=16, le=128, description="Transformer d_model 차원")
    epochs: int = Field(default=30, ge=10, le=80, description="학습 에폭 수")




@router.post("/api/ml/cross-validation")
def cross_validation(req: CrossValidationRequest) -> dict[str, object]:
    import numpy as np
    from sklearn.datasets import make_classification
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score

    X, y = make_classification(
        n_samples=req.n_samples,
        n_features=req.n_features,
        n_informative=max(2, req.n_features // 2),
        n_redundant=max(1, req.n_features // 5),
        n_classes=2,
        random_state=42,
    )

    model = LogisticRegression(max_iter=1000)
    scores = cross_val_score(model, X, y, cv=req.cv)
    return {
        "fold_scores": [float(s) for s in scores],
        "mean_accuracy": float(np.mean(scores)),
        "std_accuracy": float(np.std(scores)),
    }


@router.get("/api/ml/decision-boundary")
def decision_boundary_image() -> dict[str, str]:
    import matplotlib
    import numpy as np
    from sklearn.datasets import make_classification
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    X, y = make_classification(
        n_samples=240,
        n_features=2,
        n_redundant=0,
        n_informative=2,
        n_clusters_per_class=1,
        random_state=42,
    )
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

    model = LogisticRegression()
    model.fit(X_train, y_train)

    x_min, x_max = X[:, 0].min() - 1, X[:, 0].max() + 1
    y_min, y_max = X[:, 1].min() - 1, X[:, 1].max() + 1
    xx, yy = np.meshgrid(np.linspace(x_min, x_max, 400), np.linspace(y_min, y_max, 400))
    Z = model.predict(np.c_[xx.ravel(), yy.ravel()]).reshape(xx.shape)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.contourf(xx, yy, Z, alpha=0.3, cmap=plt.cm.coolwarm)
    ax.scatter(X_train[:, 0], X_train[:, 1], c=y_train, marker="o", edgecolors="k", label="Train")
    ax.scatter(X_test[:, 0], X_test[:, 1], c=y_test, marker="x", label="Test")
    ax.set_title("Decision Boundary")
    ax.legend()
    ax.grid(True)

    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=140)
    plt.close(fig)
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {"image_base64": image_b64}


@router.post("/api/ml/random-forest")
def random_forest(req: RandomForestRequest) -> dict[str, object]:
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import train_test_split

    data = {
        "age": [22, 45, 33, 35, 52, 23, 43, 56, 48, 29, 33, 53, 56, 58, 29],
        "monthly_spend": [10, 200, 100, 150, 300, 15, 180, 400, 250, 35, 150, 300, 15, 180, 99],
        "months_active": [1, 36, 24, 30, 60, 2, 33, 72, 50, 5, 33, 72, 50, 5, 12],
        "churn": [1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 1],
    }

    df = pd.DataFrame(data)
    X = df[["age", "monthly_spend", "months_active"]]
    y = df["churn"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=req.test_size, random_state=42)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    report = classification_report(y_test, y_pred, output_dict=True)
    return {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "report": report,
    }


@router.post("/api/cv/circle-animation")
def circle_animation(req: CircleAnimationRequest) -> dict[str, str]:
    import cv2
    import numpy as np

    output_path = GENERATED_DIR / "circle_animation.mp4"

    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), req.fps, (req.width, req.height)
    )
    for radius in list(np.linspace(20, min(req.width, req.height) // 3, 30)) + list(
        np.linspace(min(req.width, req.height) // 3, 20, 30)
    ):
        image = np.zeros((req.height, req.width, 3), dtype=np.uint8)
        image[:] = (255, 0, 0)
        cv2.circle(image, (req.width // 2, req.height // 2), int(radius), (255, 255, 255), -1)
        writer.write(image)

    writer.release()
    return {"video_url": "/files/circle_animation.mp4"}


@router.post("/api/ml/kmeans")
def kmeans_clustering(req: KMeansRequest) -> dict[str, object]:
    import matplotlib
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.datasets import make_blobs
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    X, _ = make_blobs(
        n_samples=req.n_samples,
        centers=req.n_clusters,
        cluster_std=req.cluster_std,
        random_state=42,
    )
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=req.n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)
    centers = kmeans.cluster_centers_
    sil = float(silhouette_score(X_scaled, labels))

    # Elbow data
    inertias = []
    ks = list(range(2, min(req.n_clusters + 4, 10)))
    for ki in ks:
        km = KMeans(n_clusters=ki, random_state=42, n_init=10)
        km.fit(X_scaled)
        inertias.append(float(km.inertia_))

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].scatter(X_scaled[:, 0], X_scaled[:, 1], c=labels, cmap="tab10", alpha=0.7, s=12)
    axes[0].scatter(centers[:, 0], centers[:, 1], c="red", marker="X", s=200, zorder=5)
    axes[0].set_title(f"KMeans (k={req.n_clusters})  Silhouette={sil:.3f}")
    axes[0].grid(True)
    axes[1].plot(ks, inertias, "bo-")
    axes[1].set_xlabel("k")
    axes[1].set_ylabel("Inertia")
    axes[1].set_title("Elbow Method")
    axes[1].grid(True)
    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=120)
    plt.close(fig)

    return {
        "image_base64": base64.b64encode(buffer.getvalue()).decode(),
        "silhouette_score": sil,
        "inertia": float(kmeans.inertia_),
        "elbow": {"ks": ks, "inertias": inertias},
    }


@router.post("/api/ml/svm")
def svm_classifier(req: SVMRequest) -> dict[str, object]:
    import matplotlib
    import numpy as np
    from sklearn.datasets import make_classification
    from sklearn.inspection import DecisionBoundaryDisplay
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    X, y = make_classification(
        n_samples=300, n_features=2, n_redundant=0, n_informative=2,
        n_clusters_per_class=1, random_state=42,
    )
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.3, random_state=42)

    svm = SVC(kernel=req.kernel, C=req.C, gamma="scale", random_state=42)
    svm.fit(X_train, y_train)
    y_pred = svm.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    accuracy = float(accuracy_score(y_test, y_pred))
    n_support = int(np.sum(svm.n_support_))

    fig, ax = plt.subplots(figsize=(7, 5))
    DecisionBoundaryDisplay.from_estimator(
        svm, X_scaled, ax=ax, alpha=0.3, cmap=plt.cm.coolwarm, response_method="predict"
    )
    ax.scatter(X_train[:, 0], X_train[:, 1], c=y_train, cmap=plt.cm.coolwarm, edgecolors="k", s=25, label="Train")
    ax.scatter(X_test[:, 0], X_test[:, 1], c=y_test, cmap=plt.cm.coolwarm, marker="^", edgecolors="k", s=25, label="Test")
    ax.scatter(
        svm.support_vectors_[:, 0], svm.support_vectors_[:, 1],
        s=100, linewidth=1.5, facecolors="none", edgecolors="k", label="Support Vectors",
    )
    ax.set_title(f"SVM ({req.kernel} kernel, C={req.C})  Acc={accuracy:.3f}")
    ax.legend(fontsize=8)
    ax.grid(True)
    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=140)
    plt.close(fig)

    return {
        "image_base64": base64.b64encode(buffer.getvalue()).decode(),
        "accuracy": accuracy,
        "n_support_vectors": n_support,
        "report": report,
    }


@router.post("/api/ml/mlp")
def mlp_classifier(req: MLPRequest) -> dict[str, object]:
    import matplotlib
    from sklearn.datasets import make_classification
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import train_test_split
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    hidden_layers = tuple(int(x) for x in req.hidden_layers.split(","))

    X, y = make_classification(
        n_samples=req.n_samples, n_features=10, n_informative=6,
        n_redundant=2, n_classes=2, random_state=42,
    )
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

    mlp = MLPClassifier(
        hidden_layer_sizes=hidden_layers, activation="relu", solver="adam",
        max_iter=req.max_iter, random_state=42,
    )
    mlp.fit(X_train, y_train)
    y_pred = mlp.predict(X_test)
    accuracy = float(accuracy_score(y_test, y_pred))
    report = classification_report(y_test, y_pred, output_dict=True)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(mlp.loss_curve_, linewidth=2, color="#2563eb")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Loss")
    ax.set_title(f"MLP Loss Curve  (layers={hidden_layers})  Acc={accuracy:.3f}")
    ax.grid(True)
    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=140)
    plt.close(fig)

    return {
        "image_base64": base64.b64encode(buffer.getvalue()).decode(),
        "accuracy": accuracy,
        "n_iterations": mlp.n_iter_,
        "report": report,
    }


@router.post("/api/ml/linear-regression")
def linear_regression(req: LinearRegressionRequest) -> dict[str, object]:
    import matplotlib
    import numpy as np
    from sklearn.linear_model import LinearRegression as LR
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import PolynomialFeatures

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rng = np.random.default_rng(42)
    X = rng.uniform(0, 10, size=(req.n_samples, 1))
    # True underlying function: mixture so poly can shine
    y = sum(
        c * X.ravel() ** i
        for i, c in enumerate([10, -4, 0.5][: req.degree + 1])
    ) + rng.normal(0, req.noise, req.n_samples)

    model = make_pipeline(
        PolynomialFeatures(degree=req.degree, include_bias=False),
        LR(),
    )
    model.fit(X, y)
    y_pred = model.predict(X)
    r2 = float(r2_score(y, y_pred))
    mse = float(mean_squared_error(y, y_pred))

    X_plot = np.linspace(0, 10, 200).reshape(-1, 1)
    y_plot = model.predict(X_plot)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(X, y, alpha=0.4, s=15, label="Data")
    ax.plot(X_plot, y_plot, "r-", linewidth=2, label=f"Poly degree={req.degree}")
    ax.set_title(f"Regression (degree={req.degree})  R²={r2:.3f}  MSE={mse:.2f}")
    ax.set_xlabel("X")
    ax.set_ylabel("y")
    ax.legend()
    ax.grid(True)
    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=140)
    plt.close(fig)

    return {
        "image_base64": base64.b64encode(buffer.getvalue()).decode(),
        "r2_score": r2,
        "mse": mse,
        "degree": req.degree,
    }


@router.post("/api/nlp/text-classify")
def text_classify(req: TextClassifyRequest) -> dict[str, object]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    # Inline bilingual training corpus — sports vs. politics
    _TRAIN_TEXTS = [
        # Sports (label 0)
        "The hockey team scored three goals in the final period to win the championship.",
        "Basketball playoffs begin next week with exciting matchups across the league.",
        "The pitcher threw a no-hitter in yesterday's baseball game.",
        "Football season kicks off with record-breaking ticket sales.",
        "The swimmer broke the world record in the 100m freestyle at the Olympics.",
        "Tennis star wins Grand Slam after coming back from injury.",
        "Ice hockey league announces expansion teams in new cities.",
        "The marathon runner finished in record time despite difficult conditions.",
        "Soccer World Cup qualifying matches start this weekend.",
        "Gold medals were awarded in gymnastics and rowing at the games.",
        # Politics (label 1)
        "The senator proposed a new budget policy for healthcare reform.",
        "Parliament voted on the controversial immigration bill last night.",
        "The president signed an executive order on environmental regulations.",
        "Political debates are heating up ahead of the upcoming election.",
        "The government announced a new economic stimulus package.",
        "Opposition leaders called for an emergency session of parliament.",
        "Tax reform legislation passed the Senate with bipartisan support.",
        "Foreign policy discussions dominated the United Nations summit.",
        "The prime minister addressed the nation about the economic crisis.",
        "Congressional hearings on data privacy began on Monday.",
    ]
    _TRAIN_LABELS = [0] * 10 + [1] * 10
    _LABEL_NAMES = ["rec.sport", "politics"]

    pipe = make_pipeline(
        TfidfVectorizer(max_features=req.max_features, ngram_range=(1, 2), stop_words="english"),
        LogisticRegression(max_iter=1000),
    )
    pipe.fit(_TRAIN_TEXTS, _TRAIN_LABELS)

    predictions = []
    for text in req.texts:
        pred_idx = int(pipe.predict([text])[0])
        prob = pipe.predict_proba([text])[0]
        predictions.append({
            "text": text[:200],
            "label": _LABEL_NAMES[pred_idx],
            "confidence": float(prob[pred_idx]),
        })

    return {"predictions": predictions, "categories": _LABEL_NAMES}


@router.post("/api/genai/text-to-image")
def text_to_image(req: DiffusionRequest) -> dict[str, str]:
    try:
        import torch
        from diffusers import StableDiffusionPipeline
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"Missing dependency: {exc}") from exc

    if not torch.cuda.is_available():
        raise HTTPException(status_code=503, detail="CUDA GPU is not available in this environment.")

    model_id = os.getenv("DIFFUSERS_MODEL_ID", "runwayml/stable-diffusion-v1-5")
    pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float16).to("cuda")

    image = pipe(
        req.prompt,
        guidance_scale=req.guidance_scale,
        height=req.height,
        width=req.width,
    ).images[0]

    output_path = GENERATED_DIR / "diffusion_result.png"
    image.save(output_path)
    return {"image_url": "/files/diffusion_result.png"}


@router.get("/files/{file_name}")
def get_generated_file(file_name: str) -> FileResponse:
    target = GENERATED_DIR / file_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=target)


@router.post("/api/dl/cnn-timeseries")
def cnn_timeseries(req: CNNTimeSeriesRequest) -> dict[str, object]:
    """
    1D CNN으로 주가 패턴(상승·횡보·하락)을 분류합니다. (Day036 대응)
    """
    try:
        import torch
        import torch.nn as nn
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Missing dependency: {exc}") from exc

    import numpy as np
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    SEED = 42
    rng_ = np.random.default_rng(SEED)

    windows, labels = [], []
    for _ in range(req.n_samples):
        mu_ = rng_.uniform(-0.0003, 0.0003)
        sigma_ = rng_.uniform(0.01, 0.025)
        returns = rng_.normal(mu_, sigma_, req.window + 1)
        prices = 100 * np.exp(np.cumsum(returns))
        next_ret = (prices[req.window] - prices[req.window - 1]) / prices[req.window - 1]
        windows.append(prices[: req.window])
        labels.append(2 if next_ret > 0.01 else (0 if next_ret < -0.01 else 1))

    X_raw = np.array(windows, dtype=np.float32)
    y_arr = np.array(labels, dtype=np.int64)
    X_norm = StandardScaler().fit_transform(X_raw).astype(np.float32)
    X_tr, X_te, y_tr, y_te = train_test_split(X_norm, y_arr, test_size=0.2, stratify=y_arr, random_state=SEED)

    Xtr = torch.tensor(X_tr).unsqueeze(1)
    Xte = torch.tensor(X_te).unsqueeze(1)
    ytr = torch.tensor(y_tr)
    yte = torch.tensor(y_te)

    class _CNN1D(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv1d(1, 32, 3, padding=1), nn.ReLU(),
                nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(),
                nn.AdaptiveAvgPool1d(1), nn.Flatten(),
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3), nn.Linear(32, 3),
            )
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.net(x)

    torch.manual_seed(SEED)
    model = _CNN1D()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    crit = nn.CrossEntropyLoss()
    ds = torch.utils.data.TensorDataset(Xtr, ytr)
    dl = torch.utils.data.DataLoader(ds, batch_size=64, shuffle=True)

    train_acc_hist = []
    for _ in range(req.epochs):
        model.train()
        correct, total = 0, 0
        for xb, yb in dl:
            opt.zero_grad()
            out = model(xb)
            loss = crit(out, yb)
            loss.backward()
            opt.step()
            correct += (out.argmax(1) == yb).sum().item()
            total += len(yb)
        train_acc_hist.append(correct / total)

    model.eval()
    with torch.no_grad():
        val_preds = model(Xte).argmax(1).numpy()
    val_acc = float(np.mean(val_preds == y_te))

    label_names = ["하락", "횡보", "상승"]
    class_counts = {label_names[i]: int(np.sum(val_preds == i)) for i in range(3)}

    return {
        "val_accuracy": val_acc,
        "train_accuracy_final": float(train_acc_hist[-1]),
        "predicted_class_counts": class_counts,
        "train_accuracy_history": [round(a, 4) for a in train_acc_hist],
    }


@router.post("/api/dl/lstm-predictor")
def lstm_predictor(req: LSTMRequest) -> dict[str, object]:
    """
    LSTM으로 다음 날 주가 수익률을 예측합니다. (Day037 대응)
    """
    try:
        import torch
        import torch.nn as nn
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Missing dependency: {exc}") from exc

    import numpy as np
    from sklearn.preprocessing import StandardScaler

    SEED = 42
    rng_ = np.random.default_rng(SEED)
    daily_ret = rng_.normal(0.0002, 0.015, req.n_days)
    prices = 1000 * np.exp(np.cumsum(daily_ret))
    returns = (np.diff(prices) / prices[:-1]).astype(np.float32)

    def _make_seq(series: np.ndarray, seq_len: int):
        X_, y_ = [], []
        for i in range(len(series) - seq_len):
            X_.append(series[i : i + seq_len])
            y_.append(series[i + seq_len])
        return np.array(X_, dtype=np.float32), np.array(y_, dtype=np.float32)

    scaler_X = StandardScaler()
    scaler_y = StandardScaler()
    X_raw, y_raw = _make_seq(returns, req.seq_len)
    X_norm = scaler_X.fit_transform(X_raw).astype(np.float32)
    y_norm = scaler_y.fit_transform(y_raw.reshape(-1, 1)).ravel().astype(np.float32)

    split = int(len(X_norm) * 0.8)
    Xtr = torch.tensor(X_norm[:split]).unsqueeze(-1)
    Xte = torch.tensor(X_norm[split:]).unsqueeze(-1)
    ytr = torch.tensor(y_norm[:split])
    yte_raw = y_raw[split:]

    class _LSTM(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(1, req.hidden_size, 2, batch_first=True, dropout=0.2)
            self.fc = nn.Sequential(nn.Linear(req.hidden_size, 32), nn.ReLU(), nn.Linear(32, 1))
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :]).squeeze(-1)

    torch.manual_seed(SEED)
    model = _LSTM()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    crit = nn.MSELoss()
    ds = torch.utils.data.TensorDataset(Xtr, ytr)
    dl = torch.utils.data.DataLoader(ds, batch_size=64, shuffle=True)
    val_losses = []

    for _ in range(req.epochs):
        model.train()
        for xb, yb in dl:
            opt.zero_grad()
            loss = crit(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        model.eval()
        with torch.no_grad():
            vl = crit(model(Xte), torch.tensor(y_norm[split:])).item()
        val_losses.append(float(vl))

    model.eval()
    with torch.no_grad():
        y_pred_norm = model(Xte).numpy()
    y_pred_raw = scaler_y.inverse_transform(y_pred_norm.reshape(-1, 1)).ravel()
    dir_acc = float(np.mean(np.sign(y_pred_raw) == np.sign(yte_raw)))

    return {
        "direction_accuracy": dir_acc,
        "val_loss_final": val_losses[-1],
        "val_loss_history": [round(v, 6) for v in val_losses],
    }


@router.post("/api/dl/transformer-timeseries")
def transformer_timeseries(req: TransformerTSRequest) -> dict[str, object]:
    """
    Transformer Encoder로 멀티스텝 주가를 예측합니다. (Day038-039 대응)
    """
    try:
        import math
        import torch
        import torch.nn as nn
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Missing dependency: {exc}") from exc

    import numpy as np
    from sklearn.preprocessing import MinMaxScaler

    SEED = 42
    rng_ = np.random.default_rng(SEED)
    t = np.arange(2500)
    seasonal = 0.02 * np.sin(2 * np.pi * t / 252)
    log_returns = 0.0001 + seasonal * 0.005 + rng_.normal(0, 0.012, 2500)
    prices = 1000 * np.exp(np.cumsum(log_returns))
    scaler_ = MinMaxScaler()
    prices_norm = scaler_.fit_transform(prices.reshape(-1, 1)).ravel().astype(np.float32)

    X_list, y_list = [], []
    for i in range(len(prices_norm) - req.seq_len - req.pred_steps):
        X_list.append(prices_norm[i : i + req.seq_len])
        y_list.append(prices_norm[i + req.seq_len : i + req.seq_len + req.pred_steps])
    X_all = np.array(X_list, dtype=np.float32)
    y_all = np.array(y_list, dtype=np.float32)

    split = int(len(X_all) * 0.8)
    Xtr = torch.tensor(X_all[:split]).unsqueeze(-1)
    Xte = torch.tensor(X_all[split:]).unsqueeze(-1)
    ytr = torch.tensor(y_all[:split])
    yte = torch.tensor(y_all[split:])

    class _PE(nn.Module):
        def __init__(self, d: int, max_len: int = 200) -> None:
            super().__init__()
            pe = torch.zeros(max_len, d)
            pos = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
            div = torch.exp(torch.arange(0, d, 2, dtype=torch.float) * (-math.log(10000.0) / d))
            pe[:, 0::2] = torch.sin(pos * div)
            pe[:, 1::2] = torch.cos(pos * div)
            self.register_buffer("pe", pe.unsqueeze(0))
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return x + self.pe[:, : x.size(1), :]

    class _TransformerModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.proj = nn.Linear(1, req.d_model)
            self.pe = _PE(req.d_model)
            nhead = max(1, req.d_model // 8)
            enc_layer = nn.TransformerEncoderLayer(
                d_model=req.d_model, nhead=nhead,
                dim_feedforward=req.d_model * 4, dropout=0.1, batch_first=True,
            )
            self.enc = nn.TransformerEncoder(enc_layer, num_layers=2)
            self.head = nn.Linear(req.d_model, req.pred_steps)
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = self.pe(self.proj(x))
            return self.head(self.enc(x)[:, -1, :])

    torch.manual_seed(SEED)
    model = _TransformerModel()
    opt = torch.optim.AdamW(model.parameters(), lr=5e-4)
    crit = nn.MSELoss()
    ds = torch.utils.data.TensorDataset(Xtr, ytr)
    dl = torch.utils.data.DataLoader(ds, batch_size=64, shuffle=True)
    val_losses = []

    for _ in range(req.epochs):
        model.train()
        for xb, yb in dl:
            opt.zero_grad()
            loss = crit(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        model.eval()
        with torch.no_grad():
            vl = crit(model(Xte), yte).item()
        val_losses.append(float(vl))

    model.eval()
    with torch.no_grad():
        y_pred = model(Xte).numpy()

    y_pred_orig = scaler_.inverse_transform(y_pred[:, 0].reshape(-1, 1)).ravel()
    y_true_orig = scaler_.inverse_transform(yte[:, 0].numpy().reshape(-1, 1)).ravel()
    last_input = scaler_.inverse_transform(X_all[split:, -1].reshape(-1, 1)).ravel()
    dir_acc = float(np.mean(np.sign(y_pred_orig - last_input) == np.sign(y_true_orig - last_input)))

    return {
        "direction_accuracy_step1": dir_acc,
        "val_loss_final": val_losses[-1],
        "val_loss_history": [round(v, 6) for v in val_losses],
    }


# ─── Quant Strategy Models ────────────────────────────────────────────────────

