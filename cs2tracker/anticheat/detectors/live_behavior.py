"""Détecteurs temps réel, alimentés par le Game State Integration.

Portée et limites — à garder en tête :
  - le GSI ne fournit ni les angles de visée ni la trajectoire du réticule :
    aucune détection d'aimbot « à la trame » n'est possible ici ;
  - il fournit en revanche le rythme, la régularité et l'efficacité, qui sont
    justement ce qu'un logiciel de triche altère de façon mesurable ;
  - les données ``allplayers`` ne sont transmises qu'en spectateur / GOTV.
"""

from __future__ import annotations

from cs2tracker.anticheat import baselines
from cs2tracker.anticheat.detectors.common import build_signal, pct
from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal, SignalCategory, neutral_signal
from cs2tracker.anticheat.weights import EngineConfig
from cs2tracker.core.utils import sample_confidence

CATEGORY = SignalCategory.LIVE

#: Manches nécessaires pour que les métriques live pèsent dans le verdict.
_FULL_CONFIDENCE_ROUNDS = 30
_MIN_ROUNDS = 5
#: Intervalles entre kills nécessaires pour juger du rythme.
_MIN_INTERVALS = 8


def detect(features: PlayerFeatures, config: EngineConfig) -> tuple[Signal, ...]:
    if not features.has_live or features.live_rounds < _MIN_ROUNDS:
        return (
            neutral_signal(
                "live.headshot_rate",
                "Analyse temps reel",
                CATEGORY,
                (
                    f"Seulement {features.live_rounds} manche(s) observee(s) en direct "
                    f"({_MIN_ROUNDS} minimum requis)."
                ),
            ),
        )

    round_confidence = sample_confidence(
        features.live_rounds, _FULL_CONFIDENCE_ROUNDS, _MIN_ROUNDS
    )
    return (
        _headshot_rate(features, config, round_confidence),
        _adr(features, config, round_confidence),
        _multi_kills(features, config, round_confidence),
        _kill_rhythm(features, config),
        _fast_chains(features, config),
        _utility(features, config, round_confidence),
        _survival(features, config, round_confidence),
    )


def _headshot_rate(
    features: PlayerFeatures, config: EngineConfig, confidence: float
) -> Signal:
    return build_signal(
        key="live.headshot_rate",
        label="Taux de HS observe en direct",
        category=CATEGORY,
        baseline=baselines.LIVE_HEADSHOT_RATE,
        observed=features.live_headshot_rate,
        confidence=confidence,
        sample_size=features.live_rounds,
        config=config,
        explanation_high=(
            f"{pct(features.live_headshot_rate)} de headshots sur les "
            f"{features.live_rounds} manches suivies, contre "
            f"{pct(baselines.LIVE_HEADSHOT_RATE.mean)} attendus."
        ),
        explanation_normal=(
            f"{pct(features.live_headshot_rate)} de headshots en direct — normal."
        ),
    )


def _adr(features: PlayerFeatures, config: EngineConfig, confidence: float) -> Signal:
    return build_signal(
        key="live.adr",
        label="Degats moyens par manche",
        category=CATEGORY,
        baseline=baselines.LIVE_ADR,
        observed=features.live_adr,
        confidence=confidence,
        sample_size=features.live_rounds,
        config=config,
        explanation_high=(
            f"{features.live_adr:.0f} degats par manche contre "
            f"{baselines.LIVE_ADR.mean:.0f} en moyenne : impact tres au-dessus du lot."
        ),
        explanation_normal=f"{features.live_adr:.0f} degats par manche — dans la norme.",
    )


def _multi_kills(
    features: PlayerFeatures, config: EngineConfig, confidence: float
) -> Signal:
    return build_signal(
        key="live.multi_kills",
        label="Frequence des multi-kills",
        category=CATEGORY,
        baseline=baselines.MULTI_KILL_RATE,
        observed=features.live_multi_kill_rate,
        confidence=confidence,
        sample_size=features.live_rounds,
        config=config,
        explanation_high=(
            f"{pct(features.live_multi_kill_rate)} des manches se soldent par 3 kills ou "
            f"plus (reference {pct(baselines.MULTI_KILL_RATE.mean)}) : les situations "
            "d'inferiorite numerique sont converties bien trop souvent."
        ),
        explanation_normal=(
            f"{pct(features.live_multi_kill_rate)} de manches a 3+ kills — habituel."
        ),
    )


