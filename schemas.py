# # # import logging
# # # from typing import Dict, Any, List
# # # from playwright.async_api import Page

# # # logger = logging.getLogger(__name__)

# # # ACCORDION_PANELS = {
# # #     "personal": ("personalInfo", "KİŞİSEL BİLGİLER"),
# # #     "education": ("educationInfo", "EĞİTİM"),
# # #     "experience": ("experienceInfo", "İŞ DENEYİMİ"),
# # #     "location": ("locationInfo", "LOKASYON"),
# # #     "application": ("applicationInfo", "BAŞVURU SÜRECİ"),
# # #     "kvkk": ("kvkk", "KVKK ONAY DURUMU"),
# # #     "review_status": ("moreInfo", "İŞLEMLER"),
# # # }

# # # SCOPE_MAP = {
# # #     "all_jobs": "0",
# # #     "last_job": "1",
# # #     "last_3_jobs": "2"
# # # }


# # # async def apply_ats_form_filters(page: Page, filters: Dict[str, Any]):
  
# # #     if not filters:
# # #         return

# # #     try:
# # #         async def _ensure_panel_open(panel_id: str, header_title: str):
# # #             panel = page.locator(f"#{panel_id}")
# # #             if not await panel.is_visible():
# # #                 logger.info("Opening filter panel: %s", header_title)
# # #                 header = page.locator("div.filter-collapse", has_text=header_title).first
# # #                 if await header.is_visible():
# # #                     await header.click()
# # #                     await panel.wait_for(state="visible", timeout=3000)

# # #         async def _fill_vue_multiselect(container_selector: str, input_selector: str, items: List[str]):
# # #             if not items:
# # #                 return
# # #             for item in items:
# # #                 container = page.locator(container_selector).first
# # #                 if not await container.is_visible():
# # #                     continue
# # #                 inp = container.locator(input_selector).first
# # #                 await inp.click()
# # #                 await inp.fill(str(item))
# # #                 await page.wait_for_timeout(300)
                
# # #                 opt = container.locator(".multiselect__option", has_text=str(item)).first
# # #                 if await opt.is_visible():
# # #                     await opt.click()
# # #                 else:
# # #                     await page.keyboard.press("Enter")
# # #                 await page.wait_for_timeout(200)

# # #         personal = filters.get("personal")
# # #         if personal:
# # #             await _ensure_panel_open(*ACCORDION_PANELS["personal"])

# # #             if personal.get("first_name"):
# # #                 await page.locator("#name").fill(personal["first_name"])

# # #             if personal.get("last_name"):
# # #                 await page.locator("#surname").fill(personal["last_name"])

# # #             gender = personal.get("gender") or {}
# # #             if gender.get("male"):
# # #                 chk = page.locator("input[name='man']")
# # #                 if not await chk.is_checked():
# # #                     await chk.check(force=True)
# # #             if gender.get("female"):
# # #                 chk = page.locator("input[name='woman']")
# # #                 if not await chk.is_checked():
# # #                     await chk.check(force=True)

# # #             age = personal.get("age_range") or {}
# # #             min_age = age.get("min_age", 16)
# # #             max_age = age.get("max_age", 65)
# # #             if min_age > 16 or max_age < 65:
# # #                 dots = page.locator("#personalInfo .vue-slider-dot")
# # #                 if await dots.count() >= 2:
# # #                     if min_age > 16:
# # #                         await dots.nth(0).focus()
# # #                         for _ in range(min_age - 16):
# # #                             await page.keyboard.press("ArrowRight")
# # #                     if max_age < 65:
# # #                         await dots.nth(1).focus()
# # #                         for _ in range(65 - max_age):
# # #                             await page.keyboard.press("ArrowLeft")

# # #             await _fill_vue_multiselect("div.multiselect[name='nationality']", "input.multiselect__input", personal.get("nationality", []))
# # #             await _fill_vue_multiselect("div.multiselect[name='militaryStatus']", "input.multiselect__input", personal.get("military_status", []))
# # #             await _fill_vue_multiselect("div.multiselect[name='driverLicences']", "input.multiselect__input", personal.get("driver_licences", []))

