import sys, os
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR in sys.path:
    sys.path.remove(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import pandas as pd
import numpy as np
import os
import random
import time

from config import RAW_DATA_DIR

def generate_mock_data(num_users=1000, num_items=500, num_interactions=10000):
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    
    users = np.random.randint(1, num_users + 1, num_interactions)
    items = np.random.randint(1, num_items + 1, num_interactions)
    actions = [2] * num_interactions  # 2 means purchase
    
    # Generate sequential timestamps
    start_time = int(time.time()) - 90 * 24 * 3600 # 90 days ago
    vtimes = start_time + np.random.randint(0, 90 * 24 * 3600, num_interactions)
    vtimes.sort()
    
    categories = ['Phone', 'Laptop', 'Tablet', 'Headphones', 'Accessories', 'Charger', 'Case']
    item_cats = {i: random.choice(categories) for i in range(1, num_items + 1)}
    
    titles = [f"{item_cats[i]} Product {i}" for i in items]
    
    df = pd.DataFrame({
        'user_id': users,
        'item_id': items,
        'action': actions,
        'vtime': vtimes,
        'title': titles,
        'category': [item_cats[i] for i in items]
    })
    
    file_path = RAW_DATA_DIR / "tmall_sample.csv"
    df.to_csv(file_path, index=False)
    print(f"Generated mock data at {file_path}")

if __name__ == "__main__":
    generate_mock_data()
