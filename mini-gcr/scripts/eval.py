import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) if 'scripts' not in os.path.abspath(__file__) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import ast
import torch
from tqdm import tqdm
from services.inference import InferenceService
from models.sasrec.model import SASRec
from config import TEST_FILE, TRAIN_FILE, MAX_SEQ_LENGTH, CHECKPOINTS_DIR, SASREC_EMBED_DIM, SASREC_LAYERS, SASREC_HEADS
from config import EVAL_RESULTS_FILE, EVAL_CHART_FILE

def hr_at_k(recommendations, target, k):
    return 1.0 if int(target) in [int(x) for x in recommendations[:k]] else 0.0

def ndcg_at_k(recommendations, target, k):
    target = int(target)
    for idx, item_id in enumerate(recommendations[:k]):
        if int(item_id) == target:
            return 1.0 / torch.log2(torch.tensor(float(idx + 2))).item()
    return 0.0

def complementary_ratio_at_k(inference_service, core_item_id, recommendations, k):
    if not recommendations:
        return 0.0
    selected = recommendations[:k]
    hits = sum(1 for item_id in selected if inference_service.is_complementary(core_item_id, item_id))
    return hits / len(selected)

def summarize(metric_rows, model_name):
    rows = [row for row in metric_rows if row['model'] == model_name]
    if not rows:
        return {
            "model": model_name,
            "HR@5": 0.0,
            "HR@10": 0.0,
            "NDCG@10": 0.0,
            "ComplementaryRatio@10": 0.0
        }
    return {
        "model": model_name,
        "HR@5": sum(row['HR@5'] for row in rows) / len(rows),
        "HR@10": sum(row['HR@10'] for row in rows) / len(rows),
        "NDCG@10": sum(row['NDCG@10'] for row in rows) / len(rows),
        "ComplementaryRatio@10": sum(row['ComplementaryRatio@10'] for row in rows) / len(rows)
    }

def eval_all():
    print("Evaluating models...")
    test_df = pd.read_csv(TEST_FILE)
    
    inference_service = InferenceService()
    
    from scripts.train_sasrec import get_item_num
    train_df = pd.read_csv(TRAIN_FILE)
    item_num = get_item_num(train_df)
    
    sasrec = SASRec(item_num=item_num, max_seq_len=MAX_SEQ_LENGTH, hidden_units=SASREC_EMBED_DIM, num_blocks=SASREC_LAYERS, num_heads=SASREC_HEADS)
    sasrec_path = CHECKPOINTS_DIR / "sasrec.pth"
    if sasrec_path.exists():
        sasrec.load_state_dict(torch.load(sasrec_path, map_location='cpu'))
    sasrec.eval()
    
    print("Running evaluation on test set...")
    metric_rows = []
    total = 0
    for _, row in tqdm(test_df.iterrows(), total=len(test_df)):
        seq = ast.literal_eval(row['item_seq'])
        if len(seq) < 3: continue
        
        target = seq[-1]
        inp_seq = seq[:-1]
        core_item_id = inp_seq[-1]
        
        full_recs = inference_service.recommend(inp_seq, top_k=10, use_constraint=True, use_model=True)
        full_ids = [r['item_id'] for r in full_recs]
        weak_recs = inference_service.recommend(inp_seq, top_k=10, use_constraint=False, use_model=True)
        weak_ids = [r['item_id'] for r in weak_recs]

        inp_padded = inp_seq[-MAX_SEQ_LENGTH:]
        if len(inp_padded) < MAX_SEQ_LENGTH:
            inp_padded = [0] * (MAX_SEQ_LENGTH - len(inp_padded)) + inp_padded
            
        with torch.no_grad():
            log_seq = torch.LongTensor([inp_padded])
            all_items = list(range(1, item_num + 1))
            logits = sasrec.predict(log_seq, all_items)[0]
            top_k = min(10, len(all_items))
            top10_idx = torch.topk(logits, top_k).indices.tolist()
            sasrec_ids = [all_items[i] for i in top10_idx]

        for model_name, rec_ids in [
            ("Full model", full_ids),
            ("w/o Constraint", weak_ids),
            ("Baseline SASRec", sasrec_ids)
        ]:
            metric_rows.append({
                "model": model_name,
                "target": int(target),
                "HR@5": hr_at_k(rec_ids, target, 5),
                "HR@10": hr_at_k(rec_ids, target, 10),
                "NDCG@10": ndcg_at_k(rec_ids, target, 10),
                "ComplementaryRatio@10": complementary_ratio_at_k(inference_service, core_item_id, rec_ids, 10)
            })

        total += 1
        if total >= 100:
            break
            
    summary = pd.DataFrame([
        summarize(metric_rows, "Full model"),
        summarize(metric_rows, "w/o Constraint"),
        summarize(metric_rows, "Baseline SASRec")
    ])
    summary.to_csv(EVAL_RESULTS_FILE, index=False)
    print(f"Results on {total} samples:")
    print(summary.to_string(index=False))
    print(f"Saved evaluation CSV to {EVAL_RESULTS_FILE}")

    try:
        import matplotlib.pyplot as plt
        plot_df = summary.set_index("model")[["HR@10", "NDCG@10", "ComplementaryRatio@10"]]
        ax = plot_df.plot(kind="bar", figsize=(10, 5), rot=0)
        ax.set_ylim(0, 1)
        ax.set_title("mini-GCR Evaluation Comparison")
        ax.set_ylabel("Score")
        plt.tight_layout()
        plt.savefig(EVAL_CHART_FILE)
        print(f"Saved evaluation chart to {EVAL_CHART_FILE}")
    except Exception as exc:
        print(f"Chart generation skipped: {exc}")

if __name__ == "__main__":
    eval_all()
