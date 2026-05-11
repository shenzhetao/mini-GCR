import torch
import torch.nn as nn

class PointWiseFeedForward(torch.nn.Module):
    def __init__(self, hidden_units, dropout_rate):
        super(PointWiseFeedForward, self).__init__()
        self.conv1 = torch.nn.Conv1d(hidden_units, hidden_units, kernel_size=1)
        self.dropout1 = torch.nn.Dropout(p=dropout_rate)
        self.relu = torch.nn.ReLU()
        self.conv2 = torch.nn.Conv1d(hidden_units, hidden_units, kernel_size=1)
        self.dropout2 = torch.nn.Dropout(p=dropout_rate)

    def forward(self, inputs):
        outputs = self.dropout2(self.conv2(self.relu(self.dropout1(self.conv1(inputs.transpose(-1, -2))))))
        outputs = outputs.transpose(-1, -2)
        outputs += inputs
        return outputs

class SASRec(torch.nn.Module):
    def __init__(self, item_num, max_seq_len, hidden_units=64, num_blocks=2, num_heads=2, dropout_rate=0.2):
        super(SASRec, self).__init__()
        self.item_num = item_num
        self.max_seq_len = max_seq_len
        self.item_emb = torch.nn.Embedding(self.item_num + 1, hidden_units, padding_idx=0)
        self.pos_emb = torch.nn.Embedding(max_seq_len, hidden_units)
        self.emb_dropout = torch.nn.Dropout(p=dropout_rate)

        self.attention_layernorms = torch.nn.ModuleList()
        self.attention_layers = torch.nn.ModuleList()
        self.forward_layernorms = torch.nn.ModuleList()
        self.forward_layers = torch.nn.ModuleList()

        for _ in range(num_blocks):
            self.attention_layernorms.append(torch.nn.LayerNorm(hidden_units))
            self.attention_layers.append(torch.nn.MultiheadAttention(hidden_units, num_heads, dropout_rate, batch_first=True))
            self.forward_layernorms.append(torch.nn.LayerNorm(hidden_units))
            self.forward_layers.append(PointWiseFeedForward(hidden_units, dropout_rate))

        self.last_layernorm = torch.nn.LayerNorm(hidden_units)

    def forward(self, log_seqs):
        device = self.item_emb.weight.device
        if torch.is_tensor(log_seqs):
            log_seqs = log_seqs.to(device=device, dtype=torch.long)
        else:
            log_seqs = torch.as_tensor(log_seqs, dtype=torch.long, device=device)
        seqs = self.item_emb(log_seqs)
        positions = torch.arange(log_seqs.shape[1], device=device).unsqueeze(0).expand(log_seqs.shape[0], -1)
        seqs += self.pos_emb(positions)
        seqs = self.emb_dropout(seqs)

        timeline_mask = log_seqs == 0
        seqs *= ~timeline_mask.unsqueeze(-1)

        tl = seqs.shape[1]
        attention_mask = ~torch.tril(torch.ones((tl, tl), dtype=torch.bool, device=device))

        for i in range(len(self.attention_layers)):
            Q = self.attention_layernorms[i](seqs)
            mha_outputs, _ = self.attention_layers[i](Q, seqs, seqs, attn_mask=attention_mask)
            seqs = Q + mha_outputs

            seqs = self.forward_layernorms[i](seqs)
            seqs = self.forward_layers[i](seqs)
            seqs *= ~timeline_mask.unsqueeze(-1)

        log_feats = self.last_layernorm(seqs) # (U, T, C)
        return log_feats

    def predict(self, log_seqs, item_indices):
        log_feats = self.forward(log_seqs) # (U, T, C)
        final_feat = log_feats[:, -1, :] # only use last timestamp
        if torch.is_tensor(item_indices):
            item_indices = item_indices.to(device=self.item_emb.weight.device, dtype=torch.long)
        else:
            item_indices = torch.as_tensor(item_indices, dtype=torch.long, device=self.item_emb.weight.device)
        item_embs = self.item_emb(item_indices) # (U, I, C)
        logits = item_embs.matmul(final_feat.unsqueeze(-1)).squeeze(-1)
        return logits
