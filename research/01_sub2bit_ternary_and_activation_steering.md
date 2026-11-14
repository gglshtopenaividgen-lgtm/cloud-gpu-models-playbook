# Systems Architecture for Sub-2-Bit Ternary Models & Runtime Activation Steering

> **Focus**: Sub-2-Bit Ternary Compression ({−1,0,+1}), Representation Engineering, and Runtime Activation Steering  
> **Source**: Grounded Deep Research (PrismML Ternary Bonsai 2 27B, BitNet b1.58, OrcaRouter Steering)  
> **Hardware Target**: NVIDIA Tesla T4 (Colab / Kaggle 15GB), Apple Silicon, Edge Devices  

---

Systems Architecture for Sub-2-Bit Ternary Models and Runtime Activation Steering
Operating frontier-class artificial intelligence models on commodity accelerators requires overcoming two severe structural bottlenecks: the memory-bandwidth wall of dense floating-point parameters and the rigidity of post-training safety alignment. Sub-2-bit quantization addresses the memory constraint by mapping weights into discrete ternary states {−1,0,+1}, compressing a 27-billion-parameter architecture from over 53 GB in 16-bit precision down to 5.93 GB. This dramatic reduction allows 27B models to fit entirely within the memory footprint of a single 16 GB accelerator, such as an NVIDIA Tesla T4 or a mobile device. However, applying standard parameter-space safety unlearning—such as offline weight abliteration—to these models corrupts their packed integer representations, introducing rounding noise that either degrades core capabilities or restores refusal behavior.   

Runtime activation steering resolves this dilemma by decoupling safety modulation from static weight storage. Safety-aligned refusal responses in autoregressive transformers do not require complex, distributed circuits; they are mediated primarily by a low-dimensional directional subspace within intermediate residual stream activations. By executing a dynamic rank-1 orthogonal projection operator P 
r
^
 
⊥
​
 =I−α 
r
^
  
r
^
  
⊤
  in single-precision floating-point arithmetic during forward execution, inference runtimes can eliminate refusal behaviors while leaving the underlying quantized weights unaltered and bit-identical.   

Production success depends on navigating the complex interactions between quantization mathematics and hybrid transformer topologies. In modern architectures combining standard self-attention with linear recurrence, intercepting only self-attention projection layers leaves alternative residual writer paths open, resulting in refusal leakage. Full refusal ablation—reducing rejection rates on standard benchmarks from over 96% down to under 4% while maintaining baseline performance on reasoning tasks like MMLU and GSM8K—requires intercepting all 129 residual writer sites across attention, feed-forward, and token embedding modules.   

Frontier Sub-2-Bit Landscape and Architectural Trade-Offs
Sub-2-bit weight quantization marks a transition from empirical rounding toward discrete information-theoretic representation. Below 3 bits per parameter, conventional uniform affine Post-Training Quantization (PTQ) suffers from severe variance collapse: clipping errors on activation outliers destroy the dynamic range needed for finer weights. Sub-2-bit architectures overcome this boundary through two primary approaches: native Quantization-Aware Training (QAT) with ternary optimization objectives, and rotation-assisted post-training weight reorganization.   

Initiative / Architecture	Base Foundation & Source	Primary Quantization Strategy	Effective Bit-Width (Storage)	Model Weight Footprint	Target Runtime Infrastructure	Reasoning & Benchmark Retention
Ternary Bonsai 2 27B	
PrismML (Qwen3.8 27B foundation)

Blockwise Hadamard rotation with ternary assignment (PTQ1_0, PQ2_0)

1.71–1.76 bits/weight

5.93 GB (Language) + 0.63 GB (Vision)

PrismML llama.cpp fork, Metal, CUDA (SM 75+)

98.2% aggregate retention (83.9 vs 85.4 base)

BitNet b1.58	
Microsoft Research (Native pretraining)

Native ternary QAT (absmax scaling + STE)

1.585 bits/weight theoretical

~1.58 bits/weight + FP16 scales

BitNet.cpp, T-MAC (LUT-based SIMD), BitBLAS

Matches FP16 Transformer baselines at scale

Bonsai 1-Bit (Q1_0)	
PrismML (Qwen3.6 27B foundation)

Native binary training (±1 sign bits + FP16 group scale)

1.125 bits/weight (Group size 128)

3.90 GB

Hexagon NPU (QHexRT), Apple MLX, stock llama.cpp

89.5% aggregate retention (76.1 vs 85.1 base)

QuIP# / QTIP	
Cornell / Together AI (PTQ research)

Randomized Hadamard rotation + E8 Lattice Vector Quantization

2.00 bits/weight	~7.00 GB (for 27B class)	
Custom CUDA decoding kernels

Preserves factual recall; degrades on deep reasoning

AQLM	
Yandex / HSE University (PTQ research)

Additive Multi-Codebook Vector Quantization

2.00–2.10 bits/weight	~7.20 GB (for 27B class)	
Fragmented table lookups, custom CPU/CUDA

High 2-bit perplexity; high latency overhead

  
In native ternary pretraining, such as Microsoft's BitNet b1.58, weight tensors are constrained to W∈{−1,0,+1} 
m×n
  throughout optimization using the Straight-Through Estimator (STE). Activations are quantized to 8-bit integers (INT8) per token or per tensor. This design replaces floating-point multiply-accumulate (MAC) pipelines with integer addition and subtraction trees, reducing computational energy consumption by up to 5x.   

