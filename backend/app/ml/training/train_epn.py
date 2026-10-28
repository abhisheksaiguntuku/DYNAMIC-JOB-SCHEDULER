import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from pathlib import Path

from app.ml.models.pointer_network import EnhancedPointerNetwork
from app.ml.data.subproblem_dataset import SurrogateSubproblemDataset, collate_subproblems

def train_epn(
    epochs: int = 15,
    batch_size: int = 32,
    lr: float = 0.005,
    save_path: str = "models/checkpoints/epn_model.pth"
):
    """
    Trains the Enhanced Pointer Network with Cross-Entropy Loss (Equation 40 & 41 in paper).
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 1. Datasets
    train_ds = SurrogateSubproblemDataset(num_samples=600, horizon_T=40, max_operations=5, seed=42)
    val_ds = SurrogateSubproblemDataset(num_samples=100, horizon_T=40, max_operations=5, seed=100)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, collate_fn=collate_subproblems)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_subproblems)

    # 2. Model & Optimizer
    model = EnhancedPointerNetwork(input_dim=5, hidden_dim=64, encoder_layers=2).to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    best_val_loss = float("inf")

    print(f"Starting training on {device} for {epochs} epochs...")

    for epoch in range(1, epochs + 1):
        model.train()
        total_train_loss = 0.0

        for cost_batch, target_batch, max_ops in train_loader:
            cost_batch = cost_batch.to(device)
            target_batch = target_batch.to(device)

            optimizer.zero_grad()
            _, attention_dist = model(cost_batch, num_operations=max_ops, target_seq=target_batch)

            # Flatten across batch and operations for cross-entropy
            # attention_dist: (B, num_ops, T) -> (B * num_ops, T)
            # target_batch: (B, num_ops) -> (B * num_ops)
            loss = criterion(
                attention_dist.view(-1, attention_dist.size(-1)),
                target_batch.view(-1)
            )

            loss.backward()
            optimizer.step()
            total_train_loss += loss.item()

        avg_train_loss = total_train_loss / len(train_loader)

        # Validation
        model.eval()
        total_val_loss = 0.0
        with torch.no_grad():
            for cost_batch, target_batch, max_ops in val_loader:
                cost_batch = cost_batch.to(device)
                target_batch = target_batch.to(device)
                _, attention_dist = model(cost_batch, num_operations=max_ops)
                loss = criterion(
                    attention_dist.view(-1, attention_dist.size(-1)),
                    target_batch.view(-1)
                )
                total_val_loss += loss.item()

        avg_val_loss = total_val_loss / len(val_loader)
        print(f"Epoch {epoch:02d}/{epochs:02d} | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f}")

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "val_loss": best_val_loss,
                "input_dim": 5,
                "hidden_dim": 64
            }, save_path)

    print(f"Training completed. Best model checkpoint saved to {save_path}")

if __name__ == "__main__":
    train_epn()
