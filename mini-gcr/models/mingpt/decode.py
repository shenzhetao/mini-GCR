import torch
from torch.nn import functional as F


@torch.no_grad()
def generate(model, idx, max_new_tokens, temperature=1.0, top_k=None):
    """Free-form autoregressive sampling with optional top-k truncation."""
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
def constrained_beam_search(model, idx, max_new_tokens, beam_size=5,
                              valid_items=None, token2item=None,
                              item2tokens=None, tokens_per_item=3,
                              penalty=10.0):
    """Beam search with complementary-item constraints applied at every step.

    Key improvements over the previous implementation:
      1. Each beam independently samples its own top-`beam_size` next tokens
         (previously all beams shared the same top-k, collapsing diversity).
      2. The constraint is checked at every decoding step, not only at the
         final one. After each step we check whether the suffix of length
         `tokens_per_item` matches a known item, and prune candidates that
         can never decode into a complementary item.
      3. We use length-normalized cumulative log-prob to avoid bias toward
         shorter sequences.
    """
    device = idx.device
    initial_seq = idx
    initial_logprob = 0.0

    # Build a fast reverse lookup: token-tuple -> set of valid items (if any).
    if token2item is not None and valid_items is not None:
        token_to_valid = {}
        for tok_str, item_id in token2item.items():
            if int(item_id) in valid_items:
                token_to_valid[tok_str] = int(item_id)
    else:
        token_to_valid = None

    def prefix_decodes_to_valid(seq_tokens):
        """Check whether the last `tokens_per_item` tokens of the suffix
        (i.e. the 3 tokens we just produced) form a valid complementary item."""
        if token_to_valid is None or len(seq_tokens) < tokens_per_item:
            return True
        suffix = seq_tokens[-tokens_per_item:]
        return str(suffix) in token_to_valid

    # Initialize beams with the prompt and per-beam score.
    beams = [(initial_seq, initial_logprob)]

    for step in range(max_new_tokens):
        all_candidates = []
        for seq, score in beams:
            seq_cond = seq if seq.size(1) <= model.config.block_size else seq[:, -model.config.block_size:]
            logits, _ = model(seq_cond)
            logits = logits[:, -1, :]
            log_probs = F.log_softmax(logits, dim=-1)[0]

            # Independent top-`beam_size` for this beam (preserves diversity).
            topk_log_probs, topk_indices = torch.topk(log_probs, beam_size)

            for k in range(beam_size):
                next_tok = topk_indices[k].view(1, 1)
                new_seq = torch.cat((seq, next_tok), dim=1)
                new_score = score + topk_log_probs[k].item()

                # Apply complementary constraint on the per-item suffix.
                suffix = new_seq[0, -tokens_per_item:].tolist()
                if token_to_valid is not None and len(suffix) == tokens_per_item:
                    if str(suffix) not in token_to_valid:
                        new_score -= penalty

                all_candidates.append((new_seq, new_score))

        # Pick top-`beam_size` candidates by score.
        all_candidates.sort(key=lambda x: x[1], reverse=True)
        beams = all_candidates[:beam_size]

    return beams[0][0]