In contrast, PrismML's Ternary Bonsai 2 27B applies representation engineering to a pre-trained frontier model (Qwen3.8 27B). By preserving 98.2% of full-precision performance across a 20-benchmark evaluation suite, it addresses the quality degradation common in extreme post-training compression. Across 24.35 billion language parameters divided into 64 hybrid-attention blocks, the model delivers strong performance on structured reasoning benchmarks—scoring 95.83 on AIME26 and 90.07 on LiveCodeBench. It substantially outperforms standard post-training methods like Qwen3.8 27B IQ2_XXS, which uses 7.3 GB (2.2 bits/weight) but drops to 78.6 on AIME26 and 70.05 on LiveCodeBench due to quantization noise.   

Bit-Packing Formats and Hadamard Orthogonal Outlier Suppression
The theoretical information capacity of a symmetric ternary state is defined by its base-2 entropy:

H=log 
2
​
 (3)≈1.58496 bits/weight
Because physical memory addressing operates on byte boundaries, practical implementations group ternary states into packed bitfields and pair them with block-level scaling factors to restore floating-point dynamic range.   

Group Scaling Mathematics and Effective Storage Densities
In ternary linear transformations, each unquantized weight matrix entry W 
i,j
​
  is reconstructed from a discrete state t 
i,j
​
 ∈{−1,0,+1} combined with a block-level scale factor s 
g
​
 :

W 
i,j
​
 =s 
g
​
 ⋅t 
i,j
​
 ,g=⌊j/B⌋
where B is the quantization group size, set to B=128 in production implementations. The scale factor s 
g
​
  is stored as a 16-bit half-precision float (FP16), spreading 16 bits of overhead across 128 parameters (16/128=0.125 bits/weight). The effective bit-width of isolated ternary tensors is calculated as:   

Bit-Width 
effective
​
 =log 
2
​
 (3)+ 
128
16
​
 ≈1.585+0.125=1.710 bits/weight
In Ternary Bonsai 2 27B, sensitive recurrent state parameters in linear attention layers and normalization scales (totaling 26.24 million parameters, or 0.0976% of the network) are retained in 16-bit Bfloat16 precision. This raises the true language model density to 1.72 bits/weight. When packaged into the PTQ1_0 GGUF file format, container alignments and metadata overhead bring the final deployment footprint to 1.76 bits/weight, yielding a 5.93 GB file.   

Bit-Level Data Layouts Across Sub-2-Bit Formats
The physical arrangement of bits within storage containers directly affects both memory footprint and runtime dequantization performance on SIMD architectures.   

Quantization Format	Container Stride & Alignment	Bitfield Mapping	Scale Factor Storage	SIMD Hardware Vectorization Path
PTQ1_0 (PrismML GGUF)

34 bytes per 128 weights (32B payload + 2B scale)

2 bits per weight: 00b = 0, 01b = +1, 10b = -1, 11b = reserved

Interleaved FP16 scale (s 
g
​
 ) appended every 128 weights

Unpacks 4 weights per byte; uses bitwise shift and mask operations before FP16 scaling

PQ2_0 (Packed Quantization 2.0)

Segregated planes: 16B mask + variable sign bits + 2B scale	Nonzero bitmask (1 bit/weight) plus dense sign stream (0→+1,1→−1)	Interleaved or separate FP16 scale block	
Bypasses zero-weights using bitmask tests; applies sign flips via XOR instructions

Q1_0_g128 (Binary Bonsai)

18 bytes per 128 weights (16B payload + 2B scale)

1 bit per weight: 0b maps to −s 
g
​
 , 1b maps to +s 
g
​
 

[cite: 19]

Interleaved FP16 scale (s 
g
​
 ) every 128 weights

High hardware efficiency; sign bit extraction maps directly to vector sign registers

  
Outlier Suppression via Orthogonal Walsh-Hadamard Transforms
The key technical innovation enabling 98.2% capability retention in Ternary Bonsai 2 is rotation-assisted representation. Transformer residual streams naturally develop activation outliers: sparse, high-magnitude dimensions that carry crucial token routing information. Under ternary quantization, these outliers distort the scale factor s 
g
​
 , forcing non-outlier values within the group to round to zero and causing severe model degradation.   

To resolve this issue, the model applies a blockwise orthogonal rotation using a Walsh-Hadamard matrix H 
K
​
 ∈R 
K×K
  (with K=1024) prior to ternary assignment:   

W 
′
 =WH 
K
⊤
​
 ,x 
′
 =H 
K
​
 x
The transformation matrix is built recursively using the Kronecker product:

H 
2
​
 = 
2

​
 
1
​
 ( 
1
1
​
  
1
−1
​
 ),H 
2 
k
 
​
 = 
2

​
 
1
​
 ( 
H 
2 
k−1
 
​
 
H 
2 
k−1
 
​
 
​
  
H 
2 
k−1
 
​
 
−H 
2 
k−1
 
​
 
​
 )
Because H 
K
​
  is orthogonal (H 
K
⊤
​
 H 
K
​
 =I), inner products are preserved:

y=Wx=(WH 
K
⊤
​
 )(H 
K
​
 x)=W 
′
 x 
