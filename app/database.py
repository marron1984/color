"""SQLite データベース接続の設定."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

def _default_sqlite_url() -> str:
    """既定の SQLite URL を決める.

    Vercel / AWS Lambda などのサーバーレス環境ではプロジェクト直下が
    読み取り専用のため、書き込み可能な /tmp を使う。それ以外はローカルの
    staffing.db。永続 DB を使う場合は STAFFING_DATABASE_URL で上書きする。
    """
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "sqlite:////tmp/staffing.db"
    return "sqlite:///./staffing.db"


DATABASE_URL = os.environ.get("STAFFING_DATABASE_URL", _default_sqlite_url())

# SQLite を FastAPI（複数スレッド）から使うため check_same_thread=False。
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

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
