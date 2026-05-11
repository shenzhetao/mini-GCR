import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) if 'scripts' not in os.path.abspath(__file__) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import torch
from torch.utils.data import Dataset
import pandas as pd
import ast
import json
from config import TRAIN_FILE, VAL_FILE, ITEM2TOKENS_FILE, CODEBOOK_SIZE, TOKENS_PER_ITEM, MAX_SEQ_LENGTH, CHECKPOINTS_DIR
from config import MINGPT_EMBED_DIM, MINGPT_LAYERS, MINGPT_HEADS, MINGPT_BATCH_SIZE, MINGPT_LR, MINGPT_EPOCHS
from models.mingpt.model import GPT, GPTConfig
from models.mingpt.trainer import Trainer, TrainerConfig

class RecDataset(Dataset):
    def __init__(self, df, item2tokens, max_seq_len):
        self.data = []
        for seq_str in df['item_seq']:
            seq = ast.literal_eval(seq_str)
            if len(seq) < 2: continue
            
            tokens = []
            for item in seq:
                item_str = str(item)
                if item_str in item2tokens:
                    tokens.extend(item2tokens[item_str])
                else:
                    tokens.extend([0]*TOKENS_PER_ITEM) # unknown
            
            # Context length: (max_seq_len - 1) items * 3 tokens
            max_tokens = (max_seq_len - 1) * TOKENS_PER_ITEM
            if len(tokens) > max_tokens + TOKENS_PER_ITEM:
                tokens = tokens[-(max_tokens + TOKENS_PER_ITEM):]
                
            x = tokens[:-TOKENS_PER_ITEM]
            y = tokens[TOKENS_PER_ITEM:]
            
            # Padding
            if len(x) < max_tokens:
                pad_len = max_tokens - len(x)
                x = [0] * pad_len + x
                y = [-1] * pad_len + y # -1 ignored in loss
                
            self.data.append((torch.tensor(x, dtype=torch.long), torch.tensor(y, dtype=torch.long)))
            
    def __len__(self):
        return len(self.data)
        
    def __getitem__(self, idx):
        return self.data[idx]

def train_mingpt():
    train_df = pd.read_csv(TRAIN_FILE)
    val_df = pd.read_csv(VAL_FILE)
    
    with open(ITEM2TOKENS_FILE, "r") as f:
        item2tokens = json.load(f)
        
    train_dataset = RecDataset(train_df, item2tokens, MAX_SEQ_LENGTH)
    val_dataset = RecDataset(val_df, item2tokens, MAX_SEQ_LENGTH)
    
    mconf = GPTConfig(vocab_size=CODEBOOK_SIZE, block_size=(MAX_SEQ_LENGTH-1)*TOKENS_PER_ITEM,
                      n_layer=MINGPT_LAYERS, n_head=MINGPT_HEADS, n_embd=MINGPT_EMBED_DIM)
    model = GPT(mconf)
    
    tconf = TrainerConfig(max_epochs=MINGPT_EPOCHS, batch_size=MINGPT_BATCH_SIZE, learning_rate=MINGPT_LR,
                          num_workers=0, ckpt_path=str(CHECKPOINTS_DIR / "mingpt.pth"))
    trainer = Trainer(model, train_dataset, val_dataset, tconf)
    trainer.train()
    
if __name__ == "__main__":
    train_mingpt()
