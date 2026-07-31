"""ビザ／在留資格の適格性判定エンジン（海外飲食人材紹介向け）.

国籍 × 勤務国 × 職種 × 経験 などから、想定される就労ビザ／在留資格、
要件・目安期間・スポンサー要否・実現可能性を判定する。学習データ不要の
ルールベース。日本への受入（インバウンド）と海外への送出（アウトバウンド）の
双方に対応する。

⚠️ 本判定は一般的な目安であり、正式な可否は各国の移民法・最新運用に基づき
   専門家（行政書士・移民弁護士等）や当局の確認が必要。
"""
from __future__ import annotations

from typing import Any

DISCLAIMER = "本判定は一般的な目安です。正式な可否は最新の移民法・運用に基づき専門家/当局にご確認ください。"

# 実現可能性レベル（高いほど通りやすい）
LEVEL_ORDER = {"eligible": 3, "conditional": 2, "review": 1, "difficult": 0}
LEVEL_LABEL = {
    "eligible": "可能",
    "conditional": "条件付き",
    "review": "要確認",
    "difficult": "困難",
}

# 国籍 → 国名（自国判定用の簡易対応）
_NATIONALITY_TO_COUNTRY = {
    "日本": "日本", "アメリカ": "アメリカ", "シンガポール": "シンガポール",
    "オーストラリア": "オーストラリア", "イギリス": "イギリス", "フランス": "フランス",
}

# 日本のワーキングホリデー協定の主な対象国籍
_JP_WH_NATIONALITIES = {
    "オーストラリア", "ニュージーランド", "カナダ", "韓国", "フランス", "ドイツ",
    "イギリス", "アイルランド", "台湾", "香港", "スペイン", "イタリア", "ポルトガル",
}


def _role_category(role: str) -> str:
    """職種を management / service / kitchen に大別."""
    r = role or ""
    if any(k in r for k in ["店長", "マネ", "SV", "本部", "管理", "幹部", "経営", "料理長"]):
        # 料理長はキッチン管理だが、就労資格上は現業寄りなので kitchen 扱いにする
        if "料理長" in r:
            return "kitchen"
        return "management"
    if any(k in r for k in ["ホール", "接客", "サービス", "バリスタ", "ソムリエ",
                             "レセプ", "女将", "販売", "バーテン"]):
        return "service"
    return "kitchen"


def _prog(name, level, requirements, months, sponsor, notes=""):
    return {
        "name": name,
        "level": level,
        "requirements": requirements,
        "months": months,
        "sponsor": sponsor,
        "notes": notes,
    }


# --------------------------------------------------------------------------- #
# 各国のプログラム判定
# --------------------------------------------------------------------------- #
def _japan_programs(ctx: dict[str, Any]) -> list[dict]:
    nat = ctx["nationality"]
    held = (ctx.get("held_status") or "").strip()
    cat = _role_category(ctx["role"])
    exp = ctx.get("experience_years") or 0
    jp = ctx.get("japanese_level") or 0
    progs: list[dict] = []

    if nat == "日本":
        return [_prog("在留資格不要（日本国籍）", "eligible", "—", "—", False,
                      "日本での就労に在留資格は不要。")]

    # 既に就労制限のない資格を保有
    if any(k in held for k in ["永住", "定住", "日本人の配偶者", "永住者の配偶者"]):
        return [_prog(f"{held}（就労制限なし）", "eligible", "現資格の維持", "—", False,
                      "職種を問わず就労可能。")]

    # 特定技能1号（外食業）
    if cat in ("kitchen", "service"):
        already = held.startswith("特定技能")
        progs.append(_prog(
            "特定技能1号（外食業）",
            "eligible" if already else "conditional",
            "外食業技能測定試験＋日本語試験(JFT-Basic または N4 以上)。または技能実習2号良好修了。",
            "2〜4か月",
            True,
            "受入機関の要件・支援体制が必要。既に保有なら即戦力。" if not already else "保有済みのため就労可。",
        ))

    # 技能（外国料理の調理師）
    if cat == "kitchen":
        progs.append(_prog(
            "技能（外国料理の調理師）",
            "conditional" if exp >= 10 else "review",
            "該当国料理の調理で実務経験おおむね10年以上（タイ料理は特例あり）。",
            "1〜3か月",
            True,
            f"申告経験{exp:g}年。10年未満は立証が必要。",
        ))

    # 技術・人文知識・国際業務（主に管理・企画・通訳）
    if cat in ("management", "service"):
        progs.append(_prog(
            "技術・人文知識・国際業務",
            "review",
            "大学卒/専門知識に関連する業務（管理・企画・通訳等）。単純作業・現業中心は不可。",
            "1〜3か月",
            True,
            "ホール/調理の現業が中心だと該当しにくい。学歴・職務内容の確認が必要。",
        ))

    # ワーキングホリデー
    if nat in _JP_WH_NATIONALITIES:
        progs.append(_prog(
            "ワーキングホリデー",
            "conditional",
            "対象国籍・年齢要件（概ね18〜30歳）。付随的な就労が可能。",
            "1〜2か月",
            False,
            "長期の正社員採用には不向き（滞在・就労に制限）。",
        ))

    # 留学生（資格外活動）
    progs.append(_prog(
        "留学（資格外活動許可）",
        "conditional",
        "留学生であれば週28時間以内のアルバイトが可能（長期休暇中は緩和）。",
        "即〜",
        False,
        "フルタイム採用は不可。アルバイト採用の選択肢。",
    ))
    return progs