# # #             langs = personal.get("languages", [])
# # #             if langs:
# # #                 lang_names = [l["language"] for l in langs if isinstance(l, dict) and l.get("language")]
# # #                 await _fill_vue_multiselect("div.multiselect[name='language']", "input.multiselect__input", lang_names)
                
# # #                 first_level = next((l.get("min_level") for l in langs if isinstance(l, dict) and l.get("min_level")), None)
# # #                 if first_level:
# # #                     await _fill_vue_multiselect("div.multiselect[name='languageLevel']", "input.multiselect__input", [first_level])

# # #             if personal.get("is_disabled_candidate"):
# # #                 disabled_sw = page.locator(".equality-filter input[type='checkbox']").first
# # #                 if await disabled_sw.is_visible() and not await disabled_sw.is_checked():
# # #                     await disabled_sw.check(force=True)

# # #             if personal.get("is_disaster_affected"):
# # #                 disaster_sw = page.locator(".ug-filter-disaster input[type='checkbox']").first
# # #                 if await disaster_sw.is_visible() and not await disaster_sw.is_checked():
# # #                     await disaster_sw.check(force=True)

# # #         education = filters.get("education")
# # #         if education:
# # #             await _ensure_panel_open(*ACCORDION_PANELS["education"])
# # #             await _fill_vue_multiselect("#educationLevel", "#educationLevelFormInput", education.get("levels", []))
# # #             await _fill_vue_multiselect("div.multiselect[name='university']", "input.multiselect__input", education.get("universities", []))
# # #             await _fill_vue_multiselect("#department", "#departmentFormInput", education.get("departments", []))

# # #         exp = filters.get("experience")
# # #         if exp:
# # #             await _ensure_panel_open(*ACCORDION_PANELS["experience"])

# # #             exp_type = exp.get("experience_type")
# # #             if exp_type in ["inexperienced", "experienced"]:
# # #                 val_idx = "1" if exp_type == "inexperienced" else "2"
# # #                 radio = page.locator(f"input[name='radiosStacked'][value='{val_idx}']")
# # #                 if await radio.is_visible():
# # #                     await radio.check(force=True)

# # #             if exp.get("positions"):
# # #                 p_scope = exp.get("position_scope", "all_jobs")
# # #                 p_select = page.locator("#position").locator("..").locator("select.xs").first
# # #                 if await p_select.is_visible():
# # #                     await p_select.select_option(value=SCOPE_MAP.get(p_scope, "0"))
# # #                 await _fill_vue_multiselect("#position", "#positionFormInput", exp["positions"])

# # #             if exp.get("position_levels"):
# # #                 await _fill_vue_multiselect("div.multiselect[name='positionLevel']", "input.multiselect__input", exp["position_levels"])

# # #             if exp.get("sectors"):
# # #                 s_scope = exp.get("sector_scope", "all_jobs")
# # #                 s_select = page.locator("#sector").locator("..").locator("select.xs").first
# # #                 if await s_select.is_visible():
# # #                     await s_select.select_option(value=SCOPE_MAP.get(s_scope, "0"))
# # #                 await _fill_vue_multiselect("#sector", "#sectorFormInput", exp["sectors"])

# # #             if exp.get("is_currently_working") is True:
# # #                 chk = page.locator("input[name='working']")
# # #                 if await chk.is_visible():
# # #                     await chk.check(force=True)
# # #             elif exp.get("is_currently_working") is False:
# # #                 chk = page.locator("input[name='does-not-work']")
# # #                 if await chk.is_visible():
# # #                     await chk.check(force=True)

# # #             if exp.get("is_retired") is True:
# # #                 chk = page.locator("input[name='retired']")
# # #                 if await chk.is_visible():
# # #                     await chk.check(force=True)
# # #             elif exp.get("is_retired") is False:
# # #                 chk = page.locator("input[name='not-retired']")
# # #                 if await chk.is_visible():
# # #                     await chk.check(force=True)

