"""デモ用シードデータの投入（飲食店・海外人材紹介対応）.

    python -m app.seed          # 既存データを消して再投入
    seed_if_empty()             # データが空のときだけ投入（サーバーレス起動時に使用）

企業（店舗）10 / 人材 10 / 求人 10。国内外の飲食店、外国籍スタッフ
（特定技能 等）・海外志向の日本人スタッフを含む。
"""
from __future__ import annotations

from app.database import SessionLocal, init_db
from app import models


# (client index, job) で参照するため、CLIENTS の順序は固定。
CLIENTS = [
    dict(name="居酒屋 炭火屋 蔵", kind="existing", industry="居酒屋",
         address="東京都新宿区歌舞伎町1-2-3", contact_name="蔵田 大介",
         contact_email="kura@example.com", phone="03-4000-0004",
         notes="週末のホール・キッチン補充スタッフを募集"),
    dict(name="トラットリア ソレイユ", kind="new", industry="イタリアン",
         address="東京都渋谷区神南1-4-5", contact_name="日野 陽子",
         contact_email="soleil@example.com", phone="03-5000-0005",
         notes="新規開業のイタリアン。キッチンの即戦力が必要"),
    dict(name="ひだまり珈琲", kind="existing", industry="カフェ",
         address="京都府京都市中京区寺町通1-6", contact_name="陽田 まり",
         contact_email="hidamari@example.com", phone="075-6000-0006",
         notes="2号店の店長候補とバリスタを探している"),
    dict(name="鮨 なかがわ", kind="new", industry="寿司",
         address="東京都中央区銀座5-7-8", contact_name="中川 修",
         contact_email="nakagawa@example.com", phone="03-7000-0007",
         notes="カウンター増席に伴い寿司職人を採用したい"),
    dict(name="麺屋 龍神", kind="existing", industry="ラーメン",
         address="大阪府大阪市北区梅田2-9-10", contact_name="龍田 剛",
         contact_email="ryujin@example.com", phone="06-8000-0008",
         notes="繁忙時間帯のキッチン・ホールを補強。特定技能の受入可"),
    dict(name="焼肉 大将", kind="existing", industry="焼肉",
         address="東京都豊島区東池袋1-11-12", contact_name="大将 健一",
         contact_email="taisho@example.com", phone="03-9000-0011",
         notes="ディナー帯のキッチン・ホールを増員したい"),
    dict(name="ビストロ ルミエール", kind="new", industry="フレンチ",
         address="東京都港区南青山3-13-14", contact_name="光井 彩音",
         contact_email="lumiere@example.com", phone="03-9000-0012",
         notes="ソムリエとサービススタッフを募集"),
    dict(name="中華 福来菜館", kind="existing", industry="中華",
         address="神奈川県横浜市中区山下町1-15", contact_name="福田 来人",
         contact_email="fukurai@example.com", phone="045-9000-0013",
         notes="ランチ・ディナーの調理スタッフを補充"),
    # --- 海外店舗 ---
    dict(name="SAKURA Dining (Singapore)", kind="new", industry="和食（海外）",
         address="1 Orchard Road, Singapore", contact_name="Tan Wei Ming",
         contact_email="hr@sakura.sg", phone="+65-6000-0009",
         notes="シンガポール新店の日本人スタッフ・店長候補を募集。ビザ支援あり"),
    dict(name="UMAMI New York", kind="new", industry="寿司（海外）",
         address="123 5th Avenue, New York, NY", contact_name="John Carter",
         contact_email="jobs@umami.nyc", phone="+1-212-000-0010",
         notes="NYの寿司レストラン。カウンター寿司職人を海外採用。就労ビザ支援"),
]

