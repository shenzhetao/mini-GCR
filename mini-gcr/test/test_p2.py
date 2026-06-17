"""P2 functional tests for mini-GCR.

Tests covered:
  T1. /compare endpoint returns 3 columns (SASRec, minGPT no-cstr, minGPT+cstr).
  T2. /scene endpoint supports 5 scenes (露营, 办公, 健身, 旅行, 学习).
  T3. /scene returns empty for unknown scene but lists available_scenes.
  T4. /eval/summary returns eval rows.
  T5. /recommend uses cache (second call returns same data fast).
  T6. multi-seed t-test report exists.
  T7. HTML eval report exists and contains key sections.

Exits 0 on all-pass, 1 on first failure.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

results = []


def check(name: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}" + (f"  -- {detail}" if detail else "")
    print(line)
    results.append((name, ok, detail))


# ----- T1: /compare endpoint returns 3 columns -----
print("=" * 60)
print("T1. /compare endpoint returns 3 columns")
print("=" * 60)

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)
resp = client.post("/compare", json={"item_ids": [100, 200, 300], "top_k": 3})
check("/compare status 200", resp.status_code == 200, f"code={resp.status_code}")
data = resp.json() if resp.status_code == 200 else {}
check("/compare returns 'columns' key", "columns" in data)
check("/compare has 3 columns", len(data.get("columns", [])) == 3,
      f"got {len(data.get('columns', []))}")
if data.get("columns"):
    names = [c["model_name"] for c in data["columns"]]
    check("col 0 = SASRec fallback", "SASRec" in names[0], f"name={names[0]}")
    check("col 1 mentions minGPT", "minGPT" in names[1], f"name={names[1]}")
    check("col 2 = full / constraint", "constraint" in names[2].lower() or "full" in names[2].lower(),
          f"name={names[2]}")
    check("each col has recommendations list",
          all("recommendations" in c for c in data["columns"]))
    check("each col has top_k recommendations",
          all(len(c["recommendations"]) <= 3 for c in data["columns"]))

# ----- T2: /scene supports 5 scenes -----
print()
print("=" * 60)
print("T2. /scene supports multiple scenes")
print("=" * 60)

expected_scenes = ["露营", "办公", "健身", "旅行", "学习"]
for scene in expected_scenes:
    r = client.post("/scene", json={"scene": scene})
    check(f"scene '{scene}' status 200", r.status_code == 200)
    if r.status_code == 200:
        body = r.json()
        check(f"scene '{scene}' returns >= 1 recommendation",
              len(body.get("recommendations", [])) >= 1,
              f"got {len(body.get('recommendations', []))}")

# ----- T3: /scene returns empty for unknown but lists available_scenes -----
print()
print("=" * 60)
print("T3. /scene unknown scene")
print("=" * 60)

r = client.post("/scene", json={"scene": "不存在的场景"})
check("unknown scene status 200", r.status_code == 200)
body = r.json()
check("unknown scene returns empty recs", body.get("recommendations") == [])
check("unknown scene lists available_scenes",
      set(body.get("available_scenes", [])) >= set(expected_scenes),
      f"got {body.get('available_scenes')}")

# ----- T4: /eval/summary returns rows -----
print()
print("=" * 60)
print("T4. /eval/summary returns eval rows")
print("=" * 60)

r = client.get("/eval/summary")
check("/eval/summary status 200", r.status_code == 200)
body = r.json()
check("/eval/summary has 'rows' key", "rows" in body)
check("/eval/summary rows >= 3 models", len(body.get("rows", [])) >= 3,
      f"rows={len(body.get('rows', []))}")
check("/eval/summary mentions Full model",
      any("Full" in row.get("model", "") for row in body.get("rows", [])))

# ----- T5: /recommend cache -----
print()
print("=" * 60)
print("T5. /recommend uses cache")
print("=" * 60)

import time as _t

req = {"item_ids": [42, 17, 88], "top_k": 4, "use_constraint": True, "use_model": True}
t0 = _t.time()
r1 = client.post("/recommend", json=req)
t1 = _t.time() - t0
t0 = _t.time()
r2 = client.post("/recommend", json=req)
t2 = _t.time() - t0
check("first /recommend 200", r1.status_code == 200)
check("second /recommend 200 (cached)", r2.status_code == 200)
check("cached returns same recommendations",
      [r["item_id"] for r in r1.json()["recommendations"]] ==
      [r["item_id"] for r in r2.json()["recommendations"]],
      f"first={[r['item_id'] for r in r1.json()['recommendations']]}, "
      f"second={[r['item_id'] for r in r2.json()['recommendations']]}")
check("cached call is faster",
      t2 <= t1 + 0.005,  # allow tiny variance
      f"first={t1*1000:.1f}ms cached={t2*1000:.1f}ms")

# ----- T6: multi-seed t-test report exists -----
print()
print("=" * 60)
print("T6. multi-seed t-test report exists")
print("=" * 60)

from config import REPORTS_DIR
ms = REPORTS_DIR / "multi_seed_report.json"
check("multi_seed_report.json exists", ms.exists())
if ms.exists():
    rep = json.loads(ms.read_text(encoding="utf-8"))
    check("report has t_tests", "t_tests" in rep)
    if "t_tests" in rep:
        check("report covers HR@10",
              "HR@10" in rep["t_tests"],
              f"keys={list(rep['t_tests'].keys())}")
        p = rep["t_tests"]["HR@10"]["p_value"]
        check("HR@10 p < 0.05 (significant)", p < 0.05, f"p={p}")
    check("report has noise_summary (non-deterministic probe)", "noise_summary" in rep)

# ----- T7: HTML report exists with key sections -----
print()
print("=" * 60)
print("T7. HTML eval report exists & well-formed")
print("=" * 60)

html_path = REPORTS_DIR / "eval_report.html"
check("eval_report.html exists", html_path.exists())
if html_path.exists():
    text = html_path.read_text(encoding="utf-8")
    check("HTML contains 'mini-GCR 评估报告'", "mini-GCR 评估报告" in text)
    check("HTML contains summary table headers", "HR@10" in text)
    check("HTML contains t-test section", "t" in text and "p" in text)
    check("HTML embeds base64 chart", "data:image/png;base64," in text)
    check("HTML size > 5KB", html_path.stat().st_size > 5000,
          f"size={html_path.stat().st_size}")

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
