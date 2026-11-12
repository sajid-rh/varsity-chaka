"""Training pipeline for the Varsity Chaka ETA Random Forest model.

Trains a Random Forest Regressor on synthetic travel data to predict actual motorcycle
travel duration and tree-level prediction spread based on OSRM base metrics, distance, and temporal features.
"""
from datetime import datetime, timezone
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from ml.data.generate_synthetic_trips import generate_synthetic_dataset

ML_DIR = Path(__file__).resolve().parent
DATA_PATH = ML_DIR / "data" / "synthetic_trips.csv"
MODEL_DIR = ML_DIR / "models"
MODEL_PATH = MODEL_DIR / "eta_rf_model.joblib"

FEATURE_COLUMNS = [
    "distance_km",
    "osrm_duration_s",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_peak_hour",
]
TARGET_COLUMN = "actual_duration_s"


def train_eta_model(csv_path: Path = DATA_PATH, save_path: Path = MODEL_PATH) -> dict:
    """Train and evaluate the Random Forest ETA model."""
    # 1. Load or generate dataset
    if not csv_path.exists():
        print(f"Dataset not found at {csv_path}. Generating synthetic dataset...")
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df = generate_synthetic_dataset(num_samples=5000, random_seed=42)
        df.to_csv(csv_path, index=False)
    else:
        df = pd.read_csv(csv_path)

    # 2. Prepare X and y
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]

    # 3. Train-test split (80/20) strictly separated
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )

    # 4. Fit Random Forest Regressor
    rf = RandomForestRegressor(
        n_estimators=100,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)

    # 5. Evaluate strictly on held-out test set
    y_pred = rf.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    print("================ ETA Model Evaluation (Test Set) ================")
    print(f"Test Records: {len(y_test)}")
    print(f"Mean Absolute Error (MAE): {mae:.2f} seconds ({mae/60.0:.2f} minutes)")
    print(f"Root Mean Squared Error (RMSE): {rmse:.2f} seconds ({rmse/60.0:.2f} minutes)")
    print(f"R² Score: {r2:.4f}")
    print("==================================================================")

    # Feature importances
    importances = dict(zip(FEATURE_COLUMNS, [round(float(v), 4) for v in rf.feature_importances_]))
    print("Feature Importances:", importances)

    # 6. Save model bundle
    save_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": rf,
        "features": FEATURE_COLUMNS,
        "version": "1.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "test_mae_s": round(float(mae), 2),
            "test_rmse_s": round(float(rmse), 2),
            "test_r2": round(float(r2), 4),
            "n_samples": len(df),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
        },
        "feature_importances": importances,
        "data_nature": "synthetic",
    }
    joblib.dump(bundle, save_path)
    print(f"Model bundle saved -> {save_path}")

    return bundle


if __name__ == "__main__":
    train_eta_model()