TALENTS = [
    dict(name="佐藤 みなみ", kana="サトウ ミナミ",
         skills=[{"name": "ホール接客", "level": 5}, {"name": "レジ", "level": 4},
                 {"name": "ドリンク", "level": 3}, {"name": "多言語接客", "level": 3}],
         experience_years=6, desired_salary=330, type_os="ホール", work_style="onsite",
         location="東京", availability="available", nationality="日本",
         languages=[{"name": "日本語", "level": 5}, {"name": "英語", "level": 3}],
         visa_status="", desired_countries=["日本", "シンガポール"],
         phone="090-1111-2222", email="minami.sato@example.com", contact_note="LINE: minami_s",
         profile="居酒屋・ダイニングでのホール経験6年。ピーク時のオペレーションが得意。"),
    dict(name="木村 大輔", kana="キムラ ダイスケ",
         skills=[{"name": "調理", "level": 5}, {"name": "仕込み", "level": 5},
                 {"name": "メニュー開発", "level": 4}, {"name": "原価管理", "level": 3}],
         experience_years=14, desired_salary=480, type_os="調理長", work_style="onsite",
         location="東京", availability="available", nationality="日本",
         languages=[{"name": "日本語", "level": 5}, {"name": "英語", "level": 3},
                    {"name": "イタリア語", "level": 2}],
         visa_status="", desired_countries=["日本", "イタリア", "アメリカ"],
         profile="イタリアン・和食の調理長経験。原価を抑えたメニュー設計が強み。"),
    dict(name="林 さくら", kana="ハヤシ サクラ",
         skills=[{"name": "バリスタ", "level": 5}, {"name": "ラテアート", "level": 5},
                 {"name": "ホール接客", "level": 4}],
         experience_years=5, desired_salary=310, type_os="バリスタ", work_style="onsite",
         location="京都", availability="available", nationality="日本",
         languages=[{"name": "日本語", "level": 5}, {"name": "英語", "level": 4}],
         visa_status="", desired_countries=["日本", "オーストラリア"],
         profile="スペシャルティコーヒー店で5年。ラテアート大会入賞歴あり。"),
    dict(name="岡田 亮", kana="オカダ リョウ",
         skills=[{"name": "店舗管理", "level": 4}, {"name": "原価管理", "level": 4},
                 {"name": "ホール接客", "level": 4}, {"name": "シフト管理", "level": 4},
                 {"name": "調理", "level": 3}],
         experience_years=9, desired_salary=450, type_os="店長", work_style="onsite",
         location="京都", availability="available", nationality="日本",
         languages=[{"name": "日本語", "level": 5}, {"name": "英語", "level": 3}],
         visa_status="", desired_countries=["日本", "シンガポール"],
         profile="カフェ・レストランの店長経験9年。売上管理とスタッフ育成に強み。海外勤務も希望。"),
    dict(name="中川 寿一", kana="ナカガワ ジュイチ",
         skills=[{"name": "寿司握り", "level": 5}, {"name": "魚さばき", "level": 5},
                 {"name": "仕込み", "level": 5}, {"name": "接客", "level": 4}],
         experience_years=18, desired_salary=560, type_os="寿司職人", work_style="onsite",
         location="東京", availability="available", nationality="日本",
         languages=[{"name": "日本語", "level": 5}, {"name": "英語", "level": 3}],
         visa_status="", desired_countries=["日本", "アメリカ", "シンガポール", "UAE"],
         phone="090-3333-4444", email="juichi.nakagawa@example.com", contact_note="緊急連絡先: 03-1234-5678",
         profile="老舗寿司店で18年。カウンターでの握り・接客に定評。海外店舗にも意欲。"),
    dict(name="高橋 舞", kana="タカハシ マイ",
         skills=[{"name": "製菓", "level": 5}, {"name": "パティシエ", "level": 5},
                 {"name": "盛り付け", "level": 4}],
         experience_years=8, desired_salary=400, type_os="パティシエ", work_style="onsite",
         location="大阪", availability="available", nationality="日本",
         languages=[{"name": "日本語", "level": 5}, {"name": "英語", "level": 4},
                    {"name": "フランス語", "level": 3}],
         visa_status="", desired_countries=["日本", "フランス"],
         profile="ホテル・専門店でのパティシエ経験8年。季節のデセール開発が得意。"),
    dict(name="山下 玲", kana="ヤマシタ レイ",
         skills=[{"name": "ソムリエ", "level": 5}, {"name": "ワイン", "level": 5},
                 {"name": "ホール接客", "level": 4}, {"name": "多言語接客", "level": 4}],
         experience_years=10, desired_salary=470, type_os="ソムリエ", work_style="onsite",
         location="東京", availability="available", nationality="日本",
         languages=[{"name": "日本語", "level": 5}, {"name": "英語", "level": 5},
                    {"name": "フランス語", "level": 3}],
         visa_status="", desired_countries=["日本", "シンガポール", "香港"],
         profile="フレンチ・イタリアンでソムリエ10年。ペアリング提案と英語接客が可能。"),
    # --- 外国籍スタッフ（インバウンド） ---
    dict(name="グエン・ヴァン・ミン", kana="グエン ヴァン ミン",
         skills=[{"name": "ホール接客", "level": 3}, {"name": "調理", "level": 3},
                 {"name": "仕込み", "level": 3}],
         experience_years=3, desired_salary=300, type_os="ホール", work_style="onsite",
         location="東京", availability="available", nationality="ベトナム",
         languages=[{"name": "ベトナム語", "level": 5}, {"name": "日本語", "level": 3},
                    {"name": "英語", "level": 3}],
         visa_status="特定技能（外食業）", desired_countries=["日本"],
         phone="080-5555-6666", email="minh.nguyen@example.com", contact_note="WhatsApp: +84 90 123 4567",
         profile="ベトナム出身。日本の居酒屋で3年勤務。特定技能ビザ保有で外食業に就労可能。"),
    dict(name="リー・ウェイ", kana="リー ウェイ",
         skills=[{"name": "ホール接客", "level": 4}, {"name": "店舗管理", "level": 3},
                 {"name": "多言語接客", "level": 5}],
         experience_years=7, desired_salary=420, type_os="店長", work_style="onsite",
         location="東京", availability="available", nationality="中国",
         languages=[{"name": "中国語", "level": 5}, {"name": "日本語", "level": 4},
                    {"name": "英語", "level": 4}],
         visa_status="技術・人文知識・国際業務", desired_countries=["日本", "シンガポール"],
         phone="080-7777-8888", email="wei.li@example.com", contact_note="WeChat: liwei_88",
         profile="中国出身。インバウンド対応に強い店長候補。中・日・英のトリリンガル。"),
    dict(name="キム・ミンス", kana="キム ミンス",
         skills=[{"name": "調理", "level": 4}, {"name": "焼き場", "level": 5},
                 {"name": "仕込み", "level": 4}, {"name": "衛生管理", "level": 3}],
         experience_years=6, desired_salary=360, type_os="キッチン", work_style="onsite",
         location="東京", availability="available", nationality="韓国",
         languages=[{"name": "韓国語", "level": 5}, {"name": "日本語", "level": 3},
                    {"name": "英語", "level": 2}],
         visa_status="特定技能（外食業）", desired_countries=["日本"],
         phone="080-2222-3333", email="minsu.kim@example.com", contact_note="KakaoTalk: minsu_k",
         profile="韓国出身。焼肉・韓国料理の調理6年。焼き場と仕込みが得意。特定技能で就労可能。"),
]

