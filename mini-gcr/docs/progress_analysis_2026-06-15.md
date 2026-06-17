# mini-GCR 项目进度分析报告

> 分析日期：2026-06-15（v2.1，距上次报告 +23 天） | 项目代号：mini-GCR | 版本：2.0-lite
> 报告对照基准：`DEVELOPMENT_DOC.md`（4 周速成版开发文档 v2.0-lite）

---

## 一、项目概述

本项目旨在实现一个**生成式互补品推荐原型系统**，核心目标是在 4 周内交付一个可训练、可评估的 minGPT 生成式推荐模型，在互补品命中率 HR@10 上相比 SASRec 基线提升 ≥5%，并配套模板理由生成与 API 演示界面。

> 本次更新要点：对照最新代码与文档逐项核查进展，识别从 v2.0（2026-05-23）到 v2.1（2026-06-15）期间**已解决**与**仍未解决**的项，明确当前最关键的卡点。

---

## 二、已完成模块分析

### 2.1 数据层 ✅ (代码完整，未执行)

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| Mock 数据生成 | `scripts/generate_mock_data.py` | ✅ | 生成 1000 用户 / 500 商品 / 1 万交互的模拟数据，包含类目和时间戳 |
| 数据清洗与过滤 | `scripts/preprocess.py` | ✅ | 清洗缺失值、过滤低频交互（≥3）、构造用户购买序列、按留一法划分 train/val/test |
| 互补关系标注 | `scripts/build_complementary.py` | ✅ | 基于"7 天内相邻+类目不同"共现 + 类目规则 fallback，生成 `complementary_pairs.csv` 与 `reason_templates.json`（5 条模板） |
| 商品离散化 | `scripts/tokenize.py` | ✅ | 将商品 ID 映射为 3 个 token（base-256），生成 `item2tokens.json` / `token2item.json` 双向映射 |
| 流水线串联 | `run_pipeline.py` | ✅ | 按顺序执行 4 个数据脚本；**默认跳过训练和评估**（仅提示手动执行） |

**数据层缺陷**：
- `data/raw/`、`data/processed/`、`data/splits/` 三个目录至今**全部为空**，Mock 数据尚未真正生成，整个数据管线无法端到端运行
- `preprocess.py` 采用留一法（train = seq[:-2]、val = seq[:-1]、test = seq），与文档 §3.2 提到的"8:1:1 按用户划分"存在出入，实际按"时间序列留一"实现
- `build_complementary.py` 的共现时间窗口（7 天）已实现，但当前 Mock 数据本身类目分布是随机均匀的，互补对质量本身受限
- `tokenize.py` 对 `unique_items` 中不存在于码本范围内的 ID 未做容错（mock 数据 500 商品 < 256³，暂无问题，但若切到真实数据需扩展）

---

### 2.2 模型层 ✅ (代码完整，未训练)

#### 2.2.1 SASRec 基线模型

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 模型结构 | `models/sasrec/model.py` | ✅ | 标准 SASRec：2 层 MultiheadAttention、64 维嵌入、2 头、PointWise FFN、LayerNorm |
| 训练脚本 | `scripts/train_sasrec.py` | ✅ | BCE 损失 + 随机负采样 + Adam(1e-3)，训练 50 epoch 后保存至 `checkpoints/sasrec.pth` |
| 配置 | `config.py` | ✅ | 超参 SASREC_EPOCHS=50、LR=1e-3、EMBED=64、LAYERS=2、HEADS=2、BATCH=128 |

#### 2.2.2 minGPT 生成式模型

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 模型结构 | `models/mingpt/model.py` | ✅ | CausalSelfAttention + MLP + LayerNorm，6 层/4 头/256 维，~10M 参数 |
| 训练器 | `models/mingpt/trainer.py` | ✅ | AdamW + 梯度裁剪 + 按 loss 保存最优；当前仅 print 日志，无 TensorBoard/Wandb |
| 解码器 | `models/mingpt/decode.py` | ✅ | `generate()`（温度采样+top-k）、`constrained_beam_search()`（带互补约束的 beam search） |
| 训练脚本 | `scripts/train_mingpt.py` | ✅ | RecDataset 负责 token 序列化 + padding，调用 trainer |
| 配置 | `config.py` | ✅ | MINGPT_EPOCHS=50、BATCH=128、LR=3e-4、EMBED=256、LAYERS=6、HEADS=4 |

