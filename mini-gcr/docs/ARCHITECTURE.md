# mini-GCR 项目文件归档结构说明

> 整理日期：2026-06-17
> 适用版本：v2.1 final
> 触发原因：项目根目录混杂了 17+ 个"非核心业务"文件（文档/日志/测试/工具），影响可读性

---

## 1. 归档原则

| 类别 | 判定标准 | 归宿目录 |
|------|----------|----------|
| 业务模型 / 推理 / API | 必须常驻 `import` 链路 | 根目录 + `models/` / `services/` / `scripts/` |
| 测试脚本 | 阶段化 `test_pX.py` | `test/` |
| 日志（带时间戳） | 一次性运行产物 | `logs/runs/` |
| 日志（历史） | 旧版本快照 | `logs/archive/` |
| Markdown / LaTeX / PDF 报告 | 项目文档与交付物 | `docs/` |
| 非业务工具脚本 | PPT 辅助、PDF 渲染 | `tools/` |
| 训练产物 | 模型 checkpoint / 训练日志 | `checkpoints/` |
| 评估产物 | CSV / PNG / HTML / 多 seed | `reports/` |
| 数据集 | 原始 / 处理 / 划分 | `data/raw/` `data/processed/` `data/splits/` |
| 前端 | Vue 3 项目 | `frontend/` |

---

## 2. 最终目录结构

```
mini-gcr/                                  ← 项目根
├── app.py                  ← FastAPI 入口
├── config.py               ← 集中配置
├── run_pipeline.py         ← 数据 + 训练 + 评估流水线
├── requirements.txt
│
├── models/                 ← 业务模型
│   ├── mingpt/             (model.py / trainer.py / decode.py)
│   └── sasrec/             (model.py)
│
├── services/               ← 推理 + 理由
│   ├── inference.py
│   └── reason.py
│
├── scripts/                ← 数据 / 训练 / 评估脚本
│   ├── build_complementary.py
│   ├── build_tokens.py
│   ├── eval.py
│   ├── eval_seeds.py
│   ├── generate_mock_data.py
│   ├── preprocess.py
│   ├── report_html.py
│   ├── train_mingpt.py
│   └── train_sasrec.py
│
├── data/                   ← 数据集
│   ├── raw/tmall_sample.csv
│   ├── processed/          (user_seq.csv / complementary_pairs.csv
│   │                        / item2tokens.json / token2item.json
│   │                        / reason_templates.json)
│   └── splits/             (train.csv / val.csv / test.csv)
│
├── checkpoints/            ← 训练产物
│   ├── sasrec.pth
│   ├── mingpt.pth
│   └── *_train.log
│
├── reports/                ← 评估产物
│   ├── eval_results.csv
│   ├── eval_results_seed[1-3].csv
│   ├── eval_comparison.png
│   ├── eval_report.html
│   ├── multi_seed_report.json
│   ├── architecture.png        ← PDF 嵌入
│   ├── frontend_screenshot.png  ← PDF 嵌入
│   ├── title_banner.png         ← PDF 嵌入
│   └── *.log                    ← 评估 / 多 seed 日志
│
├── frontend/               ← Vue 3 + Vite 前端
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/                (App.vue / main.js / style.css)
│
├── test/                   ← 阶段化测试套件（NEW）
│   ├── test_p0.py          ← P0 核心交付测试  (45 断言)
│   ├── test_p1.py          ← P1 完成度提升   (29 断言)
│   └── test_p2.py          ← P2 精进方向     (40 断言)
│
├── logs/                   ← 日志（NEW）
│   ├── runs/               ← 2026-06-17 18:20 一轮带时间戳的运行日志
│   │   ├── test_p0_run_20260617_182044.log
│   │   ├── test_p1_run_20260617_182102.log
│   │   └── test_p2_run_20260617_182103.log
│   └── archive/            ← 2026-06-15 旧版测试日志
│       ├── test_p0.log
│       ├── test_p1.log
│       └── test_p2.log
│
├── docs/                   ← 项目文档与交付物（NEW）
│   ├── README.md                       ← 项目说明（原根目录）
│   ├── test_report_2026-06-17.md       ← 最新版测试报告
│   ├── test_report_v2.1_2026-06-15.md  ← 上一版测试报告（归档）
│   ├── speech_2026-06-17.md            ← 答辩演讲稿
│   ├── project_report_2026-06-17.tex   ← LaTeX 源
│   ├── project_report_2026-06-17.pdf   ← PDF 渲染
│   ├── progress_analysis_2026-06-15.md ← 进度分析
│   └── pptx_analysis_2026-05-23.txt    ← 课程 PPT 分析快照
│
└── tools/                  ← 非业务工具脚本（NEW）
    ├── analyze_pptx.py              ← PPT 课程作业分析
    ├── analyze_pptx_style.py        ← PPT 风格分析
    ├── add_slides_to_pptx.py        ← 批量添加幻灯片
    ├── reorganize_slides.py         ← 重新组织幻灯片
    ├── full_reorganize.py           ← PPT 全量重构
    └── render_report_pdf.py         ← LaTeX 报告 → PDF 渲染
```

---

## 3. 关键改动记录（2026-06-17）

| 操作 | 详情 |
|------|------|
| 新建目录 | `test/` `logs/` `docs/` `tools/` + `logs/runs/` + `logs/archive/` |
| 移动文件 | 17 个根目录散落文件按用途归档到 4 个新目录 |
| 路径修正 | `test/test_p*.py` 改 `ROOT = Path(__file__).resolve().parent.parent` |
| 路径修正 | `tools/render_report_pdf.py` 改 ROOT + 输出 PDF 路径到 `docs/` |
| 测试验证 | 114/114 全部通过（重跑 test_p0/p1/p2.py） |
| 渲染验证 | `python tools/render_report_pdf.py` 输出 487 KB PDF 到 `docs/` |

---

## 4. 后续维护建议

1. **测试运行**：从项目根目录跑 `python test/test_p0.py`（不是 `cd test`）。
2. **日志归档策略**：每次新跑测试时把带时间戳的 `.log` 放 `logs/runs/`，定期把超 1 个月的移入 `logs/archive/`。
3. **文档版本管理**：每次出报告用日期尾缀（`_2026-06-17`），旧版本直接移入 `docs/` 不删除。
4. **工具脚本**：未来新增的非业务脚本（如其他 PPT 辅助、PDF 工具）应直接进 `tools/`，不要回到根目录。
5. **根目录白名单**：`app.py` / `config.py` / `run_pipeline.py` / `requirements.txt` + 9 个业务子目录。其它文件都应该有归处。
