# Kronos Synapse Dialogue Core

![Python](https://img.shields.io/badge/python-3.12+-blue)
![PyTorch](https://img.shields.io/badge/PyTorch-CPU-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Params](https://img.shields.io/badge/params-%7E15.3M-informational)

**Languages:** **English** · [Español](docs/i18n/es/README.md) · [Deutsch](docs/i18n/de/README.md) · [中文](docs/i18n/zh/README.md) · [Русский](docs/i18n/ru/README.md)

A decoder-only GPT-style language model (~15.3M parameters) written from scratch on
pure `torch.nn` primitives and trained entirely on CPU. It ships with a BPE tokenizer,
a memmap-backed training pipeline, and a streaming CLI chat built around a KV-cache
generator. The whole stack — model, data, training, inference — is implemented by hand,
without `transformers` or `nanoGPT` scaffolding.

> **What this is (and isn't).** This model does **prompt continuation**, not
> instruction-following. It is trained on literary prose (Project Gutenberg), not on
> annotated dialogue pairs. You type text; it continues it. It is not a role-playing
> assistant. See [Chat paradigm & limitations](#chat-paradigm--limitations).

---

## Table of contents

- [Quickstart](#quickstart)
- [Highlights](#highlights)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Preparing data](#preparing-data)
- [Training](#training)
- [Evaluation](#evaluation)
- [Chat & inference](#chat--inference)
- [Chat paradigm & limitations](#chat-paradigm--limitations)
- [Testing](#testing)
- [Development](#development)
- [Performance notes](#performance-notes)
- [Roadmap](#roadmap)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

## Quickstart

If you just want to see it run, here's the whole loop end to end:

```bash
# 1. install
pip install -e ".[dev]"

# 2. drop some .txt books into data/raw/gutenberg/, then:
kronos_synapse tokenize --corpus-dir data/raw/gutenberg

# 3. train (Ctrl+C is safe; resume from a checkpoint later)
kronos_synapse train

# 4. talk to it
kronos_synapse chat checkpoints/best.pt
```

There's also a `Makefile` if you prefer `make tokenize`, `make train`, `make chat`.
Everything runs on CPU — no GPU, no cloud account, no API keys.

## Highlights

- **Hand-rolled transformer.** `CausalSelfAttention`, `MLP`, `TransformerBlock`, and
  `MiniGPT` are built directly on `nn.Linear`, `nn.LayerNorm`, `nn.Embedding`, and
  `nn.Dropout`. Attention goes through `F.scaled_dot_product_attention`, which selects
  the optimized fused kernel on CPU.
- **CPU-first.** Everything runs without CUDA. The training loop threads the needle with
  gradient accumulation, `bfloat16` autocast, configurable thread counts, and an optional
  `torch.compile` fallback.
- **KV-cache generation.** Inference does one prefill pass over the prompt, then decodes
  one token at a time against the cached keys/values — the difference between usable and
  unusable chat on a laptop CPU.
- **Sampler you can steer.** Temperature, top-k, top-p (nucleus), and repetition penalty
  are all exposed as CLI flags.
- **Typed configuration.** Three `pydantic-settings` configs (`ModelConfig`,
  `TrainConfig`, `DataConfig`) replace magic dictionaries with validated, frozen settings.

## Architecture

A standard pre-LN GPT decoder. The table below is the default `ModelConfig`.

| Component | Value | Notes |
|---|---|---|
| `vocab_size` | 12,000 | BPE, trained from scratch |
| `d_model` | 384 | embedding / hidden width |
| `n_layers` | 6 | transformer blocks |
| `n_heads` | 6 | head dim = 64 |
| `d_ff` | 1,536 | 4× `d_model`, GELU MLP |
| `context_length` | 256 | learned absolute positional embeddings |
| `dropout` | 0.1 | embeddings, attention output, MLP output |
| `lm_head` | tied to `tok_emb` | saves ~4.6M parameters |
| Attention kernel | `F.scaled_dot_product_attention` | fused, causal in training |
| Weight init | GPT-2 scheme | `N(0, 0.02)`, residual projections scaled by `1/√(2·n_layers)` |

**Parameter budget (~15.3M):**

| Component | Parameters |
|---|---|
| Token embedding (tied with `lm_head`) | 4,608,000 |
| Positional embedding | 98,304 |
| 6 × transformer block (attn + MLP + 2× LayerNorm) | 10,626,048 |
| Final LayerNorm | 768 |
| **Total** | **≈ 15,333,120** |

The count is logged at the start of every training run, so you can confirm it lands within
±5% of the target.

## Project structure

```text
kronos-synapse-dialogue/
├── pyproject.toml          # dependencies + console entry point
├── config.py               # ModelConfig / TrainConfig / DataConfig (pydantic-settings)
├── cli.py                  # Typer entry point: tokenize / train / eval / chat
├── tokenizer/
│   ├── trainer.py          # BPE training (HF tokenizers, ByteLevel)
│   └── wrapper.py          # KronosTokenizer: encode / decode / dialogue turns
├── model/
│   ├── attention.py        # CausalSelfAttention + KVCache
│   ├── mlp.py              # GELU feedforward
│   ├── block.py            # pre-LN TransformerBlock
│   └── gpt.py              # MiniGPT (embeddings + blocks + tied lm_head)
├── data/
│   ├── sources.py          # TextCorpusSource ABC + GutenbergCorpusSource
│   ├── packing.py          # corpus → book-level split → uint16 memmap
│   └── dataset.py          # BinaryTokenDataset + DataLoader factory
├── training/
│   ├── scheduler.py        # cosine decay with linear warmup
│   ├── checkpoint.py       # save / load model + optimizer + scheduler
│   └── loop.py             # training loop, metrics, Rich progress
├── inference/
│   ├── generate.py         # KV-cache sampling generator
│   └── conversation.py     # ConversationBuffer (sentence-boundary trimming)
├── tests/                  # shape, causal-mask, packing, buffer unit tests
└── data/
    ├── raw/gutenberg/      # <-- you put .txt corpus files here
    └── processed/          # generated: tokenizer.json, train.bin, val.bin
```

## Requirements

- **Python** 3.12 or newer
- **PyTorch** 2.3+ (CPU build; `bfloat16` autocast is emulated on Alder Lake but still
  saves memory bandwidth — there is an fp32 fallback)
- **Hardware**: a modern multi-core CPU. Development target was an Intel i7-1225U
  (2P+8E, AVX2, no AVX-512). No GPU required.

## Installation

```bash
git clone <repo-url> kronos-synapse-dialogue
cd kronos-synapse-dialogue
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

This registers the `kronos_synapse` console command and pulls in the dev tools
(`pytest`, `mypy`).

## Configuration

All settings live in [`config.py`](config.py) as frozen `pydantic-settings` models.
Edit the defaults there to retune the model or training schedule.

### `ModelConfig`

| Option | Default | Description |
|---|---|---|
| `vocab_size` | `12_000` | BPE vocabulary size |
| `d_model` | `384` | hidden width |
| `n_layers` | `6` | transformer blocks |
| `n_heads` | `6` | attention heads |
| `d_ff` | `1536` | MLP inner width |
| `context_length` | `256` | max sequence length |
| `dropout` | `0.1` | dropout probability |

### `TrainConfig`

| Option | Default | Description |
|---|---|---|
| `num_threads` | `8` | `torch.set_num_threads` |
| `batch_size` | `16` | micro-batch size |
| `grad_accum_steps` | `8` | effective batch = `16 × 8 = 128` |
| `max_iters` | `50_000` | optimizer steps |
| `lr` | `3e-4` | peak learning rate |
| `lr_min` | `1e-5` | cosine floor |
| `warmup_iters` | `200` | linear warmup steps |
| `weight_decay` | `0.1` | applied to 2D params only |
| `max_grad_norm` | `1.0` | gradient clipping |
| `use_bf16` | `True` | `bfloat16` autocast on CPU |
| `compile_model` | `False` | optional `torch.compile` with fp32 fallback |
| `checkpoint_every` | `1_000` | checkpoint + val-eval cadence |
| `checkpoint_dir` | `checkpoints/` | output directory |
| `log_file` | `logs/train.jsonl` | per-checkpoint metrics log |

### `DataConfig`

| Option | Default | Description |
|---|---|---|
| `raw_dir` | `data/raw/gutenberg/` | input `.txt` corpus |
| `processed_dir` | `data/processed/` | `train.bin` / `val.bin` output |
| `tokenizer_dir` | `data/processed/tokenizer/` | `tokenizer.json` output |
| `min_quote_line_ratio` | `0.0` | optional dialogue-density filter |
| `split_seed` | `42` | book-level split seed |
| `val_fraction` | `0.10` | held-out books (unseen in training) |

## Preparing data

1. Drop Project Gutenberg `.txt` files into `data/raw/gutenberg/`. (19th–early-20th
   century novels — Austen, Dickens, Twain, etc. — work well: lots of direct speech and
   short exchanges.)
2. Train the tokenizer and pack the corpus into memory-mapped binary splits:

```bash
kronos_synapse tokenize --corpus-dir data/raw/gutenberg
```

This produces three artifacts in `data/processed/`:

- `tokenizer/tokenizer.json` — the BPE tokenizer
- `train.bin` — training tokens as a `uint16` memmap
- `val.bin` — validation tokens (whole books held out, so no window leakage)

Corpus cleanup happens automatically: Project Gutenberg header/footer boilerplate is
stripped, text is Unicode-NFKC normalized, and runs of whitespace are collapsed. Set
`min_quote_line_ratio` above 0 to keep only documents dense in quoted dialogue.

Special tokens are fixed: `<pad>=0`, `<unk>=1`, `<bos>=2`, `<eos>=3`. No role tokens
(`<user>`/`<bot>`) are added — see the [chat paradigm](#chat-paradigm--limitations) note.

## Training

```bash
kronos_synapse train
```

The loop prints the parameter count on start, then runs with a Rich progress bar.
At every `checkpoint_every` steps it:

- evaluates validation loss,
- appends `{step, train_loss, val_loss}` to `logs/train.jsonl`,
- writes `checkpoints/step_<n>.pt`,
- updates `checkpoints/best.pt` if validation loss improved.

**Resume** from any checkpoint (optimizer and scheduler state are restored):

```bash
kronos_synapse train --resume checkpoints/best.pt
```

## Evaluation

Evaluate a checkpoint on the held-out validation books:

```bash
kronos_synapse eval checkpoints/best.pt --split val
```

Reports cross-entropy loss and perplexity (`2^loss`) over the split.

## Chat & inference

```bash
kronos_synapse chat checkpoints/best.pt --temperature 0.8 --top-p 0.9
```

Generation streams token-by-token into the terminal. The first call prefills the prompt
and builds the KV cache; each subsequent token decodes against that cache, so long
conversations stay responsive.

| Flag | Default | Description |
|---|---|---|
| `--temperature` | `0.8` | sharpens (`<1`) or flattens (`>1`) the distribution |
| `--top-k` | `50` | keep only the `k` highest-probability tokens (`0` disables) |
| `--top-p` | `0.9` | nucleus sampling (`1.0` disables) |
| `--repetition-penalty` | `1.1` | down-weights already-generated tokens |
| `--max-new-tokens` | `128` | generation cap per turn |

The conversation buffer keeps a growing plain-text history and, when it nears
`context_length`, trims from the front at the nearest sentence boundary (never mid-word),
preserving the leading `<bos>`. That sliding window *is* the short-term memory — the model
reads the whole buffer each turn.

## Chat paradigm & limitations

This project is deliberately scoped and honest about what a 15M-parameter model can learn
from continuous prose:

- **It continues text, it does not follow instructions.** There are no `<user>`/`<bot>`
  turns in the training data, so the model has no signal for explicit turn-taking. What
  you type is treated as the start of a passage; the model writes what comes next.
- **Coherence is local.** Expect ~5–6 sentences of consistent style and entity tracking
  within the context window. Longer-range coherence is not guaranteed.
- **It is English-only** and literary-flavored, because the corpus is English fiction.

A reasonable sanity check that the context window is actually used: mention a character
name early in the buffer and confirm the model still refers to it 4–6 sentences later.
A `DialogueDatasetSource` stub is left in `data/sources.py` as an extension point if you
later fine-tune on annotated dialogue.

## Testing

```bash
pytest
```

Unit tests cover the parts most likely to silently break:

- `tests/test_model_shapes.py` — forward-pass tensor shapes, parameter count
- `tests/test_attention.py` — attention output shapes and KV-cache behavior
- `tests/test_causal_mask.py` — no leakage to future positions
- `tests/test_packing.py` — book-level split and binary packing logic
- `tests/test_conversation_buffer.py` — sentence-boundary trimming keeps `<bos>`

The tests use a tiny throwaway config and a small tokenizer trained on the fly, so the
whole suite finishes in a few seconds and needs no downloaded data.

## Development

Common tasks are wrapped in the `Makefile`:

```bash
make dev         # editable install with dev extras
make test        # pytest -q
make typecheck   # mypy .
make clean       # drop caches and build artifacts
```

The code is fully type-annotated and checked with `mypy`. When you add code, keep it
typed and add a test if you're touching the model, tokenizer, or packing paths. Style is
plain 4-space Python; comments explain *why*, not *what*. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the full rundown.

## Performance notes

On the development CPU (i7-1225U), expect roughly **400–800 tokens/sec** during training,
which works out to about **7–14 hours per epoch** over a ~20M-token corpus. Throughput
scales with `num_threads`, `use_bf16`, and `batch_size × grad_accum_steps`; tune these to
fit your own cores and memory. Generation with the KV-cache is measurably faster than the
no-cache baseline on the same CPU — that gap is the reason caching is mandatory here.

## Roadmap

Rough ordering, not promises:

- **RoPE positional encoding** to replace learned absolute positions and let the model
  extrapolate past `context_length`.
- **Optional instruction fine-tuning** on top of the base model, wiring up the
  `DialogueDatasetSource` stub and real `<user>`/`<bot>` role tokens.
- **Longer context** (512+) once training throughput allows it.
- **A `sample` CLI command** for one-shot continuation without the interactive loop.
- **KV-cache eviction** so chat sessions can run indefinitely instead of trimming text.

## FAQ

**Why CPU only?** Because the point was to see how far a from-scratch model gets on a
laptop with no GPU. Everything is tuned around that constraint.

**Why not just use `transformers`?** Building the pieces by hand is the whole exercise.
You get to see exactly what attention, the KV cache, and the training loop are doing.

**It replies with gibberish / repeats itself.** Small models trained on limited data do
that. Give it more corpus and more steps, lower `--temperature`, and raise
`--repetition-penalty` a little. Also remember it *continues* text — it doesn't answer
questions (see [Chat paradigm & limitations](#chat-paradigm--limitations)).

**Can I use my own text instead of Gutenberg?** Yes. Any plain `.txt` files work; the
Gutenberg-specific step is just the header/footer stripping, which is a no-op on other
text. For a different format, add a `TextCorpusSource` subclass in `data/sources.py`.

**How do I make it bigger/smaller?** Edit the defaults in `config.py` (`d_model`,
`n_layers`, `n_heads`, `context_length`). The param count is printed at the start of
training so you can check where you landed.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup and
expectations, and [CHANGELOG.md](CHANGELOG.md) for the release history. For anything
large, open an issue first so we can agree on the approach.

## License

[MIT](LICENSE) © 2026 Kronos
