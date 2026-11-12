"""Independent evaluation script for the trained Varsity Chaka ETA model."""
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ML_DIR = Path(__file__).resolve().parent
DATA_PATH = ML_DIR / "data" / "synthetic_trips.csv"
MODEL_PATH = ML_DIR / "models" / "eta_rf_model.joblib"


def run_evaluation():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Run train_eta.py first.")

    bundle = joblib.load(MODEL_PATH)
    rf = bundle["model"]
    features = bundle["features"]

    df = pd.read_csv(DATA_PATH)
    X = df[features]
    y = df["actual_duration_s"]

    # Global metrics on full dataset
    preds = rf.predict(X)
    mae = mean_absolute_error(y, preds)
    rmse = np.sqrt(mean_squared_error(y, preds))
    r2 = r2_score(y, preds)

    print("--- Model Metadata ---")
    print("Version:", bundle.get("version"))
    print("Trained At:", bundle.get("trained_at"))
    print("Data Nature:", bundle.get("data_nature"))
    print("Reported Test MAE (s):", bundle.get("metrics", {}).get("test_mae_s"))
    print("Reported Test R²:", bundle.get("metrics", {}).get("test_r2"))
    print("Feature Importances:")
    for f, imp in bundle.get("feature_importances", {}).items():
        print(f"  - {f}: {imp:.4f}")

    # Sub-slice analysis: Peak vs Off-peak
    peak_idx = df["is_peak_hour"] == 1
    mae_peak = mean_absolute_error(y[peak_idx], preds[peak_idx])
    mae_offpeak = mean_absolute_error(y[~peak_idx], preds[~peak_idx])

    print("\n--- Sliced Performance ---")
    print(f"Peak Hours MAE: {mae_peak:.2f} s ({mae_peak/60.0:.2f} min)")
    print(f"Off-Peak Hours MAE: {mae_offpeak:.2f} s ({mae_offpeak/60.0:.2f} min)")

    return {
        "global_mae": mae,
        "global_rmse": rmse,
        "global_r2": r2,
        "peak_mae": mae_peak,
        "offpeak_mae": mae_offpeak,
    }


if __name__ == "__main__":
    run_evaluation()
