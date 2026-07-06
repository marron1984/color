"""SQLAlchemy ORM モデル.

PDF「人材紹介事業 3つの構成要素」に対応:
  - クライアント (Client)  : 企業側の求人ニーズ
  - 求職者・人材 (Talent)  : 登録された職人・スタッフ
  - マッチング業務 (Job / Match): 求人票と、AI マッチング結果
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class Client(Base):
    """クライアント企業（求人を出す側）."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 新規開拓 / 既存顧客
    kind: Mapped[str] = mapped_column(String(20), default="new")
    industry: Mapped[str] = mapped_column(String(100), default="")
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    contact_email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_now)

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class Talent(Base):
    """登録人材（職人・スタッフ）. PDF「求職者、人材」."""

    __tablename__ = "talents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kana: Mapped[str] = mapped_column(String(100), default="")
    # スキル: [{"name": "溶接", "level": 4}, ...]  level は 1-5
    skills: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    experience_years: Mapped[float] = mapped_column(Float, default=0.0)
    # 希望待遇（年収・万円）
    desired_salary: Mapped[int] = mapped_column(Integer, default=0)
    # タイプ(OS) — 職種の分類タグ（ホール/キッチン/店長 など）
    type_os: Mapped[str] = mapped_column(String(50), default="")
    # 勤務形態の希望: onsite / online / both
    work_style: Mapped[str] = mapped_column(String(20), default="both")
    location: Mapped[str] = mapped_column(String(100), default="")
    # --- 海外人材紹介向け項目 ---
    nationality: Mapped[str] = mapped_column(String(50), default="")  # 国籍
    # 対応言語: [{"name": "英語", "level": 5}, ...]  level は 1-5(5=ネイティブ)
    languages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # 在留資格 / 就労資格（例: 特定技能, 技術・人文知識・国際業務, 永住者, 要ビザサポート）
    visa_status: Mapped[str] = mapped_column(String(100), default="")
    # 希望勤務国・地域: ["日本", "シンガポール", ...]
    desired_countries: Mapped[list[str]] = mapped_column(JSON, default=list)
    # available / assigned / unavailable
    availability: Mapped[str] = mapped_column(String(20), default="available")
    profile: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_now)

    matches: Mapped[list["Match"]] = relationship(
        back_populates="talent", cascade="all, delete-orphan"
    )


class Job(Base):
    """求人票（求人内容ヒアリングの結果）."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # 必須スキル: [{"name": "溶接", "weight": 3, "min_level": 3}, ...]
    required_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # 提示待遇（年収・通貨は currency）
    offered_salary: Mapped[int] = mapped_column(Integer, default=0)
    type_os: Mapped[str] = mapped_column(String(50), default="")
    work_style: Mapped[str] = mapped_column(String(20), default="both")
    location: Mapped[str] = mapped_column(String(100), default="")
    # --- 海外人材紹介向け項目 ---
    country: Mapped[str] = mapped_column(String(50), default="日本")  # 勤務国・地域
    # 必要言語: [{"name": "英語", "min_level": 4}, ...]
    required_languages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    visa_support: Mapped[bool] = mapped_column(default=False)  # ビザサポート有無
    currency: Mapped[str] = mapped_column(String(10), default="JPY")  # 給与通貨
    headcount: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open / closed
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_now)

    client: Mapped["Client"] = relationship(back_populates="jobs")
    matches: Mapped[list["Match"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class Match(Base):
    """マッチング結果（AI ピックアップの提案とその後の進捗）."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    talent_id: Mapped[int] = mapped_column(ForeignKey("talents.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="scoring")  # scoring / ai
    # proposed / interview / offer / hired / rejected
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_now)

    job: Mapped["Job"] = relationship(back_populates="matches")
    talent: Mapped["Talent"] = relationship(back_populates="matches")