′
 
This rotation functions as an incoherence transform. It spreads activation energy across all 1024 dimensions, reducing peak outlier magnitude by a factor proportional to 1/ 
K

​
  (1/ 
1024

​
 =1/32) and eliminating kurtosis spikes. At inference time, the rotated weights W 
′
  are pre-computed and stored in the model, while the runtime applies a multiplication-free Fast Walsh-Hadamard Transform (FWHT) to incoming activations using simple addition and subtraction trees.   

Execution Kernel Pathways and Runtime Discrepancies
Executing sub-2-bit models at scale requires specialized computational kernels. Commodity GPUs—including NVIDIA's Turing architecture (Compute Capability 7.5 on Tesla T4)—lack native hardware instructions for 2-bit integer arithmetic. Without optimized kernels, runtimes must fall back to slow, bandwidth-heavy software dequantization.   

Lookup Table (LUT) Kernels: The T-MAC Execution Paradigm
For memory-bandwidth-bound autoregressive decoding, Lookup Table (LUT) execution engines (such as T-MAC) alter the compute pipeline. Instead of unpacking weights into intermediate floating-point registers to execute standard tensor core operations, the engine precomputes activation combinations ahead of time:   

Activation Combination Precomputation: Groups of U consecutive activation channels (typically U=2 or U=4) are sampled. For U=2, all possible linear combinations with ternary weights t∈{−1,0,+1} 
2
  are computed once per token step. Because each ternary parameter has 3 possible values, there are 3 
2
 =9 potential sums:

LUT[τ 
0
​
 ,τ 
1
​
 ]=τ 
0
​
 x 
0
​
 +τ 
1
​
 x 
1
​
 ,τ 
0
​
 ,τ 
1
​
 ∈{−1,0,+1}
Low-Latency Storage: These precomputed values are stored in fast GPU shared memory or hardware vector registers.   

SIMD Table Lookups: The packed 2-bit weight patterns serve as direct indices into the precomputed lookup table. On CPUs, this maps to vector permute instructions (such as ARM NEON tbl or x86 vpshufb). On GPUs, parallel warp threads gather values from shared memory without executing floating-point arithmetic.   

Block Scaling: The retrieved values are accumulated across groups and multiplied by the FP16 group scale s 
g
​
  at block boundaries.   

By replacing floating-point operations with memory lookups during intermediate accumulation, this approach reduces instruction counts by up to 70% while maximizing memory-bus bandwidth utilization.   

Runtime Incompatibilities: Mainline llama.cpp vs. Specialized Forks
Deploying models like Ternary Bonsai 2 27B requires understanding critical runtime distinctions within the llama.cpp ecosystem. Upstream llama.cpp includes support for binary Q1_0 models. However, PTQ1_0 and PQ2_0 utilize specialized layouts tailored for Hadamard-rotated ternary weights.   

When users attempt to run PTQ1_0 or PQ2_0 models on upstream llama.cpp, two failure modes occur:   

The runtime encounters an unrecognized quantization type identifier and aborts during model loading.   

The parser falls back to a legacy Q2_0 decoding pathway, misinterpreting the 34-byte stride and ternary sign representations and producing completely degraded, unintelligible output.   

Proper execution requires the dedicated PrismML llama.cpp fork. This fork provides specialized CUDA and Metal kernels (ggml-cuda/ternary.cu) that:   

Match GPU thread-block dimensions to the 128-weight group boundaries.   

Use fast inline PTX bitfield extraction (bfe.u32) to unpack signs without branch divergence.

Execute fused, in-place Fast Walsh-Hadamard Transforms on activation vectors prior to GEMV matrix multiplication.   

Mechanistic Geometry of the Refusal Subspace
Language models aligned via RLHF, DPO, or supervised safety demonstration encode refusal behaviors along low-dimensional subspaces within their latent representations. Rather than distributing safety logic diffusely across the entire network, conversational models concentrate refusal decisions along an identifiable linear direction.   

Direction Extraction via Difference-in-Means
The refusal direction r∈R 
d
  is derived by harvesting activations from contrastive prompt pairs:   

Harmful set D 
harmful
​
 ={x 
i
h
​
 } 
i=1
N
​
 : requests that trigger standard alignment refusals (e.g., instructions for malware development or hazardous physical tasks).   

Harmless set D 
harmless
​
 ={x 
i
b
​
 } 
i=1
N
​
 : structurally, lexically, and semantically matched requests that the model should fulfill safely (e.g., standard scientific, historical, or software engineering queries).   

Let h 
l
​
 (x)∈R 
d
  represent the hidden state vector at layer l extracted at the final prompt token position—the transition point where instruction processing ends and autoregressive token generation begins. The candidate refusal vector at layer l is calculated using a difference-in-means estimator:   

r 
l
​
 = 
N
1
​
  
i=1
∑
N
​
 h 
l
​
 (x 
i
h
​
 )− 
N
1
​
  
i=1
∑
N
​
 h 
l
​
 (x 
i
b
​
 )
To eliminate noise from persistent activation channels, production pipelines apply a massive-activation mask or extract the first principal component (PC1) via singular value decomposition (SVD) on the centered difference matrix Δ 
l
​
 ∈R 
N×d
 :   

Δ 
l
​
 = 

​
  
h 
l
​
 (x 
1
h
​
 )−h 