**模型层缺陷**：
- `checkpoints/` 目录为空，两个模型均未完成训练，HR@10 验收标准无法验证
- `constrained_beam_search` 的 beam 扩展时 `topk_probs / topk_indices` 在所有 beam 之间共享（每步从同一 top-`beam_size` 候选集中挑），导致 beam 多样性严重不足；同时约束惩罚仅在最后一步施加，对前两步的 token 序列没有引导效果
- `trainer.py` 中 `train_dataset` 同时承担 train/val 两个 split 的 DataLoader，未实现"早停 + 按验证 HR@10 保存最优"（文档 §4.2 明文要求"保存验证集 HR@10 最优模型"）
- `trainer.py` 缺少混合精度（AMP）、学习率 warmup、teacher forcing 比例调节等通用增强

---

### 2.3 服务层 ✅ (代码完整)

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 推理服务 | `services/inference.py` | ✅ | 端到端：加载 checkpoint → token 化 → beam search → 查互补表 → 包装推荐列表；带 fallback |
| 理由生成 | `services/reason.py` | ✅ | 类目对查模板并填商品名称；无模板时回退为"为您推荐一款搭配商品：xxx" |
| FastAPI 接口 | `app.py` | ✅ | `/health`、`/items`、`/recommend`、`/scene` 四个端点；CORS 已开启 |

**服务层缺陷**：
- `inference.py` 静默降级：`use_model=True` 但模型未加载时，自动 fallback 到查表，不返回任何 warning；调用方无法区分"模型生成"和"规则兜底"
- `reason.py` 的模板覆盖率：核心互补对仅 5 条规则（`Phone↔Case`、`Phone↔Charger`、`Laptop↔Accessories` 等），其余 `(core_cat, comp_cat)` 组合都回退到通用话术，覆盖率显著低于文档 §4.3 要求的 ≥80%
- `/scene` 接口只硬编码"露营"场景，其他输入返回空列表
- `inference.py` 启动时即 `load_state_dict`，未将加载逻辑做成 lazy；数据/模型缺失会让整个 service 启动时打 warning

---

### 2.4 评估层 ✅ (代码完整，未执行)

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 指标计算 | `scripts/eval.py` | ✅ | HR@K、NDCG@K、ComplementaryRatio@K 三类指标 |
| 消融实验 | `scripts/eval.py` | ✅ | 三路对比：Full model（minGPT+约束）、w/o Constraint（minGPT 无约束）、Baseline SASRec |
| 图表生成 | `scripts/eval.py` | ✅ | matplotlib 柱状图输出至 `reports/eval_comparison.png` |
| 结果导出 | `scripts/eval.py` | ✅ | 汇总指标写入 `reports/eval_results.csv` |

**评估层缺陷**：
- 评测上限硬编码 100 条（`if total >= 100: break`），样本量偏小，统计意义有限
- 缺少 `MRR`、`Coverage@K`、AUC-ROC 等文档 §5.1 提到但未实现的扩展指标
- 缺少多次随机种子实验 + t-test，无法判定 HR@10 ≥5% 提升是否统计显著
- 由于模型未训练，`reports/` 目录为空，评估结果暂无法产出

---

### 2.5 前端层 ✅ (基础完成)

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| Vue 3 项目 | `frontend/src/App.vue` | ✅ | 商品样例网格、购物车选择、Top-K / 约束 / 模型开关、推荐结果卡片、场景接口 |
| 样式 | `frontend/src/style.css` | ✅ | 玻璃拟态 UI（径向渐变 hero + 卡片阴影 + 响应式 grid），无 Tailwind 依赖 |
| 构建配置 | `frontend/package.json` + `vite.config.js` | ✅ | `/api` 代理到 `http://localhost:8000`，含 lucide-vue-next 图标 |
| 入口 | `frontend/index.html` + `main.js` | ✅ | Vue 挂载正常 |

