"""食べログ（tabelog.com）からの店舗情報の自動取得.

店舗ページの URL を受け取り、ページ内の構造化データ（schema.org の
JSON-LD, Restaurant）を解析して店名・ジャンル・住所・電話などを抽出する。
JSON-LD が無い場合は og:title 等をフォールバックで参照する。

注意:
- 取得は利用者が URL を指定したときにのみ 1 ページ分行う。
- 対象サイトの利用規約・robots に従って適法な範囲で利用すること。
- ネットワークが外部へ到達できない環境では取得は失敗する（その場合は
  呼び出し側でエラーを表示する）。
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def is_tabelog_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host == "tabelog.com" or host.endswith(".tabelog.com")


def _iter_jsonld(html: str):
    """HTML 内の JSON-LD オブジェクトを（@graph も展開して）列挙する."""
    for m in _JSONLD_RE.finditer(html):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack: list[Any] = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
                yield item


def _is_restaurant(obj: dict) -> bool:
    t = obj.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(k in {"Restaurant", "FoodEstablishment", "LocalBusiness"} for k in map(str, types))


def _format_address(addr: Any) -> str:
    if isinstance(addr, dict):
        parts = [addr.get("addressRegion"), addr.get("addressLocality"), addr.get("streetAddress")]
        return "".join(str(p) for p in parts if p)
    return str(addr or "").strip()


def _format_genre(v: Any) -> str:
    if isinstance(v, list):
        return "、".join(str(x) for x in v if x)
    return str(v or "").strip()


def parse_store(html: str, url: str) -> dict[str, str]:
    """HTML から店舗情報を抽出して店舗フォームの下書きを返す."""
    restaurant: dict | None = None
    for obj in _iter_jsonld(html):
        if _is_restaurant(obj):
            restaurant = obj
            break

    name = phone = genre = address = rating = ""
    if restaurant:
        name = str(restaurant.get("name") or "").strip()
        phone = str(restaurant.get("telephone") or "").strip()
        genre = _format_genre(restaurant.get("servesCuisine"))
        address = _format_address(restaurant.get("address"))
        ar = restaurant.get("aggregateRating")
        if isinstance(ar, dict) and ar.get("ratingValue"):
            count = ar.get("reviewCount") or ar.get("ratingCount") or "?"
            rating = f"{ar.get('ratingValue')}（{count}件）"

    if not name:
        m = _OG_TITLE_RE.search(html)
        if m:
            # 「店名 (エリア/ジャンル) - 食べログ」等から店名部分を取り出す
            name = re.split(r"[\(\|｜\-]", m.group(1).strip())[0].strip()

    # 業態は代表ジャンル（先頭）を採用
    industry = genre.split("、")[0] if genre else ""

    notes_parts = [f"食べログ: {url}"]
    if genre:
        notes_parts.append(f"ジャンル: {genre}")
    if address:
        notes_parts.append(f"住所: {address}")
    if rating:
        notes_parts.append(f"食べログ評価: {rating}")

    return {
        "name": name,
        "industry": industry,
        "address": address,
        "phone": phone,
        "notes": "\n".join(notes_parts),
    }


def fetch_store(url: str) -> dict[str, str]:
    """食べログの店舗 URL から店舗情報を取得する.

    ValueError: URL が食べログでない場合
    httpx.HTTPError / その他: 取得失敗（呼び出し側でハンドリング）
    """
    if not is_tabelog_url(url):
        raise ValueError("食べログ（tabelog.com）の店舗 URL を指定してください")
    resp = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"},
        timeout=20.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return parse_store(resp.text, url)