# (client index, job) — client index は CLIENTS のインデックス
JOBS = [
    (0, dict(title="居酒屋ホールスタッフ（週末中心）",
             required_skills=[{"name": "ホール接客", "weight": 3, "min_level": 3},
                              {"name": "レジ", "weight": 1, "min_level": 2}],
             offered_salary=330, type_os="ホール", work_style="onsite",
             location="東京", headcount=3, country="日本",
             required_languages=[{"name": "日本語", "min_level": 3}],
             visa_support=False, currency="JPY",
             description="繁忙な金土日を中心にホールを担当。ピーク時対応ができる方歓迎。")),
    (1, dict(title="イタリアン キッチンスタッフ（調理）",
             required_skills=[{"name": "調理", "weight": 3, "min_level": 4},
                              {"name": "仕込み", "weight": 2, "min_level": 3},
                              {"name": "メニュー開発", "weight": 1, "min_level": 2}],
             offered_salary=470, type_os="調理長", work_style="onsite",
             location="東京", headcount=1, country="日本",
             required_languages=[{"name": "日本語", "min_level": 3}],
             visa_support=False, currency="JPY",
             description="新規開業イタリアンのキッチン中核。仕込みからメニュー提案まで。")),
    (2, dict(title="カフェ 店長候補",
             required_skills=[{"name": "店舗管理", "weight": 3, "min_level": 3},
                              {"name": "原価管理", "weight": 2, "min_level": 3},
                              {"name": "ホール接客", "weight": 1, "min_level": 3}],
             offered_salary=440, type_os="店長", work_style="onsite",
             location="京都", headcount=1, country="日本",
             required_languages=[{"name": "日本語", "min_level": 4}, {"name": "英語", "min_level": 3}],
             visa_support=False, currency="JPY",
             description="2号店の店長候補。売上・原価管理とスタッフ育成。インバウンド対応で英語歓迎。")),
    (2, dict(title="カフェ バリスタ",
             required_skills=[{"name": "バリスタ", "weight": 3, "min_level": 4},
                              {"name": "ラテアート", "weight": 2, "min_level": 3},
                              {"name": "ホール接客", "weight": 1, "min_level": 3}],
             offered_salary=320, type_os="バリスタ", work_style="onsite",
             location="京都", headcount=1, country="日本",
             required_languages=[{"name": "日本語", "min_level": 3}],
             visa_support=False, currency="JPY",
             description="スペシャルティコーヒーの抽出とラテアート。接客も含めお任せします。")),
    (3, dict(title="寿司職人（カウンター）",
             required_skills=[{"name": "寿司握り", "weight": 3, "min_level": 4},
                              {"name": "魚さばき", "weight": 2, "min_level": 3},
                              {"name": "仕込み", "weight": 1, "min_level": 3}],
             offered_salary=540, type_os="寿司職人", work_style="onsite",
             location="東京", headcount=1, country="日本",
             required_languages=[{"name": "日本語", "min_level": 3}],
             visa_support=False, currency="JPY",
             description="カウンターでの握りと接客。仕入れ・仕込みまで担える方を歓迎。")),
    (4, dict(title="ラーメン店 キッチンスタッフ（特定技能可）",
             required_skills=[{"name": "調理", "weight": 3, "min_level": 3},
                              {"name": "仕込み", "weight": 2, "min_level": 3},
                              {"name": "衛生管理", "weight": 1, "min_level": 2}],
             offered_salary=360, type_os="キッチン", work_style="onsite",
             location="大阪", headcount=2, country="日本",
             required_languages=[{"name": "日本語", "min_level": 3}],
             visa_support=True, currency="JPY",
             description="繁忙時間帯の調理・仕込みを担当。特定技能の外国籍の方も歓迎、ビザ支援あり。")),
    (5, dict(title="焼肉店 キッチンスタッフ（焼き場）",
             required_skills=[{"name": "調理", "weight": 2, "min_level": 3},
                              {"name": "焼き場", "weight": 3, "min_level": 3},
                              {"name": "仕込み", "weight": 1, "min_level": 3}],
             offered_salary=360, type_os="キッチン", work_style="onsite",
             location="東京", headcount=2, country="日本",
             required_languages=[{"name": "日本語", "min_level": 3}],
             visa_support=True, currency="JPY",
             description="ディナー帯の焼き場・仕込みを担当。特定技能の方も歓迎。")),
    (6, dict(title="ビストロ ソムリエ／サービス",
             required_skills=[{"name": "ソムリエ", "weight": 3, "min_level": 4},
                              {"name": "ワイン", "weight": 2, "min_level": 3},
                              {"name": "ホール接客", "weight": 1, "min_level": 3}],
             offered_salary=460, type_os="ソムリエ", work_style="onsite",
             location="東京", headcount=1, country="日本",
             required_languages=[{"name": "日本語", "min_level": 4}, {"name": "英語", "min_level": 3}],
             visa_support=False, currency="JPY",
             description="ワインのペアリング提案とサービス。外国人客も多く英語歓迎。")),
    (8, dict(title="【シンガポール】和食店 店長候補",
             required_skills=[{"name": "店舗管理", "weight": 3, "min_level": 3},
                              {"name": "ホール接客", "weight": 2, "min_level": 3},
                              {"name": "原価管理", "weight": 1, "min_level": 3}],
             offered_salary=66000, type_os="店長", work_style="onsite",
             location="シンガポール", headcount=1, country="シンガポール",
             required_languages=[{"name": "英語", "min_level": 4}, {"name": "日本語", "min_level": 3}],
             visa_support=True, currency="SGD",
             description="シンガポール新店の店長候補。就労ビザ・渡航支援あり。英語必須。")),
    (9, dict(title="【NY】寿司職人（カウンター）",
             required_skills=[{"name": "寿司握り", "weight": 3, "min_level": 4},
                              {"name": "魚さばき", "weight": 2, "min_level": 3},
                              {"name": "接客", "weight": 1, "min_level": 3}],
             offered_salary=75000, type_os="寿司職人", work_style="onsite",
             location="ニューヨーク", headcount=1, country="アメリカ",
             required_languages=[{"name": "英語", "min_level": 4}],
             visa_support=True, currency="USD",
             description="NYの寿司レストランでカウンターを担当。就労ビザ（O-1/E-2等）支援あり。")),
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
