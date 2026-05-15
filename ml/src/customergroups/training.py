"""Training pipeline: LR baseline + XGBoost, with stratified CV and business metric."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from .columns import TARGET
from .features import FeatureBuilder, swap_augment

log = logging.getLogger(__name__)

RANDOM_STATE = 42


def campaign_success_rate(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Business metric: fraction of campaigns where the model's pick is right.

    Definition:
      - true class 0 (neither profitable) -> any prediction is a miss
      - true class 1 -> only correct if predicted 1
      - true class 2 -> only correct if predicted 2
    Equivalent to accuracy under that interpretation.
    """
    correct = (y_true != 0) & (y_pred == y_true)
    return float(correct.sum() / len(y_true))


def baseline_always_group1(y_true: np.ndarray) -> float:
    """Baseline strategy: always pick group 1."""
    pred = np.ones_like(y_true)
    return campaign_success_rate(y_true, pred)


@dataclass
class ModelResult:
    name: str
    cv_accuracy_mean: float
    cv_accuracy_std: float
    cv_macro_f1_mean: float
    cv_macro_f1_std: float
    test_accuracy: float
    test_macro_f1: float
    test_success_rate: float
    confusion: list[list[int]]
    classification_report: dict[str, Any]
    feature_importance: dict[str, float] | None = field(default=None)


class Trainer:
    def __init__(self, feature_builder: FeatureBuilder, augment: bool = True) -> None:
        self.feature_builder = feature_builder
        self.augment = augment

    def prepare_splits(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """Stratified train/test, then optionally swap-augment the training half only."""
        train_df, test_df = train_test_split(
            df, test_size=0.2, stratify=df[TARGET], random_state=RANDOM_STATE
        )
        if self.augment:
            train_df = swap_augment(train_df)

        # Feature build (drops post-campaign cols implicitly via FeatureBuilder schema)
        # but first remove post-campaign cols so FeatureBuilder accepts the frame.
        from .columns import POST_CAMPAIGN
        train_X = self.feature_builder.transform(train_df.drop(columns=POST_CAMPAIGN, errors="ignore"))
        test_X = self.feature_builder.transform(test_df.drop(columns=POST_CAMPAIGN, errors="ignore"))
        train_y = train_df[TARGET].reset_index(drop=True)
        test_y = test_df[TARGET].reset_index(drop=True)
        return train_X, test_X, train_y, test_y

    def cv_score(self, model: Any, X: pd.DataFrame, y: pd.Series) -> tuple[float, float, float, float]:
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        accs, f1s = [], []
        for fold, (tr, va) in enumerate(skf.split(X, y), 1):
            model.fit(X.iloc[tr], y.iloc[tr])
            pred = model.predict(X.iloc[va])
            accs.append(accuracy_score(y.iloc[va], pred))
            f1s.append(f1_score(y.iloc[va], pred, average="macro"))
            log.info("  fold %d: acc=%.4f, f1=%.4f", fold, accs[-1], f1s[-1])
        return float(np.mean(accs)), float(np.std(accs)), float(np.mean(f1s)), float(np.std(f1s))

    def evaluate(self, model: Any, X_test: pd.DataFrame, y_test: pd.Series) -> tuple[float, float, float, list[list[int]], dict[str, Any]]:
        pred = model.predict(X_test)
        acc = accuracy_score(y_test, pred)
        f1m = f1_score(y_test, pred, average="macro")
        sr = campaign_success_rate(y_test.values, pred)
        cm = confusion_matrix(y_test, pred).tolist()
        report = classification_report(y_test, pred, output_dict=True, zero_division=0)
        return acc, f1m, sr, cm, report

    def train_lr(self, X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame, y_test: pd.Series) -> tuple[ModelResult, Pipeline]:
        log.info("=== Logistic Regression ===")
        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, multi_class="multinomial", random_state=RANDOM_STATE)),
        ])
        cv_acc_m, cv_acc_s, cv_f1_m, cv_f1_s = self.cv_score(pipe, X_train, y_train)
        pipe.fit(X_train, y_train)
        acc, f1m, sr, cm, rep = self.evaluate(pipe, X_test, y_test)
        # coef-based importance for LR
        coef = pipe.named_steps["clf"].coef_
        importance = np.abs(coef).mean(axis=0)
        imp_dict = dict(zip(X_train.columns, importance.tolist()))
        return (
            ModelResult(
                name="logistic_regression",
                cv_accuracy_mean=cv_acc_m,
                cv_accuracy_std=cv_acc_s,
                cv_macro_f1_mean=cv_f1_m,
                cv_macro_f1_std=cv_f1_s,
                test_accuracy=acc,
                test_macro_f1=f1m,
                test_success_rate=sr,
                confusion=cm,
                classification_report=rep,
                feature_importance=imp_dict,
            ),
            pipe,
        )

    def train_xgb(self, X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame, y_test: pd.Series) -> tuple[ModelResult, XGBClassifier]:
        log.info("=== XGBoost ===")
        model = XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            n_estimators=400,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            tree_method="hist",
        )
        cv_acc_m, cv_acc_s, cv_f1_m, cv_f1_s = self.cv_score(model, X_train, y_train)
        model.fit(X_train, y_train)
        acc, f1m, sr, cm, rep = self.evaluate(model, X_test, y_test)
        imp_dict = dict(zip(X_train.columns, model.feature_importances_.tolist()))
        return (
            ModelResult(
                name="xgboost",
                cv_accuracy_mean=cv_acc_m,
                cv_accuracy_std=cv_acc_s,
                cv_macro_f1_mean=cv_f1_m,
                cv_macro_f1_std=cv_f1_s,
                test_accuracy=acc,
                test_macro_f1=f1m,
                test_success_rate=sr,
                confusion=cm,
                classification_report=rep,
                feature_importance=imp_dict,
            ),
            model,
        )