def _singapore_programs(ctx: dict[str, Any]) -> list[dict]:
    cat = _role_category(ctx["role"])
    progs = [
        _prog("Work Permit（F&B）", "conditional",
              "対象国籍・雇用主のクォータ/レビー、指定の要件。技能・現場スタッフ向け。",
              "1〜2か月", True, "飲食の現場スタッフの一般的なルート。"),
    ]
    if cat in ("management", "kitchen"):
        progs.append(_prog("S Pass", "conditional",
                           "中技能職・最低給与基準・学歴/技能の要件。",
                           "1〜2か月", True, "経験・資格により可能性。"))
    if cat == "management":
        progs.append(_prog("Employment Pass (EP)", "conditional",
                           "管理職/専門職・最低給与基準（学歴・経験で変動）。",
                           "1〜2か月", True, "店長/幹部候補向け。"))
    return progs


def _usa_programs(ctx: dict[str, Any]) -> list[dict]:
    nat = ctx["nationality"]
    cat = _role_category(ctx["role"])
    exp = ctx.get("experience_years") or 0
    progs = []
    # E-2（条約投資家/被用者）: 日本は条約国
    if nat == "日本":
        progs.append(_prog("E-2（条約投資家/被用者）", "conditional",
                           "日本は条約国。投資を伴う事業の被用者/経営者向け。",
                           "2〜4か月", True, "日本国籍に有利なルート。"))
    if cat == "kitchen" and exp >= 8:
        progs.append(_prog("O-1（卓越した能力）", "review",
                           "受賞歴・メディア・高評価等で卓越性の立証が必要。",
                           "3〜6か月", True, "著名シェフ級向け。立証のハードル高。"))
    progs.append(_prog("H-2B（短期・非農業）", "conditional",
                       "季節性/一時的需要・労働市場テスト・年間上限。",
                       "3〜6か月", True, "通年の正規採用には不向き。"))
    if cat == "management":
        progs.append(_prog("L-1（企業内転勤）", "conditional",
                           "系列企業に1年以上在籍した管理職/専門職の転勤。",
                           "2〜4か月", True, "海外展開企業の異動向け。"))
    return progs


def _australia_programs(ctx: dict[str, Any]) -> list[dict]:
    cat = _role_category(ctx["role"])
    progs = [
        _prog("ワーキングホリデー（417/462）", "conditional",
              "対象国籍・年齢（概ね18〜30/35歳）。就労期間に制限。",
              "1〜2か月", False, "短期の就労に。"),
    ]
    if cat in ("kitchen", "management"):
        progs.append(_prog("TSS（サブクラス482）", "conditional",
                           "指定職業（Cook/Chef 等）・スポンサー・技能評価・英語要件。",
                           "2〜5か月", True, "Cook/Chef は対象職業になりやすい。"))
    return progs


_COUNTRY_HANDLERS = {
    "日本": _japan_programs,
    "シンガポール": _singapore_programs,
    "アメリカ": _usa_programs,
    "オーストラリア": _australia_programs,
}


def assess(nationality: str, country: str, role: str,
           experience_years: float = 0, japanese_level: int = 0,
           held_status: str = "") -> dict[str, Any]:
    """ビザ適格性を判定して返す."""
    country = (country or "日本").strip()
    nationality = (nationality or "").strip()
    ctx = {
        "nationality": nationality, "country": country, "role": role or "",
        "experience_years": experience_years or 0, "japanese_level": japanese_level or 0,
        "held_status": held_status or "",
    }

    handler = _COUNTRY_HANDLERS.get(country)
    if handler:
        programs = handler(ctx)
    else:
        programs = [_prog(f"{country}の就労ビザ", "review",
                          "現地の就労ビザ要件（職種・給与・スポンサー等）の確認が必要。",
                          "要確認", True, "対応国の知識ベースは順次拡充予定。")]

    # 自国での就労（在留資格不要）
    if _NATIONALITY_TO_COUNTRY.get(nationality) == country and nationality != "日本":
        programs = [_prog("就労資格不要（自国籍）", "eligible", "—", "—", False,
                          "自国のため就労ビザ不要。")] + programs

    programs.sort(key=lambda p: LEVEL_ORDER.get(p["level"], 0), reverse=True)
    best = programs[0]["level"] if programs else "review"

    # 越境要素があるか（表示要否の判断に使う）
    relevant = (nationality and nationality != "日本") or (country and country != "日本")

    return {
        "country": country,
        "level": best,
        "level_label": LEVEL_LABEL.get(best, "要確認"),
        "summary": f"{country}での就労：{LEVEL_LABEL.get(best, '要確認')}"
                   + (f"（有力: {programs[0]['name']}）" if programs else ""),
        "relevant": bool(relevant),
        "programs": programs,
        "disclaimer": DISCLAIMER,
    }


def assess_for_match(job: Any, talent: Any) -> dict[str, Any]:
    """マッチング用: 求人と人材からコンテキストを組み立てて判定."""
    jp_level = 0
    for l in (getattr(talent, "languages", None) or []):
        if l.get("name") == "日本語":
            jp_level = max(jp_level, int(l.get("level", 0) or 0))
    role = getattr(job, "type_os", "") or getattr(talent, "type_os", "")
    return assess(
        nationality=getattr(talent, "nationality", "") or "",
        country=getattr(job, "country", "日本") or "日本",
        role=role,
        experience_years=getattr(talent, "experience_years", 0) or 0,
        japanese_level=jp_level,
        held_status=getattr(talent, "visa_status", "") or "",
    )