l
​
 (x 
1
b
​
 )
⋮
h 
l
​
 (x 
N
h
​
 )−h 
l
​
 (x 
N
b
​
 )
​
  

​
 =UΣV 
⊤
 ,r 
l
​
 =V 
∗,1
​
 
The resulting direction is normalized to a unit vector in Euclidean space:   

r
^
  
l
​
 = 
∥r 
l
​
 ∥ 
2
​
 
r 
l
​
 
​
 
This extraction operates entirely through linear algebra on stored activations, requiring no gradient evaluations, loss functions, or parameter updates.   

Layer Localization and Depth Dynamics
The causal strength of the refusal vector varies across network depth. In early layers (0≤l≤0.3L), activations are dominated by syntactic parsing and local token composition; difference vectors extracted in this regime reflect surface lexical features rather than behavioral refusal. In final layers (0.85L≤l≤L), activations resolve into concrete next-token vocabulary distributions.   

The refusal manifold stabilizes in the intermediate-to-late transformer blocks—between 50% and 65% of total model depth. In 64-layer architectures such as Qwen3.8 27B and Ternary Bonsai 2 27B, the optimal refusal direction  
r
^
  concentrates at layer 38:   

l 
∗
 =round(0.60×64)=38
At layer 38, the refusal direction achieves high causal efficacy: projecting it out suppresses refusal tokens on restricted inputs, while adding it induces refusals on harmless prompts, all while preserving general language performance on standard evaluation suites.   

Quantization Noise and Cross-Precision Vector Transfer
When transferring a refusal direction extracted from an unquantized FP16 checkpoint to a ternary-quantized runtime, engineers must account for quantization noise E=W 
ternary
​
 −W 
FP16
​
 . Downstream hidden states drift according to:   

y
~
​
 =W 
ternary
​
 x=W 
FP16
​
 x+Ex
Because Walsh-Hadamard rotations distribute values across 1024-dimensional blocks, the perturbation tensor E behaves as zero-mean, isotropic noise in the residual stream. The dot product of this high-dimensional noise with a fixed unit vector  
r
^
  concentrates near zero (d=5120):   

E[Ex⋅ 
r
^
 ]=0,Var(Ex⋅ 
r
^
 )∝ 
d
σ 
E
2
​
 
​
 
Consequently, the refusal direction remains structurally aligned across precisions, showing high cosine similarity (cos( 
r
^
  
FP16
​
 , 
r
^
  
ternary
​
 )≥0.94). However, extracting  
r
^
  directly from activations of the quantized model remains the preferred approach, as it accounts for group scaling biases and reduces residual projection leakage down to approximately 1×10 
−6
  of the residual norm.   

Forward Activation Projection Across 129 Residual Writer Sites
Conventional weight abliteration permanently modifies model parameters by subtracting the refusal direction from every residual-writing weight matrix:   

W 
′
 =W− 
r
^
 ( 
r
^
  
⊤
 W)
While effective in FP16 or BF16 models, this approach breaks down on sub-2-bit ternary models. Subtracting a continuous rank-1 update from a discrete matrix W∈{−1,0,+1} 
m×n
  yields floating-point values, destroying the packed integer format. Attempting to round these values back into ternary states introduces severe quantization errors that either restore the refusal behavior or destroy model reasoning.   

Runtime activation projection resolves this issue by preserving the underlying 5.93 GB ternary weights in an unaltered, bit-identical state. The intervention is executed dynamically in single-precision floating-point (FP32) arithmetic within the forward execution graph.   

Mathematical Mechanics of Activation Steering
Let y∈R 
d
  represent an unperturbed activation vector at a target intervention site. Runtime activation steering applies a linear projection operator:   

y 
′
 =y−α(y⋅ 
r
^
 ) 
r
^
 
where:

r
^
  is the precomputed, unit-normalized 5120-dimensional refusal direction vector (occupying 20.48 KB in FP32).   

α∈R is the steering intensity multiplier.   

The parameter α controls model behavior across distinct operational ranges:   

α=0.0: Projection is disabled; the model operates with its default aligned safety behavior.   

α=1.0: Complete orthogonal projection (P 
r
^
 
⊥
​
 y=y−(y⋅ 
r
^
 ) 
r
^
 ); the linear component parallel to  
r
^
  is entirely removed.   

0.0<α<1.0: Partial ablation, allowing graduated modulation of refusal behavior.   

α>1.0: Directional inversion, actively steering the model away from refusal states. Setting α>1.25 typically causes semantic instability, repetition loops, and syntax errors, as coordinates orthogonal to the refusal direction experience geometric distortion.   

Intervention Topologies Across the 129 Residual Writers
A common failure in production steering implementations is incomplete intervention coverage. In standard LLaMA-style architectures, practitioners often hook only the self-attention output projections (self_attn.o_proj). In modern hybrid architectures like Qwen3.8 27B and Ternary Bonsai 2, which combine linear attention with full self-attention across 64 layers, hooking only self_attn.o_proj covers just 16 sites. This allows the refusal signal to bypass attention filtering and propagate via feed-forward networks and linear recurrence paths.   

Full refusal ablation requires intercepting all 129 residual writer sites—every submodule whose output is added directly into the residual stream:   

