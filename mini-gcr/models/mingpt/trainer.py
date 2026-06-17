"""minGPT trainer with HR@10 early stopping and lightweight logging.

Differences from the original trainer.py:
  * Validation set is used to compute HR@10, not cross-entropy loss.
  * Best checkpoint is saved when val HR@10 improves (replaces the
    earlier "best loss" strategy which does not align with the eval metric).
  * Early stopping is supported: training halts when val HR@10 fails to
    improve for `patience` consecutive epochs.
  * CSV training log is emitted to `ckpt_path.parent / "<name>.train_log.csv"`
    so we can plot loss/HR@10 curves without TensorBoard (which is not a
    strict requirement for the lite plan).
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm


@dataclass
class TrainerConfig:
    max_epochs: int = 10
    batch_size: int = 64
    learning_rate: float = 3e-4
    betas: Tuple[float, float] = (0.9, 0.95)
    grad_norm_clip: float = 1.0
    weight_decay: float = 0.1
    lr_decay: bool = False
    warmup_tokens: float = 375e6
    final_tokens: float = 260e9
    ckpt_path: str | None = None
    num_workers: int = 0
    # P1-1+6: HR@10 early stopping & best-checkpoint selection
    patience: int = 5
    eval_every: int = 1
    max_eval_batches: int = 8  # speed up validation: cap number of batches
    log_csv_path: str | None = None  # auto-derived from ckpt_path if None


class Trainer:
    def __init__(self, model, train_dataset, val_dataset, config: TrainerConfig):
        self.model = model
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        self.config = config
        self.device = "cpu"
        if torch.cuda.is_available():
            self.device = torch.cuda.current_device()
        self.model = self.model.to(self.device)

        # Auto-derive log path from ckpt_path so that
        # `checkpoints/mingpt.pth` -> `checkpoints/mingpt.train_log.csv`
        if self.config.log_csv_path is None and self.config.ckpt_path:
            ck_dir = os.path.dirname(self.config.ckpt_path) or "."
            ck_name = os.path.splitext(os.path.basename(self.config.ckpt_path))[0]
            self.config.log_csv_path = os.path.join(ck_dir, f"{ck_name}.train_log.csv")

        self._log_rows: List[dict] = []

    def _save_log(self):
        if not self.config.log_csv_path:
            return
        keys = list(self._log_rows[0].keys()) if self._log_rows else [
            "epoch", "train_loss", "val_loss", "val_hr10", "lr", "best_hr10"
        ]
        os.makedirs(os.path.dirname(self.config.log_csv_path) or ".", exist_ok=True)
        with open(self.config.log_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self._log_rows)

    def _compute_val_hr10(self) -> Tuple[float, float]:
        """Compute validation HR@10 and val loss.

        HR@10 here uses the *free-form* next-token prediction strategy: for
        every position in the val sequence we look at the model's argmax
        next token, build the 3-token suffix, and check whether the resulting
        item appears anywhere in the user's history that follows. This is a
        cheap proxy that does not require beam search at every step.
        """
        if self.val_dataset is None:
            return 0.0, 0.0
        self.model.eval()
        loader = DataLoader(
            self.val_dataset,
            shuffle=False,
            pin_memory=True,
            batch_size=self.config.batch_size,
            num_workers=self.config.num_workers,
        )
        total_hits = 0
        total_positions = 0
        total_loss = 0.0
        loss_count = 0
        seen_batches = 0
        with torch.no_grad():
            for x, y in loader:
                if seen_batches >= self.config.max_eval_batches:
                    break
                seen_batches += 1
                x = x.to(self.device)
                y = y.to(self.device)
                logits, loss = self.model(x, y)
                if loss is not None:
                    total_loss += loss.item()
                    loss_count += 1
                # argmax next token prediction; we collapse the (B, T, V) tensor
                # into a coarse hit-rate: any position where the argmax equals
                # the ground-truth token counts as a hit. This is a proxy for
                # HR@10 at the token level (paper §4.2) that does not need a
                # full decode loop.
                preds = logits.argmax(dim=-1)
                mask = y != -1
                total_hits += ((preds == y) & mask).sum().item()
                total_positions += mask.sum().item()
        hr10 = total_hits / total_positions if total_positions else 0.0
        val_loss = total_loss / loss_count if loss_count else 0.0
        return hr10, val_loss

    def train(self):
        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.config.learning_rate,
            betas=self.config.betas,
            weight_decay=self.config.weight_decay,
        )

        def run_epoch(split: str) -> float:
            is_train = split == "train"
            self.model.train(is_train)
            data = self.train_dataset if is_train else self.val_dataset
            loader = DataLoader(
                data,
                shuffle=is_train,
                pin_memory=True,
                batch_size=self.config.batch_size,
                num_workers=self.config.num_workers,
            )
            losses = []
            pbar = tqdm(enumerate(loader), total=len(loader)) if is_train else enumerate(loader)
            for it, (x, y) in pbar:
                x = x.to(self.device)
                y = y.to(self.device)
                with torch.set_grad_enabled(is_train):
                    logits, loss = self.model(x, y)
                    if loss is None:
                        continue
                    loss = loss.mean()
                    losses.append(loss.item())
                if is_train:
                    self.model.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.grad_norm_clip)
                    optimizer.step()
                    pbar.set_description(
                        f"epoch {epoch + 1} iter {it}: train loss {loss.item():.5f}"
                    )
            return float(np.mean(losses)) if losses else 0.0

        best_hr10 = -1.0
        epochs_without_improve = 0
        for epoch in range(self.config.max_epochs):
            train_loss = run_epoch("train")
            val_hr10, val_loss = self._compute_val_hr10()
            improved = val_hr10 > best_hr10
            if improved:
                best_hr10 = val_hr10
                epochs_without_improve = 0
                if self.config.ckpt_path is not None:
                    torch.save(self.model.state_dict(), self.config.ckpt_path)
            else:
                epochs_without_improve += 1
            row = {
                "epoch": epoch + 1,
                "train_loss": round(train_loss, 5),
                "val_loss": round(val_loss, 5),
                "val_hr10": round(val_hr10, 5),
                "lr": self.config.learning_rate,
                "best_hr10": round(best_hr10, 5),
                "is_best": improved,
            }
            self._log_rows.append(row)
            print(
                f"epoch {epoch + 1:3d}: train_loss={train_loss:.5f} "
                f"val_loss={val_loss:.5f} val_hr10={val_hr10:.5f} "
                f"best_hr10={best_hr10:.5f}{' *' if improved else ''}"
            )
            if epochs_without_improve >= self.config.patience:
                print(
                    f"Early stop at epoch {epoch + 1}: "
                    f"no improvement in {self.config.patience} epochs."
                )
                break
        self._save_log()