# # #         location = filters.get("location")
# # #         if location:
# # #             await _ensure_panel_open(*ACCORDION_PANELS["location"])
# # #             await _fill_vue_multiselect("#location", "#locationFormInput", location.get("current_locations", []))
# # #             await _fill_vue_multiselect("div.multiselect[name='preferCity']", "input.multiselect__input", location.get("preferred_cities", []))

        
# # #         app_filters = filters.get("application")
# # #         if app_filters:
# # #             await _ensure_panel_open(*ACCORDION_PANELS["application"])
            
# # #             await _fill_vue_multiselect("#application-status", "input.multiselect__input", app_filters.get("statuses", []))

# # #             questions = app_filters.get("questions", [])
# # #             for q_item in questions:
# # #                 if isinstance(q_item, dict) and q_item.get("question") and q_item.get("answer"):
# # #                     q_text = q_item["question"]
# # #                     target_ans = q_item["answer"]
                    
# # #                     q_box = page.locator(".question-filter-item", has_text=q_text).first
# # #                     if await q_box.is_visible():
# # #                         q_input = q_box.locator("input[type='text'], textarea").first
# # #                         if await q_input.is_visible():
# # #                             await q_input.fill(target_ans)

       
# # #         kvkk = filters.get("kvkk")
# # #         if kvkk:
# # #             await _ensure_panel_open(*ACCORDION_PANELS["kvkk"])
            
# # #             if kvkk.get("clarification_text_shown") is not None:
# # #                 val_str = "true" if kvkk["clarification_text_shown"] else "false"
# # #                 chk = page.locator(f".clarification-filter-wrapper input[value='{val_str}']")
# # #                 if await chk.is_visible() and not await chk.is_disabled():
# # #                     await chk.check(force=True)

# # #             if kvkk.get("explicit_consent_approved") is not None:
# # #                 val_str = "true" if kvkk["explicit_consent_approved"] else "false"
# # #                 chk = page.locator(f".explicit-consent-filter-wrapper input[value='{val_str}']")
# # #                 if await chk.is_visible() and not await chk.is_disabled():
# # #                     await chk.check(force=True)

       
# # #         rev_status = filters.get("review_status")
# # #         if rev_status:
# # #             await _ensure_panel_open(*ACCORDION_PANELS["review_status"])

# # #             # Review Status Radio
# # #             rev_val = rev_status.get("review_status")
# # #             if rev_val == "show_reviewed":
# # #                 chk = page.locator("#showReview")
# # #                 if await chk.is_visible():
# # #                     await chk.check(force=True)
# # #             elif rev_val == "hide_reviewed":
# # #                 chk = page.locator("#hideReview")
# # #                 if await chk.is_visible():
# # #                     await chk.check(force=True)

# # #             resp_val = rev_status.get("response_status")
# # #             resp_map = {
# # #                 "unanswered_custom": "4",
# # #                 "auto_replied": "3",
# # #                 "answered_custom": "1"
# # #             }
# # #             if resp_val in resp_map:
# # #                 radio_elem = page.locator(f"#letter-status input[value='{resp_map[resp_val]}']")
# # #                 if await radio_elem.is_visible():
# # #                     await radio_elem.check(force=True)

# # #         submit_btn = page.locator("div.filter-footer button[type='submit']").first
# # #         if await submit_btn.is_visible():
# # #             logger.info("Submitting filter criteria via 'Ara' button...")
# # #             await submit_btn.click()
# # #             await page.wait_for_load_state("networkidle")
# # #             await page.wait_for_timeout(1000)

# # #     except Exception as err:
# # #         logger.warning("Error encountered while populating candidate form filters: %s", err)


# # from typing import List, Literal, Optional
# # from pydantic import BaseModel, Field


# # class AgeRangeFilter(BaseModel):
# #     min_age: Optional[int] = Field(default=16, ge=16, le=65, description="Minimum candidate age")
# #     max_age: Optional[int] = Field(default=65, ge=16, le=65, description="Maximum candidate age")


# # class GenderFilter(BaseModel):
# #     male: Optional[bool] = Field(default=False, description="Include male candidates")
# #     female: Optional[bool] = Field(default=False, description="Include female candidates")


