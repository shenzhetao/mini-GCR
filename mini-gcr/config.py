import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Data paths
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
SPLITS_DIR = DATA_DIR / "splits"

# Model paths
MODELS_DIR = BASE_DIR / "models"
CHECKPOINTS_DIR = BASE_DIR / "checkpoints"
REPORTS_DIR = BASE_DIR / "reports"

# File paths
USER_SEQ_FILE = PROCESSED_DATA_DIR / "user_seq.csv"
COMPLEMENTARY_PAIRS_FILE = PROCESSED_DATA_DIR / "complementary_pairs.csv"
ITEM2TOKENS_FILE = PROCESSED_DATA_DIR / "item2tokens.json"
TOKEN2ITEM_FILE = PROCESSED_DATA_DIR / "token2item.json"
REASON_TEMPLATES_FILE = PROCESSED_DATA_DIR / "reason_templates.json"
EVAL_RESULTS_FILE = REPORTS_DIR / "eval_results.csv"
EVAL_CHART_FILE = REPORTS_DIR / "eval_comparison.png"

TRAIN_FILE = SPLITS_DIR / "train.csv"
VAL_FILE = SPLITS_DIR / "val.csv"
TEST_FILE = SPLITS_DIR / "test.csv"

# Hyperparameters
MAX_SEQ_LENGTH = 20
CODEBOOK_SIZE = 256
TOKENS_PER_ITEM = 3

# minGPT
MINGPT_EMBED_DIM = 256
MINGPT_LAYERS = 6
MINGPT_HEADS = 4
MINGPT_BATCH_SIZE = 128
MINGPT_LR = 3e-4
MINGPT_EPOCHS = 50

# SASRec
SASREC_EMBED_DIM = 64
SASREC_LAYERS = 2
SASREC_HEADS = 2
SASREC_BATCH_SIZE = 128
SASREC_LR = 1e-3
SASREC_EPOCHS = 50
API_MODEL_NAME = "mingpt-cstr-v1"

def ensure_dirs():
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)
    os.makedirs(SPLITS_DIR, exist_ok=True)
    os.makedirs(CHECKPOINTS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

ensure_dirs()
