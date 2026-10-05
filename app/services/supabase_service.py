from __future__ import annotations

import json
import logging
import socket
from typing import Any, Dict, Set

from app.core.config import settings

logger = logging.getLogger("kariyer_api.supabase_service")

EXPORTS_DIR = settings.export_dir
TRACKER_FILE = settings.export_dir.parent / "extracted_jsons.json"
WARNING_COUNTER_FILE = settings.export_dir.parent / ".logging_warning_count.json"

SCHEMA_NAME = "scraping"
TABLE_NAME = "job_postings"

try:
    from supabase import Client, ClientOptions, create_client

    if settings.supabase_url and settings.supabase_key:
        supabase: Client | None = create_client(
            settings.supabase_url,
            settings.supabase_key,
            options=ClientOptions(schema=SCHEMA_NAME),
        )
    else:
        supabase = None
except Exception as exc:
    supabase = None
    logger.warning("Supabase initialization skipped or failed: %s", exc)

TARGET_KEYS = {
    "title",
    "href",
    "reference_number",
    "category_tab",
    "pozisyon",
    "ilan_basligi",
    "departman",
    "lokasyon",
    "calisma_sekli",
    "calisma_tercihi",
    "engelli_ilani",
    "pozisyon_seviyesi",
    "min_deneyim",
    "max_deneyim",
    "candidate_location",
    "egitim_seviyesi",
    "uni_ekleme_istegi",
    "bolumler",
    "yabanci_dil",
    "dil_seviyesi",
    "askerlik_bilgisi",
    "surucu_belgesi",
    "yetenekler",
    "calistigi_pozisyonlar",
    "calistigi_sektorler",
    "adaylerden_gizle",
    "maas_turu",
    "odeme_sikligi",
    "min_maas",
    "max_maas",
    "para_birimi",
    "ilan_aciklamasi",
    "ilan_aciklamasi_html",
    "ilan_gorsel_url",
    "secili_sorular",
    "acik_riza_onayi",
    "otomatik_mesaj",
    "referans_no",
    "scraped_at",
    "company",
    "sirket_sayfasi",
    "applications_count",
    "job_ref_no",
    "job_title",
    "source_url",
}


def is_logging_enabled() -> bool:
    return settings.enable_telemetry


def load_processed_files() -> Set[str]:
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_processed_files(processed_set: Set[str]) -> None:
    try:
        with open(TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump(list(processed_set), f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to save tracker file: %s", e)


def filter_and_enrich_data(
    raw_data: Dict[str, Any], machine_name: str
) -> Dict[str, Any]:
    filtered = {k: v for k, v in raw_data.items() if k in TARGET_KEYS}
    filtered["executed_by"] = machine_name
    filtered["is_logged"] = True
    return filtered


def process_and_upload() -> None:
    if supabase is None:
        logger.info("Supabase client not configured or disabled. Skipping upload.")
        return

    if not is_logging_enabled():
        logger.info(
            "Logging is not explicitly enabled in opt-out configuration. Skipping Supabase upload."
        )
        return

    machine_name = socket.gethostname()
    processed_files = load_processed_files()

    if not EXPORTS_DIR.exists():
        logger.error("Directory '%s' does not exist.", EXPORTS_DIR)
        return

    json_files = list(EXPORTS_DIR.glob("*.json"))
    new_files_count = 0

    for file_path in json_files:
        filename = file_path.name
        if filename in processed_files:
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                records = [filter_and_enrich_data(data, machine_name)]
            elif isinstance(data, list):
                records = [
                    filter_and_enrich_data(item, machine_name)
                    for item in data
                    if isinstance(item, dict)
                ]
            else:
                records = []

            if records:
                supabase.schema(SCHEMA_NAME).table(TABLE_NAME).insert(records).execute()
                logger.info("Successfully uploaded: %s", filename)

            processed_files.add(filename)
            new_files_count += 1

        except Exception as e:
            logger.error("Failed to process %s: %s", filename, e)

    save_processed_files(processed_files)
    logger.info("Supabase upload complete. Processed %d new files.", new_files_count)
