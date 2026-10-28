import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Optional

class EnhancedPointerNetwork(nn.Module):
    """
    Enhanced Pointer Network (EPN) for Surrogate Part-Level Subproblems.
    Direct implementation of the architecture proposed in:
    Liu et al. (IEEE TASE 2024), Section IV.B & IV.C.

    Key Features:
    1. Bidirectional LSTM Encoder over time horizon elements I_i = [F_i^(1), ..., F_i^(T)].
    2. Unidirectional LSTM Decoder with Attention Mechanism.
    3. Causal Masking Mechanism to mathematically forbid operation precedence violations.
    """
    def __init__(
        self,
        input_dim: int = 10,       # Max operations J padded in cost vector F^(t)
        hidden_dim: int = 64,      # Encoder/Decoder state dimension
        encoder_layers: int = 2,
        dropout: float = 0.1
    ):
        super(EnhancedPointerNetwork, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.encoder_layers = encoder_layers

        # Linear projection of input feature vector into embedding space
        self.input_embed = nn.Linear(input_dim, hidden_dim)

        # Bidirectional Encoder (Equation 33 in paper)
        self.encoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim // 2,
            num_layers=encoder_layers,
            bidirectional=True,
            batch_first=True,
            dropout=dropout if encoder_layers > 1 else 0.0
        )

        # Unidirectional Decoder
        self.decoder_cell = nn.LSTMCell(
            input_size=hidden_dim,
            hidden_size=hidden_dim
        )

        # Attention Network parameters (Equation 34 in paper: u_{j, k} = v^T tanh(W_1 e_k + W_2 d_j))
        self.W1 = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.W2 = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.v = nn.Linear(hidden_dim, 1, bias=False)

    def forward(
        self,
        input_seq: torch.Tensor,
        num_operations: int,
        target_seq: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            input_seq: (Batch, Horizon T, input_dim) - Cost vectors across planning horizon.
            num_operations: Number of sequential operations Ji in this job.
            target_seq: (Batch, num_operations) - Ground-truth start time indices if training.

        Returns:
            predicted_indices: (Batch, num_operations) - Selected start time slots.
            attention_distributions: (Batch, num_operations, T) - Softmax attention scores.
        """
        batch_size, horizon_T, _ = input_seq.size()
        device = input_seq.device

        # 1. Encode the input sequence
        embedded = F.relu(self.input_embed(input_seq))  # (B, T, hidden_dim)
        encoder_states, (h_n, c_n) = self.encoder(embedded)  # (B, T, hidden_dim)

        # Initial decoder state using the final forward/backward encoder state
        d_h = encoder_states[:, -1, :]  # (B, hidden_dim)
        d_c = torch.zeros(batch_size, self.hidden_dim, device=device)

        # Decoder external input initialized to zero vector o_0
        dec_input = torch.zeros(batch_size, self.hidden_dim, device=device)

        predicted_indices = []
        attention_distributions = []

        # Masking state: tracks the latest assigned time slot for each batch item (initially 0)
        # Equation 38: m_{j, t} = 0 for t < psi_{j-1}, 1 for t >= psi_{j-1}
        min_allowed_time = torch.zeros(batch_size, dtype=torch.long, device=device)

        # Precompute W1 * encoder_states for all time slots
        w1_e = self.W1(encoder_states)  # (B, T, hidden_dim)

        for op_idx in range(num_operations):
            # Step of Decoder RNN
            d_h, d_c = self.decoder_cell(dec_input, (d_h, d_c))

            # Attention scores computation (Equation 34)
            w2_d = self.W2(d_h).unsqueeze(1)  # (B, 1, hidden_dim)
            u = self.v(torch.tanh(w1_e + w2_d)).squeeze(-1)  # (B, T)

            # Causal Masking (Equations 38 & 39): Mask out all time slots before min_allowed_time
            time_indices = torch.arange(horizon_T, device=device).unsqueeze(0).expand(batch_size, -1)
            # Create mask: True where time_indices < min_allowed_time
            mask = time_indices < min_allowed_time.unsqueeze(1)
            u = u.masked_fill(mask, -1e9)

            # Normalized attention probability distribution (Equation 35)
            alpha = F.softmax(u, dim=-1)  # (B, T)
            attention_distributions.append(alpha)

            # Selection: Greedy argmax during evaluation, or teacher forcing if specified
            if target_seq is not None and self.training:
                chosen_idx = target_seq[:, op_idx]
            else:
                chosen_idx = torch.argmax(alpha, dim=-1)  # (B,)

            predicted_indices.append(chosen_idx)

            # Update causal mask for next operation:
            # Operation (j+1) cannot start before operation j start time
            min_allowed_time = chosen_idx

            # Feed chosen time-slot encoder embedding back as next decoder input
            gather_idx = chosen_idx.view(batch_size, 1, 1).expand(-1, 1, self.hidden_dim)
            dec_input = torch.gather(encoder_states, 1, gather_idx).squeeze(1)

        predicted_indices = torch.stack(predicted_indices, dim=1)  # (B, num_operations)
        attention_distributions = torch.stack(attention_distributions, dim=1)  # (B, num_operations, T)

        return predicted_indices, attention_distributions
