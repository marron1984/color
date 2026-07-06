"""Pydantic スキーマ（API の入出力）."""
from __future__ import annotations

import datetime as _dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class ClientBase(BaseModel):
    name: str
    kind: str = "new"  # new / existing
    industry: str = ""
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


class TalentBase(BaseModel):
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


class TalentCreate(TalentBase):
    pass


class TalentOut(TalentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: _dt.datetime


# --------------------------------------------------------------------------- #
# Job
# --------------------------------------------------------------------------- #
class RequiredSkill(BaseModel):
    name: str
    weight: float = 1.0
    min_level: int = Field(default=1, ge=1, le=5)


class JobBase(BaseModel):
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
class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_id: int
    talent_id: int
    score: float
    breakdown: dict[str, Any]
    reason: str
    source: str
    status: str
    created_at: _dt.datetime
    talent: TalentOut | None = None


class MatchCandidate(BaseModel):
    """マッチング実行時に返す候補（DB 未保存のプレビュー）."""

    talent: TalentOut
    score: float
    breakdown: dict[str, Any]
    reason: str
    source: str


class RunMatchRequest(BaseModel):
    top_n: int = Field(default=5, ge=1, le=50)
    use_llm: bool = True  # False にするとスコアリングのみ
    persist: bool = False  # True なら候補を Match として保存


class MatchStatusUpdate(BaseModel):
    # proposed / interview / offer / hired / rejected
    status: str
