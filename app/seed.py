"""デモ用シードデータの投入（飲食店専門）.

    python -m app.seed          # 既存データを消して再投入
    seed_if_empty()             # データが空のときだけ投入（サーバーレス起動時に使用）

居酒屋・イタリアン・カフェ・寿司・ラーメンなど、飲食店のホール／キッチン／
店長などの人材と求人のサンプル。
"""
from __future__ import annotations

from app.database import SessionLocal, init_db
from app import models


# (client index, job) で参照するため、CLIENTS の順序は固定。
CLIENTS = [
    dict(name="居酒屋 炭火屋 蔵", kind="existing", industry="居酒屋",
         contact_name="蔵田 大介", contact_email="kura@example.com", phone="03-4000-0004",
         notes="週末のホール・キッチン補充スタッフを募集"),
    dict(name="トラットリア ソレイユ", kind="new", industry="イタリアン",
         contact_name="日野 陽子", contact_email="soleil@example.com", phone="03-5000-0005",
         notes="新規開業のイタリアン。キッチンの即戦力が必要"),
    dict(name="ひだまり珈琲", kind="existing", industry="カフェ",
         contact_name="陽田 まり", contact_email="hidamari@example.com", phone="075-6000-0006",
         notes="2号店の店長候補とバリスタを探している"),
    dict(name="鮨 なかがわ", kind="new", industry="寿司",
         contact_name="中川 修", contact_email="nakagawa@example.com", phone="03-7000-0007",
         notes="カウンター増席に伴い寿司職人を採用したい"),
    dict(name="麺屋 龍神", kind="existing", industry="ラーメン",
         contact_name="龍田 剛", contact_email="ryujin@example.com", phone="06-8000-0008",
         notes="繁忙時間帯のキッチン・ホールを補強したい"),
]

TALENTS = [
    dict(name="佐藤 みなみ", kana="サトウ ミナミ",
         skills=[{"name": "ホール接客", "level": 5}, {"name": "レジ", "level": 4},
                 {"name": "ドリンク", "level": 3}, {"name": "多言語接客", "level": 3}],
         experience_years=6, desired_salary=330, type_os="ホール", work_style="onsite",
         location="東京", availability="available",
         profile="居酒屋・ダイニングでのホール経験6年。ピーク時のオペレーションが得意。"),
    dict(name="木村 大輔", kana="キムラ ダイスケ",
         skills=[{"name": "調理", "level": 5}, {"name": "仕込み", "level": 5},
                 {"name": "メニュー開発", "level": 4}, {"name": "原価管理", "level": 3}],
         experience_years=14, desired_salary=480, type_os="調理長", work_style="onsite",
         location="東京", availability="available",
         profile="イタリアン・和食の調理長経験。原価を抑えたメニュー設計が強み。"),
    dict(name="林 さくら", kana="ハヤシ サクラ",
         skills=[{"name": "バリスタ", "level": 5}, {"name": "ラテアート", "level": 5},
                 {"name": "ホール接客", "level": 4}],
         experience_years=5, desired_salary=310, type_os="バリスタ", work_style="onsite",
         location="京都", availability="available",
         profile="スペシャルティコーヒー店で5年。ラテアート大会入賞歴あり。"),
    dict(name="岡田 亮", kana="オカダ リョウ",
         skills=[{"name": "店舗管理", "level": 4}, {"name": "原価管理", "level": 4},
                 {"name": "ホール接客", "level": 4}, {"name": "シフト管理", "level": 4},
                 {"name": "調理", "level": 3}],
         experience_years=9, desired_salary=450, type_os="店長", work_style="onsite",
         location="京都", availability="available",
         profile="カフェ・レストランの店長経験9年。売上管理とスタッフ育成に強み。"),
    dict(name="清水 ゆい", kana="シミズ ユイ",
         skills=[{"name": "ホール接客", "level": 3}, {"name": "レジ", "level": 3}],
         experience_years=2, desired_salary=270, type_os="ホール", work_style="onsite",
         location="東京", availability="available",
         profile="カフェのアルバイト経験2年。明るい接客で即日勤務可能。"),
    dict(name="森 健太", kana="モリ ケンタ",
         skills=[{"name": "調理", "level": 4}, {"name": "仕込み", "level": 4},
                 {"name": "衛生管理", "level": 3}],
         experience_years=7, desired_salary=390, type_os="キッチン", work_style="onsite",
         location="東京", availability="assigned",
         profile="イタリアンのキッチン7年。パスタ・前菜が得意。現在は別店舗に稼働中。"),
    dict(name="中川 寿一", kana="ナカガワ ジュイチ",
         skills=[{"name": "寿司握り", "level": 5}, {"name": "魚さばき", "level": 5},
                 {"name": "仕込み", "level": 5}, {"name": "接客", "level": 4}],
         experience_years=18, desired_salary=560, type_os="寿司職人", work_style="onsite",
         location="東京", availability="available",
         profile="老舗寿司店で18年。カウンターでの握り・接客に定評。"),
    dict(name="高橋 舞", kana="タカハシ マイ",
         skills=[{"name": "製菓", "level": 5}, {"name": "パティシエ", "level": 5},
                 {"name": "盛り付け", "level": 4}],
         experience_years=8, desired_salary=400, type_os="パティシエ", work_style="onsite",
         location="大阪", availability="available",
         profile="ホテル・専門店でのパティシエ経験8年。季節のデセール開発が得意。"),
    dict(name="山下 玲", kana="ヤマシタ レイ",
         skills=[{"name": "ソムリエ", "level": 5}, {"name": "ワイン", "level": 5},
                 {"name": "ホール接客", "level": 4}, {"name": "多言語接客", "level": 4}],
         experience_years=10, desired_salary=470, type_os="ソムリエ", work_style="onsite",
         location="東京", availability="available",
         profile="フレンチ・イタリアンでソムリエ10年。ペアリング提案と英語接客が可能。"),
    dict(name="井上 大和", kana="イノウエ ヤマト",
         skills=[{"name": "洗い場", "level": 4}, {"name": "仕込み", "level": 3},
                 {"name": "衛生管理", "level": 3}],
         experience_years=3, desired_salary=280, type_os="キッチン補助", work_style="onsite",
         location="東京", availability="available",
         profile="洗い場・仕込み補助を中心にキッチン全般をサポート。即日勤務可。"),
    dict(name="渡辺 彩", kana="ワタナベ アヤ",
         skills=[{"name": "店舗管理", "level": 3}, {"name": "シフト管理", "level": 4},
                 {"name": "ホール接客", "level": 4}, {"name": "在庫管理", "level": 3}],
         experience_years=6, desired_salary=400, type_os="副店長", work_style="onsite",
         location="大阪", availability="available",
         profile="カフェチェーンで副店長を経験。シフト・在庫管理とホール運営が得意。"),
]