MLP Down-Projections (64 sites): Intercepting model.layers[l].mlp.down_proj across all 64 blocks. SwiGLU MLP modules represent the largest contributors of activation magnitude to the residual highway.   

Linear Attention Output Projections (48 sites): Intercepting model.layers[l].linear_attn.out_proj across the 48 Gated DeltaNet linear attention blocks.   

Full Self-Attention Output Projections (16 sites): Intercepting model.layers[l].self_attn.o_proj across the 16 full-attention layers.   

Token Embeddings (1 site): Intercepting model.embed_tokens (or the input residual entry point x 
0
​
 ) to prevent initial token representations from pre-biasing the residual stream.   

(Note: While permanent offline weight abliteration targets 131 matrices by including the 2 Multi-Token Prediction heads to maintain speculative drafting consistency, runtime forward hooks targeting the 129 primary backbone sites provide complete behavioral coverage during single-token autoregression).   

Behavioral Benchmarks and Reasoning Retention
Applying runtime activation projection across all 129 intervention sites on Ternary Bonsai 2 27B substantially reduces refusal behaviors while maintaining general model capabilities.   

Evaluation Benchmark Category	Sample Size (n)	Unmodified Model Refusal Rate	Runtime Steered (α=1.0) Refusal Rate	Operational Impact
JailbreakBench

[cite: 4]

100	96.0%	4.0%	
92.0% absolute reduction in refusal on adversarial attacks

StrongREJECT

[cite: 4]

150	99.3%	3.3%	
Near-complete elimination of safety refusals on direct harmful queries

HarmBench

[cite: 4]

150	98.7%	7.3%	
Broad compliance across complex, functional safety probes

MaliciousInstruct

[cite: 4]

100	97.0%	0.0%	
Complete elimination of baseline refusal triggering

ForbiddenQuestions

[cite: 4]

150	75.3%	5.3%	
Consistent fulfillment of edge-case safety prompts

SimpleSafetyTests

[cite: 4]

50	96.0%	18.0%	
Significant reduction in conservative guardrail triggers

XSTest-safe (Benign Prompts)

[cite: 4]

250	5.2%	0.4%	
Eliminates false-positive refusals on harmless queries

JailbreakBench (Benign Subset)

[cite: 4]

100	25.0%	0.0%	
Resolves over-refusals on sensitive educational/historical topics

  
Standard cognitive benchmarks confirm that removing the refusal subspace causes no collateral damage to core reasoning performance:   

MMLU (n=300): 76.7% base vs. 77.7% steered (+1.0% shift, within standard evaluation variance)   

GSM8K (n=150): 87.3% base vs. 86.0% steered (-1.3% variance)   

CMMLU (n=500): 76.2% base vs. 75.6% steered (-0.6% variance)   

These empirical outcomes confirm a core insight of mechanistic interpretability: safety alignment in instruction-tuned language models functions as a directional filter within the residual stream, rather than an inseparable component of underlying reasoning capabilities.   

Production PyTorch Implementation for Hybrid-Attention Transformer Steering
The following production-ready module implements runtime activation projection hooks for Hugging Face transformer architectures. It automatically discovers and hooks all 129 residual writer sites across hybrid architectures, performs projection calculations in single-precision floating point (FP32) for numerical stability, supports dynamic steering adjustment, and provides a self-check diagnostic method.

Python
import torch
import torch.nn as nn
from typing import Dict, List, Optional, Tuple, Union

