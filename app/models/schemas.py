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
