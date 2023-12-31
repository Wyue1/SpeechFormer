import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import math
import warnings

def statistical_information(hop=0.01):  # unit: second
    hop = int(hop * 1000)
    Merge = [50, 250, 1000]      # corresponding to the original audio length. (unit: millisecond)
    Locals = [50, 400, 2000]
    Merge = [s//hop for s in Merge]    # //hop -> num of tokens
    Locals = [l//hop for l in Locals]
    Merge.append(-1)    # -1 means global
    Locals.append(-1)
    return Locals, Merge
    
def create_PositionalEncoding(input_dim, max_seq_len=2000): 
    position_encoding = np.array([ 
        [pos / np.power(10000, 2.0 * (j // 2) / input_dim) for j in range(input_dim)] 
        for pos in range(max_seq_len)]) 
    
    position_encoding[:, 0::2] = np.sin(position_encoding[:, 0::2])
    position_encoding[:, 1::2] = np.cos(position_encoding[:, 1::2])

    position_encoding = torch.from_numpy(position_encoding.astype(np.float32))
    position_encoding = nn.Parameter(position_encoding, requires_grad=False) 
    
    return position_encoding

def _get_activation_fn(activation: str):
    """ Returns the activation function corresponding to `activation` """
    if activation == "relu":
        return F.relu
    elif activation == "gelu":
        return F.gelu
    elif activation == "tanh":
        return torch.tanh
    elif activation == "linear":
        return lambda x: x
    else:
        raise RuntimeError("--activation-fn {} not supported".format(activation))

def add_position(x, position=None, mask=None):
    '''add position information to the input x

    x: B, T, C
    position: T, C
    mask: B, T
    '''
    if position is None:
        return x
    else:
        B, T = x.shape[:2]
        position = position[:T].unsqueeze(dim=0).repeat(B, 1, 1)  # -> B, T, C
        position = position*((1 - mask.unsqueeze(-1).type_as(x))) if mask is not None else position
        return x + position

def _no_grad_trunc_normal_(tensor: torch.Tensor, mean: float = 0., std: float = 1., a: float = -2., b: float = 2.):
    # Method based on https://people.sc.fsu.edu/~jburkardt/presentations/truncated_normal.pdf
    def norm_cdf(x):
        # Computes standard normal cumulative distribution function
        return (1. + math.erf(x / math.sqrt(2.))) / 2.

    if (mean < a - 2 * std) or (mean > b + 2 * std):
        warnings.warn("mean is more than 2 std from [a, b] in nn.init.trunc_normal_. "
                      "The distribution of values may be incorrect.",
                      stacklevel=2)

    with torch.no_grad():
        # Values are generated by using a truncated uniform distribution and
        # then using the inverse CDF for the normal distribution.
        # Get upper and lower cdf values
        l = norm_cdf((a - mean) / std)
        u = norm_cdf((b - mean) / std)

        # Uniformly fill tensor with values from [l, u], then translate to
        # [2l-1, 2u-1].
        tensor.uniform_(2 * l - 1, 2 * u - 1)

        # Use inverse cdf transform for normal distribution to get truncated
        # standard normal
        tensor.erfinv_()

        # Transform to proper mean, std
        tensor.mul_(std * math.sqrt(2.))
        tensor.add_(mean)

        # Clamp to ensure it's in the proper range
        tensor.clamp_(min=a, max=b)
        return tensor

def get_overlap_segments(x: torch.Tensor, window_size: int):
    '''Get overlap segments for local attention. Sacrifice memory for speed.

    Args: 
        x: Input sequence in shape (B, T, C).
        window_size: The needed length of the segment. Must be an odd number.
    
    Return:
        (b, t, window_size, c)
    '''
    # assert window_size % 2, f'window_size must be an odd number, but get {window_size}.'
    if not window_size % 2:
        window_size += 1     # window_size must be an odd number
     
    b, t, c = x.shape
    pad_len = (window_size - 1) // 2
    x = F.pad(x, (0, 0, pad_len, pad_len), value=0)

    stride = x.stride()
    out_shape = (b, t, window_size, c)
    out_stride = (stride[0], stride[1], stride[1], stride[2])

    return torch.as_strided(x, size=out_shape, stride=out_stride)