**前端层缺陷**：
- 商品样例仅显示 ID/标题/类目，无图片缩略图
- 推荐结果卡片缺少"模型对比视图"（无法在同一界面比较 SASRec / minGPT+约束 / minGPT 无约束 三路输出）
- 无训练状态/指标可视化（无法看到 loss 曲线或 HR@10 柱状图）
- "优先使用已训练 minGPT 权重" 开关为前端可勾选项，但当前无任何 checkpoint，勾选后端会进入 fallback，前端没有提示这一点

---

### 2.6 基础设施 ✅

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 配置中心 | `config.py` | ✅ | 集中管理所有路径、超参数、目录初始化（`ensure_dirs()`） |
| 流水线脚本 | `run_pipeline.py` | ✅ | 串联数据生成→预处理→互补对构建→离散化；**跳过训练和评估步骤**（仅打印提示） |
| 依赖管理 | `requirements.txt` | ✅ | FastAPI / Uvicorn / PyTorch / Pandas / NumPy / Pydantic / matplotlib / tqdm |
| 前端依赖 | `frontend/package.json` | ✅ | Vue 3 + Vite + lucide-vue-next |
| README | `README.md` | ✅ | 提供 backend / train / eval / api / frontend 五段启动说明 |

---

## 三、未完成任务清单

### P0 — 必须完成（影响核心交付，验收硬阻塞）

