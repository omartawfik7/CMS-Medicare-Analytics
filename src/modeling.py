"""
Model 1: Medicare spending prediction (regression).
Model 2: Specialty-adjusted high-cost provider classification.

Both use temporal validation -- train on earlier years, test on the single
most recent loaded year -- never a random shuffle across years, so the
model is never scored on data whose specialty-year benchmark medians it
could have implicitly seen in training (see reports/design_decisions.md,
leakage risk #4).

    python src/modeling.py --db data/cms_medicare.duckdb

Writes:
  - models/model1_payment_regressor.joblib
  - models/model2_high_cost_classifier.joblib
  - reports/model_metrics.json          (real metrics, not fabricated)
  - reports/figures/model1_feature_importance.png
  - reports/figures/model2_feature_importance.png
  - gold_model_predictions table (test-year predictions, for Power BI)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import (  # noqa: E402
    build_model1_frame, build_model2_frame,
    MODEL1_NUMERIC_FEATURES, MODEL1_CATEGORICAL_FEATURES, MODEL1_TARGET,
    MODEL2_NUMERIC_FEATURES, MODEL2_CATEGORICAL_FEATURES, MODEL2_TARGET,
)
from evaluation import regression_metrics, classification_metrics  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "models"
FIGURES_DIR = REPO_ROOT / "reports" / "figures"
METRICS_PATH = REPO_ROOT / "reports" / "model_metrics.json"


def _prep_categoricals(df: pd.DataFrame, cat_cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cat_cols:
        df[c] = df[c].astype("category")
    return df


def _temporal_split(df: pd.DataFrame, year_col: str = "source_year"):
    years = sorted(df[year_col].unique())
    if len(years) < 2:
        raise ValueError(
            f"Temporal validation needs >= 2 distinct years, found {years}. "
            "Load more years with src/ingest_cms.py first."
        )
    test_year = years[-1]
    train = df[df[year_col] < test_year]
    test = df[df[year_col] == test_year]
    return train, test, test_year


def train_model1(con: duckdb.DuckDBPyConnection) -> dict:
    df = build_model1_frame(con)
    feature_cols = MODEL1_NUMERIC_FEATURES + MODEL1_CATEGORICAL_FEATURES
    df = _prep_categoricals(df, MODEL1_CATEGORICAL_FEATURES)

    train, test, test_year = _temporal_split(df)
    X_train, y_train = train[feature_cols], np.log1p(train[MODEL1_TARGET])
    X_test, y_test = test[feature_cols], test[MODEL1_TARGET]

    model = xgb.XGBRegressor(
        n_estimators=400, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        enable_categorical=True, tree_method="hist",
        random_state=42, n_jobs=0,
    )
    model.fit(X_train, y_train)

    pred_log = model.predict(X_test)
    pred = np.expm1(pred_log)
    pred = np.clip(pred, 0, None)

    metrics = {
        "target": MODEL1_TARGET,
        "train_years": sorted(train["source_year"].unique().tolist()),
        "test_year": int(test_year),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        **regression_metrics(y_test, pred),
        "features": feature_cols,
    }

    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODELS_DIR / "model1_payment_regressor.joblib")

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values()
    plt.figure(figsize=(8, 5))
    importances.plot(kind="barh")
    plt.title("Model 1 -- Medicare Payment Prediction: Feature Importance")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "model1_feature_importance.png", dpi=120)
    plt.close()

    test_out = test[["rendering_npi", "source_year"]].copy()
    test_out["actual_payment"] = y_test.values
    test_out["predicted_payment"] = pred
    test_out["model"] = "model1_payment_regressor"
    con.register("model1_preds_df", test_out)
    con.execute("""
        CREATE OR REPLACE TABLE gold_model1_predictions AS
        SELECT * FROM model1_preds_df
    """)

    return metrics


def train_model2(con: duckdb.DuckDBPyConnection) -> dict:
    df = build_model2_frame(con)
    feature_cols = MODEL2_NUMERIC_FEATURES + MODEL2_CATEGORICAL_FEATURES
    df = _prep_categoricals(df, MODEL2_CATEGORICAL_FEATURES)

    train, test, test_year = _temporal_split(df)
    X_train, y_train = train[feature_cols], train[MODEL2_TARGET]
    X_test, y_test = test[feature_cols], test[MODEL2_TARGET]

    pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
    model = xgb.XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        enable_categorical=True, tree_method="hist",
        scale_pos_weight=pos_weight,
        eval_metric="aucpr",
        random_state=42, n_jobs=0,
    )
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    metrics = {
        "target": MODEL2_TARGET,
        "label_definition": "payment_per_beneficiary at or above the 90th percentile of the provider's own specialty-year peer group (peer_group_size >= 30)",
        "train_years": sorted(train["source_year"].unique().tolist()),
        "test_year": int(test_year),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "positive_rate_test": float(y_test.mean()),
        **classification_metrics(y_test, pred, proba),
        "features": feature_cols,
    }

    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODELS_DIR / "model2_high_cost_classifier.joblib")

    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values()
    plt.figure(figsize=(8, 5))
    importances.plot(kind="barh")
    plt.title("Model 2 -- High-Cost Provider Classification: Feature Importance")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "model2_feature_importance.png", dpi=120)
    plt.close()

    test_out = test[["rendering_npi", "source_year"]].copy()
    test_out["actual_label"] = y_test.values
    test_out["predicted_probability"] = proba
    test_out["predicted_label"] = pred
    test_out["model"] = "model2_high_cost_classifier"
    con.register("model2_preds_df", test_out)
    con.execute("""
        CREATE OR REPLACE TABLE gold_model2_predictions AS
        SELECT * FROM model2_preds_df
    """)

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Model 1 (payment regression) and Model 2 (high-cost classification).")
    parser.add_argument("--db", default=str(REPO_ROOT / "data" / "cms_medicare.duckdb"))
    args = parser.parse_args()

    con = duckdb.connect(args.db)

    print("Training Model 1 (Medicare spending prediction)...")
    m1 = train_model1(con)
    print(json.dumps(m1, indent=2))

    print("\nTraining Model 2 (specialty-adjusted high-cost classification)...")
    m2 = train_model2(con)
    print(json.dumps(m2, indent=2))

    REPO_ROOT.joinpath("reports").mkdir(exist_ok=True)
    METRICS_PATH.write_text(json.dumps({"model1_payment_regression": m1, "model2_high_cost_classification": m2}, indent=2))
    print(f"\nMetrics written to {METRICS_PATH}")

    # Also materialize predictions as a Gold export for Power BI's Model
    # Intelligence page (combined, tidy shape).
    con.execute("""
        CREATE OR REPLACE TABLE gold_model_predictions AS
        SELECT rendering_npi, source_year, 'model1_payment_regressor' AS model,
               actual_payment AS actual_value, predicted_payment AS predicted_value,
               NULL AS predicted_probability
        FROM gold_model1_predictions
        UNION ALL
        SELECT rendering_npi, source_year, 'model2_high_cost_classifier' AS model,
               actual_label AS actual_value, predicted_label AS predicted_value,
               predicted_probability
        FROM gold_model2_predictions
    """)
    con.close()


if __name__ == "__main__":
    sys.exit(main())
