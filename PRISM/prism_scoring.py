from __future__ import annotations

from typing import Any, Iterable


def _to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _normalize_text(s: str) -> str:
    return " ".join((s or "").replace("\n", " ").replace("\r", " ").split()).strip()


def _word_count(s: str) -> int:
    s = _normalize_text(s)
    if not s:
        return 0
    parts = [p for p in s.replace(",", " ").split(" ") if p.strip()]
    return len([p for p in parts if any(ch.isalnum() for ch in p)])


def _clamp_0_100(n: float) -> int:
    if n < 0:
        return 0
    if n > 100:
        return 100
    return int(round(n))


def _has_any_keyword(s: str, keywords: Iterable[str]) -> bool:
    s_norm = _normalize_text(s).lower()
    return any(k.lower() in s_norm for k in keywords)


def score_novelty(*, product_concept: str = "", comparable_products: list[str] | None = None, **kwargs: Any) -> int:
    product_concept = _normalize_text(_to_str(product_concept)).lower()
    comparable_products = comparable_products or []
    comparable_products = [str(x).strip() for x in comparable_products if str(x).strip()]

    wc = _word_count(product_concept)
    base = 35
    # Longer concepts tend to contain more differentiation structure.
    base += min(40, wc * 3.0)

    # More comparables implies a crowded market and reduces "assumed" differentiation.
    if comparable_products:
        base -= min(25, len(comparable_products) * 5.0)
    else:
        # No comparables means differentiation can't be validated.
        base -= 5

    # Differentiation cues.
    diff_cues = ["unique", "distinct", "bespoke", "radically", "new", "unlike", "breakthrough", "studio", "system"]
    if _has_any_keyword(product_concept, diff_cues):
        base += 12

    return _clamp_0_100(base)


def score_clarity(
    *,
    product_concept: str = "",
    problem_solved: str = "",
    target_audience: str = "",
    feature_list: list[str] | None = None,
    **kwargs: Any,
) -> int:
    product_concept = _normalize_text(_to_str(product_concept))
    problem_solved = _normalize_text(_to_str(problem_solved))
    target_audience = _normalize_text(_to_str(target_audience))
    feature_list = feature_list or []
    feature_list = [str(x).strip() for x in feature_list if str(x).strip()]

    base = 10
    base += min(30, _word_count(product_concept) * 2.5)
    base += min(35, _word_count(problem_solved) * 2.5)
    if target_audience:
        base += 25
    if feature_list:
        base += min(25, len(feature_list) * 6.0)

    # Clarity is hurt by vague "solution without problem".
    if not problem_solved and product_concept:
        base -= 20

    return _clamp_0_100(base)


def score_emotional_pull(*, problem_solved: str = "", launch_angle: str = "", notes: str = "", **kwargs: Any) -> int:
    text = " ".join([_normalize_text(_to_str(problem_solved)), _normalize_text(_to_str(launch_angle)), _normalize_text(_to_str(notes))])
    text_l = text.lower()

    base = 25
    wc = _word_count(text)
    base += min(30, wc * 1.5)

    urgency = ["urgent", "fast", "immediately", "stop", "today", "friction", "confusing", "overwhelmed", "waste", "pain", "hard", "stuck"]
    if _has_any_keyword(text_l, urgency):
        base += 25

    desire = ["better", "simpler", "easier", "delight", "joy", "win", "confident", "control", "freedom"]
    if _has_any_keyword(text_l, desire):
        base += 15

    return _clamp_0_100(base)


def score_curiosity(*, product_concept: str = "", launch_angle: str = "", notes: str = "", **kwargs: Any) -> int:
    text = " ".join([_normalize_text(_to_str(product_concept)), _normalize_text(_to_str(launch_angle)), _normalize_text(_to_str(notes))]).lower()
    base = 20
    wc = _word_count(text)
    base += min(25, wc * 1.2)

    intrigue = ["secret", "why", "how", "unlocks", "reveals", "proves", "breakdown", "explained", "mystery", "master"]
    if _has_any_keyword(text, intrigue):
        base += 30

    # Strong curiosity also needs some clarity; avoid over-scoring empty copy.
    if wc < 8:
        base -= 10

    return _clamp_0_100(base)


def score_virality(*, clarity: int = 0, curiosity: int = 0, target_audience: str = "", **kwargs: Any) -> int:
    target_audience = _normalize_text(_to_str(target_audience)).lower()
    base = 10
    base += clarity * 0.25
    base += curiosity * 0.35

    share_cues = ["community", "share", "template", "open", "public", "collaborate", "team", "group"]
    if _has_any_keyword(target_audience, share_cues):
        base += 18

    # Cap.
    return _clamp_0_100(base)


def score_monetization(
    *,
    monetization_model: str = "",
    product_concept: str = "",
    problem_solved: str = "",
    **kwargs: Any,
) -> int:
    monetization_model = _normalize_text(_to_str(monetization_model)).lower()
    product_concept = _normalize_text(_to_str(product_concept)).lower()
    problem_solved = _normalize_text(_to_str(problem_solved)).lower()

    base = 15
    if monetization_model:
        base += 35
        # More specific models tend to be more coherent for launch planning.
        model_bonus = 0
        for k in ["subscription", "monthly", "annual", "tier", "seat", "usage", "metered", "license", "freemium", "one-time", "pay"]:
            if k in monetization_model:
                model_bonus += 8
        base += min(30, model_bonus)
    else:
        base -= 10

    # Value alignment cues.
    value_cues = ["roi", "saves", "reduce", "cost", "time", "faster", "productivity", "revenue", "profit", "manage"]
    if _has_any_keyword(" ".join([product_concept, problem_solved]), value_cues):
        base += 18

    return _clamp_0_100(base)


def score_success_estimate(
    *,
    novelty: int = 0,
    clarity: int = 0,
    emotional_pull: int = 0,
    curiosity: int = 0,
    virality_potential: int = 0,
    monetization_potential: int = 0,
    friction_points: list[str] | None = None,
    prism_status: str = "insufficient_input",
    **kwargs: Any,
) -> int:
    friction_points = friction_points or []

    base = (
        0.15 * novelty
        + 0.25 * clarity
        + 0.10 * emotional_pull
        + 0.10 * curiosity
        + 0.15 * virality_potential
        + 0.15 * monetization_potential
    )

    # Penalize missing clarity and friction.
    if clarity < 50:
        base -= 15
    base -= min(25, max(0, len(friction_points) - 1) * 6)

    # Insufficient input reduces "confidence" in success estimate.
    if prism_status != "evaluated":
        base -= 20

    return _clamp_0_100(base)

