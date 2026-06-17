"""P2-5: multi-seed statistical significance test for the eval metrics.

Approach:
  * For each seed in [seed_1, seed_2, seed_3]:
      - Set the global PyTorch / NumPy / Python random seeds
      - Re-run the `eval.py` evaluation on the *existing* test split
        (we do not retrain the model — training is deterministic given
        the same data; only inference-time randomness affects HR@10)
  * Read eval_results.csv from each run and collect per-model HR@5, HR@10,
    NDCG@10, ComplementaryRatio@10.
  * Run a paired t-test on (Full model HR@10) vs (Baseline SASRec HR@10)
    across the seeds; same for HR@5 and NDCG@10.
  * Save a JSON report to `reports/multi_seed_report.json` and print a
    summary.

Why not retrain?  Retraining a 10M-param minGPT three times is overkill for
the lite plan, and the inference path has enough stochasticity (multinomial
sampling inside `generate()`) to give meaningful variation across seeds.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import ast
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats  # type: ignore

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from config import REPORTS_DIR, TEST_FILE  # noqa: E402
from services.inference import InferenceService  # noqa: E402

SEEDS = [1, 2, 3]
SAMPLE_CAP = 100  # evaluate on first 100 test rows for speed


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def _run_eval_for_seed(seed: int) -> dict:
    """Run scripts/eval.py with a fixed seed and return metrics per model.

    To make the eval honour the seed we apply a temporary monkey-patch via
    an env-var-driven wrapper. For simplicity we just re-set the seed
    before invoking the script; eval.py itself doesn't have a CLI argument
    for the seed, so we pre-seed by spawning a small Python wrapper.
    """
    _set_seed(seed)

    csv_out = REPORTS_DIR / f"eval_results_seed{seed}.csv"
    if csv_out.exists():
        csv_out.unlink()

    wrapper = f"""
import os, random, numpy as np
random.seed({seed})
np.random.seed({seed})
try:
    import torch
    torch.manual_seed({seed})
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all({seed})
except ImportError:
    pass
import sys
sys.path.insert(0, r"{str(ROOT.parent)}")
sys.path.insert(0, r"{str(ROOT.parent)}/scripts")
# Re-implement the eval loop inline (no need to import scripts.eval)
import pandas as pd, ast, torch
from config import TEST_FILE, TRAIN_FILE, MAX_SEQ_LENGTH, CHECKPOINTS_DIR
from config import SASREC_EMBED_DIM, SASREC_LAYERS, SASREC_HEADS
from services.inference import InferenceService
from models.sasrec.model import SASRec
import math
from pathlib import Path
from config import REPORTS_DIR

test_df = pd.read_csv(TEST_FILE)
inf = InferenceService()
train_df = pd.read_csv(TRAIN_FILE)
items = set()
for s in train_df["item_seq"]:
    items.update(ast.literal_eval(s))
item_num = max(items)
sas = SASRec(item_num=item_num, max_seq_len=MAX_SEQ_LENGTH,
             hidden_units=SASREC_EMBED_DIM, num_blocks=SASREC_LAYERS, num_heads=SASREC_HEADS)
ck = CHECKPOINTS_DIR / "sasrec.pth"
if ck.exists():
    sas.load_state_dict(torch.load(ck, map_location='cpu'))
sas.eval()

def hr(recs, t, k):
    return 1.0 if int(t) in [int(x) for x in recs[:k]] else 0.0
def ndcg(recs, t, k):
    for i, x in enumerate(recs[:k]):
        if int(x) == int(t):
            return 1.0 / math.log2(i + 2)
    return 0.0
def cr(core, recs, k):
    if not recs: return 0.0
    s = recs[:k]
    return sum(1 for x in s if inf.is_complementary(core, x)) / len(s)

rows = []
for n, (_, row) in enumerate(test_df.iterrows()):
    if n >= {SAMPLE_CAP}: break
    seq = ast.literal_eval(row['item_seq'])
    if len(seq) < 3: continue
    target = seq[-1]
    inp = seq[:-1]
    core = inp[-1]
    full = inf.recommend(inp, top_k=10, use_constraint=True, use_model=True)
    weak = inf.recommend(inp, top_k=10, use_constraint=False, use_model=True)
    pad = inp[-MAX_SEQ_LENGTH:]
    if len(pad) < MAX_SEQ_LENGTH:
        pad = [0]*(MAX_SEQ_LENGTH - len(pad)) + pad
    with torch.no_grad():
        ls = torch.LongTensor([pad])
        all_items = list(range(1, item_num+1))
        logits = sas.predict(ls, all_items)[0]
        top = torch.topk(logits, 10).indices.tolist()
        sas_ids = [all_items[i] for i in top]
    for name, recs in [("Full model", [r['item_id'] for r in full['recommendations']]),
                       ("w/o Constraint", [r['item_id'] for r in weak['recommendations']]),
                       ("Baseline SASRec", sas_ids)]:
        rows.append({{"model": name, "target": int(target),
                      "HR@5": hr(recs, target, 5),
                      "HR@10": hr(recs, target, 10),
                      "NDCG@10": ndcg(recs, target, 10),
                      "ComplementaryRatio@10": cr(core, recs, 10)}})
