import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) if 'scripts' not in os.path.abspath(__file__) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from config import API_MODEL_NAME
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
        return {"recommendations": [], "model": "error-not-loaded", "status": {"error": "inference service not loaded"}}
        
    recs = inference_service.recommend(req.item_ids, top_k=req.top_k, use_constraint=req.use_constraint, use_model=req.use_model)
    return {
        "recommendations": recs,
        "model": API_MODEL_NAME,
        "status": inference_service.status()
    }

class SceneRequest(BaseModel):
    scene: str

@app.post("/scene")
def scene_recommend(req: SceneRequest):
    # Hardcoded rules for presentation
    if req.scene == "露营":
        return {
            "scene": "露营",
            "recommendations": [
                {"item_id": 1001, "title": "便携折叠椅", "reason": "露营场景必备，方便休息"},
                {"item_id": 1002, "title": "户外防风炉头", "reason": "野外烹饪好帮手"}
            ]
        }
    return {"scene": req.scene, "recommendations": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