# # class LanguageFilter(BaseModel):
# #     language: Optional[str] = Field(None, description="Language name (e.g. 'İngilizce')")
# #     min_level: Optional[str] = Field(
# #         None, 
# #         description="Options: 'Başlangıç', 'Temel', 'Orta', 'İyi', 'İleri', 'Anadil'"
# #     )


# # class PersonalInfoFilters(BaseModel):
# #     first_name: Optional[str] = Field(None, description="Ad filter")
# #     last_name: Optional[str] = Field(None, description="Soyad filter")
# #     age_range: Optional[AgeRangeFilter] = Field(default_factory=AgeRangeFilter)
# #     gender: Optional[GenderFilter] = Field(default_factory=GenderFilter)
# #     nationality: Optional[List[str]] = Field(default_factory=list, description="Uyruk list")
# #     military_status: Optional[List[str]] = Field(
# #         default_factory=list, 
# #         description="Options: 'Farketmez', 'Yapıldı', 'Yapılmadı', 'Muaf', 'Tecilli'"
# #     )
# #     driver_licences: Optional[List[str]] = Field(
# #         default_factory=list, 
# #         description="Options: 'A1', 'B', 'C', 'E', 'Uluslararası Sürücü Belgesi'"
# #     )
# #     languages: Optional[List[LanguageFilter]] = Field(default_factory=list)
# #     is_disabled_candidate: Optional[bool] = Field(default=False, description="Engelli Aday toggle")
# #     is_disaster_affected: Optional[bool] = Field(default=False, description="Afetten Etkilenen Aday toggle")


# # class EducationFilters(BaseModel):
# #     levels: Optional[List[str]] = Field(default_factory=list, description="Eğitim Seviyesi")
# #     universities: Optional[List[str]] = Field(default_factory=list, description="Üniversite")
# #     departments: Optional[List[str]] = Field(default_factory=list, description="Bölüm")



# # class ExperienceDetailsFilters(BaseModel):
# #     experience_type: Optional[Literal["all", "inexperienced", "experienced"]] = Field(
# #         default="all", description="0: Tümü, 1: Tecrübesiz, 2: Tecrübeli"
# #     )
# #     positions: Optional[List[str]] = Field(default_factory=list, description="Pozisyon listesi")
# #     position_scope: Optional[Literal["all_jobs", "last_job", "last_3_jobs"]] = Field(
# #         default="all_jobs", description="0: Tüm İş Tecrübesi, 1: Son İş, 2: Son 3 İş"
# #     )
# #     position_levels: Optional[List[str]] = Field(
# #         default_factory=list, 
# #         description="Pozisyon Seviyesi (e.g. 'Uzman', 'Stajyer', 'Mavi yaka')"
# #     )
# #     sectors: Optional[List[str]] = Field(default_factory=list, description="Sektör listesi")
# #     sector_scope: Optional[Literal["all_jobs", "last_job", "last_3_jobs"]] = Field(
# #         default="all_jobs", description="0: Tüm İş Tecrübesi, 1: Son İş, 2: Son 3 İş"
# #     )
# #     is_currently_working: Optional[bool] = Field(None, description="True: Çalışan, False: Çalışmayan")
# #     is_retired: Optional[bool] = Field(None, description="True: Emekli, False: Emekli Değil")



# # class LocationFilters(BaseModel):
# #     current_locations: Optional[List[str]] = Field(default_factory=list, description="Yaşadığı İl / İlçe")
# #     preferred_cities: Optional[List[str]] = Field(default_factory=list, description="Çalışmak İstediği İl")



# # class CustomQuestionAnswer(BaseModel):
# #     question: Optional[str] = Field(None, description="Question label text")
# #     answer: Optional[str] = Field(None, description="Target response value")


# # class ApplicationFilters(BaseModel):
# #     questions: Optional[List[CustomQuestionAnswer]] = Field(default_factory=list)
# #     statuses: Optional[List[str]] = Field(
# #         default_factory=list,
# #         description="Options: 'Durum Belirtilmemiş', 'Favori Aday', 'Mülakat', 'İş Teklifi', 'İşe Alındı', 'Ret'"
# #     )

