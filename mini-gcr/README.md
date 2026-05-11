# mini-GCR 生成式互补品推荐系统

## 后端准备

```powershell
pip install -r requirements.txt
python run_pipeline.py
```

## 训练与评估

```powershell
python scripts/train_sasrec.py
python scripts/train_mingpt.py
python scripts/eval.py
```

评估结果输出到：

- `reports/eval_results.csv`
- `reports/eval_comparison.png`

## 启动 FastAPI

```powershell
uvicorn app:app --port 8000
```

可用接口：

- `GET /health`
- `GET /items?limit=30`
- `POST /recommend`
- `POST /scene`

## 启动 Vue 前端

```powershell
cd frontend
npm install
npm run dev
```

默认访问：`http://localhost:5173`

Vue 开发服务器已配置 `/api` 代理到 `http://localhost:8000`。
