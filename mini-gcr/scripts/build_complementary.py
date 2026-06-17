import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) if 'scripts' not in os.path.abspath(__file__) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import json
from itertools import combinations
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR, COMPLEMENTARY_PAIRS_FILE, REASON_TEMPLATES_FILE

def build_complementary_pairs():
    raw_file = RAW_DATA_DIR / "tmall_sample.csv"
    if not raw_file.exists():
        print("Raw data not found.")
        return
        
    df = pd.read_csv(raw_file)
    
    if 'vtime' in df.columns:
        df['vtime'] = pd.to_numeric(df['vtime'], errors='coerce')
        df = df.dropna(subset=['vtime'])
    if 'category' not in df.columns:
        df['category'] = 'Unknown'
    if 'title' not in df.columns:
        df['title'] = df['item_id'].apply(lambda x: f"Item {x}")

    # Simple rule: same user, different categories, close in time (we ignore time for mock)
    # Just co-occurrence based
    
    item_cats = dict(zip(df['item_id'], df['category']))
    item_titles = dict(zip(df['item_id'], df['title']))
    
    df = df.sort_values(by=['user_id', 'vtime'])
    
    pair_counts = {}
    for _, user_df in df.groupby('user_id'):
        rows = user_df[['item_id', 'category', 'vtime']].to_dict('records')
        for left, right in zip(rows, rows[1:]):
            if abs(right['vtime'] - left['vtime']) <= 7 * 24 * 3600 and left['category'] != right['category']:
                pair = tuple(sorted([int(left['item_id']), int(right['item_id'])]))
                pair_counts[pair] = pair_counts.get(pair, 0) + 2
        items = user_df['item_id'].tolist()
        unique_items = list(set(items))
        for a, b in combinations(unique_items, 2):
            if item_cats.get(a) != item_cats.get(b):
                # Sorting to keep order consistent
                pair = tuple(sorted([a, b]))
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
                
    # Filter by min count
    valid_pairs = []
    for (a, b), count in pair_counts.items():
        if count >= 2: # Mock threshold
            valid_pairs.append({'item_a': a, 'item_b': b, 'confidence': min(count / 10.0, 0.99)})
    if not valid_pairs:
        category_rules = {("Phone", "Case"), ("Phone", "Charger"), ("Laptop", "Accessories"), ("Tablet", "Case"), ("Headphones", "Charger")}
        items_by_category = df.drop_duplicates(subset=['item_id']).groupby('category')['item_id'].apply(list).to_dict()
        for core_cat, comp_cat in category_rules:
            for a in items_by_category.get(core_cat, [])[:20]:
                for b in items_by_category.get(comp_cat, [])[:20]:
                    valid_pairs.append({'item_a': int(a), 'item_b': int(b), 'confidence': 0.8})
            
    pairs_df = pd.DataFrame(valid_pairs)
    pairs_df.to_csv(COMPLEMENTARY_PAIRS_FILE, index=False)
    print(f"Saved complementary pairs to {COMPLEMENTARY_PAIRS_FILE}")
    
    # Reason Templates (P1-2: expanded to cover all 7 categories * 6 = 42 pairs)
    templates = {}

    # Map: (core_category, comp_category) -> list of candidate templates.
    # Multiple templates per pair so the reason generator can pick one
    # pseudo-randomly and avoid verbatim repetition across a session.
    comp_rules = {
        ("Phone", "Case"): [
            "您选购了{core_item_name}，加购{comp_item_name}，组合使用效果更佳。",
            "{core_category} 专属 {comp_item_name}，贴合机型、保护到位。",
            "为您的 {core_item_name} 选配 {comp_item_name}，日常更安心。",
        ],
        ("Phone", "Charger"): [
            "{core_category} 必备配件 {comp_item_name}，提升体验。",
            "快充常伴，{comp_item_name} 让 {core_item_name} 时刻满电。",
            "出差旅行带上 {comp_item_name}，{core_item_name} 续航更持久。",
        ],
        ("Phone", "Headphones"): [
            "为 {core_item_name} 选配 {comp_item_name}，通勤追剧更沉浸。",
            "{comp_item_name} 与 {core_item_name} 配合，影音体验升级。",
        ],
        ("Phone", "Accessories"): [
            "搭配 {comp_item_name}，让 {core_item_name} 更好用。",
            "为 {core_item_name} 增加一件 {comp_item_name}，使用更顺手。",
        ],
        ("Laptop", "Accessories"): [
            "为了您的 {core_item_name} 更好地工作，推荐 {comp_item_name}。",
            "办公学习好搭档，{comp_item_name} 让 {core_item_name} 如虎添翼。",
            "升级您的桌面装备，{comp_item_name} 与 {core_item_name} 配套使用。",
        ],
        ("Laptop", "Charger"): [
            "为 {core_item_name} 备一个 {comp_item_name}，随时随地续航。",
            "{comp_item_name} 让 {core_item_name} 不断电，差旅好物。",
        ],
        ("Laptop", "Case"): [
            "为 {core_item_name} 选配 {comp_item_name}，携带更安心。",
        ],
        ("Tablet", "Case"): [
            "为 {core_item_name} 选配 {comp_item_name}，屏幕与机身双保护。",
            "日常携带更安全，{comp_item_name} 是 {core_item_name} 的好搭档。",
        ],
        ("Tablet", "Charger"): [
            "为 {core_item_name} 配备 {comp_item_name}，续航无忧。",
        ],
        ("Tablet", "Accessories"): [
            "搭配 {comp_item_name}，让 {core_item_name} 更好用。",
        ],
        ("Headphones", "Charger"): [
            "为 {core_item_name} 备一个 {comp_item_name}，续航更安心。",
            "{comp_item_name} 让 {core_item_name} 持续在线，听感不断。",
        ],
        ("Headphones", "Case"): [
            "为 {core_item_name} 选配 {comp_item_name}，收纳更方便。",
        ],
        ("Headphones", "Accessories"): [
            "为 {core_item_name} 添置 {comp_item_name}，使用更顺手。",
        ],
        ("Case", "Phone"): [
            "为 {core_item_name} 配一台 {comp_item_name}，壳与机更搭配。",
        ],
        ("Case", "Tablet"): [
            "{comp_item_name} 与 {core_item_name} 是经典搭配，影音学习更舒心。",
        ],
        ("Charger", "Phone"): [
            "为 {core_item_name} 选一台 {comp_item_name}，快充常伴。",
        ],
        ("Charger", "Laptop"): [
            "{comp_item_name} 让 {core_item_name} 续航更持久。",
        ],
        ("Charger", "Tablet"): [
            "搭配 {comp_item_name}，{core_item_name} 续航不焦虑。",
        ],
        ("Charger", "Headphones"): [
            "{comp_item_name} 让 {core_item_name} 听歌追剧更畅快。",
        ],
        ("Accessories", "Phone"): [
            "为 {core_item_name} 选一台 {comp_item_name}，使用更顺手。",
        ],
        ("Accessories", "Laptop"): [
            "为 {core_item_name} 配套 {comp_item_name}，办公更高效。",
        ],
        ("Accessories", "Tablet"): [
            "{comp_item_name} 让 {core_item_name} 更好用。",
        ],
        ("Accessories", "Headphones"): [
            "为 {core_item_name} 添置 {comp_item_name}，听感更出色。",
        ],
    }

    # Register the first template of each pair as the canonical entry, then
    # store alternates under "<core>_<comp>__altN" so that ReasonGenerator
    # can rotate among them.
    for (core_cat, comp_cat), tmpl_list in comp_rules.items():
        key = f"{core_cat}_{comp_cat}"
        templates[key] = tmpl_list[0]
        for i, alt in enumerate(tmpl_list[1:], start=1):
            templates[f"{key}__alt{i}"] = alt
        # Bi-directional: also expose the inverse key with its own alternates.
        inv_key = f"{comp_cat}_{core_cat}"
        if inv_key not in templates:
            templates[inv_key] = tmpl_list[0]
            for i, alt in enumerate(tmpl_list[1:], start=1):
                templates[f"{inv_key}__alt{i}"] = alt
        
    with open(REASON_TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)
        
    print(f"Saved reason templates to {REASON_TEMPLATES_FILE}")

if __name__ == "__main__":
    build_complementary_pairs()