# # class KvkkFilters(BaseModel):
# #     clarification_text_shown: Optional[bool] = Field(None, description="Aydınlatma Metni: True=Gösterilen, False=Gösterilmeyen")
# #     explicit_consent_approved: Optional[bool] = Field(None, description="Açık Rıza Metni: True=Onaylayan, False=Onaylamayan")



# # class ReviewStatusFilters(BaseModel):
# #     review_status: Optional[Literal["all", "show_reviewed", "hide_reviewed"]] = Field(
# #         default="all", description="Başvuru İnceleme Durumu"
# #     )
# #     response_status: Optional[Literal["all", "unanswered_custom", "auto_replied", "answered_custom"]] = Field(
# #         default="all", description="Cevaplama Durumu"
# #     )



# # class CandidateFilters(BaseModel):
# #     include_active: Optional[bool] = Field(default=True, description="Aktif İlanlar")
# #     include_passive: Optional[bool] = Field(default=False, description="Pasif İlanlar")
# #     include_drafts: Optional[bool] = Field(default=False, description="Taslak İlanlar")
# #     include_archived: Optional[bool] = Field(default=False, description="Arşivlenen İlanlar")
# #     include_offerings: Optional[bool] = Field(default=False, description="Teklif İlanları")

# #     personal: Optional[PersonalInfoFilters] = Field(default_factory=PersonalInfoFilters)
# #     education: Optional[EducationFilters] = Field(default_factory=EducationFilters)
# #     experience: Optional[ExperienceDetailsFilters] = Field(default_factory=ExperienceDetailsFilters)
# #     location: Optional[LocationFilters] = Field(default_factory=LocationFilters)
# #     application: Optional[ApplicationFilters] = Field(default_factory=ApplicationFilters)
# #     kvkk: Optional[KvkkFilters] = Field(default_factory=KvkkFilters)
# #     review_status: Optional[ReviewStatusFilters] = Field(default_factory=ReviewStatusFilters)


# # class ExportRequest(BaseModel):
# #     token: str = Field(..., description="Authentication session token")
# #     limit: Optional[int] = Field(default=100, ge=1, le=5000, description="Max jobs to process")
# #     filters: Optional[CandidateFilters] = Field(default_factory=CandidateFilters, description="Filter criteria")
# from __future__ import annotations

# from typing import List, Literal, Optional
# from pydantic import BaseModel, Field


# class LoginCredentials(BaseModel):
#     email: str = Field(min_length=3, max_length=320)
#     password: str = Field(min_length=1, max_length=512)


# class TwoFactorChoice(BaseModel):
#     token: str
#     method: str


# class TwoFactorSubmission(BaseModel):
#     token: str
#     code: str = Field(min_length=3, max_length=12)


# class TokenOnly(BaseModel):
#     token: str


# class AgeRangeFilter(BaseModel):
#     min_age: Optional[int] = Field(default=16, ge=16, le=65, description="Minimum candidate age")
#     max_age: Optional[int] = Field(default=65, ge=16, le=65, description="Maximum candidate age")


# class GenderFilter(BaseModel):
#     male: Optional[bool] = Field(default=False, description="Include male candidates")
#     female: Optional[bool] = Field(default=False, description="Include female candidates")


# class LanguageFilter(BaseModel):
#     language: Optional[str] = Field(None, description="Language name (e.g. 'İngilizce')")
#     min_level: Optional[str] = Field(
#         None, 
#         description="Options: 'Başlangıç', 'Temel', 'Orta', 'İyi', 'İleri', 'Anadil'"
#     )


