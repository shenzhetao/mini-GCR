import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) if 'scripts' not in os.path.abspath(__file__) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import json
from config import RAW_DATA_DIR, ITEM2TOKENS_FILE, TOKEN2ITEM_FILE, CODEBOOK_SIZE, TOKENS_PER_ITEM

def tokenize_items():
    raw_file = RAW_DATA_DIR / "tmall_sample.csv"
    if not raw_file.exists():
        return
        
    df = pd.read_csv(raw_file)
    unique_items = df['item_id'].unique()
    
    item2tokens = {}
    token2item = {}
    
    # Simple strategy: convert item ID to base-CODEBOOK_SIZE
    for item_id in unique_items:
        item_id_int = int(item_id)
        val = item_id_int
        tokens = []
        for _ in range(TOKENS_PER_ITEM):
            tokens.append(val % CODEBOOK_SIZE)
            val = val // CODEBOOK_SIZE
        
        # Pad or truncate (our mock item ids are small, so 3 tokens is enough)
        tokens = tokens[::-1] # high order first
        item2tokens[str(item_id)] = tokens
        token2item[str(tokens)] = int(item_id)
        
    with open(ITEM2TOKENS_FILE, "w") as f:
        json.dump(item2tokens, f)
        
    with open(TOKEN2ITEM_FILE, "w") as f:
        json.dump(token2item, f)
        
    print(f"Saved token mapping to {ITEM2TOKENS_FILE} and {TOKEN2ITEM_FILE}")

if __name__ == "__main__":
    tokenize_items()
