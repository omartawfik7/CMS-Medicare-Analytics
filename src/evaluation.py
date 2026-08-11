"""Metric computation for Model 1 (regression) and Model 2 (classification).
Kept separate from modeling.py so the training loop and the scoring logic
can be tested/reasoned about independently."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    precision_score, recall_score, f1_score, roc_auc_score,
    average_precision_score, confusion_matrix,
)


def regression_metrics(y_true, y_pred) -> dict:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def classification_metrics(y_true, y_pred, y_proba) -> dict:
    cm = confusion_matrix(y_true, y_pred).tolist()
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_proba)),
        "pr_auc": float(average_precision_score(y_true, y_proba)),
        "confusion_matrix": {"labels": ["not_high_cost", "high_cost"], "matrix": cm},
    }
