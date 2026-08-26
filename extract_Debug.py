import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

HTML_DIR = Path(r"C:\Users\KRR\Desktop\LastRodeo\html_stuff")


def clean_text(el) -> str:
    if not el:
        return ""
    return " ".join(el.get_text().split())


def get_multiselect_data(soup, wrapper_selector: str):
    wrapper = soup.select_one(wrapper_selector)
    if not wrapper:
        return []

    tags = [clean_text(tag) for tag in wrapper.select(".multiselect__tag span") if clean_text(tag)]
    if tags:
        return tags

    single = wrapper.select_one(".multiselect__single")
    if single:
        txt = clean_text(single)
        return txt if txt else "[]"

    placeholder = wrapper.select_one(".multiselect__placeholder")
    if placeholder:
        return "[]"

    return []


def get_input_val(soup, selector: str) -> str:
    el = soup.select_one(selector)
    if not el:
        return "[]"
    val = el.get("value", "").strip()
    if val:
        return val
    txt = clean_text(el)
    return txt if txt else "[]"


def get_checkbox_state(soup, selector: str) -> bool:
    el = soup.select_one(selector)
    if not el:
        return False
    return el.has_attr("checked") or el.get("value") == "true"


def inspect_wizard_extraction(file_path: Path):
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    soup = BeautifulSoup(file_path.read_text(encoding="utf-8"), "html.parser")

    job_title = get_input_val(soup, "#titleFormInput")
    position = get_multiselect_data(soup, "#jobPosition")
    department = get_multiselect_data(soup, "#businessArea")
    job_location = get_multiselect_data(soup, "#jobLocation")
    working_type = get_multiselect_data(soup, '[name="workingTypeList"]')
    remote_work_type = get_multiselect_data(soup, '[name="remoteWorkType"]')
    disabled_job = get_checkbox_state(soup, "#__BVID__422")

    position_level = get_multiselect_data(soup, '[name="positionLevelList"]')
    min_experience = get_multiselect_data(soup, ".min-experience-wrapper")
    max_experience = get_multiselect_data(soup, ".max-experience-wrapper")
    candidate_location = get_multiselect_data(soup, "#candidateLocation")

    education_level = get_multiselect_data(soup, "#educationLevel")
    add_uni_request = get_checkbox_state(soup, "#__BVID__428")
    department_req = get_multiselect_data(soup, "#department")
    foreign_lang = get_multiselect_data(soup, '[name="language"]')
    lang_level = get_multiselect_data(soup, '[name="languageLevel"]')
    military_status = get_multiselect_data(soup, '[name="militaryStatus"]')
    driver_licence = get_multiselect_data(soup, '[name="driverLicence"]')

    skills = get_multiselect_data(soup, "#keyword")
    candidate_positions = get_multiselect_data(soup, "#applicantPosition")
    candidate_sectors = get_multiselect_data(soup, "#applicantSector")

    hide_salary = get_checkbox_state(soup, "#__BVID__484")
    salary_type = get_multiselect_data(soup, "#salaryType")
    payment_freq = get_multiselect_data(soup, "#paymentFrequency")
    min_salary = get_input_val(soup, 'input[placeholder="Minimum değer"]')
    max_salary = get_input_val(soup, 'input[placeholder="Maksimum değer"]')

    editor_el = soup.select_one(".trumbowyg-editor")
    job_desc_text = clean_text(editor_el) if editor_el else "[]"
    job_desc_html = str(editor_el) if editor_el else "[]"

    bg_style_el = soup.select_one(".skin-job-images-wrapper")
    job_image_url = "[]"
    if bg_style_el and bg_style_el.has_attr("style"):
        match = re.search(r'url\("?(.*?)"?\)', bg_style_el["style"])
        if match:
            job_image_url = match.group(1)

    selected_questions = [
        clean_text(item.select_one(".lg"))
        for item in soup.select(".question-item")
        if item.select_one('input[type="checkbox"]') and item.select_one('input[type="checkbox"]').has_attr("checked")
    ]

    explicit_consent = get_checkbox_state(soup, "#explicitConsentText")

    selected_msg_el = soup.select_one('.quick-messages-list-item input[type="radio"][checked]')
    auto_msg = "[]"
    if selected_msg_el:
        parent_item = selected_msg_el.find_parent(class_="quick-messages-list-item")
        if parent_item:
            auto_msg = clean_text(parent_item.select_one(".quick-messages-list-item-title"))

    ref_no = get_input_val(soup, "#jobCodeFormInput")
    company_profile = get_multiselect_data(soup, "#companyProfiles")

    wizard_data = {
        "source_file": file_path.name,
        "general_info": {
            "job_title": job_title,
            "position": position,
            "department": department,
            "job_location": job_location,
            "working_type": working_type,
            "remote_work_type": remote_work_type,
            "is_disabled_job": disabled_job,
        },
        "candidate_requirements": {
            "position_level": position_level,
            "min_experience": min_experience,
            "max_experience": max_experience,
            "candidate_location": candidate_location,
            "education_level": education_level,
            "add_university_request": add_uni_request,
            "department_requirement": department_req,
            "foreign_language": foreign_lang,
            "language_level": lang_level,
            "military_status": military_status,
            "driver_licence": driver_licence,
            "skills": skills,
            "candidate_positions": candidate_positions,
            "candidate_sectors": candidate_sectors,
        },
        "salary_info": {
            "hide_from_candidates": hide_salary,
            "salary_type": salary_type,
            "payment_frequency": payment_freq,
            "min_salary": min_salary,
            "max_salary": max_salary,
        },
        "job_description": {
            "text": job_desc_text,
            "image_url": job_image_url,
        },
        "screening_and_settings": {
            "selected_questions": selected_questions,
            "explicit_consent_required": explicit_consent,
            "automatic_message": auto_msg,
            "reference_number": ref_no,
            "company_profile": company_profile,
        },
    }

    print("\n--- Complete Wizard Data Extraction Output ---")
    print(json.dumps(wizard_data, indent=2, ensure_ascii=False))