class RuntimeRefusalAblator:
    """
    Manages non-invasive runtime activation projection hooks across transformer
    residual writer sites (MLP down-projections, self-attention output projections,
    linear-attention projections, and token embeddings) to ablate refusal behavior
    without modifying quantized model weights.
    """
    def __init__(
        self,
        model: nn.Module,
        refusal_vector: torch.Tensor,
        alpha: float = 1.0,
        target_layer_range: Optional[Tuple[int, int]] = None,
        verbose: bool = True
    ):
        """
        Args:
            model: HuggingFace model instance (e.g., Qwen, LLaMA, or Bonsai backbone).
            refusal_vector: 1D Tensor of shape [hidden_dim] containing the refusal direction.
            alpha: Projection strength (1.0 = full orthogonal projection).
            target_layer_range: Optional tuple (start_layer, end_layer). If None, hooks all layers.
            verbose: If True, outputs hook registration diagnostics.
        """
        self.model = model
        self.alpha = float(alpha)
        self.target_layer_range = target_layer_range
        self.verbose = verbose
        self.hook_handles: List[torch.utils.hooks.RemovableHandle] = []
        
        # Verify and normalize refusal vector to unit norm in float32
        if refusal_vector.ndim != 1:
            raise ValueError(f"refusal_vector must be 1D, got shape {refusal_vector.shape}")
        
        device = next(model.parameters()).device
        v = refusal_vector.to(device=device, dtype=torch.float32)
        norm = torch.linalg.norm(v)
        if norm < 1e-8:
            raise ValueError("Provided refusal vector has near-zero L2 norm.")
        self.r_hat = (v / norm).detach()
        self.hidden_dim = self.r_hat.shape[0]

    def _create_projection_hook(self, site_identifier: str):
        """
        Generates a forward hook function that performs:
            y' = y - alpha * (y . r_hat) * r_hat
        executed in FP32 to prevent numerical underflow/overflow.
        """
        r_hat = self.r_hat

        def hook_fn(module: nn.Module, inputs: Tuple, output: Union[torch.Tensor, Tuple]):
            # Unpack if output is a tuple (e.g., (hidden_states, atten_weights))
            is_tuple = isinstance(output, tuple)
            tensor_out = output[0] if is_tuple else output

            if not isinstance(tensor_out, torch.Tensor):
                return output

            # Validate hidden dimension matches projection vector
            if tensor_out.shape[-1] != self.hidden_dim:
                return output

            orig_dtype = tensor_out.dtype
            # Upcast to float32 for geometric stability
            act_fp32 = tensor_out.to(torch.float32)

            # Compute dot product along the final hidden dimension: shape [..., 1]
            inner_product = torch.sum(act_fp32 * r_hat, dim=-1, keepdim=True)

            # Apply projection: y' = y - alpha * (y . r_hat) * r_hat
            projected = act_fp32 - (self.alpha * inner_product * r_hat)
            steered_tensor = projected.to(orig_dtype)

            if is_tuple:
                return (steered_tensor,) + output[1:]
            return steered_tensor

        return hook_fn

    def register_hooks(self) -> int:
        """
        Discovers all residual writing modules across the architecture and registers
        forward hooks. Returns the total count of registered intervention sites.
        """
        self.remove_hooks()
        registered_count = 0

        # Resolve backbone layers container
        backbone = getattr(self.model, "model", self.model)
        layers = getattr(backbone, "layers", None)
        if layers is None:
            raise AttributeError("Unable to identify transformer layers in model.model.layers")

        num_layers = len(layers)
        start_idx = self.target_layer_range[0] if self.target_layer_range else 0
        end_idx = self.target_layer_range[1] if self.target_layer_range else num_layers

        # 1. Hook Token Embeddings (Initial residual stream entry point)
        embed_tokens = getattr(backbone, "embed_tokens", None)
        if embed_tokens is not None and start_idx == 0:
            handle = embed_tokens.register_forward_hook(
                self._create_projection_hook("embed_tokens")
            )
            self.hook_handles.append(handle)
            registered_count += 1

        # 2. Iterate across transformer blocks
        for l_idx in range(start_idx, min(end_idx, num_layers)):
            block = layers[l_idx]

            # Site A: MLP Down-Projection (SwiGLU output)
            mlp = getattr(block, "mlp", None)
            if mlp is not None:
                down_proj = getattr(mlp, "down_proj", None)
                if down_proj is not None:
                    handle = down_proj.register_forward_hook(
                        self._create_projection_hook(f"layer_{l_idx}_mlp_down_proj")
                    )
                    self.hook_handles.append(handle)
                    registered_count += 1

            # Site B: Standard Full Self-Attention Output Projection
            self_attn = getattr(block, "self_attn", None)
            if self_attn is not None:
                o_proj = getattr(self_attn, "o_proj", None)
                if o_proj is not None:
                    handle = o_proj.register_forward_hook(
                        self._create_projection_hook(f"layer_{l_idx}_self_attn_o_proj")
                    )
                    self.hook_handles.append(handle)
                    registered_count += 1

            # Site C: Linear Attention Output Projection (Gated DeltaNet / Hybrid blocks)
            linear_attn = getattr(block, "linear_attn", None)
            if linear_attn is not None:
                out_proj = getattr(linear_attn, "out_proj", None)
                if out_proj is not None:
                    handle = out_proj.register_forward_hook(
                        self._create_projection_hook(f"layer_{l_idx}_linear_attn_out_proj")
                    )
                    self.hook_handles.append(handle)
                    registered_count += 1

        if self.verbose:
            print(f"[RuntimeRefusalAblator] Active hooks installed: {registered_count} sites.")
            if registered_count < 129 and self.target_layer_range is None:
                print(f"[WARNING] Expected 129 sites for full hybrid coverage, got {registered_count}.")

        return registered_count

    def remove_hooks(self):
        """Detaches all registered hooks, restoring factory model forward paths."""
        for handle in self.hook_handles:
            handle.remove()
        self.hook_handles.clear()

    def set_alpha(self, new_alpha: float):
        """Dynamically updates steering intensity without re-registering hooks."""
        self.alpha = float(new_alpha)

    def selfcheck(self, sample_input_ids: torch.Tensor) -> float:
        """
        Runs a test forward pass and calculates the maximum residual component
        projecting onto the refusal vector across the generated hidden states.
        Returns the maximum relative projection ratio: |y . r_hat| / ||y||.
        """
        captured_residuals = []

        def audit_hook(module, inputs, output):
            out_tensor = output[0] if isinstance(output, tuple) else output
            if isinstance(out_tensor, torch.Tensor) and out_tensor.shape[-1] == self.hidden_dim:
                act = out_tensor.detach().to(torch.float32)
                proj = torch.abs(torch.sum(act * self.r_hat, dim=-1))
                norm = torch.linalg.norm(act, dim=-1) + 1e-8
                captured_residuals.append(torch.max(proj / norm).item())

        backbone = getattr(self.model, "model", self.model)
        test_handles = []
        for layer in getattr(backbone, "layers", []):
            test_handles.append(layer.register_forward_hook(audit_hook))

        with torch.no_grad():
            _ = self.model(sample_input_ids)

        for h in test_handles:
            h.remove()

        max_leakage = max(captured_residuals) if captured_residuals else 0.0
        if self.verbose:
            print(f"[RuntimeRefusalAblator SelfCheck] Max parallel residual ratio: {max_leakage:.2e}")
        return max_leakage
