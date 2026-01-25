"""キーワード分類の不整合を修正するスクリプト"""
from app import create_app, db
from app.models import CategoryKeyword, DisplayCategory, CategoryMapping

app = create_app()

with app.app_context():
    print("=== キーワード分類修正スクリプト ===\n")

    # 1. 訪問営業キーワードを削除
    print("1. 「訪問営業」キーワードを削除...")
    deleted = CategoryKeyword.query.filter_by(keyword='訪問営業').delete()
    print(f"   削除件数: {deleted}")

    # 2. コア業務カテゴリのIDを取得
    core_cat = DisplayCategory.query.filter_by(name='コア業務').first()
    if not core_cat:
        print("ERROR: コア業務カテゴリが見つかりません")
        exit(1)
    print(f"\n2. コア業務カテゴリID: {core_cat.id}")

    # 3. 新規キーワードを追加
    print("\n3. 新規キーワードを追加...")
    new_keywords = [
        {'keyword': '営業', 'priority': 20},
        {'keyword': '電話', 'priority': 20},
        {'keyword': 'tel', 'priority': 20},
        {'keyword': '対応', 'priority': 15},
    ]

    for kw_data in new_keywords:
        existing = CategoryKeyword.query.filter_by(keyword=kw_data['keyword']).first()
        if existing:
            print(f"   「{kw_data['keyword']}」は既に存在 (ID:{existing.id}) - スキップ")
        else:
            kw = CategoryKeyword(
                keyword=kw_data['keyword'],
                display_category_id=core_cat.id,
                match_type='contains',
                priority=kw_data['priority'],
                is_active=True
            )
            db.session.add(kw)
            print(f"   「{kw_data['keyword']}」を追加 (優先度:{kw_data['priority']})")

    # 4. 既存キーワードの優先度を更新
    print("\n4. 既存キーワードの優先度を更新...")

    priority_updates = [
        (['mtg', '面談', '打ち合わせ', '会議', 'ミーティング'], 30),
        (['移動', '出張'], 25),
        (['事務', 'チェック', '確認', '集計', '入力'], 15),
        (['その他', '雑務', '待機', '不明'], 5),
    ]

    for keywords, new_priority in priority_updates:
        updated = CategoryKeyword.query.filter(
            CategoryKeyword.keyword.in_(keywords)
        ).update({CategoryKeyword.priority: new_priority}, synchronize_session=False)
        print(f"   {keywords} -> 優先度 {new_priority} (更新: {updated}件)")

    # 5. コミット
    db.session.commit()
    print("\n5. 変更をコミットしました")

    # 6. キャッシュクリア
    CategoryMapping.clear_cache()
    print("6. 分類キャッシュをクリアしました")

    # 7. 結果確認
    print("\n=== 現在のキーワード一覧 ===")
    keywords = CategoryKeyword.query.order_by(
        CategoryKeyword.priority.desc(),
        CategoryKeyword.id
    ).all()

    for kw in keywords:
        print(f"  {kw.priority:2d}: 「{kw.keyword}」 -> {kw.display_category.name}")

    print("\n完了!")
