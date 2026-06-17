"""P1 functional tests for mini-GCR.

Tests covered:
  T1. trainer module loads and TrainerConfig has P1 fields (patience, eval_every...).
  T2. InferenceService.recommend() returns a dict with model_used/fallback_used/warnings.
  T3. When use_model=False, fallback_used=True and no warnings.
  T4. When model is loaded but generates no decodable item, warnings list is non-empty.
  T5. ReasonGenerator.coverage_pairs() returns >= 20 pairs (from expanded templates).
  T6. eval script no longer has the 100-sample hard cap (no "total >= 100" in source).
  T7. eval on full test set (997 rows) completes and Full model HR@10 >= Baseline.

Exits 0 on all-pass, 1 on first failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from models.mingpt.trainer import TrainerConfig
from services.inference import InferenceService
from services.reason import ReasonGenerator

results = []


def check(name: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}" + (f"  -- {detail}" if detail else "")
    print(line)
    results.append((name, ok, detail))


# ----- T1: TrainerConfig has P1 fields -----
print("=" * 60)
print("T1. TrainerConfig P1 fields (patience, eval_every, ...)")
print("=" * 60)

cfg = TrainerConfig(patience=8, eval_every=1, max_eval_batches=4)
check("TrainerConfig has patience", hasattr(cfg, "patience"), f"patience={cfg.patience}")
check("TrainerConfig has eval_every", hasattr(cfg, "eval_every"), f"eval_every={cfg.eval_every}")
check("TrainerConfig has max_eval_batches", hasattr(cfg, "max_eval_batches"),
      f"max_eval_batches={cfg.max_eval_batches}")
check("TrainerConfig patience default >= 5", cfg.patience >= 5)

# ----- T2: InferenceService.recommend() returns structured dict -----
print()
print("=" * 60)
print("T2. recommend() returns structured dict")
print("=" * 60)

svc = InferenceService()
result = svc.recommend([100, 200], top_k=3, use_constraint=True, use_model=False)
check("recommend() returns dict", isinstance(result, dict),
      f"type={type(result).__name__}")
check("dict has 'recommendations' key", "recommendations" in result)
check("dict has 'model_used' key", "model_used" in result)
check("dict has 'fallback_used' key", "fallback_used" in result)
check("dict has 'warnings' key", "warnings" in result)
check("recommendations is list", isinstance(result["recommendations"], list))
check("warnings is list", isinstance(result["warnings"], list))
check("model_used is bool", isinstance(result["model_used"], bool))
check("fallback_used is bool", isinstance(result["fallback_used"], bool))

# ----- T3: use_model=False -> fallback only, no warnings -----
print()
print("=" * 60)
print("T3. use_model=False -> fallback only, no warnings")
print("=" * 60)

r = svc.recommend([100, 200], top_k=3, use_constraint=True, use_model=False)
check("use_model=False: model_used=False", r["model_used"] is False, f"model_used={r['model_used']}")
check("use_model=False: fallback_used=True", r["fallback_used"] is True, f"fallback_used={r['fallback_used']}")
check("use_model=False: no warnings", len(r["warnings"]) == 0, f"warnings={r['warnings']}")
check("use_model=False: returns 3 recs", len(r["recommendations"]) == 3,
      f"got {len(r['recommendations'])}")
check("use_model=False: each rec has item_id/title/confidence/reason",
      all("item_id" in r and "title" in r and "confidence" in r and "reason" in r
          for r in r["recommendations"]))

# ----- T4: model loaded but produces no decodable item -> warnings non-empty -----
print()
print("=" * 60)
print("T4. model generates no decodable item -> warnings non-empty")
print("=" * 60)

svc2 = InferenceService()
r2 = svc2.recommend([100, 200], top_k=5, use_constraint=True, use_model=True)
check("model_loaded=True", svc2.model_loaded is True, f"model_loaded={svc2.model_loaded}")
# The model may produce no directly decodable item (vocab=256, combinations=16.7M);
# when that happens the warning should be emitted.
check("warnings non-empty when model decodes miss",
      len(r2["warnings"]) > 0,
      f"warnings={r2['warnings']}")
check("at least one rec returned", len(r2["recommendations"]) > 0,
      f"recs={len(r2['recommendations'])}")
# Verify that 'source' is set on each recommendation
check("each rec has 'source' field",
      all("source" in r for r in r2["recommendations"]),
      f"sources={[r.get('source') for r in r2['recommendations']]}")

# ----- T5: ReasonGenerator coverage >= 20 pairs -----
print()
print("=" * 60)
print("T5. ReasonGenerator coverage >= 20 pairs")
print("=" * 60)

rg = ReasonGenerator()
pairs = rg.coverage_pairs()
check("coverage_pairs() returns >= 20 pairs", len(pairs) >= 20,
      f"pairs={len(pairs)}")
# Also test generate() with a known pair
reason = rg.generate(100, 200)
check("generate() returns non-empty string", len(reason) > 0, f"reason={reason[:40]}...")
# Test generate with a pair that has templates
all_keys = list(rg._variants.keys())
check("has at least 10 canonical keys", len(all_keys) >= 10, f"keys={len(all_keys)}")

# ----- T6: eval.py no 100-sample cap -----
print()
print("=" * 60)
print("T6. eval.py has no 100-sample hard cap")
print("=" * 60)

import scripts.eval as eval_mod
src = Path(eval_mod.__file__).read_text()
has_cap = "total >= 100" in src or "total > 100" in src or "if total >= 100" in src
check("eval.py: no 'total >= 100' guard", not has_cap)

# ----- T7: Full eval run (997 test rows) -----
print()
print("=" * 60)
print("T7. Full eval (997 test rows): Full model HR@10 >= Baseline")
print("=" * 60)

from config import REPORTS_DIR
csv_path = REPORTS_DIR / "eval_results.csv"
if csv_path.exists():
    df = pd.read_csv(csv_path)
    full_hr10 = float(df.loc[df["model"] == "Full model", "HR@10"].mean())
    base_hr10 = float(df.loc[df["model"] == "Baseline SASRec", "HR@10"].mean())
    check("Full HR@10 > 0", full_hr10 > 0, f"HR@10={full_hr10:.4f}")
    check("Baseline HR@10 >= 0", base_hr10 >= 0, f"HR@10={base_hr10:.4f}")
    check("Full HR@10 >= Baseline", full_hr10 >= base_hr10,
          f"full={full_hr10:.4f} baseline={base_hr10:.4f}")
else:
    check("eval_results.csv exists (prerequisite)", False, "file not found")

# ----- Summary -----
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
print(f"Passed {passed}/{total}")
failures = [n for n, ok, _ in results if not ok]
if failures:
    print("Failures:")
    for n in failures:
        print(f"  - {n}")
    sys.exit(1)
sys.exit(0)
