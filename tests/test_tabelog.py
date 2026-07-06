"""食べログ店舗情報パーサのテスト（ネットワーク不要）.

実サイトへの通信は行わず、JSON-LD を含むサンプル HTML を解析して
抽出ロジックを検証する。
"""
from __future__ import annotations

from app import tabelog


SAMPLE_HTML = """
<html><head>
<meta property="og:title" content="炭火焼鳥 とりまる 渋谷店 (渋谷/焼き鳥) - 食べログ" />
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Restaurant",
  "name": "炭火焼鳥 とりまる 渋谷店",
  "telephone": "03-1234-5678",
  "servesCuisine": ["焼き鳥", "居酒屋"],
  "address": {
    "@type": "PostalAddress",
    "addressRegion": "東京都",
    "addressLocality": "渋谷区",
    "streetAddress": "道玄坂1-2-3 ビル5F"
  },
  "aggregateRating": {"@type": "AggregateRating", "ratingValue": "3.54", "reviewCount": "128"}
}
</script>
</head><body></body></html>
"""

GRAPH_HTML = """
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"BreadcrumbList","itemListElement":[]},
  {"@type":"Restaurant","name":"鮨 なかがわ","telephone":"03-9999-0000",
   "servesCuisine":"寿司",
   "address":{"@type":"PostalAddress","addressRegion":"東京都","addressLocality":"中央区","streetAddress":"銀座1-1-1"}}
]}
</script>
"""


def test_is_tabelog_url():
    assert tabelog.is_tabelog_url("https://tabelog.com/tokyo/A1301/A130101/13001111/")
    assert tabelog.is_tabelog_url("https://s.tabelog.com/tokyo/")
    assert not tabelog.is_tabelog_url("https://example.com/foo")
    assert not tabelog.is_tabelog_url("not a url")


def test_parse_store_jsonld():
    f = tabelog.parse_store(SAMPLE_HTML, "https://tabelog.com/tokyo/A/13001111/")
    assert f["name"] == "炭火焼鳥 とりまる 渋谷店"
    assert f["phone"] == "03-1234-5678"
    assert f["industry"] == "焼き鳥"                       # 代表ジャンル
    assert f["address"] == "東京都渋谷区道玄坂1-2-3 ビル5F"
    assert "ジャンル: 焼き鳥、居酒屋" in f["notes"]
    assert "食べログ評価: 3.54（128件）" in f["notes"]
    assert "tabelog.com" in f["notes"]


def test_parse_store_graph():
    f = tabelog.parse_store(GRAPH_HTML, "https://tabelog.com/tokyo/A/13002222/")
    assert f["name"] == "鮨 なかがわ"
    assert f["industry"] == "寿司"
    assert f["address"] == "東京都中央区銀座1-1-1"


def test_parse_store_fallback_og_title():
    html = '<meta property="og:title" content="カフェ ひだまり (京都/カフェ) - 食べログ" />'
    f = tabelog.parse_store(html, "https://tabelog.com/kyoto/A/13003333/")
    assert f["name"] == "カフェ ひだまり"


def test_parse_store_empty():
    f = tabelog.parse_store("<html></html>", "https://tabelog.com/x/")
    assert f["name"] == ""