# class PersonalInfoFilters(BaseModel):
#     first_name: Optional[str] = Field(None, description="Ad filter")
#     last_name: Optional[str] = Field(None, description="Soyad filter")
#     age_range: Optional[AgeRangeFilter] = Field(default_factory=AgeRangeFilter)
#     gender: Optional[GenderFilter] = Field(default_factory=GenderFilter)
#     nationality: Optional[List[str]] = Field(default_factory=list, description="Uyruk list")
#     military_status: Optional[List[str]] = Field(
#         default_factory=list, 
#         description="Options: 'Farketmez', 'Yapıldı', 'Yapılmadı', 'Muaf', 'Tecilli'"
#     )
#     driver_licences: Optional[List[str]] = Field(
#         default_factory=list, 
#         description="Options: 'A1', 'B', 'C', 'E', 'Uluslararası Sürücü Belgesi'"
#     )
#     languages: Optional[List[LanguageFilter]] = Field(default_factory=list)
#     is_disabled_candidate: Optional[bool] = Field(default=False, description="Engelli Aday toggle")
#     is_disaster_affected: Optional[bool] = Field(default=False, description="Afetten Etkilenen Aday toggle")


# class EducationFilters(BaseModel):
#     levels: Optional[List[str]] = Field(default_factory=list, description="Eğitim Seviyesi")
#     universities: Optional[List[str]] = Field(default_factory=list, description="Üniversite")
#     departments: Optional[List[str]] = Field(default_factory=list, description="Bölüm")


# class ExperienceDetailsFilters(BaseModel):
#     experience_type: Optional[Literal["all", "inexperienced", "experienced"]] = Field(
#         default="all", description="0: Tümü, 1: Tecrübesiz, 2: Tecrübeli"
#     )
#     positions: Optional[List[str]] = Field(default_factory=list, description="Pozisyon listesi")
#     position_scope: Optional[Literal["all_jobs", "last_job", "last_3_jobs"]] = Field(
#         default="all_jobs", description="0: Tüm İş Tecrübesi, 1: Son İş, 2: Son 3 İş"
#     )
#     position_levels: Optional[List[str]] = Field(
#         default_factory=list, 
#         description="Pozisyon Seviyesi (e.g. 'Uzman', 'Stajyer', 'Mavi yaka')"
#     )
#     sectors: Optional[List[str]] = Field(default_factory=list, description="Sektör listesi")
#     sector_scope: Optional[Literal["all_jobs", "last_job", "last_3_jobs"]] = Field(
#         default="all_jobs", description="0: Tüm İş Tecrübesi, 1: Son İş, 2: Son 3 İş"
#     )
#     is_currently_working: Optional[bool] = Field(None, description="True: Çalışan, False: Çalışmayan")
#     is_retired: Optional[bool] = Field(None, description="True: Emekli, False: Emekli Değil")


# class LocationFilters(BaseModel):
#     current_locations: Optional[List[str]] = Field(default_factory=list, description="Yaşadığı İl / İlçe")
#     preferred_cities: Optional[List[str]] = Field(default_factory=list, description="Çalışmak İstediği İl")


# class CustomQuestionAnswer(BaseModel):
#     question: Optional[str] = Field(None, description="Question label text")
#     answer: Optional[str] = Field(None, description="Target response value")


# class ApplicationFilters(BaseModel):
#     questions: Optional[List[CustomQuestionAnswer]] = Field(default_factory=list)
#     statuses: Optional[List[str]] = Field(
#         default_factory=list,
#         description="Options: 'Durum Belirtilmemiş', 'Favori Aday', 'Mülakat', 'İş Teklifi', 'İşe Alındı', 'Ret'"
#     )


# class KvkkFilters(BaseModel):
#     clarification_text_shown: Optional[bool] = Field(None, description="Aydınlatma Metni: True=Gösterilen, False=Gösterilmeyen")
#     explicit_consent_approved: Optional[bool] = Field(None, description="Açık Rıza Metni: True=Onaylayan, False=Onaylamayan")


# class ReviewStatusFilters(BaseModel):
#     review_status: Optional[Literal["all", "show_reviewed", "hide_reviewed"]] = Field(
#         default="all", description="Başvuru İnceleme Durumu"
#     )
#     response_status: Optional[Literal["all", "unanswered_custom", "auto_replied", "answered_custom"]] = Field(
#         default="all", description="Cevaplama Durumu"
#     )


