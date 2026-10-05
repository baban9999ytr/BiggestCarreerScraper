from app.services.job_filter_service import (
    evaluate_candidate_filters,
    matches_age_criteria,
    matches_gender_criteria,
    matches_language_level,
    matches_military_status,
    normalize_turkish_text,
)


def test_normalize_turkish_text():
    assert normalize_turkish_text("İSTANBUL ŞİŞLİ") == "istanbul sisli"
    assert normalize_turkish_text("Çalışkan Öğrenci") == "caliskan ogrenci"
    assert normalize_turkish_text("") == ""
    assert normalize_turkish_text(None) == ""


def test_matches_age_criteria():
    assert matches_age_criteria(25, 18, 30) is True
    assert matches_age_criteria(17, 18, 30) is False
    assert matches_age_criteria(31, 18, 30) is False
    assert matches_age_criteria(None, 18, 30) is True


def test_matches_gender_criteria():
    assert matches_gender_criteria("Erkek", allow_male=True, allow_female=False) is True
    assert (
        matches_gender_criteria("Kadın", allow_male=True, allow_female=False) is False
    )
    assert matches_gender_criteria("Kadın", allow_male=False, allow_female=True) is True
    assert (
        matches_gender_criteria("Erkek", allow_male=False, allow_female=False) is True
    )


def test_matches_military_status():
    assert matches_military_status("Yapıldı", ["Yapıldı", "Muaf"]) is True
    assert matches_military_status("Tecilli", ["Yapıldı", "Muaf"]) is False
    assert matches_military_status("Tecilli", ["Farketmez"]) is True
    assert matches_military_status("Tecilli", []) is True


def test_matches_language_level():
    assert matches_language_level("İleri", "Orta") is True
    assert matches_language_level("Temel", "İleri") is False
    assert matches_language_level("Anadil", "Başlangıç") is True
    assert matches_language_level(None, "Orta") is False
    assert matches_language_level("İleri", None) is True


def test_evaluate_candidate_filters():
    candidate = {
        "age": 28,
        "gender": "Erkek",
        "military_status": "Yapıldı",
    }
    filters = {
        "personal": {
            "age_range": {"min_age": 20, "max_age": 35},
            "gender": {"male": True, "female": False},
            "military_status": ["Yapıldı", "Muaf"],
        }
    }
    assert evaluate_candidate_filters(candidate, filters) is True

    # Age fail
    candidate["age"] = 40
    assert evaluate_candidate_filters(candidate, filters) is False