def inspect_cv_extraction(file_path: Path):
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    soup = BeautifulSoup(file_path.read_text(encoding="utf-8"), "html.parser")

    candidate_name = clean_text(soup.select_one(".resume-candidate-card .name")) or "[]"
    candidate_title = clean_text(soup.select_one(".resume-candidate-card .lg.font-weight-bold")) or "[]"
    location = clean_text(soup.select_one("#shortAddress")) or "[]"
    birth_date = clean_text(soup.select_one("#birthDate")) or "[]"
    gender = clean_text(soup.select_one("#sex")) or "[]"

    experiences = []
    for exp in soup.select(".work-information .list-content-wrapper"):
        experiences.append({
            "title": clean_text(exp.select_one(".bold.md")),
            "duration": clean_text(exp.select_one(".xs.col-5")),
            "sector": clean_text(exp.select_one(".summary-info-item:nth-child(1) .summary-label")),
        })

    education = []
    for edu in soup.select(".education-information .education-wrapper"):
        education.append({
            "school": clean_text(edu.select_one(".name")),
            "degree": clean_text(edu.select_one(".f-major")),
            "years": clean_text(edu.select_one(".year")),
        })

    cv_data = {
        "source_file": file_path.name,
        "candidate_name": candidate_name,
        "candidate_title": candidate_title,
        "location": location,
        "birth_date": birth_date,
        "gender": gender,
        "experiences": experiences,
        "education": education,
    }

    print("\n--- Complete Candidate CV Data Extraction Output ---")
    print(json.dumps(cv_data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    inspect_wizard_extraction(HTML_DIR / "fourth_Header_first_jobs_page_example.html")
    inspect_cv_extraction(HTML_DIR / "fifth_header_appplicants_example_details_with_consent.html")