"""履歴書の読み込み（自動入力）レイヤー.

アップロードされた履歴書（PDF / 画像 / テキスト）から、人材登録フォームの
各項目を推定して返す。

- ANTHROPIC_API_KEY があれば Claude API に文書/画像を渡して構造化抽出する。
  PDF・画像もそのまま解析できる（Claude の document / image 入力を利用）。
- API キーが無い場合は、テキストを抽出して簡易ヒューリスティックで抽出する
  （名前・経験年数・希望年収などのベストエフォート）。

いずれの場合も「フォームの下書き」を返すだけで、保存はしない。
利用者が内容を確認してから登録する想定。
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Any

import httpx

from app import ai

MAX_TEXT_CHARS = 20000

IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

EXTRACTION_PROMPT = (
    "あなたは飲食店専門の人材紹介会社のアシスタントです。"
    "添付の履歴書・職務経歴書から、飲食店スタッフの登録に必要な情報を抽出し、"
    "次の JSON スキーマに厳密に従って日本語で出力してください。\n"
    "{\n"
    '  "name": "氏名(文字列)",\n'
    '  "kana": "フリガナ(不明なら空文字)",\n'
    '  "skills": [{"name": "スキル名", "level": 1〜5の整数}],\n'
    '  "experience_years": 飲食店での実務経験年数(数値),\n'
    '  "desired_salary": 希望年収(万円・整数, 不明なら0),\n'
    '  "type_os": "職種(例: ホール, キッチン, 調理長, 店長, 副店長, バリスタ, 寿司職人, パティシエ, ソムリエ)",\n'
    '  "work_style": "onsite / online / both のいずれか(飲食店は基本 onsite)",\n'
    '  "location": "希望勤務地または居住地",\n'
    '  "profile": "経歴の要約(120字程度)"\n'
    "}\n"
    "スキルは接客・調理・仕込み・ドリンク・レジ・メニュー開発・原価管理・"
    "店舗管理・衛生管理など飲食店で使うものを想定し、"
    "レベルは記載が無ければ経験から1〜5で推定してください。"
    "JSON 以外の文章・コードフェンスは出力しないでください。"
)


def _content_block(filename: str, content_type: str, data: bytes) -> dict[str, Any]:
    """Claude Messages API に渡す content ブロックを組み立てる."""
    lower = filename.lower()
    ext = os.path.splitext(lower)[1]
    b64 = base64.standard_b64encode(data).decode("ascii")

    if ext == ".pdf" or content_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }
    if ext in IMAGE_MEDIA or (content_type or "").startswith("image/"):
        media = IMAGE_MEDIA.get(ext) or content_type or "image/png"
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media, "data": b64},
        }
    # テキスト系はそのまま埋め込む
    text = data.decode("utf-8", errors="ignore")[:MAX_TEXT_CHARS]
    return {"type": "text", "text": f"【履歴書テキスト】\n{text}"}


def _extract_json(text: str) -> dict[str, Any] | None:
    """モデル出力から JSON 部分を取り出してパースする."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        # 最初の { から最後の } までを試す
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _normalize(fields: dict[str, Any]) -> dict[str, Any]:
    """抽出結果をフォーム項目の形に整える（型・範囲を安全側に補正）."""
    out: dict[str, Any] = {}
    out["name"] = str(fields.get("name") or "").strip()
    out["kana"] = str(fields.get("kana") or "").strip()

    skills = []
    for s in fields.get("skills") or []:
        if isinstance(s, dict) and s.get("name"):
            try:
                level = int(s.get("level", 3))
            except (TypeError, ValueError):
                level = 3
            skills.append({"name": str(s["name"]).strip(), "level": max(1, min(5, level))})
        elif isinstance(s, str) and s.strip():
            skills.append({"name": s.strip(), "level": 3})
    out["skills"] = skills

    try:
        out["experience_years"] = float(fields.get("experience_years") or 0)
    except (TypeError, ValueError):
        out["experience_years"] = 0.0
    try:
        out["desired_salary"] = int(float(fields.get("desired_salary") or 0))
    except (TypeError, ValueError):
        out["desired_salary"] = 0

    out["type_os"] = str(fields.get("type_os") or "").strip()
    ws = str(fields.get("work_style") or "both").strip()
    out["work_style"] = ws if ws in {"onsite", "online", "both"} else "both"
    out["location"] = str(fields.get("location") or "").strip()
    out["profile"] = str(fields.get("profile") or "").strip()
    return out


