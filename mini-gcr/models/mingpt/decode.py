import torch
from torch.nn import functional as F

@torch.no_grad()
def generate(model, idx, max_new_tokens, temperature=1.0, top_k=None):
    for _ in range(max_new_tokens):
        idx_cond = idx if idx.size(1) <= model.config.block_size else idx[:, -model.config.block_size:]
        logits, _ = model(idx_cond)
        logits = logits[:, -1, :] / temperature
        if top_k is not None:
            v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
            logits[logits < v[:, [-1]]] = -float('Inf')
        probs = F.softmax(logits, dim=-1)
        idx_next = torch.multinomial(probs, num_samples=1)
        idx = torch.cat((idx, idx_next), dim=1)
    return idx

@torch.no_grad()
def constrained_beam_search(model, idx, max_new_tokens, beam_size=5, valid_items=None, token2item=None):
    # Simplified beam search
    # valid_items: set of valid item ids
    device = idx.device
    beams = [(idx, 0.0)]
    
    for step in range(max_new_tokens):
        new_beams = []
        for seq, score in beams:
            seq_cond = seq if seq.size(1) <= model.config.block_size else seq[:, -model.config.block_size:]
            logits, _ = model(seq_cond)
            logits = logits[:, -1, :]
            probs = F.log_softmax(logits, dim=-1)
            
            topk_probs, topk_indices = torch.topk(probs[0], beam_size)
            for i in range(beam_size):
                next_tok = topk_indices[i].unsqueeze(0).unsqueeze(0)
                new_seq = torch.cat((seq, next_tok), dim=1)
                new_score = score + topk_probs[i].item()
                
                # Apply constraint at the final token
                if step == max_new_tokens - 1 and valid_items is not None and token2item is not None:
                    # check if the generated 3 tokens map to a valid item
                    gen_tokens = new_seq[0, -3:].tolist()
                    gen_item_id = token2item.get(str(gen_tokens), None)
                    if gen_item_id not in valid_items:
                        new_score -= 100.0 # penalty
                
                new_beams.append((new_seq, new_score))
                
        beams = sorted(new_beams, key=lambda x: x[1], reverse=True)[:beam_size]
        
    return beams[0][0] # Return the best sequence
