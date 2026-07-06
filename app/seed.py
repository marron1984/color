"""デモ用シードデータの投入.

    python -m app.seed

既存データを消して、クライアント・人材・求人のサンプルを作成する。
建設・製造系の「職人」を中心にした例。
"""
from __future__ import annotations

from app.database import SessionLocal, init_db
from app import models


CLIENTS = [
    dict(name="株式会社ミナト建設", kind="existing", industry="建設",
         contact_name="港 一郎", contact_email="minato@example.com", phone="03-1000-0001",
         notes="新規開業の現場向けに職人を補充したい"),
    dict(name="あおぞら製作所", kind="new", industry="製造",
         contact_name="青空 花子", contact_email="aozora@example.com", phone="06-2000-0002",
         notes="SNS 広告経由の新規開拓"),
    dict(name="さくら内装", kind="existing", industry="内装",
         contact_name="佐倉 健", contact_email="sakura@example.com", phone="052-3000-0003",
         notes="繁忙期の補充スタッフ"),
]

TALENTS = [
    dict(name="田中 太郎", kana="タナカ タロウ",
         skills=[{"name": "溶接", "level": 5}, {"name": "鉄骨組立", "level": 4}, {"name": "図面読解", "level": 3}],
         experience_years=12, desired_salary=480, type_os="現場リーダー", work_style="onsite",
         location="東京", availability="available",
         profile="鉄骨工事一筋12年。班長経験あり。安全管理に強み。"),
    dict(name="鈴木 次郎", kana="スズキ ジロウ",
         skills=[{"name": "溶接", "level": 3}, {"name": "配管", "level": 4}],
         experience_years=6, desired_salary=380, type_os="職人", work_style="onsite",
         location="神奈川", availability="available",
         profile="配管と溶接が得意。丁寧な仕事で評価が高い。"),
    dict(name="高橋 三郎", kana="タカハシ サブロウ",
         skills=[{"name": "CNC加工", "level": 5}, {"name": "図面読解", "level": 4}, {"name": "品質管理", "level": 3}],
         experience_years=15, desired_salary=520, type_os="職人", work_style="onsite",
         location="大阪", availability="available",
         profile="精密機械加工のスペシャリスト。CNC 全般に精通。"),
    dict(name="伊藤 四郎", kana="イトウ シロウ",
         skills=[{"name": "内装仕上げ", "level": 4}, {"name": "クロス貼り", "level": 5}],
         experience_years=8, desired_salary=400, type_os="職人", work_style="onsite",
         location="愛知", availability="available",
         profile="内装仕上げ・クロスのプロ。工期厳守。"),
    dict(name="渡辺 五郎", kana="ワタナベ ゴロウ",
         skills=[{"name": "電気工事", "level": 4}, {"name": "配管", "level": 2}],
         experience_years=5, desired_salary=360, type_os="職人", work_style="both",
         location="東京", availability="assigned",
         profile="第二種電気工事士。現在は別現場に稼働中。"),
    dict(name="山本 六郎", kana="ヤマモト ロクロウ",
         skills=[{"name": "溶接", "level": 4}, {"name": "鉄骨組立", "level": 5}, {"name": "クレーン操作", "level": 3}],
         experience_years=10, desired_salary=450, type_os="現場リーダー", work_style="onsite",
         location="埼玉", availability="available",
         profile="鉄骨組立とクレーン操作が可能。まとめ役も担える。"),
    dict(name="中村 七海", kana="ナカムラ ナナミ",
         skills=[{"name": "品質管理", "level": 5}, {"name": "図面読解", "level": 4}, {"name": "CAD", "level": 4}],
         experience_years=7, desired_salary=430, type_os="管理", work_style="both",
         location="大阪", availability="available",
         profile="品質管理と CAD に強み。製造現場の改善提案が得意。"),
]

# (client index, job) — client index は CLIENTS のインデックス
JOBS = [
    (0, dict(title="鉄骨溶接工（現場リーダー候補）",
             required_skills=[{"name": "溶接", "weight": 3, "min_level": 4},
                              {"name": "鉄骨組立", "weight": 2, "min_level": 3},
                              {"name": "図面読解", "weight": 1, "min_level": 2}],
             offered_salary=500, type_os="現場リーダー", work_style="onsite",
             location="東京", headcount=2,
             description="新規現場の立ち上げに伴う鉄骨溶接工。班をまとめられる方歓迎。")),
    (1, dict(title="精密機械加工オペレーター",
             required_skills=[{"name": "CNC加工", "weight": 3, "min_level": 4},
                              {"name": "品質管理", "weight": 2, "min_level": 3},
                              {"name": "図面読解", "weight": 1, "min_level": 3}],
             offered_salary=520, type_os="職人", work_style="onsite",
             location="大阪", headcount=1,
             description="精密部品の CNC 加工。品質管理まで一貫して担える方。")),
    (2, dict(title="内装仕上げスタッフ（繁忙期補充）",
             required_skills=[{"name": "内装仕上げ", "weight": 3, "min_level": 3},
                              {"name": "クロス貼り", "weight": 2, "min_level": 3}],
             offered_salary=410, type_os="職人", work_style="onsite",
             location="愛知", headcount=3,
             description="繁忙期の内装仕上げ補充スタッフ。即戦力歓迎。")),
]


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        # 既存データを削除（依存順に）
        db.query(models.Match).delete()
        db.query(models.Job).delete()
        db.query(models.Talent).delete()
        db.query(models.Client).delete()
        db.commit()

        clients = [models.Client(**c) for c in CLIENTS]
        db.add_all(clients)
        db.add_all(models.Talent(**t) for t in TALENTS)
        db.commit()

        for ci, job in JOBS:
            db.add(models.Job(client_id=clients[ci].id, **job))
        db.commit()

        print(f"投入完了: クライアント {len(CLIENTS)} 件 / 人材 {len(TALENTS)} 名 / 求人 {len(JOBS)} 件")
    finally:
        db.close()


if __name__ == "__main__":
    run()
