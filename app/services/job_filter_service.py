"""
app/services/job_filter_service.py
──────────────────────────────────
Pure-function predicate filters for job applicant matching and candidate evaluation.
Decoupled from Playwright DOM automation to enable fast, headless unit testing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_TR_MAP = str.maketrans(
    {
        "I": "i",
        "İ": "i",
        "ı": "i",
        "Ş": "s",
        "ş": "s",
        "Ğ": "g",
        "ğ": "g",
        "Ü": "u",
        "ü": "u",
        "Ö": "o",
        "ö": "o",
        "Ç": "c",
        "ç": "c",
    }
)

LANGUAGE_LEVEL_RANKS: Dict[str, int] = {
    "baslangic": 1,
    "temel": 2,
    "orta": 3,
    "iyi": 4,
    "ileri": 5,
    "anadil": 6,
}


def normalize_turkish_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\u0307", "").translate(_TR_MAP).lower().split())


def matches_age_criteria(
    candidate_age: Optional[int], min_age: int = 16, max_age: int = 65
) -> bool:
    if candidate_age is None:
        return True
    return min_age <= candidate_age <= max_age


def matches_gender_criteria(
    candidate_gender: Optional[str], allow_male: bool, allow_female: bool
) -> bool:
    if not allow_male and not allow_female:
        return True
    if not candidate_gender:
        return True

    norm = normalize_turkish_text(candidate_gender)
    if allow_male and "erkek" in norm:
        return True
    if allow_female and ("kadin" in norm or "bayan" in norm):
        return True
    return False


def matches_military_status(
    candidate_status: Optional[str], allowed_statuses: List[str]
) -> bool:
    if (
        not allowed_statuses
        or "Farketmez" in allowed_statuses
        or "farketmez" in [s.lower() for s in allowed_statuses]
    ):
        return True
    if not candidate_status:
        return False

    norm_candidate = normalize_turkish_text(candidate_status)
    norm_allowed = [normalize_turkish_text(status) for status in allowed_statuses]
    return any(allowed in norm_candidate for allowed in norm_allowed)


def matches_language_level(
    candidate_level: Optional[str], required_min_level: Optional[str]
) -> bool:
    if not required_min_level:
        return True
    if not candidate_level:
        return False

    c_rank = LANGUAGE_LEVEL_RANKS.get(normalize_turkish_text(candidate_level), 0)
    req_rank = LANGUAGE_LEVEL_RANKS.get(normalize_turkish_text(required_min_level), 0)
    return c_rank >= req_rank


def evaluate_candidate_filters(
    candidate: Dict[str, Any], filters: Dict[str, Any]
) -> bool:
    if not filters:
        return True

    personal = filters.get("personal") or {}
    age_filter = personal.get("age_range") or {}
    min_age = age_filter.get("min_age", 16)
    max_age = age_filter.get("max_age", 65)

    if not matches_age_criteria(candidate.get("age"), min_age, max_age):
        return False

    gender_filter = personal.get("gender") or {}
    if not matches_gender_criteria(
        candidate.get("gender"),
        gender_filter.get("male", False),
        gender_filter.get("female", False),
    ):
        return False

    military_allowed = personal.get("military_status") or []
    if not matches_military_status(candidate.get("military_status"), military_allowed):
        return False

    return True