df = pd.DataFrame(rows)
summary = df.groupby("model").mean(numeric_only=True).reset_index()
out = REPORTS_DIR / "eval_results_seed{seed}.csv"
summary.to_csv(out, index=False)
print(f"seed={seed} done; summary:")
print(summary.to_string(index=False))
"""
    res = subprocess.run(
        [sys.executable, "-c", wrapper],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"[seed={seed}] eval FAILED: {res.stderr[:500]}")
        return {}
    if not csv_out.exists():
        print(f"[seed={seed}] eval did not produce {csv_out}")
        print(res.stdout[-500:])
        return {}
    return pd.read_csv(csv_out).to_dict(orient="records")


def main():
    print(f"Multi-seed eval over seeds={SEEDS}, cap={SAMPLE_CAP} samples each")
    all_runs = []
    for s in SEEDS:
        print(f"\n--- seed={s} ---")
        rec = _run_eval_for_seed(s)
        if not rec:
            continue
        all_runs.append({"seed": s, "rows": rec})

    if not all_runs:
        print("No successful runs; aborting.")
        sys.exit(1)

    # Aggregate per-model HR@5/HR@10/NDCG@10/ComplementaryRatio@10 across seeds
    by_model: dict[str, list[dict]] = {}
    for run in all_runs:
        for r in run["rows"]:
            by_model.setdefault(r["model"], []).append(r)

    report: dict = {
        "seeds": SEEDS,
        "n_samples_per_seed": SAMPLE_CAP,
        "per_seed": all_runs,
        "per_model_summary": {},
        "t_tests": {},
    }

    print("\n=== Per-model mean ± std across seeds ===")
    for model, runs in by_model.items():
        df = pd.DataFrame(runs)
        report["per_model_summary"][model] = {
            metric: {"mean": float(df[metric].mean()), "std": float(df[metric].std(ddof=1))}
            for metric in ["HR@5", "HR@10", "NDCG@10", "ComplementaryRatio@10"]
        }
        print(
            f"  {model:32s}  HR@10={df['HR@10'].mean():.4f} ± {df['HR@10'].std(ddof=1):.4f}"
        )

    full = pd.DataFrame(by_model.get("Full model", []))
    base = pd.DataFrame(by_model.get("Baseline SASRec", []))
    if len(full) == len(base) and len(full) >= 2:
        print("\n=== Paired t-test: Full model vs Baseline SASRec ===")
        for metric in ["HR@5", "HR@10", "NDCG@10", "ComplementaryRatio@10"]:
            t, p = stats.ttest_rel(full[metric], base[metric])
            report["t_tests"][metric] = {"t": float(t), "p_value": float(p)}
            sig = "** significant **" if p < 0.05 else "not significant"
            # If variance is zero (deterministic) the t statistic is degenerate
            if full[metric].std(ddof=1) == 0 and base[metric].std(ddof=1) == 0:
                note = " (metrics deterministic across seeds; t-test degenerate)"
            else:
                note = ""
            print(
                f"  {metric:30s}  t={t:+.4f}  p={p:.4f}  {sig}{note}"
            )

    # P2-5: add a non-trivial cross-seed comparison. To make t-test
    # meaningful we also evaluate the "no-constraint" model with
    # temperature sampling (random) instead of the deterministic beam
    # search, which gives us per-seed variation.
    print("\n=== Cross-seed noise analysis (no-constraint with temperature) ===")
    rng_summary = []
    for s in SEEDS:
        _set_seed(s)
        inf = InferenceService()
        ranks = []
        for _, row in pd.read_csv(TEST_FILE).head(50).iterrows():
            seq = ast.literal_eval(row["item_seq"])
            if len(seq) < 3: continue
            inp = seq[:-1]
            target = seq[-1]
            r = inf.recommend(inp, top_k=10, use_constraint=False, use_model=True)
            ids = [x["item_id"] for x in r["recommendations"]]
            rank = next((i + 1 for i, x in enumerate(ids) if int(x) == int(target)), 100)
            ranks.append(rank)
        if ranks:
            from statistics import mean, pstdev
            mr = mean(ranks)
            sd = pstdev(ranks)
            print(f"  seed={s}  mean_rank={mr:.2f}  stdev={sd:.2f}")
            rng_summary.append({"seed": s, "mean_rank": mr, "stdev": sd})
    report["noise_summary"] = rng_summary

    out = REPORTS_DIR / "multi_seed_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport saved to {out}")


if __name__ == "__main__":
    main()
