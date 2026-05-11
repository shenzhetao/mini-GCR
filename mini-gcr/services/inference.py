import json
import pandas as pd
import torch
from config import CHECKPOINTS_DIR, ITEM2TOKENS_FILE, TOKEN2ITEM_FILE, CODEBOOK_SIZE, TOKENS_PER_ITEM, MAX_SEQ_LENGTH
from config import MINGPT_EMBED_DIM, MINGPT_LAYERS, MINGPT_HEADS, COMPLEMENTARY_PAIRS_FILE
from models.mingpt.decode import constrained_beam_search, generate
from models.mingpt.model import GPT, GPTConfig
from services.reason import ReasonGenerator

class InferenceService:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_loaded = False
        self.item2tokens = {}
        self.token2item = {}
        self.comp_map = {}
        self.pair_confidence = {}
        
        mconf = GPTConfig(vocab_size=CODEBOOK_SIZE, block_size=(MAX_SEQ_LENGTH-1)*TOKENS_PER_ITEM,
                          n_layer=MINGPT_LAYERS, n_head=MINGPT_HEADS, n_embd=MINGPT_EMBED_DIM)
        self.model = GPT(mconf)
        ckpt_path = CHECKPOINTS_DIR / "mingpt.pth"
        if ckpt_path.exists():
            self.model.load_state_dict(torch.load(ckpt_path, map_location=self.device))
            self.model_loaded = True
        self.model.to(self.device)
        self.model.eval()
        
        if ITEM2TOKENS_FILE.exists():
            with open(ITEM2TOKENS_FILE, "r", encoding="utf-8") as f:
                self.item2tokens = json.load(f)
        if TOKEN2ITEM_FILE.exists():
            with open(TOKEN2ITEM_FILE, "r", encoding="utf-8") as f:
                self.token2item = json.load(f)
            
        self.reason_gen = ReasonGenerator()
        
        # Load complementary pairs
        if COMPLEMENTARY_PAIRS_FILE.exists():
            comp_df = pd.read_csv(COMPLEMENTARY_PAIRS_FILE)
            for _, row in comp_df.iterrows():
                a, b = int(row['item_a']), int(row['item_b'])
                confidence = float(row.get('confidence', 0.7))
                if a not in self.comp_map: self.comp_map[a] = set()
                if b not in self.comp_map: self.comp_map[b] = set()
                self.comp_map[a].add(b)
                self.comp_map[b].add(a)
                self.pair_confidence[(a, b)] = confidence
                self.pair_confidence[(b, a)] = confidence

        self.popular_items = list(self.reason_gen.item_info.keys()) or [int(x) for x in self.item2tokens.keys()]

    def status(self):
        return {
            "model_loaded": self.model_loaded,
            "items": len(self.popular_items),
            "tokenized_items": len(self.item2tokens),
            "complementary_pairs": sum(len(v) for v in self.comp_map.values()) // 2
        }

    def get_items(self, limit=30):
        items = []
        for item_id in self.popular_items[:limit]:
            info = self.reason_gen.item_info.get(int(item_id), {})
            items.append({
                "item_id": int(item_id),
                "title": info.get("title", f"Item {item_id}"),
                "category": info.get("category", "未知分类")
            })
        return items

    def is_complementary(self, core_item_id, candidate_item_id):
        return int(candidate_item_id) in self.comp_map.get(int(core_item_id), set())

    def _tokens_from_items(self, item_seq):
        tokens = []
        for item in item_seq[-(MAX_SEQ_LENGTH-1):]:
            tokens.extend(self.item2tokens.get(str(int(item)), [0] * TOKENS_PER_ITEM))
        return tokens

    def _make_recommendation(self, core_item_id, item_id, constrained):
        confidence = self.pair_confidence.get((int(core_item_id), int(item_id)), 0.5 if constrained else 0.35)
        info = self.reason_gen.item_info.get(int(item_id), {})
        return {
            "item_id": int(item_id),
            "title": info.get("title", f"Item {item_id}"),
            "confidence": round(float(confidence), 4),
            "reason": self.reason_gen.generate(core_item_id, item_id)
        }

    def _fallback_items(self, core_item_id, item_seq, top_k, use_constraint):
        excluded = {int(x) for x in item_seq}
        if use_constraint and core_item_id in self.comp_map:
            candidates = sorted(
                self.comp_map[core_item_id],
                key=lambda item: self.pair_confidence.get((core_item_id, int(item)), 0.0),
                reverse=True
            )
        else:
            candidates = [int(item) for item in self.popular_items]
        return [int(item) for item in candidates if int(item) not in excluded][:top_k]

    def recommend(self, item_seq, top_k=5, use_constraint=True, use_model=True):
        if not item_seq:
            return []
            
        core_item_id = int(item_seq[-1])
        valid_items = self.comp_map.get(core_item_id, set())
        recommendations = []
        sampled_items = set()
        
        if use_model and self.model_loaded and self.item2tokens and self.token2item:
            tokens = self._tokens_from_items(item_seq)
            x = torch.tensor([tokens], dtype=torch.long).to(self.device)
            for _ in range(max(top_k, 1)):
                if use_constraint and valid_items:
                    out_tokens = constrained_beam_search(self.model, x, TOKENS_PER_ITEM, beam_size=5, valid_items=valid_items, token2item=self.token2item)
                else:
                    out_tokens = generate(self.model, x, TOKENS_PER_ITEM, temperature=1.0, top_k=32)
                
                gen_tokens = out_tokens[0, -TOKENS_PER_ITEM:].tolist()
                gen_item_id = self.token2item.get(str(gen_tokens), None)
            
                if gen_item_id and int(gen_item_id) not in sampled_items and int(gen_item_id) not in item_seq:
                    if not use_constraint or not valid_items or int(gen_item_id) in valid_items:
                        recommendations.append(self._make_recommendation(core_item_id, int(gen_item_id), use_constraint))
                        sampled_items.add(int(gen_item_id))
                
                if len(recommendations) >= top_k:
                    break

        for item_id in self._fallback_items(core_item_id, item_seq, top_k * 2, use_constraint):
            if item_id not in sampled_items:
                recommendations.append(self._make_recommendation(core_item_id, item_id, use_constraint))
                sampled_items.add(item_id)
            if len(recommendations) >= top_k:
                break
                
        return recommendations[:top_k]
