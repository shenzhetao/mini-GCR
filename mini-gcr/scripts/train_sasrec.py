import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) if 'scripts' not in os.path.abspath(__file__) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
import torch
import ast
import json
from config import TRAIN_FILE, VAL_FILE, SASREC_EMBED_DIM, SASREC_LAYERS, SASREC_HEADS, SASREC_BATCH_SIZE, SASREC_LR, SASREC_EPOCHS, MAX_SEQ_LENGTH, CHECKPOINTS_DIR
from models.sasrec.model import SASRec

def get_item_num(train_df):
    items = set()
    for seq in train_df['item_seq']:
        items.update(ast.literal_eval(seq))
    return max(items)

def train_sasrec():
    train_df = pd.read_csv(TRAIN_FILE)
    val_df = pd.read_csv(VAL_FILE)
    
    item_num = get_item_num(train_df)
    
    model = SASRec(item_num=item_num, max_seq_len=MAX_SEQ_LENGTH, hidden_units=SASREC_EMBED_DIM, num_blocks=SASREC_LAYERS, num_heads=SASREC_HEADS)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    optimizer = torch.optim.Adam(model.parameters(), lr=SASREC_LR)
    bce_criterion = torch.nn.BCEWithLogitsLoss()
    
    def prepare_data(df):
        seqs, pos_targets, neg_targets = [], [], []
        for seq in df['item_seq']:
            s = ast.literal_eval(seq)
            if len(s) < 2: continue
            
            # input seq
            inp = s[:-1]
            # padding
            if len(inp) < MAX_SEQ_LENGTH:
                inp = [0] * (MAX_SEQ_LENGTH - len(inp)) + inp
            else:
                inp = inp[-MAX_SEQ_LENGTH:]
                
            # target seq
            pos = s[1:]
            if len(pos) < MAX_SEQ_LENGTH:
                pos = [0] * (MAX_SEQ_LENGTH - len(pos)) + pos
            else:
                pos = pos[-MAX_SEQ_LENGTH:]
                
            neg = [np.random.randint(1, item_num + 1) for _ in pos]
            
            seqs.append(inp)
            pos_targets.append(pos)
            neg_targets.append(neg)
        return torch.LongTensor(seqs), torch.LongTensor(pos_targets), torch.LongTensor(neg_targets)

    train_seqs, train_pos, train_neg = prepare_data(train_df)
    dataset = torch.utils.data.TensorDataset(train_seqs, train_pos, train_neg)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=SASREC_BATCH_SIZE, shuffle=True)
    
    model.train()
    for epoch in range(SASREC_EPOCHS):
        total_loss = 0
        for seq, pos, neg in dataloader:
            seq, pos, neg = seq.to(device), pos.to(device), neg.to(device)
            log_feats = model(seq)
            
            pos_embs = model.item_emb(pos)
            neg_embs = model.item_emb(neg)
            
            pos_logits = (log_feats * pos_embs).sum(dim=-1)
            neg_logits = (log_feats * neg_embs).sum(dim=-1)
            
            pos_labels = torch.ones(pos_logits.shape, device=device)
            neg_labels = torch.zeros(neg_logits.shape, device=device)
            
            indices = torch.where(pos != 0)
            loss = bce_criterion(pos_logits[indices], pos_labels[indices]) + \
                   bce_criterion(neg_logits[indices], neg_labels[indices])
                   
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            
        print(f"Epoch {epoch+1}/{SASREC_EPOCHS}, Loss: {total_loss/len(dataloader)}")
        
    torch.save(model.state_dict(), CHECKPOINTS_DIR / "sasrec.pth")
    print("Saved SASRec model")

if __name__ == "__main__":
    train_sasrec()
