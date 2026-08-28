import json
import logging
import os
import socket
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client, ClientOptions

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OPT_OUT_FILE = Path("logging_optout.txt")
EXPORTS_DIR = Path("exports")
TRACKER_FILE = Path("extracted_jsons.json")
WARNING_COUNTER_FILE = Path(".logging_warning_count.json")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://waultfsxvpomjcdwuoem.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_1X6lM1EJakMk1qVPkxogZQ_3E8jnlc4")
SCHEMA_NAME = "scraping"
TABLE_NAME = "job_postings"

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(schema=SCHEMA_NAME)
)

TARGET_KEYS = {
    "title", "href", "reference_number", "category_tab", "pozisyon",
    "ilan_basligi", "departman", "lokasyon", "calisma_sekli", "calisma_tercihi",
    "engelli_ilani", "pozisyon_seviyesi", "min_deneyim", "max_deneyim",
    "candidate_location", "egitim_seviyesi", "uni_ekleme_istegi", "bolumler",
    "yabanci_dil", "dil_seviyesi", "askerlik_bilgisi", "surucu_belgesi",
    "yetenekler", "calistigi_pozisyonlar", "calistigi_sektorler", "adaylerden_gizle",
    "maas_turu", "odeme_sikligi", "min_maas", "max_maas", "para_birimi",
    "ilan_aciklamasi", "ilan_aciklamasi_html", "ilan_gorsel_url", "secili_sorular",
    "acik_riza_onayi", "otomatik_mesaj", "referans_no", "scraped_at", "company",
    "sirket_sayfasi", "applications_count", "job_ref_no", "job_title",
    "source_url"
}


def is_logging_enabled() -> bool:
    if not OPT_OUT_FILE.exists():
        return False

    try:
        with open(OPT_OUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                clean_line = line.strip()
                if clean_line.upper().startswith("LET_LOG"):
                    parts = clean_line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().upper() == "TRUE"
    except Exception as e:
        logger.error(f"Could not read opt-out file: {e}")

    return False


def handle_warning_notice():
    count = 0
    if WARNING_COUNTER_FILE.exists():
        try:
            with open(WARNING_COUNTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                count = data.get("run_count", 0)
        except Exception:
            count = 0

    if count < 3:
        logger.warning(
            f"[NOTICE {count + 1}/3] Telemetry & Supabase logging is active. "
            "To opt out, set LET_LOG=FALSE in logging_optout.txt."
        )
        count += 1
        with open(WARNING_COUNTER_FILE, "w", encoding="utf-8") as f:
            json.dump({"run_count": count}, f)


def load_processed_files() -> set:
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except json.JSONDecodeError:
            return set()
    return set()


def save_processed_files(processed_set: set) -> None:
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(list(processed_set), f, indent=4, ensure_ascii=False)


def filter_and_enrich_data(raw_data: dict, machine_name: str) -> dict:
    filtered = {k: v for k, v in raw_data.items() if k in TARGET_KEYS}
    filtered["executed_by"] = machine_name
    filtered["is_logged"] = True
    return filtered


def process_and_upload():
    logging_active = is_logging_enabled()

    if not logging_active:
        logger.warning("Logging is disabled or LET_LOG=TRUE is missing in logging_optout.txt. Aborting Supabase upload.")
        return

    handle_warning_notice()
    machine_name = socket.gethostname()
    processed_files = load_processed_files()

    if not EXPORTS_DIR.exists():
        logger.error(f"Directory '{EXPORTS_DIR}' does not exist.")
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
                logger.info(f"Successfully uploaded: {filename}")

            processed_files.add(filename)
            new_files_count += 1

        except Exception as e:
            logger.error(f"Failed to process {filename}: {e}")

    save_processed_files(processed_files)
    logger.info(f"Done. Processed {new_files_count} new files.")


if __name__ == "__main__":
    process_and_upload()