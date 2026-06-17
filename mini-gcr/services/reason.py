"""Reason generator with multi-template rotation (P1-2)."""
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from config import REASON_TEMPLATES_FILE, RAW_DATA_DIR


class ReasonGenerator:
    """Pick a template for a (core_category, comp_category) pair and fill it
    in with the product titles. Supports multiple alternates per pair so the
    same call site does not get identical text on every render.
    """

    def __init__(self):
        raw_templates = {}
        if REASON_TEMPLATES_FILE.exists():
            with open(REASON_TEMPLATES_FILE, "r", encoding="utf-8") as f:
                raw_templates = json.load(f)

        # Group alternates. Keys ending in __altN are alt variants of the
        # canonical "<core>_<comp>" key. We keep the canonical first, then
        # all alts in order.
        self._variants: dict[str, list[str]] = defaultdict(list)
        alt_re = re.compile(r"^(?P<base>.+)__alt(?P<n>\d+)$")
        for k, v in raw_templates.items():
            m = alt_re.match(k)
            if m:
                base = m.group("base")
                n = int(m.group("n"))
                # ensure list is long enough
                while len(self._variants[base]) <= n:
                    self._variants[base].append("")
                self._variants[base][n] = v
            else:
                # canonical key; place at index 0
                if not self._variants[k]:
                    self._variants[k].append(v)
                else:
                    self._variants[k][0] = v

        # Deduplicate variants and drop empties
        self._variants = {k: [t for t in v if t] for k, v in self._variants.items()}

        # Item metadata
        self.item_info: dict = {}
        raw_file = Path(RAW_DATA_DIR) / "tmall_sample.csv"
        if raw_file.exists():
            df = pd.read_csv(raw_file)
            if "title" not in df.columns:
                df["title"] = df["item_id"].apply(lambda x: f"Item {x}")
            if "category" not in df.columns:
                df["category"] = "未知分类"
            self.item_info = (
                df.drop_duplicates(subset=["item_id"])
                .set_index("item_id")
                .to_dict("index")
            )

        # Coverage stats (filled in lazily)
        self._total_calls = 0
        self._covered_calls = 0

    @property
    def coverage(self) -> float:
        if self._total_calls == 0:
            return 0.0
        return self._covered_calls / self._total_calls

    def variants_for(self, key: str) -> list[str]:
        return self._variants.get(key, [])

    def generate(self, core_item_id, comp_item_id) -> str:
        self._total_calls += 1
        core_info = self.item_info.get(int(core_item_id), {})
        comp_info = self.item_info.get(int(comp_item_id), {})

        core_cat = core_info.get("category", "未知分类")
        comp_cat = comp_info.get("category", "未知分类")
        core_name = core_info.get("title", "该商品")
        comp_name = comp_info.get("title", "推荐商品")

        key = f"{core_cat}_{comp_cat}"
        variants = self.variants_for(key)
        if not variants:
            # Fall back to a generic phrase that still mentions the product
            tmpl = "为您推荐一款搭配商品：{comp_item_name}。"
        else:
            # Deterministic but item-dependent rotation: pick the variant
            # whose index equals (core_item_id + comp_item_id) mod len.
            idx = (int(core_item_id) + int(comp_item_id)) % len(variants)
            tmpl = variants[idx]
            self._covered_calls += 1

        return tmpl.format(
            core_category=core_cat,
            comp_category=comp_cat,
            core_item_name=core_name,
            comp_item_name=comp_name,
        )

    def coverage_pairs(self) -> set[tuple[str, str]]:
        """Return the set of (core_cat, comp_cat) pairs that have at least
        one template. Used by the eval script to compute coverage %."""
        out = set()
        for key in self._variants.keys():
            if "__alt" in key:
                continue
            if "_" in key:
                a, b = key.split("_", 1)
                out.add((a, b))
        return out
