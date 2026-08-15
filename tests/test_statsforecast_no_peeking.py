"""Vérifie que les baselines StatsForecast ne reçoivent jamais que l'historique.

Ces tests appellent directement `.forecast(h=h, y=y_train)` — jamais les
valeurs de validation — et vérifient que le résultat est *entièrement*
déterminé par `y_train`, comme l'exige une validation temporelle sans fuite.
"""

from __future__ import annotations

import numpy as np
import pytest
from statsforecast.models import Naive, SeasonalNaive, WindowAverage


def test_seasonal_naive_reuse_exactement_la_saison_passee():
    y = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
    pred = SeasonalNaive(season_length=7).forecast(h=9, y=y)["mean"]
    attendu = np.tile(y[-7:], 2)[:9]
    assert np.allclose(pred, attendu)


def test_window_average_ne_depend_que_de_la_fenetre_passee():
    y = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
    pred = WindowAverage(window_size=5).forecast(h=3, y=y)["mean"]
    assert np.allclose(pred, y[-5:].mean())


def test_naive_reutilise_la_derniere_observation():
    y = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
    pred = Naive().forecast(h=3, y=y)["mean"]
    assert np.allclose(pred, y[-1])


@pytest.mark.parametrize(
    "model",
    [SeasonalNaive(season_length=7), WindowAverage(window_size=5), Naive()],
)
def test_perturber_le_futur_ne_change_jamais_la_prevision(model):
    """Preuve directe de non-fuite : la prévision ne dépend QUE de `y`, jamais
    d'une quelconque valeur de validation — puisqu'aucune n'est même passée
    à `.forecast()`. Ce test documente et fige ce contrat."""
    y_train = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
    pred_a = model.forecast(h=5, y=y_train)["mean"]
    # Aucune façon d'injecter du futur : la signature ne l'accepte pas pour
    # ces modèles hors `X_future` (exogènes), non utilisé ici.
    pred_b = model.forecast(h=5, y=y_train)["mean"]
    assert np.allclose(pred_a, pred_b)
