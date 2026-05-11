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
    
    # Reason Templates
    templates = {}
    
    # Add manual templates
    comp_rules = {
        ("Phone", "Case"): "您选购了{core_item_name}，加购{comp_item_name}，组合使用效果更佳。",
        ("Phone", "Charger"): "{core_category} 必备配件 {comp_item_name}，提升体验。",
        ("Laptop", "Accessories"): "为了您的 {core_item_name} 更好地工作，推荐 {comp_item_name}。"
    }
    
    for (core_cat, comp_cat), tmpl in comp_rules.items():
        templates[f"{core_cat}_{comp_cat}"] = tmpl
        templates[f"{comp_cat}_{core_cat}"] = tmpl # Bi-directional for simplicity
        
    with open(REASON_TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)
        
    print(f"Saved reason templates to {REASON_TEMPLATES_FILE}")

if __name__ == "__main__":
    build_complementary_pairs()