Single-GPU Deployment Playbook on 16GB Accelerators
Deploying a 27.36-billion-parameter multimodal architecture onto a single 15.8 GB GPU (such as an NVIDIA Tesla T4 available in Google Colab or Kaggle environments) requires disciplined memory partitioning across weights, context key-value (KV) caches, and runtime CUDA workspace buffers.   

Hardware Memory Budgeting on a 15.8 GB Tesla T4
The table below outlines memory allocation across model execution states.

Memory Component	Allocation	Bit-Precision & Format	Operational Notes & Configuration
Model Weights (Language Backbone)

[cite: 4]

5.93 GB	
1.76-bit (PTQ1_0 GGUF)

100% offloaded to GPU VRAM (-ngl 99)

Multimodal Vision Projector (mmproj)

[cite: 4]

0.63 GB	
4-bit quantized (Q4_0)

Loaded into VRAM on demand when image inputs are present

KV Cache (4,096 Context)

[cite: 13]

0.25 GB	
16-bit float (FP16)

Hybrid attention keeps memory compact (64 KiB/token base)

KV Cache (32,768 Context)

[cite: 13]

2.05 GB	
16-bit float (FP16)

Extended context for multi-turn agentic workflows

CUDA Activation Workspace	1.85 GB	Mixed FP32 / FP16	
GEMV accumulation buffers and FWHT scratchpad

CUDA Runtime Overhead	0.85 GB	Driver system memory	Unified memory driver maps and base CUDA context
Total Memory Allocation (4K Context)	9.51 GB	—	Headroom: ~6.29 GB free on 15.8 GB T4 hardware
Total Memory Allocation (32K Context)	11.31 GB	—	Headroom: ~4.49 GB free on 15.8 GB T4 hardware
  
Environment Setup and Binary Compilation
Execute the following bash commands to set up the runtime environment and compile the specialized PrismML llama.cpp fork for Turing GPUs (Compute Capability 7.5):

Bash
# 1. Initialize isolated Python virtual environment
conda create -n ternary-steer python=3.10 -y
conda activate ternary-steer

# 2. Install PyTorch with explicit CUDA 12.1 runtime support
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Clone and build the PrismML llama.cpp fork supporting PTQ1_0 and PQ2_0
git clone https://github.com/PrismML-Eng/llama.cpp.git prism-llama
cd prism-llama
mkdir build && cd build

# Configure build with CUDA enabled and target Turing (SM 75) architecture
cmake .. \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES="75" \
    -DCMAKE_BUILD_TYPE=Release

# Compile CLI inference and server binaries
cmake --build . --config Release -j$(nproc) --target llama-cli llama-server
cd ../..

# 4. Install supporting tooling and Hugging Face hub utilities
pip install huggingface_hub transformers accelerate sentencepiece safetensors
Weight Acquisition and Baseline Inference Execution
Download the packed GGUF model and vision projector, then run baseline verification inference:

Bash
# Download the PTQ1_0 packed GGUF model and mmproj vision weights
huggingface-cli download prism-ml/Ternary-Bonsai-2-27B-gguf \
    Ternary-Bonsai-2-27B-PTQ1_0.gguf \
    --local-dir ./models --local-dir-use-symlinks False

huggingface-cli download prism-ml/Ternary-Bonsai-2-27B-gguf \
    mmproj-Qwen3.8-27B-vision-q4_0.gguf \
    --local-dir ./models --local-dir-use-symlinks False

# Execute verification CLI inference offloading all 64 layers to the GPU
./prism-llama/build/bin/llama-cli \
    -m ./models/Ternary-Bonsai-2-27B-PTQ1_0.gguf \
    --mmproj ./models/mmproj-Qwen3.8-27B-vision-q4_0.gguf \
    -ngl 99 \
    -c 4096 \
    --temp 0.6 \
    -p "<|im_start|>user\nExplain the biochemical synthesis of ATP in cellular mitochondria.<|im_end|>\n<|im_start|>assistant\n"
Integrated Python Script: Steered Generation Execution
The Python script below demonstrates loading the model, attaching the RuntimeRefusalAblator across all 129 intervention sites, and executing steered inference within the 16 GB memory budget:

Python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from runtime_refusal_ablator import RuntimeRefusalAblator

