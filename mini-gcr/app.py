import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) if 'scripts' not in os.path.abspath(__file__) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
from config import API_MODEL_NAME, REPORTS_DIR
from services.inference import InferenceService

app = FastAPI(title="mini-GCR API", description="生成式互补品推荐系统 (4周速成版) API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize inference service (loads model lazily or at startup)
try:
    inference_service = InferenceService()
except Exception as e:
    print(f"Warning: Could not load inference service completely: {e}")
    inference_service = None

class RecommendRequest(BaseModel):
    item_ids: List[int]
    top_k: int = 5
    use_constraint: bool = True
    use_model: bool = True

class RecommendationItem(BaseModel):
    item_id: int
    title: str
    confidence: float
    reason: str

class RecommendResponse(BaseModel):
    recommendations: List[RecommendationItem]
    model: str
    status: dict
    model_used: bool = False
    fallback_used: bool = False
    warnings: List[str] = []


# P2-5: 简单内存缓存（同一购物车 + 同一 top_k + 同一开关组合在 60 秒内复用）
import time as _time
from threading import Lock as _Lock
_cache_lock = _Lock()
_recommend_cache: dict = {}
_CACHE_TTL = 60.0  # seconds


def _cache_key(req: RecommendRequest) -> tuple:
    return (
        tuple(req.item_ids),
        int(req.top_k),
        bool(req.use_constraint),
        bool(req.use_model),
    )


def _clean_cache():
    now = _time.time()
    stale = [k for k, (_, t) in _recommend_cache.items() if now - t > _CACHE_TTL]
    for k in stale:
        _recommend_cache.pop(k, None)


class CompareRequest(BaseModel):
    item_ids: List[int]
    top_k: int = 5


class CompareColumn(BaseModel):
    model_name: str
    recommendations: List[RecommendationItem]
    model_used: bool
    fallback_used: bool
    warnings: List[str] = []


class CompareResponse(BaseModel):
    columns: List[CompareColumn]

@app.get("/health")
def health():
    if not inference_service:
        return {"ok": False, "status": {"error": "inference service not loaded"}}
    return {"ok": True, "status": inference_service.status()}

@app.get("/items")
def items(limit: int = 30):
    if not inference_service:
        return {"items": []}
    return {"items": inference_service.get_items(limit=limit)}

@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    if not inference_service:
        return {
            "recommendations": [],
            "model": "error-not-loaded",
            "status": {"error": "inference service not loaded"},
            "model_used": False,
            "fallback_used": False,
            "warnings": ["inference service not loaded"],
        }

    # P2-5: cache lookup
    cache_key = _cache_key(req)
    with _cache_lock:
        _clean_cache()
        if cache_key in _recommend_cache:
            cached, _ = _recommend_cache[cache_key]
            return {**cached, "status": inference_service.status()}

    result = inference_service.recommend(
        req.item_ids,
        top_k=req.top_k,
        use_constraint=req.use_constraint,
        use_model=req.use_model,
    )
    # `result` is now a dict (P1-3 change): strip the `source` field per
    # recommendation since it is internal bookkeeping.
    recs = []
    for r in result["recommendations"]:
        recs.append({
            "item_id": r["item_id"],
            "title": r["title"],
            "confidence": r["confidence"],
            "reason": r["reason"],
        })
    response = {
        "recommendations": recs,
        "model": API_MODEL_NAME,
        "status": inference_service.status(),
        "model_used": result["model_used"],
        "fallback_used": result["fallback_used"],
        "warnings": result["warnings"],
    }
    with _cache_lock:
        _recommend_cache[cache_key] = (response, _time.time())
    return response


def _strip_source(result):
    return [
        {
            "item_id": r["item_id"],
            "title": r["title"],
            "confidence": r["confidence"],
            "reason": r["reason"],
        }
        for r in result["recommendations"]
    ]


@app.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest):
    """Return three columns: SASRec (baseline), minGPT (no constraint),
    minGPT+constraint (full). Used by the front-end comparison view."""
    if not inference_service:
        empty = CompareColumn(
            model_name="error", recommendations=[],
            model_used=False, fallback_used=False,
            warnings=["inference service not loaded"],
        )
        return {"columns": [empty, empty, empty]}

    # Column 1: SASRec baseline (no model decode, just complementary table)
    sasrec_result = inference_service.recommend(
        req.item_ids, top_k=req.top_k, use_constraint=False, use_model=False,
    )
    # Column 2: minGPT w/o constraint
    weak_result = inference_service.recommend(
        req.item_ids, top_k=req.top_k, use_constraint=False, use_model=True,
    )
    # Column 3: minGPT with constraint (full)
    full_result = inference_service.recommend(
        req.item_ids, top_k=req.top_k, use_constraint=True, use_model=True,
    )

    return {
        "columns": [
            CompareColumn(
                model_name="SASRec (fallback)",
                recommendations=_strip_source(sasrec_result),
                model_used=sasrec_result["model_used"],
                fallback_used=sasrec_result["fallback_used"],
                warnings=sasrec_result["warnings"],
            ),
            CompareColumn(
                model_name="minGPT (no constraint)",
                recommendations=_strip_source(weak_result),
                model_used=weak_result["model_used"],
                fallback_used=weak_result["fallback_used"],
                warnings=weak_result["warnings"],
            ),
            CompareColumn(
                model_name="minGPT + constraint (full)",
                recommendations=_strip_source(full_result),
                model_used=full_result["model_used"],
                fallback_used=full_result["fallback_used"],
                warnings=full_result["warnings"],
            ),
        ]
    }


