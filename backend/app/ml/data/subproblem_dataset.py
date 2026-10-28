import random
# pyrefly: ignore [missing-import]
import torch
# pyrefly: ignore [missing-import]
from torch.utils.data import Dataset, DataLoader
from typing import List, Dict, Any, Tuple

class SurrogateSubproblemDataset(Dataset):
    """
    Synthetic Surrogate Part-Subproblem Dataset Generator.
    Models part-wise subproblems derived from Surrogate Lagrangian Relaxation.
    Generates cost vectors F_i^(t) across horizon T and optimal ground-truth targets.
    """
    def __init__(
        self,
        num_samples: int = 500,
        horizon_T: int = 40,
        max_operations: int = 5,
        seed: int = 42
    ):
        super(SurrogateSubproblemDataset, self).__init__()
        random.seed(seed)
        torch.manual_seed(seed)
        self.num_samples = num_samples
        self.horizon_T = horizon_T
        self.max_operations = max_operations

        self.data: List[Tuple[torch.Tensor, torch.Tensor, int]] = []
        self._generate_samples()

    def _generate_samples(self):
        for _ in range(self.num_samples):
            num_ops = random.randint(3, self.max_operations)
            # Create synthetic cost matrix over time horizon T: (T, max_operations)
            cost_matrix = torch.rand(self.horizon_T, self.max_operations) * 10.0

            # Realistic optimal target start times satisfying precedence (start_k <= start_{k+1})
            targets = []
            cur_time = random.randint(0, 5)
            for _ in range(num_ops):
                targets.append(cur_time)
                # Next operation begins after a duration of 3 to 7 slots
                cur_time = min(self.horizon_T - 1, cur_time + random.randint(3, 7))

            target_tensor = torch.tensor(targets, dtype=torch.long)
            self.data.append((cost_matrix, target_tensor, num_ops))

    def __len__(self) -> int:
        return self.num_samples

    def __getitem__(self, idx: int):
        return self.data[idx]

def collate_subproblems(batch):
    cost_matrices, targets, num_ops = zip(*batch)
    cost_batch = torch.stack(cost_matrices, dim=0)  # (B, T, max_operations)
    max_ops = max(num_ops)
    
    # Pad targets to uniform length for batch processing
    padded_targets = []
    for t in targets:
        if len(t) < max_ops:
            padding = torch.full((max_ops - len(t),), t[-1].item(), dtype=torch.long)
            padded_targets.append(torch.cat([t, padding]))
        else:
            padded_targets.append(t[:max_ops])
    target_batch = torch.stack(padded_targets, dim=0)

    return cost_batch, target_batch, max_ops