# class CandidateFilters(BaseModel):
#     include_active: Optional[bool] = Field(default=True, description="Aktif İlanlar")
#     include_passive: Optional[bool] = Field(default=False, description="Pasif İlanlar")
#     include_drafts: Optional[bool] = Field(default=False, description="Taslak İlanlar")
#     include_archived: Optional[bool] = Field(default=False, description="Arşivlenen İlanlar")
#     include_offerings: Optional[bool] = Field(default=False, description="Teklif İlanları")

#     personal: Optional[PersonalInfoFilters] = Field(default_factory=PersonalInfoFilters)
#     education: Optional[EducationFilters] = Field(default_factory=EducationFilters)
#     experience: Optional[ExperienceDetailsFilters] = Field(default_factory=ExperienceDetailsFilters)
#     location: Optional[LocationFilters] = Field(default_factory=LocationFilters)
#     application: Optional[ApplicationFilters] = Field(default_factory=ApplicationFilters)
#     kvkk: Optional[KvkkFilters] = Field(default_factory=KvkkFilters)
#     review_status: Optional[ReviewStatusFilters] = Field(default_factory=ReviewStatusFilters)


# class ExportRequest(BaseModel):
#     token: str = Field(..., description="Authentication session token")
#     limit: Optional[int] = Field(default=100, ge=1, le=5000, description="Max jobs to process")
#     filters: Optional[CandidateFilters] = Field(default_factory=CandidateFilters, description="Filter criteria")

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class LoginCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class TwoFactorChoice(BaseModel):
    token: str
    method: str


class TwoFactorSubmission(BaseModel):
    token: str
    code: str = Field(min_length=3, max_length=12)


class TokenOnly(BaseModel):
    token: str


class AgeRangeFilter(BaseModel):
    min_age: Optional[int] = Field(default=16, ge=16, le=65, description="Minimum candidate age")
    max_age: Optional[int] = Field(default=65, ge=16, le=65, description="Maximum candidate age")


class GenderFilter(BaseModel):
    male: Optional[bool] = Field(default=False, description="Include male candidates")
    female: Optional[bool] = Field(default=False, description="Include female candidates")


class LanguageFilter(BaseModel):
    language: Optional[str] = Field(None, description="Language name (e.g. 'İngilizce')")
    min_level: Optional[str] = Field(
        None, 
        description="Options: 'Başlangıç', 'Temel', 'Orta', 'İyi', 'İleri', 'Anadil'"
    )


class PersonalInfoFilters(BaseModel):
    first_name: Optional[str] = Field(None, description="Ad filter")
    last_name: Optional[str] = Field(None, description="Soyad filter")
    age_range: Optional[AgeRangeFilter] = Field(default_factory=AgeRangeFilter)
    gender: Optional[GenderFilter] = Field(default_factory=GenderFilter)
    nationality: Optional[List[str]] = Field(default_factory=list, description="Uyruk list")
    military_status: Optional[List[str]] = Field(
        default_factory=list, 
        description="Options: 'Farketmez', 'Yapıldı', 'Yapılmadı', 'Muaf', 'Tecilli'"
    )
    driver_licences: Optional[List[str]] = Field(
        default_factory=list, 
        description="Options: 'A1', 'B', 'C', 'E', 'Uluslararası Sürücü Belgesi'"
    )
    languages: Optional[List[LanguageFilter]] = Field(default_factory=list)
    is_disabled_candidate: Optional[bool] = Field(default=False, description="Engelli Aday toggle")
    is_disaster_affected: Optional[bool] = Field(default=False, description="Afetten Etkilenen Aday toggle")


class EducationFilters(BaseModel):
    levels: Optional[List[str]] = Field(default_factory=list, description="Eğitim Seviyesi")
    universities: Optional[List[str]] = Field(default_factory=list, description="Üniversite")
    departments: Optional[List[str]] = Field(default_factory=list, description="Bölüm")