| # | 任务 | 优先级 | 阻塞项 / 当前状态 |
|---|------|--------|------------------|
| 1 | **运行数据管线，端到端生成 data/** | P0 | 当前 `data/` 为空；需按序执行 `generate_mock_data.py` → `preprocess.py` → `build_complementary.py` → `tokenize.py` |
| 2 | **训练 SASRec 基线** | P0 | 需执行 `scripts/train_sasrec.py` → 生成 `checkpoints/sasrec.pth`；当前无任何训练日志 |
| 3 | **训练 minGPT 生成式模型** | P0 | 需执行 `scripts/train_mingpt.py` → 生成 `checkpoints/mingpt.pth`；50 epoch 在 CPU 上预估耗时较长 |
| 4 | **运行离线评估并验证 HR@10 ≥5% 提升** | P0 | 需执行 `scripts/eval.py`；当前 eval 上限仅 100 条样本，建议先扩大 |
| 5 | **修复 `constrained_beam_search` beam 多样性 bug** | P0 | 当前实现 beam 共享 top-k；改为每 beam 独立采样，或在每步都施加互补约束 |

### P1 — 应该完成（影响完成度与可解释性）

| # | 任务 | 优先级 |
|---|------|--------|
| 6 | 将 `trainer.py` 改为按**验证集 HR@10**保存最优（满足文档 §4.2） |
| 7 | 扩展 `reason_templates.json` 模板覆盖范围（目标 ≥80% 常见类目对） |
| 8 | 修复 `inference.py` 的静默降级：模型未加载时显式返回 warning 或 `model_used: false` 字段 |
| 9 | 评估脚本去掉 `if total >= 100: break` 上限，跑完整测试集 |
| 10 | 增加 TensorBoard / Wandb 训练监控（替代 print） |
| 11 | 增加早停（基于验证集 HR@10 而非 loss） |

### P2 — 建议完成（演示与精进）

| # | 任务 |
|---|------|
| 12 | 前端增加三路模型对比视图（SASRec / minGPT / minGPT+约束） |
| 13 | 前端接入训练日志展示 / 评估柱状图（评估完成后） |
| 14 | `/scene` 接口扩展多场景（办公、户外、健身等） |
| 15 | 增加 API 缓存 / 推理结果预计算（提升演示流畅度） |
| 16 | 多次随机种子实验 + t-test，给出统计显著性 |
| 17 | 评估结果导出为 PDF 报告（`scripts/report_pdf.py`） |

---

## 四、可精进方向分析

### 4.1 模型层精进

#### (1) minGPT 生成质量提升

当前实现是标准 GPT 自回归生成，可以从以下角度增强：

- **商品感知位置编码**：将标准正弦位置编码换成"商品类别 + 位置"双轴编码，让模型感知商品类目边界（每个商品占 3 个 token，但跨商品时应强信号切换）
- **类别条件解码**：在解码时将核心商品类别作为额外条件输入（prefix-tuning 风格），引导生成特定类别的互补品
- **对比学习损失**：在交叉熵损失之外，引入 InfoNCE 拉近"已知互补对"商品在隐空间的距离

#### (2) SASRec 基线增强

- 加入类别特征 Embedding（当前只用了 item ID）
- 训练时使用更长序列（如 50）+ LayerDrop 正则化
- 评估时计算 SASRec 的 ComplementaryRatio@10（当前 eval.py 只算了 minGPT 两侧的互补率），作为基线互补能力的对照

#### (3) 互补约束解码优化

当前 `constrained_beam_search`：
- 每步从 `topk_probs/topk_indices` 共享集合中扩展 → beam 多样性严重不足
- 惩罚仅施加在**第 3 个 token（最后一步）** 完成时 → 前两个 token 不受约束，可能导致前两个 token 已锁死到非互补商品

可改进为：
- 每步从每个 beam 自己的 logits 中独立取 top-`beam_size`，保持多样性
- **逐步解码 + 早期剪枝**：每生成 1 个 token 后即检查前缀能否组合成 `valid_items` 中的商品 ID；不能则剪掉
- 多样化束搜索（Diverse Beam Search）分组惩罚
- 温度 / 长度归一化（目前 score 简单累加 log_prob）

---

### 4.2 数据层精进

#### (1) 引入真实数据集

- 接入天池 Tmall 数据集（替代 100% 随机的 Mock）
- 备选：Amazon Electronics 子集

#### (2) 互补对质量提升

当前互补对构建策略：

- 时间窗口 7 天 + 类目不同的相邻购买（每对 +2 分）
- 同用户跨类目共现（每对 +1 分，threshold ≥2）

可精进为：
- 引入外部知识图谱（ProductKB、ConceptNet）辅助标注
- 用商品标题语义相似度过滤噪声对
- 用 GNN 建模商品之间的互补/替代关系

#### (3) 数据增强

- 序列增强：随机截断/重复采样扩充训练集
- 负采样策略：popularity-based 或对抗负采样替代随机负采样

---

### 4.3 理由生成精进

当前理由生成是纯模板填充 + 类目对查表（5 条模板），覆盖率低：

| 方向 | 说明 |
|------|------|
| 模板库扩充 | 从 5 条扩展到 ≥80% 常见类目对 |
| 关键词抽取 | 从商品标题中抽取关键词（TF-IDF / RAKE）替换占位符 |
| 多层级模板 | 短/中/长三种理由长度版本供前端选择 |
| 大模型后处理（可选） | 离线调用 Qwen/ChatGLM 对模板理由润色 |

---

### 4.4 评估层精进

#### (1) 评估指标扩展

- **MRR**（Mean Reciprocal Rank）：更敏感的排名指标
- **Coverage@K**：推荐列表的多样性覆盖
- **类目多样性**：Top-K 中覆盖的类目数量
- **AUC-ROC**：整体排序能力

#### (2) 统计显著性检验

多次随机种子实验，对各模型指标做 t-test，验证 HR@10 提升是否统计显著。

#### (3) 消融分析完善

- **w/o Tokenization**：minGPT 直接预测商品 ID 而非 token
- **w/o Complementary Pairs**：仅靠序列模式生成
- **w/o Reason**：不评估理由，仅看推荐指标（文档 §5.2 已列为可选）

---

### 4.5 工程层精进

| 方向 | 当前状态 | 精进建议 |
|------|----------|----------|
| 模型保存与加载 | 仅按 loss 保存 | 改为按 HR@10 早停 + 版本管理 |
| GPU 训练支持 | trainer 写了 CUDA 检查但未充分测试 | 验证多卡 DataParallel |
| 配置管理 | 硬编码在 `config.py` | 迁移到 YAML/JSON，支持多实验切换 |
| 日志系统 | 仅 print | 迁移到 Python `logging` 或 Wandb |
| Docker 部署 | 无 | 添加 Dockerfile |
| API 文档 | 默认 FastAPI docs | 补充请求/响应 Schema 文档 |

---

### 4.6 前端层精进

| 功能 | 当前状态 | 精进建议 |
|------|----------|----------|
| 模型对比视图 | 无 | 三列对比（SASRec / minGPT / minGPT+约束） |
| 指标仪表盘 | 无 | 展示 HR@10、NDCG 柱状图 |
| 实时训练曲线 | 无 | 接入 TensorBoard 或 WebSocket 推送 |
| 商品图片 | 无 | 接入商品图片 URL |
| 场景推荐扩展 | 仅有"露营"硬编码 | 多场景下拉菜单 |

---

## 五、四周开发建议

按照原计划的四周节奏，**当前已超过第 4 周节点**（2026-05-23 文档所列第 1 周起点），因此建议改为"剩余冲刺清单"：

```
剩余冲刺（4 周剩余任务压缩到未来 1~2 周）
├── 数据与基线（必须做）
│   ├── 立刻跑通 run_pipeline.py，确认 data/ 全部生成
│   ├── 训练 SASRec，记录基线 HR@10
│   └── 训练 minGPT（CPU 至少 1~2 小时）
│
├── 核心修复（必须做）
│   ├── 修复 constrained_beam_search 的 beam 多样性 bug
│   ├── 改造 trainer.py 为按验证 HR@10 早停
│   └── 修复 inference.py 的静默降级
│
├── 评估与理由（必须做）
│   ├── 跑通 eval.py（去掉 100 条上限）
│   ├── 验证 HR@10 ≥5% 提升并多次随机种子做显著性检验
│   └── 扩充 reason_templates 至 ≥80% 覆盖
│
└── 演示（应该做）
    ├── 启动 FastAPI + 前端联调
    ├── 准备静态缓存结果用于答辩
    └── 撰写评估报告
```

---

## 六、与 v2.0 报告（2026-05-23）对比

| 维度 | v2.0（5/23）状态 | v2.1（6/15）状态 | 变化 |
|------|------------------|------------------|------|
| 数据目录 | 空 | **仍为空** | ❌ 未推进 |
| 模型 checkpoint | 空 | **仍为空** | ❌ 未推进 |
| 评估结果 | 无 | **仍无** | ❌ 未推进 |
| 核心代码完整性 | ~80% | ~80%（与上次一致） | ➖ 无新增代码 |
| 课程作业 PPT | 未提及 | 新增 4 个辅助脚本（analyze_pptx / add_slides / reorganize / full_reorganize）+ 1 个分析快照（pptx_analysis.txt） | ✅ 已并入项目 |

---

## 七、总结

**代码完成度**：项目整体架构清晰，模块划分合理，核心代码（模型、推理、评估、API、前端）均已实现，与 `DEVELOPMENT_DOC.md` v2.0-lite 的要求一致，约覆盖文档中 **80%** 的代码量。剩余 20% 主要是"工程化增强项"（TensorBoard、Docker、YAML 配置等），不影响 MVP 演示。

**功能完成度**：从 v2.0 到 v2.1 的 23 天里，**功能完成度无实质推进**——数据目录、checkpoint 目录、reports 目录依然全部为空，核心模块（数据→训练→评估）的端到端链路未跑通。HR@10 ≥5% 这一硬验收指标尚无任何数据支撑。

**最关键卡点**（按优先级）：
1. **执行数据管线**（一行命令即可解决，是后续所有步骤的前置）
2. **完成 SASRec + minGPT 训练**（约 1~2 小时 CPU 训练）
3. **修复 beam search 多样性 bug**（影响 minGPT 实际生成质量）
4. **按 HR@10 验证提升**（这是 4 周计划的验收硬指标）

**核心待解决问题**：Beam search 多样性不足、互补约束解码效果待验证、理由模板覆盖率低、评估指标提升幅度未知。即使从今天起 0 推进，按"先模型后接口，先评估后美化"的原则，**1 周内仍有可能完成数据+训练+评估三步走**，但需要在未来 1~2 周集中突破。