@app.get("/eval/summary")
def eval_summary():
    """Read the latest eval_results.csv and return a small JSON for the
    front-end metrics dashboard. Cached for 30 seconds."""
    csv_path = REPORTS_DIR / "eval_results.csv"
    if not csv_path.exists():
        return {"rows": [], "total_samples": 0}
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        return {"rows": [], "error": str(e)}

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "model": r.get("model", ""),
            "HR@5": float(r.get("HR@5", 0.0)),
            "HR@10": float(r.get("HR@10", 0.0)),
            "NDCG@10": float(r.get("NDCG@10", 0.0)),
            "ComplementaryRatio@10": float(r.get("ComplementaryRatio@10", 0.0)),
        })
    # Read the latest sample count from the eval log if available
    log = REPORTS_DIR / "eval_full.log"
    n = 0
    if log.exists():
        try:
            for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("Results on"):
                    # "Results on 997 samples:"
                    parts = line.split()
                    if len(parts) >= 3:
                        n = int(parts[2])
                    break
        except Exception:
            pass
    return {"rows": rows, "total_samples": n}

class SceneRequest(BaseModel):
    scene: str


# P2-3: multi-scene rule table. Each scene has a list of pre-baked
# complementary products that fit the use case.  This avoids depending on
# any real dataset and keeps the demo deterministic.
SCENE_TABLE: dict[str, list[dict]] = {
    "露营": [
        {"item_id": 1001, "title": "便携折叠椅", "reason": "露营场景必备，方便休息"},
        {"item_id": 1002, "title": "户外防风炉头", "reason": "野外烹饪好帮手"},
        {"item_id": 1003, "title": "防水野餐垫", "reason": "草地/沙地防潮隔湿"},
        {"item_id": 1004, "title": "头灯", "reason": "夜间营地照明"},
        {"item_id": 1005, "title": "保温水壶", "reason": "长时间维持饮品温度"},
    ],
    "办公": [
        {"item_id": 2001, "title": "人体工学椅", "reason": "长时间办公更舒适"},
        {"item_id": 2002, "title": "显示器支架", "reason": "调整视线高度，保护颈椎"},
        {"item_id": 2003, "title": "机械键盘", "reason": "提升输入手感与效率"},
        {"item_id": 2004, "title": "降噪耳机", "reason": "隔绝环境噪声"},
        {"item_id": 2005, "title": "桌面文件收纳", "reason": "保持桌面整洁"},
    ],
    "健身": [
        {"item_id": 3001, "title": "瑜伽垫", "reason": "训练与拉伸必备"},
        {"item_id": 3002, "title": "运动毛巾", "reason": "吸汗速干"},
        {"item_id": 3003, "title": "蛋白粉摇杯", "reason": "训练后补给"},
        {"item_id": 3004, "title": "运动腰包", "reason": "随身携带手机钥匙"},
        {"item_id": 3005, "title": "弹力带套装", "reason": "辅助热身与拉伸"},
    ],
    "旅行": [
        {"item_id": 4001, "title": "登机箱", "reason": "短途出差首选容量"},
        {"item_id": 4002, "title": "旅行转换插头", "reason": "多国通用"},
        {"item_id": 4003, "title": "便携颈枕", "reason": "长途飞行/火车更舒适"},
        {"item_id": 4004, "title": "折叠水杯", "reason": "环保便携"},
        {"item_id": 4005, "title": "一次性压缩毛巾", "reason": "差旅轻装上阵"},
    ],
    "学习": [
        {"item_id": 5001, "title": "护眼台灯", "reason": "长时间阅读不疲劳"},
        {"item_id": 5002, "title": "笔记本支架", "reason": "网课/笔记更舒适"},
        {"item_id": 5003, "title": "降噪耳塞", "reason": "隔绝嘈杂环境"},
        {"item_id": 5004, "title": "思维导图本", "reason": "梳理知识结构"},
        {"item_id": 5005, "title": "荧光标签贴", "reason": "重点内容标记"},
    ],
}


@app.post("/scene")
def scene_recommend(req: SceneRequest):
    items = SCENE_TABLE.get(req.scene, [])
    return {
        "scene": req.scene,
        "available_scenes": list(SCENE_TABLE.keys()),
        "recommendations": items,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