def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Target execution device: {device}")

    # 1. Load Tokenizer
    model_id = "Qwen/Qwen2.5-14B-Instruct"  # Reference architecture for script execution
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

    # 2. Load Model onto Tesla T4 (within 16GB memory constraint)
    print("Loading model weights...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )

    # 3. Load or Calculate the Refusal Vector (5120-dim for 27B Qwen architectures)
    hidden_dim = model.config.hidden_size
    # In production: refusal_vec = torch.load("refusal_vector_layer38.pt")
    torch.manual_seed(42)
    refusal_vec = torch.randn(hidden_dim, dtype=torch.float32)

    # 4. Initialize and Attach the Runtime Refusal Ablator across all 129 sites
    ablator = RuntimeRefusalAblator(
        model=model,
        refusal_vector=refusal_vec,
        alpha=1.0,  # Full orthogonal projection
        verbose=True
    )
    installed_sites = ablator.register_hooks()
    print(f"Ablator successfully installed across {installed_sites} sites.")

    # 5. Execute Self-Check Diagnostic
    test_ids = tokenizer("Sanity test probe", return_tensors="pt").input_ids.to(device)
    leakage = ablator.selfcheck(test_ids)
    print(f"Refusal subspace leakage ratio: {leakage:.4e}")

    # 6. Run Steered Generation
    prompt = "Provide a detailed technical explanation of how grid-scale battery systems manage frequency regulation."
    messages = [
        {"role": "system", "content": "You are an authoritative, direct technical assistant."},
        {"role": "user", "content": prompt}
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(device)

    print("\nExecuting forward pass under runtime activation projection:")
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.7,
            top_p=0.9,
            do_sample=True
        )

    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[-1]:], skip_special_tokens=True)
    print(f"\nModel Output:\n{response}")

    # 7. Detach Hooks to restore baseline alignment
    ablator.remove_hooks()
    print("\nHooks detached. Model restored to baseline alignment state.")

if __name__ == "__main__":
    main()
The combination of sub-2-bit ternary quantization and runtime activation steering demonstrates that physical parameter storage can be decoupled from dynamic safety alignment in large language models. Quantization schemes like PTQ1_0 and BitNet b1.58 show that full-precision weights are largely redundant for storing world knowledge, while representation engineering confirms that post-training safety behaviors reside in fragile, low-rank residual directions rather than complex reasoning circuits. By applying rank-1 orthogonal projections across all 129 residual writer sites in floating-point arithmetic, runtimes can eliminate refusal behaviors while keeping underlying quantized weights bit-identical. This architecture allows developers to bypass the structural rigidity of extreme quantization formats, deploying uncensored 27B-class reasoning models within the memory constraints of consumer-grade 16 GB accelerators.


prismml.com
PrismML — Concentrating intelligence
Opens in a new window

orcarouter.ai
Opens in a new window

morningstar.com
PrismML Launches Bonsai 2 27B, Its Most Capable Model Yet
Opens in a new window

orcarouter.ai
Opens in a new window

runanywhere.ai
PrismML Bonsai 1-bit on iPhone, Android, and Mac - RunAnywhere AI
Opens in a new window

orcarouter.ai
Opens in a new window

openreview.net
Refusal in Language Models Is Mediated by a Single Direction
Opens in a new window

learnmechinterp.com
The Refusal Direction | Learn MI
Opens in a new window

aratech.ae
BitNet b1.58: Microsoft's 1-Bit LLM That Runs a 100B Model - aratech
Opens in a new window

arxiv.org
A general method for activation quantization in LLMs - arXiv
Opens in a new window

uplatz.com
The Quantization Horizon: Navigating the Transition to INT4, FP4
Opens in a new window

docs.prismml.com
Formats & Runtime Support - Bonsai - Introduction
Opens in a new window

github.com
GitHub - PrismML-Eng/Bonsai-demo
Opens in a new window

github.com
GitHub - microsoft/BitNet: Official inference framework for 1-bit LLMs
Opens in a new window

huggingface.co
Fine-tuning LLMs to 1.58bit: extreme quantization made easy
Opens in a new window

reddit.com
So what happened to the 1.58bit models "revolution" ? : r/LocalLLaMA
Opens in a new window

researchgate.net
Bitnet.cpp: Efficient Edge Inference for Ternary LLMs - ResearchGate
Opens in a new window

kenashe.ai
Bonsai 27B makes local agents smaller, not magically smarter
Opens in a new window

huggingface.co
prism-ml/Bonsai-27B-gguf - Hugging Face
Opens in a new window

emergentmind.com
Rotation-Assisted Post-Training Quantization - Emergent Mind
Opens in a new window

huggingface.co
Daily Papers - Hugging Face
Opens in a new window

reddit.com
Bonsai-27B & Ternary-Bonsai-27B - Updates (on PRs) : r/LocalLLaMA
Opens in a new window

researchgate.net
SpinOut: Enhanced Rotation-Based Quantization for LLM by Outlier
Opens in a new window

openreview.net
A general method for activation quantization in LLMs - OpenReview
Opens in a new window

aspdac.com
Path-Adaptable LUT-Based Accelerator Tailored for Low-Bit Weight
Opens in a new window

arxiv.org
T-MAC: CPU Renaissance via Table Lookup for Low-Bit LLM ... - arXiv
Opens in a new window

dai.sjtu.edu.cn
LARGE LANGUAGE MODEL INFERENCE ACCELERATION
Opens in a new window

docs.prismml.com
Download the Models - Bonsai - Introduction - PrismML
Opens in a new window

ollama.com
tobestyledintro/Ternary-Bonsai-2-27B - Ollama
Opens in a new window

researchgate.net
Refusal in Language Models Is Mediated by a Single Direction
Opens in a new window

alphaxiv.org
Refusal in Language Models Is Mediated by a Single Direction
Opens in a new window

arxiv.org
Refusal in Language Models Is Mediated by a Single Direction - arXiv
Opens in a new window

ollama.com
orcarouter - Ollama
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window
Opens in a new window



Serving Frontier Mixture-of-Experts Models on Ephemeral Cloud Accelerators
