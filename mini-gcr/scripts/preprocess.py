import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) if 'scripts' not in os.path.abspath(__file__) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import ast
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR, USER_SEQ_FILE, SPLITS_DIR, TRAIN_FILE, VAL_FILE, TEST_FILE

def preprocess_data():
    raw_file = RAW_DATA_DIR / "tmall_sample.csv"
    if not raw_file.exists():
        print("Raw data not found. Run generate_mock_data.py first.")
        return
        
    df = pd.read_csv(raw_file)
    
    # Clean and filter
    df = df.dropna(subset=['user_id', 'item_id'])
    if 'action' in df.columns:
        df = df[df['action'] == 2]
    if 'vtime' in df.columns:
        df['vtime'] = pd.to_numeric(df['vtime'], errors='coerce')
        df = df.dropna(subset=['vtime'])
    
    # Filter interactions < 3
    for _ in range(2):
        user_counts = df['user_id'].value_counts()
        item_counts = df['item_id'].value_counts()
        valid_users = user_counts[user_counts >= 3].index
        valid_items = item_counts[item_counts >= 3].index
        df = df[df['user_id'].isin(valid_users) & df['item_id'].isin(valid_items)]
    if df.empty:
        print("No valid interactions after filtering.")
        return
    
    # Sort by time
    df = df.sort_values(by=['user_id', 'vtime'])
    
    # Construct sequence
    seq_df = df.groupby('user_id')['item_id'].apply(list).reset_index()
    
    # Truncate to max length 20
    # Actually, we should keep the last 20
    seq_df['item_seq'] = seq_df['item_id'].apply(lambda x: x[-20:])
    seq_df = seq_df.drop(columns=['item_id'])
    
    seq_df.to_csv(USER_SEQ_FILE, index=False)
    print(f"Saved user sequences to {USER_SEQ_FILE}")
    
    # Train/Val/Test split (Leave-one-out or Time-based)
    # We will use simple leave-one-out for the sake of simplicity
    train_data, val_data, test_data = [], [], []
    for _, row in seq_df.iterrows():
        seq = row['item_seq']
        if len(seq) < 3:
            continue
        
        train_seq = seq[:-2]
        val_seq = seq[:-1]
        test_seq = seq
        
        train_data.append({'user_id': row['user_id'], 'item_seq': train_seq})
        val_data.append({'user_id': row['user_id'], 'item_seq': val_seq})
        test_data.append({'user_id': row['user_id'], 'item_seq': test_seq})
        
    pd.DataFrame(train_data).to_csv(TRAIN_FILE, index=False)
    pd.DataFrame(val_data).to_csv(VAL_FILE, index=False)
    pd.DataFrame(test_data).to_csv(TEST_FILE, index=False)
    
    print(f"Data splits saved to {SPLITS_DIR}")

if __name__ == "__main__":
    preprocess_data()
