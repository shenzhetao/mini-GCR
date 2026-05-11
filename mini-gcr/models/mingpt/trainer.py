import torch
import numpy as np
from torch.utils.data import DataLoader
from tqdm import tqdm

class Trainer:
    def __init__(self, model, train_dataset, test_dataset, config):
        self.model = model
        self.train_dataset = train_dataset
        self.test_dataset = test_dataset
        self.config = config
        self.device = 'cpu'
        if torch.cuda.is_available():
            self.device = torch.cuda.current_device()
        self.model = self.model.to(self.device)

    def train(self):
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=self.config.learning_rate)

        def run_epoch(split):
            is_train = split == 'train'
            self.model.train(is_train)
            data = self.train_dataset if is_train else self.test_dataset
            loader = DataLoader(data, shuffle=is_train, pin_memory=True,
                                batch_size=self.config.batch_size,
                                num_workers=self.config.num_workers)

            losses = []
            pbar = tqdm(enumerate(loader), total=len(loader)) if is_train else enumerate(loader)
            for it, (x, y) in pbar:
                x = x.to(self.device)
                y = y.to(self.device)

                with torch.set_grad_enabled(is_train):
                    logits, loss = self.model(x, y)
                    loss = loss.mean()
                    losses.append(loss.item())

                if is_train:
                    self.model.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.grad_norm_clip)
                    optimizer.step()
                    pbar.set_description(f"epoch {epoch+1} iter {it}: train loss {loss.item():.5f}")

            return float(np.mean(losses))

        best_loss = float('inf')
        for epoch in range(self.config.max_epochs):
            train_loss = run_epoch('train')
            if self.test_dataset is not None:
                test_loss = run_epoch('test')
                print(f"epoch {epoch+1} test loss: {test_loss:.5f}")
            else:
                print(f"epoch {epoch+1} train loss: {train_loss:.5f}")
                test_loss = train_loss

            if test_loss < best_loss:
                best_loss = test_loss
                if self.config.ckpt_path is not None:
                    torch.save(self.model.state_dict(), self.config.ckpt_path)

class TrainerConfig:
    max_epochs = 10
    batch_size = 64
    learning_rate = 3e-4
    betas = (0.9, 0.95)
    grad_norm_clip = 1.0
    weight_decay = 0.1
    lr_decay = False
    warmup_tokens = 375e6
    final_tokens = 260e9
    ckpt_path = None
    num_workers = 0

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
