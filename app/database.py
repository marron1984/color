"""データベース接続の設定.

優先順位を持って接続先を解決する:
  1. 明示指定: STAFFING_DATABASE_URL
  2. Vercel/Neon 等が自動注入する環境変数:
     POSTGRES_URL_NON_POOLING → POSTGRES_URL → DATABASE_URL
  3. 既定の SQLite（ローカルは ./staffing.db、サーバーレスは /tmp）

外部 DB（Postgres 等）を指定すればデータは永続化される。SQLite の /tmp は
サーバーレスの再起動で消えるため「非永続」として扱い、UI に警告を出す。
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# 外部 DB URL を探す環境変数（この順に優先）
_EXTERNAL_ENV_KEYS = (
    "STAFFING_DATABASE_URL",
    "POSTGRES_URL_NON_POOLING",  # Vercel Postgres（非プーリング推奨）
    "POSTGRES_URL",
    "DATABASE_URL",
)


def _normalize(url: str) -> str:
    """SQLAlchemy + psycopg で使える形式に正規化する.

    Vercel/Neon などは postgres:// を返すが、SQLAlchemy は postgresql+psycopg://
    を要求するため変換する。
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _resolve() -> tuple[str, bool, bool]:
    """(接続URL, 永続か, 外部DBか) を返す."""
    for key in _EXTERNAL_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            return _normalize(val), True, True  # 外部 DB は永続
    # 外部 DB 未指定 → SQLite
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        # /tmp は再起動で消える = 非永続
        return "sqlite:////tmp/staffing.db", False, False
    # ローカルのファイルは永続
    return "sqlite:///./staffing.db", True, False


DATABASE_URL, IS_PERSISTENT, USING_EXTERNAL = _resolve()

_is_sqlite = DATABASE_URL.startswith("sqlite")
# SQLite を FastAPI（複数スレッド）から使うため check_same_thread=False。
connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    future=True,
    # 外部 DB はサーバーレスで接続が切れることがあるため事前 ping する
    pool_pre_ping=not _is_sqlite,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """全 ORM モデルの基底クラス."""


def get_db():
    """FastAPI 依存性注入用のセッションジェネレータ."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """テーブルを作成する（存在しなければ）."""
    # モデルを import してメタデータに登録してから create_all する。
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
