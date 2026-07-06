"""Vercel サーバーレス用エントリポイント.

Vercel の @vercel/python ランタイムは、このモジュールが公開する ASGI
アプリ `app` を検出して配信する。ローカル開発は従来どおり
`uvicorn app.main:app` を使う。
"""
from app.main import app  # noqa: F401