def _parse_with_llm(filename: str, content_type: str, data: bytes) -> dict[str, Any] | None:
    block = _content_block(filename, content_type, data)
    messages = [{"role": "user", "content": [block, {"type": "text", "text": EXTRACTION_PROMPT}]}]
    try:
        resp = httpx.post(
            ai.ANTHROPIC_API_URL,
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": ai.DEFAULT_MODEL, "max_tokens": 1024, "messages": messages},
            timeout=60.0,
        )
        resp.raise_for_status()
        body = resp.json()
        text = "".join(
            b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"
        )
        parsed = _extract_json(text)
        if parsed:
            return _normalize(parsed)
    except Exception:  # noqa: BLE001 - 失敗時はヒューリスティックにフォールバック
        return None
    return None


# --------------------------------------------------------------------------- #
# ヒューリスティック（LLM 無しのフォールバック）
# --------------------------------------------------------------------------- #
def _to_text(filename: str, content_type: str, data: bytes) -> str:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".pdf" or content_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            return ""
    if ext in IMAGE_MEDIA or (content_type or "").startswith("image/"):
        return ""  # 画像は OCR 不可（LLM が必要）
    return data.decode("utf-8", errors="ignore")


# 簡易辞書：テキストに含まれていれば拾う代表的な飲食店スキル
_SKILL_VOCAB = [
    "ホール接客", "接客", "レジ", "ドリンク", "配膳", "多言語接客",
    "調理", "仕込み", "焼き場", "揚げ場", "盛り付け", "寿司握り", "魚さばき",
    "製菓", "パティシエ", "バリスタ", "ラテアート", "ソムリエ", "ワイン",
    "メニュー開発", "原価管理", "店舗管理", "シフト管理", "在庫管理",
    "衛生管理", "発注", "洗い場", "マネジメント",
]


def _heuristic_parse(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if not text.strip():
        return _normalize(fields)

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 氏名: 「氏名」「名前」ラベル、無ければ先頭行
    for l in lines[:15]:
        m = re.search(r"(?:氏\s*名|名\s*前|Name)[:：\s]*([^\s／/]+(?:\s+[^\s／/]+)?)", l)
        if m:
            fields["name"] = m.group(1).strip()
            break
    if "name" not in fields and lines:
        fields["name"] = lines[0][:20]

    m = re.search(r"(?:フリガナ|ふりがな|カナ)[:：\s]*([ァ-ヶ゛゜ー\sぁ-ん]+)", text)
    if m:
        fields["kana"] = m.group(1).strip()

    m = re.search(r"(?:実務)?経験\s*(?:年数)?[:：\s]*約?\s*(\d+(?:\.\d+)?)\s*年", text)
    if m:
        fields["experience_years"] = float(m.group(1))

    m = re.search(r"(?:希望(?:年収)?|年収)[:：\s]*(\d{2,4})\s*万", text)
    if m:
        fields["desired_salary"] = int(m.group(1))

    m = re.search(r"(?:希望(?:勤務地)?|勤務地|居住地|住所)[:：\s]*([^\s／/,、\n]{2,10})", text)
    if m:
        fields["location"] = m.group(1).strip()

    found = [s for s in _SKILL_VOCAB if s in text]
    if found:
        fields["skills"] = [{"name": s, "level": 3} for s in found]

    # プロフィール: 全文の冒頭を要約代わりに
    summary = " ".join(lines)[:200]
    fields["profile"] = summary

    return _normalize(fields)


def parse_resume(filename: str, content_type: str, data: bytes) -> tuple[dict[str, Any], str]:
    """履歴書を解析してフォーム下書きを返す.

    戻り値: (fields, source)。source は "ai" または "heuristic"。
    """
    if ai.is_llm_enabled():
        result = _parse_with_llm(filename, content_type, data)
        if result is not None:
            return result, "ai"
    text = _to_text(filename, content_type, data)
    return _heuristic_parse(text), "heuristic"