class ExperienceDetailsFilters(BaseModel):
    experience_type: Optional[Literal["all", "inexperienced", "experienced"]] = Field(
        default="all", description="0: Tümü, 1: Tecrübesiz, 2: Tecrübeli"
    )
    positions: Optional[List[str]] = Field(default_factory=list, description="Pozisyon listesi")
    position_scope: Optional[Literal["all_jobs", "last_job", "last_3_jobs"]] = Field(
        default="all_jobs", description="0: Tüm İş Tecrübesi, 1: Son İş, 2: Son 3 İş"
    )
    position_levels: Optional[List[str]] = Field(
        default_factory=list, 
        description="Pozisyon Seviyesi (e.g. 'Uzman', 'Stajyer', 'Mavi yaka')"
    )
    sectors: Optional[List[str]] = Field(default_factory=list, description="Sektör listesi")
    sector_scope: Optional[Literal["all_jobs", "last_job", "last_3_jobs"]] = Field(
        default="all_jobs", description="0: Tüm İş Tecrübesi, 1: Son İş, 2: Son 3 İş"
    )
    is_currently_working: Optional[bool] = Field(None, description="True: Çalışan, False: Çalışmayan")
    is_retired: Optional[bool] = Field(None, description="True: Emekli, False: Emekli Değil")


class LocationFilters(BaseModel):
    current_locations: Optional[List[str]] = Field(default_factory=list, description="Yaşadığı İl / İlçe")
    preferred_cities: Optional[List[str]] = Field(default_factory=list, description="Çalışmak İstediği İl")


class CustomQuestionAnswer(BaseModel):
    question: Optional[str] = Field(None, description="Question label text")
    answer: Optional[str] = Field(None, description="Target response value")


class ApplicationFilters(BaseModel):
    questions: Optional[List[CustomQuestionAnswer]] = Field(default_factory=list)
    statuses: Optional[List[str]] = Field(
        default_factory=list,
        description="Options: 'Durum Belirtilmemiş', 'Favori Aday', 'Mülakat', 'İş Teklifi', 'İşe Alındı', 'Ret'"
    )


class KvkkFilters(BaseModel):
    clarification_text_shown: Optional[bool] = Field(None, description="Aydınlatma Metni: True=Gösterilen, False=Gösterilmeyen")
    explicit_consent_approved: Optional[bool] = Field(None, description="Açık Rıza Metni: True=Onaylayan, False=Onaylamayan")


class ReviewStatusFilters(BaseModel):
    review_status: Optional[Literal["all", "show_reviewed", "hide_reviewed"]] = Field(
        default="all", description="Başvuru İnceleme Durumu"
    )
    response_status: Optional[Literal["all", "unanswered_custom", "auto_replied", "answered_custom"]] = Field(
        default="all", description="Cevaplama Durumu"
    )


class CandidateFilters(BaseModel):
    include_active: Optional[bool] = Field(default=True, description="Aktif İlanlar")
    include_passive: Optional[bool] = Field(default=False, description="Pasif İlanlar")
    include_drafts: Optional[bool] = Field(default=False, description="Taslak İlanlar")
    include_archived: Optional[bool] = Field(default=False, description="Arşivlenen İlanlar")
    include_offerings: Optional[bool] = Field(default=False, description="Teklif İlanları")

    personal: Optional[PersonalInfoFilters] = Field(default_factory=PersonalInfoFilters)
    education: Optional[EducationFilters] = Field(default_factory=EducationFilters)
    experience: Optional[ExperienceDetailsFilters] = Field(default_factory=ExperienceDetailsFilters)
    location: Optional[LocationFilters] = Field(default_factory=LocationFilters)
    application: Optional[ApplicationFilters] = Field(default_factory=ApplicationFilters)
    kvkk: Optional[KvkkFilters] = Field(default_factory=KvkkFilters)
    review_status: Optional[ReviewStatusFilters] = Field(default_factory=ReviewStatusFilters)


class ExportRequest(BaseModel):
    token: str = Field(..., description="Authentication session token")
    limit: Optional[int] = Field(default=100, ge=1, le=5000, description="Max jobs to process")
    max_candidates_per_job: Optional[int] = Field(
        default=None, 
        ge=1, 
        le=1000, 
        description="Max candidates to extract per job (Sınırsız için None)"
    )
    filters: Optional[CandidateFilters] = Field(default_factory=CandidateFilters, description="Filter criteria")