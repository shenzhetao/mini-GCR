import json
import pandas as pd
from config import REASON_TEMPLATES_FILE, RAW_DATA_DIR

class ReasonGenerator:
    def __init__(self):
        if REASON_TEMPLATES_FILE.exists():
            with open(REASON_TEMPLATES_FILE, "r", encoding="utf-8") as f:
                self.templates = json.load(f)
        else:
            self.templates = {}
            
        raw_file = RAW_DATA_DIR / "tmall_sample.csv"
        if raw_file.exists():
            df = pd.read_csv(raw_file)
            if 'title' not in df.columns:
                df['title'] = df['item_id'].apply(lambda x: f"Item {x}")
            if 'category' not in df.columns:
                df['category'] = '未知分类'
            self.item_info = df.drop_duplicates(subset=['item_id']).set_index('item_id').to_dict('index')
        else:
            self.item_info = {}

    def generate(self, core_item_id, comp_item_id):
        core_info = self.item_info.get(int(core_item_id), {})
        comp_info = self.item_info.get(int(comp_item_id), {})
        
        core_cat = core_info.get('category', '未知分类')
        comp_cat = comp_info.get('category', '未知分类')
        core_name = core_info.get('title', '该商品')
        comp_name = comp_info.get('title', '推荐商品')
        
        key = f"{core_cat}_{comp_cat}"
        tmpl = self.templates.get(key, "为您推荐一款搭配商品：{comp_item_name}。")
        
        reason = tmpl.format(
            core_category=core_cat,
            comp_category=comp_cat,
            core_item_name=core_name,
            comp_item_name=comp_name
        )
        return reason