# (client index, job) — client index は CLIENTS のインデックス
JOBS = [
    (0, dict(title="居酒屋ホールスタッフ（週末中心）",
             required_skills=[{"name": "ホール接客", "weight": 3, "min_level": 3},
                              {"name": "レジ", "weight": 1, "min_level": 2}],
             offered_salary=330, type_os="ホール", work_style="onsite",
             location="東京", headcount=3,
             description="繁忙な金土日を中心にホールを担当。ピーク時対応ができる方歓迎。")),
    (1, dict(title="イタリアン キッチンスタッフ（調理）",
             required_skills=[{"name": "調理", "weight": 3, "min_level": 4},
                              {"name": "仕込み", "weight": 2, "min_level": 3},
                              {"name": "メニュー開発", "weight": 1, "min_level": 2}],
             offered_salary=470, type_os="調理長", work_style="onsite",
             location="東京", headcount=1,
             description="新規開業イタリアンのキッチン中核。仕込みからメニュー提案まで。")),
    (2, dict(title="カフェ 店長候補",
             required_skills=[{"name": "店舗管理", "weight": 3, "min_level": 3},
                              {"name": "原価管理", "weight": 2, "min_level": 3},
                              {"name": "ホール接客", "weight": 1, "min_level": 3}],
             offered_salary=440, type_os="店長", work_style="onsite",
             location="京都", headcount=1,
             description="2号店の店長候補。売上・原価管理とスタッフ育成をお任せします。")),
    (2, dict(title="カフェ バリスタ",
             required_skills=[{"name": "バリスタ", "weight": 3, "min_level": 4},
                              {"name": "ラテアート", "weight": 2, "min_level": 3},
                              {"name": "ホール接客", "weight": 1, "min_level": 3}],
             offered_salary=320, type_os="バリスタ", work_style="onsite",
             location="京都", headcount=1,
             description="スペシャルティコーヒーの抽出とラテアート。接客も含めお任せします。")),
    (3, dict(title="寿司職人（カウンター）",
             required_skills=[{"name": "寿司握り", "weight": 3, "min_level": 4},
                              {"name": "魚さばき", "weight": 2, "min_level": 3},
                              {"name": "仕込み", "weight": 1, "min_level": 3}],
             offered_salary=540, type_os="寿司職人", work_style="onsite",
             location="東京", headcount=1,
             description="カウンターでの握りと接客。仕入れ・仕込みまで担える方を歓迎。")),
    (4, dict(title="ラーメン店 キッチンスタッフ",
             required_skills=[{"name": "調理", "weight": 3, "min_level": 3},
                              {"name": "仕込み", "weight": 2, "min_level": 3},
                              {"name": "衛生管理", "weight": 1, "min_level": 2}],
             offered_salary=360, type_os="キッチン", work_style="onsite",
             location="東京", headcount=2,
             description="繁忙時間帯の調理・仕込みを担当。未経験可、研修あり。")),
]


def _populate(db) -> None:
    """CLIENTS / TALENTS / JOBS を DB に投入する."""
    clients = [models.Client(**c) for c in CLIENTS]
    db.add_all(clients)
    db.add_all(models.Talent(**t) for t in TALENTS)
    db.commit()

    for ci, job in JOBS:
        db.add(models.Job(client_id=clients[ci].id, **job))
    db.commit()


def run() -> None:
    """既存データを消してから再投入する（CLI 用）."""
    init_db()
    db = SessionLocal()
    try:
        db.query(models.Match).delete()
        db.query(models.Job).delete()
        db.query(models.Talent).delete()
        db.query(models.Client).delete()
        db.commit()
        _populate(db)
        print(f"投入完了: 店舗 {len(CLIENTS)} 件 / 人材 {len(TALENTS)} 名 / 求人 {len(JOBS)} 件")
    finally:
        db.close()


def seed_if_empty() -> None:
    """データが 1 件も無いときだけデモデータを投入する.

    サーバーレスの初回起動時などに、空の画面にならないようにする。
    """
    init_db()
    db = SessionLocal()
    try:
        if db.query(models.Client).count() > 0:
            return
        _populate(db)
    finally:
        db.close()


if __name__ == "__main__":
    run()