def _kill_rhythm(features: PlayerFeatures, config: EngineConfig) -> Signal:
    """Régularité du délai entre deux éliminations.

    Un humain alterne duels instantanés et affrontements longs. Une dispersion
    quasi nulle évoque un déclenchement automatisé.
    """
    if features.live_kill_intervals < _MIN_INTERVALS:
        return neutral_signal(
            "live.kill_rhythm",
            "Regularite du rythme d'elimination",
            CATEGORY,
            f"Seulement {features.live_kill_intervals} intervalle(s) mesure(s).",
            weight=config.weight_of("live.kill_rhythm"),
        )
    return build_signal(
        key="live.kill_rhythm",
        label="Regularite du rythme d'elimination",
        category=CATEGORY,
        baseline=baselines.KILL_INTERVAL_STDEV,
        observed=features.live_kill_interval_stdev,
        confidence=sample_confidence(features.live_kill_intervals, 60, _MIN_INTERVALS),
        sample_size=features.live_kill_intervals,
        config=config,
        inverted=True,
        explanation_high=(
            f"Les delais entre eliminations varient de seulement "
            f"{features.live_kill_interval_stdev:.1f} s (reference "
            f"{baselines.KILL_INTERVAL_STDEV.mean:.1f} s). Une cadence aussi metronomique "
            "est difficile a produire manuellement."
        ),
        explanation_normal=(
            f"Delais entre eliminations disperses de "
            f"{features.live_kill_interval_stdev:.1f} s — variabilite humaine normale."
        ),
    )


def _fast_chains(features: PlayerFeatures, config: EngineConfig) -> Signal:
    if features.live_kill_intervals < _MIN_INTERVALS:
        return neutral_signal(
            "live.fast_chains",
            "Enchainements ultra-rapides",
            CATEGORY,
            "Echantillon d'intervalles insuffisant.",
            weight=config.weight_of("live.fast_chains"),
        )
    return build_signal(
        key="live.fast_chains",
        label="Enchainements ultra-rapides",
        category=CATEGORY,
        baseline=baselines.FAST_CHAIN_RATE,
        observed=features.live_fast_chain_rate,
        confidence=sample_confidence(features.live_kill_intervals, 60, _MIN_INTERVALS),
        sample_size=features.live_kill_intervals,
        config=config,
        explanation_high=(
            f"{pct(features.live_fast_chain_rate)} des eliminations s'enchainent en moins "
            "de 1,2 s. Basculer d'une cible a l'autre aussi vite, de facon repetee, "
            "suppose une acquisition de cible assistee."
        ),
        explanation_normal=(
            f"{pct(features.live_fast_chain_rate)} d'enchainements rapides — plausible."
        ),
    )


def _utility(
    features: PlayerFeatures, config: EngineConfig, confidence: float
) -> Signal:
    return build_signal(
        key="live.utility_neglect",
        label="Usage des utilitaires",
        category=CATEGORY,
        baseline=baselines.UTILITY_PER_ROUND,
        observed=features.live_utility_per_round,
        confidence=confidence * 0.7,
        sample_size=features.live_rounds,
        config=config,
        inverted=True,
        explanation_high=(
            f"{features.live_utility_per_round:.1f} utilitaire(s) par manche contre "
            f"{baselines.UTILITY_PER_ROUND.mean:.1f} attendus. Un joueur qui gagne ses "
            "duels sans avoir besoin d'information ni de couverture s'appuie rarement "
            "sur le jeu d'equipe."
        ),
        explanation_normal=(
            f"{features.live_utility_per_round:.1f} utilitaire(s) par manche — "
            "usage normal."
        ),
    )


def _survival(
    features: PlayerFeatures, config: EngineConfig, confidence: float
) -> Signal:
    return build_signal(
        key="live.survival",
        label="Taux de survie",
        category=CATEGORY,
        baseline=baselines.SURVIVAL_RATE,
        observed=features.live_survival_rate,
        confidence=confidence,
        sample_size=features.live_rounds,
        config=config,
        explanation_high=(
            f"{pct(features.live_survival_rate)} de manches terminees en vie "
            f"(reference {pct(baselines.SURVIVAL_RATE.mean)}) : anticipation des "
            "dangers tres au-dessus de la moyenne."
        ),
        explanation_normal=f"{pct(features.live_survival_rate)} de survie — normal.",
    )
