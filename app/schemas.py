"""Pydantic スキーマ（API の入出力）."""
from __future__ import annotations

import datetime as _dt
from typing import Any, get_origin

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _CoerceBase(BaseModel):
    """DB の NULL 値に強くするための基底.

    後から追加した列や旧データで値が None でも、文字列は空文字、
    リストは空配列に補正して検証エラー（＝500）を防ぐ。
    """

    @field_validator("*", mode="before")
    @classmethod
    def _coerce_none(cls, v, info):
        if v is None:
            fld = cls.model_fields.get(info.field_name)
            if fld is not None:
                ann = fld.annotation
                if ann is str:
                    return ""
                if get_origin(ann) is list:
                    return []
        return v


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class ClientBase(_CoerceBase):
    name: str
    kind: str = "new"  # new / existing
    industry: str = ""
    address: str = ""
    contact_name: str = ""
    contact_email: str = ""
    phone: str = ""
    notes: str = ""


class ClientCreate(ClientBase):
    pass


class ClientOut(ClientBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: _dt.datetime


# --------------------------------------------------------------------------- #
# Talent
# --------------------------------------------------------------------------- #
class SkillItem(BaseModel):
    name: str
    level: int = Field(default=1, ge=1, le=5)


class LanguageItem(BaseModel):
    name: str
    level: int = Field(default=1, ge=1, le=5)  # 5=ネイティブ/流暢


class TalentBase(_CoerceBase):
    name: str
    kana: str = ""
    skills: list[SkillItem] = Field(default_factory=list)
    experience_years: float = 0.0
    desired_salary: int = 0
    type_os: str = ""
    work_style: str = "both"  # onsite / online / both
    location: str = ""
    availability: str = "available"  # available / assigned / unavailable
    profile: str = ""
    tags: list[str] = Field(default_factory=list)
    # 海外人材紹介向け
    nationality: str = ""
    languages: list[LanguageItem] = Field(default_factory=list)
    visa_status: str = ""
    desired_countries: list[str] = Field(default_factory=list)
    # 連絡先（保有するが一覧には表示しない）
    phone: str = ""
    email: str = ""
    contact_note: str = ""
    # 追記項目（人材登録）
    gender: str = ""
    birthdate: str = ""
    address: str = ""
    desired_industry: str = ""
    employment_type: str = ""
    relocation: str = ""
    education: str = ""
    certifications: str = ""
    work_history: str = ""
    overseas_experience: str = ""
    self_pr: str = ""
    future_goals: str = ""


class TalentCreate(TalentBase):
    pass


class TalentOut(TalentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: _dt.datetime
    trust: dict[str, Any] | None = None  # 検証スコア（信頼度サマリ）


# --------------------------------------------------------------------------- #
# Verification（検証レイヤー）
# --------------------------------------------------------------------------- #
class VerificationBase(_CoerceBase):
    category: str = "identity"
    item: str = ""
    status: str = "unverified"
    method: str = ""
    evidence: str = ""
    verified_by: str = ""
    note: str = ""


class VerificationCreate(VerificationBase):
    pass


class VerificationUpdate(BaseModel):
    category: str | None = None
    item: str | None = None
    status: str | None = None
    method: str | None = None
    evidence: str | None = None
    verified_by: str | None = None
    note: str | None = None


class VerificationOut(VerificationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    talent_id: int
    verified_at: _dt.datetime | None = None
    created_at: _dt.datetime


# --------------------------------------------------------------------------- #
# Job
# --------------------------------------------------------------------------- #
class RequiredSkill(BaseModel):
    name: str
    weight: float = 1.0
    min_level: int = Field(default=1, ge=1, le=5)


class RequiredLanguage(BaseModel):
    name: str
    min_level: int = Field(default=1, ge=1, le=5)


class JobBase(_CoerceBase):
    client_id: int
    title: str
    required_skills: list[RequiredSkill] = Field(default_factory=list)
    offered_salary: int = 0
    type_os: str = ""
    work_style: str = "both"
    location: str = ""
    headcount: int = 1
    description: str = ""
    status: str = "open"
    # 海外人材紹介向け
    country: str = "日本"
    required_languages: list[RequiredLanguage] = Field(default_factory=list)
    visa_support: bool = False
    currency: str = "JPY"
    # 追記項目（求人登録）
    employment_type: str = ""
    salary_detail: str = ""
    working_hours: str = ""
    holidays: str = ""
    requirements: str = ""
    benefits: str = ""
    ideal_candidate: str = ""
    selection_flow: str = ""
    store_info: str = ""


class JobCreate(JobBase):
    pass


class JobOut(JobBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: _dt.datetime
    client_name: str | None = None


# --------------------------------------------------------------------------- #
# Match
# --------------------------------------------------------------------------- #
class MatchOut(_CoerceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_id: int
    talent_id: int
    score: float
    breakdown: dict[str, Any]
    reason: str = ""
    source: str = ""
    status: str = "proposed"
    # アウトカム
    hired_at: _dt.datetime | None = None
    retention: str = ""
    retention_days: int = 0
    left_reason: str = ""
    created_at: _dt.datetime
    talent: TalentOut | None = None
    job_title: str | None = None
    client_name: str | None = None


class MatchCreate(BaseModel):
    job_id: int
    talent_id: int


class MatchUpdate(BaseModel):
    status: str | None = None
    retention: str | None = None
    retention_days: int | None = None
    left_reason: str | None = None


class MatchCandidate(BaseModel):
    """マッチング実行時に返す候補（DB 未保存のプレビュー）."""

    talent: TalentOut
    score: float
    breakdown: dict[str, Any]
    reason: str
    source: str
    visa: dict[str, Any] | None = None  # ビザ適格性判定
    trust: dict[str, Any] | None = None  # 検証スコア（信頼度サマリ）


class VisaAssessRequest(BaseModel):
    nationality: str = ""
    country: str = "日本"
    role: str = ""
    experience_years: float = 0
    japanese_level: int = 0
    held_status: str = ""


class RunMatchRequest(BaseModel):
    top_n: int = Field(default=5, ge=1, le=50)
    use_llm: bool = True  # False にするとスコアリングのみ
    persist: bool = False  # True なら候補を Match として保存
    use_learned: bool = False  # True なら学習済みの重みで評価
