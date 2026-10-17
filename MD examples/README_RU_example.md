# Kronos Synapse Dialogue Core

![Python](https://img.shields.io/badge/python-3.12+-blue)
![PyTorch](https://img.shields.io/badge/PyTorch-CPU-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Params](https://img.shields.io/badge/params-%7E15.3M-informational)

**Языки:** [English](README.md) · [Español](docs/i18n/es/README.md) · [Deutsch](docs/i18n/de/README.md) · [中文](docs/i18n/zh/README.md) · **Русский**

Декодерная языковая модель в стиле GPT (~15.3M параметров), написанная с нуля на чистых примитивах `torch.nn` и полностью обученная на CPU. Поставляется с BPE-токенизатором, пайплайном обучения на `memmap` и потоковым CLI-чатом, построенным вокруг генератора с KV-кешем. Весь стек — модель, данные, обучение, инференс — реализован вручную, без обвязок `transformers` или `nanoGPT`.

> **Что это такое (и чем не является).** Модель делает **продолжение промпта**, а не следование инструкциям. Она обучена на художественной прозе (Project Gutenberg), а не на размеченных диалоговых парах. Вы вводите текст — она его продолжает. Это не ролевой ассистент. См. [Парадигма чата и ограничения](#парадигма-чата-и-ограничения).

---

## Оглавление

- [Быстрый старт](#быстрый-старт)
- [Ключевые особенности](#ключевые-особенности)
- [Архитектура](#архитектура)
- [Структура проекта](#структура-проекта)
- [Требования](#требования)
- [Установка](#установка)
- [Конфигурация](#конфигурация)
- [Подготовка данных](#подготовка-данных)
- [Обучение](#обучение)
- [Оценка](#оценка)
- [Чат и инференс](#чат-и-инференс)
- [Парадигма чата и ограничения](#парадигма-чата-и-ограничения)
- [Тестирование](#тестирование)
- [Разработка](#разработка)
- [Заметки о производительности](#заметки-о-производительности)
- [Дорожная карта](#дорожная-карта)
- [FAQ](#faq)
- [Участие](#участие)
- [Лицензия](#лицензия)

## Быстрый старт

Если хочется просто посмотреть, как это работает — весь цикл от начала до конца:

```bash
# 1. установка
pip install -e ".[dev]"

# 2. положите несколько .txt книг в data/raw/gutenberg/, затем:
kronos_synapse tokenize --corpus-dir data/raw/gutenberg

# 3. обучение (Ctrl+C безопасен; позже можно продолжить с чекпоинта)
kronos_synapse train

# 4. поговорите с ней
kronos_synapse chat checkpoints/best.pt
```

Есть также `Makefile`, если предпочитаете `make tokenize`, `make train`, `make chat`.
Всё работает на CPU — без GPU, без облака, без API-ключей.

## Ключевые особенности

- **Трансформер, собранный вручную.** `CausalSelfAttention`, `MLP`, `TransformerBlock` и `MiniGPT` построены напрямую на `nn.Linear`, `nn.LayerNorm`, `nn.Embedding` и `nn.Dropout`. Attention идёт через `F.scaled_dot_product_attention`, который выбирает оптимизированное fused-ядро на CPU.
- **В первую очередь CPU.** Всё работает без CUDA. Цикл обучения выжимает максимум за счёт gradient accumulation, `bfloat16` autocast, настраиваемого числа потоков и опционального `torch.compile` fallback.
- **Генерация с KV-кешем.** Инференс делает один prefill-проход по промпту, затем декодирует по одному токену, опираясь на закешированные ключи/значения — разница между usable и unusable чатом на ноутбучном CPU.
- **Управляемый сэмплер.** Temperature, top-k, top-p (nucleus) и repetition penalty — все доступны как CLI-флаги.
- **Типизированная конфигурация.** Три конфига `pydantic-settings` (`ModelConfig`, `TrainConfig`, `DataConfig`) заменяют магические словари валидированными, замороженными настройками.

## Архитектура

Стандартный pre-LN GPT-декодер. Таблица ниже — дефолтный `ModelConfig`.

| Компонент | Значение | Примечание |
|---|---|---|
| `vocab_size` | 12,000 | BPE, обучен с нуля |
| `d_model` | 384 | ширина эмбеддинга / hidden |
| `n_layers` | 6 | трансформер-блоки |
| `n_heads` | 6 | head dim = 64 |
| `d_ff` | 1,536 | 4× `d_model`, GELU MLP |
| `context_length` | 256 | выученные абсолютные позиционные эмбеддинги |
| `dropout` | 0.1 | эмбеддинги, выход attention, выход MLP |
| `lm_head` | tied to `tok_emb` | экономит ~4.6M параметров |
| Attention kernel | `F.scaled_dot_product_attention` | fused, каузальный при обучении |
| Инициализация весов | GPT-2 схема | `N(0, 0.02)`, residual-проекции масштабированы `1/√(2·n_layers)` |

**Бюджет параметров (~15.3M):**

| Компонент | Параметры |
|---|---|
| Token embedding (tied с `lm_head`) | 4,608,000 |
| Positional embedding | 98,304 |
| 6 × transformer block (attn + MLP + 2× LayerNorm) | 10,626,048 |
| Final LayerNorm | 768 |
| **Всего** | **≈ 15,333,120** |

Счётчик выводится в начале каждого обучения, так что вы можете убедиться, что попали в ±5% от цели.

## Структура проекта

```text
kronos-synapse-dialogue/
├── pyproject.toml          # зависимости + консольная точка входа
├── config.py               # ModelConfig / TrainConfig / DataConfig (pydantic-settings)
├── cli.py                  # Typer entry point: tokenize / train / eval / chat
├── tokenizer/
│   ├── trainer.py          # обучение BPE (HF tokenizers, ByteLevel)
│   └── wrapper.py          # KronosTokenizer: encode / decode / dialogue turns
├── model/
│   ├── attention.py        # CausalSelfAttention + KVCache
│   ├── mlp.py              # GELU feedforward
│   ├── block.py            # pre-LN TransformerBlock
│   └── gpt.py              # MiniGPT (эмбеддинги + блоки + tied lm_head)
├── data/
│   ├── sources.py          # TextCorpusSource ABC + GutenbergCorpusSource
│   ├── packing.py          # корпус → book-level split → uint16 memmap
│   └── dataset.py          # BinaryTokenDataset + DataLoader factory
├── training/
│   ├── scheduler.py        # cosine decay с linear warmup
│   ├── checkpoint.py       # save / load модели + оптимизатора + scheduler
│   └── loop.py             # цикл обучения, метрики, Rich progress
├── inference/
│   ├── generate.py         # KV-cache сэмплирующий генератор
│   └── conversation.py     # ConversationBuffer (обрезка по границам предложений)
├── tests/                  # shape, causal-mask, packing, buffer unit-тесты
└── data/
    ├── raw/gutenberg/      # <-- сюда кладите .txt файлы корпуса
    └── processed/          # генерируется: tokenizer.json, train.bin, val.bin
```

## Требования

- **Python** 3.12 или новее
- **PyTorch** 2.3+ (CPU-сборка; `bfloat16` autocast эмулируется на Alder Lake, но всё равно экономит память — есть fallback на fp32)
- **Железо**: современный многоядерный CPU. Целевая машина разработки — Intel i7-1225U (2P+8E, AVX2, без AVX-512). GPU не требуется.

## Установка

```bash
git clone <repo-url> kronos-synapse-dialogue
cd kronos-synapse-dialogue
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Регистрирует команду `kronos_synapse` и подтягивает dev-инструменты (`pytest`, `mypy`).

## Конфигурация

Все настройки живут в [`config.py`](config.py) как замороженные модели `pydantic-settings`.
Правьте дефолты там, чтобы перенастроить модель или расписание обучения.

### `ModelConfig`

| Параметр | Дефолт | Описание |
|---|---|---|
| `vocab_size` | `12_000` | размер BPE-словаря |
| `d_model` | `384` | hidden ширина |
| `n_layers` | `6` | трансформер-блоки |
| `n_heads` | `6` | головы attention |
| `d_ff` | `1536` | внутренняя ширина MLP |
| `context_length` | `256` | максимальная длина последовательности |
| `dropout` | `0.1` | вероятность dropout |

### `TrainConfig`

| Параметр | Дефолт | Описание |
|---|---|---|
| `num_threads` | `8` | `torch.set_num_threads` |
| `batch_size` | `16` | micro-batch size |
| `grad_accum_steps` | `8` | эффективный batch = `16 × 8 = 128` |
| `max_iters` | `50_000` | шагов оптимизатора |
| `lr` | `3e-4` | пиковый learning rate |
| `lr_min` | `1e-5` | пол cosine floor |
| `warmup_iters` | `200` | шагов linear warmup |
| `weight_decay` | `0.1` | применяется только к 2D параметрам |
| `max_grad_norm` | `1.0` | gradient clipping |
| `use_bf16` | `True` | `bfloat16` autocast на CPU |
| `compile_model` | `False` | опциональный `torch.compile` с fp32 fallback |
| `checkpoint_every` | `1_000` | частота чекпоинтов + val-оценки |
| `checkpoint_dir` | `checkpoints/` | выходная директория |
| `log_file` | `logs/train.jsonl` | лог метрик по чекпоинтам |

### `DataConfig`

| Параметр | Дефолт | Описание |
|---|---|---|
| `raw_dir` | `data/raw/gutenberg/` | входной `.txt` корпус |
| `processed_dir` | `data/processed/` | `train.bin` / `val.bin` выход |
| `tokenizer_dir` | `data/processed/tokenizer/` | `tokenizer.json` выход |
| `min_quote_line_ratio` | `0.0` | опциональный фильтр по плотности диалогов |
| `split_seed` | `42` | seed для book-level split |
| `val_fraction` | `0.10` | held-out книги (не видны при обучении) |

## Подготовка данных

1. Положите `.txt` файлы Project Gutenberg в `data/raw/gutenberg/`. (Романы XIX–начала XX века — Austen, Dickens, Twain и т.д. — подходят хорошо: много прямой речи и коротких обменов.)
2. Обучите токенизатор и упакуйте корпус в memory-mapped бинарные сплиты:

```bash
kronos_synapse tokenize --corpus-dir data/raw/gutenberg
```

Это создаёт три артефакта в `data/processed/`:

- `tokenizer/tokenizer.json` — BPE-токенизатор
- `train.bin` — токены обучения как `uint16` memmap
- `val.bin` — токены валидации (целые книги held-out, так что нет утечки окон)

Очистка корпуса происходит автоматически: boilerplate заголовков/футеров Project Gutenberg вырезается, текст нормализуется Unicode-NFKC, серии пробелов схлопываются. Установите `min_quote_line_ratio` выше 0, чтобы оставить только документы, насыщенные цитатами-диалогами.

Специальные токены фиксированы: `<pad>=0`, `<unk>=1`, `<bos>=2`, `<eos>=3`. Ролевые токены (`<user>`/`<bot>`) не добавляются — см. заметку [парадигма чата](#парадигма-чата-и-ограничения).

## Обучение

```bash
kronos_synapse train
```

Цикл выводит количество параметров на старте, затем работает с Rich progress bar.
На каждом `checkpoint_every` шагов он:

- оценивает validation loss,
- дописывает `{step, train_loss, val_loss}` в `logs/train.jsonl`,
- пишет `checkpoints/step_<n>.pt`,
- обновляет `checkpoints/best.pt`, если validation loss улучшился.

**Продолжение** с любого чекпоинта (состояние оптимизатора и scheduler восстанавливаются):

```bash
kronos_synapse train --resume checkpoints/best.pt
```

## Оценка

Оценка чекпоинта на held-out валидационных книгах:

```bash
kronos_synapse eval checkpoints/best.pt --split val
```

Сообщает cross-entropy loss и perplexity (`2^loss`) по сплиту.

## Чат и инференс

```bash
kronos_synapse chat checkpoints/best.pt --temperature 0.8 --top-p 0.9
```

Генерация стримит токен за токеном в терминал. Первый вызов делает prefill промпта и строит KV-кеш; каждый следующий токен декодируется с этим кешем, так что длинные беседы остаются отзывчивыми.

| Флаг | Дефолт | Описание |
|---|---|---|
| `--temperature` | `0.8` | заостряет (`<1`) или сглаживает (`>1`) распределение |
| `--top-k` | `50` | оставлять только `k` самых вероятных токенов (`0` отключает) |
| `--top-p` | `0.9` | nucleus sampling (`1.0` отключает) |
| `--repetition-penalty` | `1.1` | штрафует уже сгенерированные токены |
| `--max-new-tokens` | `128` | лимит генерации за ход |

Буфер беседы ведёт растущую plain-text историю и, приближаясь к `context_length`, обрезает спереди по ближайшей границе предложения (никогда не посередине слова), сохраняя начальный `<bos>`. Это скользящее окно *и есть* краткосрочная память — модель читает весь буфер каждый ход.

## Парадигма чата и ограничения

Проект намеренно ограничен и честен о том, чему 15M-параметровая модель может научиться на непрерывной прозе:

- **Она продолжает текст, а не следует инструкциям.** В обучающих данных нет ходов `<user>`/`<bot>`, так что у модели нет сигнала для явного turn-taking. То, что вы вводите, считается началом отрывка; модель пишет, что идёт дальше.
- **Когерентность локальна.** Ожидайте ~5–6 предложений согласованного стиля и отслеживания сущностей внутри контекстного окна. Дальняя когерентность не гарантируется.
- **Только английский** и литературный оттенок, потому что корпус — английская художественная литература.

Разумный sanity-check, что контекстное окно реально используется: упомяните имя персонажа в начале буфера и убедитесь, что модель всё ещё ссылается на него через 4–6 предложений. Заглушка `DialogueDatasetSource` оставлена в `data/sources.py` как точка расширения, если позже дообучите на размеченных диалогах.

## Тестирование

```bash
pytest
```

Юнит-тесты покрывают части, которые чаще всего ломаются тихо:

- `tests/test_model_shapes.py` — формы forward-pass тензоров, количество параметров
- `tests/test_attention.py` — формы выхода attention и поведение KV-кеша
- `tests/test_causal_mask.py` — отсутствие утечки в будущие позиции
- `tests/test_packing.py` — book-level split и логика бинарной упаковки
- `tests/test_conversation_buffer.py` — обрезка по границам предложений сохраняет `<bos>`

Тесты используют крошечный throwaway-конфиг и маленький токенизатор, обученный на лету, так что весь набор проходит за несколько секунд и не требует скачанных данных.

## Разработка

Общие задачи завёрнуты в `Makefile`:

```bash
make dev         # editable install с dev extras
make test        # pytest -q
make typecheck   # mypy .
make clean       # удалить кеши и артефакты сборки
```

Код полностью типизирован и проверяется `mypy`. Добавляя код, держите его типизированным и добавьте тест, если трогаете модель, токенизатор или пути упаковки. Стиль — обычный 4-пробельный Python; комментарии объясняют *почему*, а не *что*. См. [CONTRIBUTING.md](CONTRIBUTING.md) для полного разбора.

## Заметки о производительности

На dev CPU (i7-1225U) ожидайте примерно **400–800 токенов/сек** при обучении, что даёт около **7–14 часов на эпоху** на корпусе ~20M токенов. Пропускная способность масштабируется с `num_threads`, `use_bf16` и `batch_size × grad_accum_steps`; тюнингуйте под свои ядра и память. Генерация с KV-кешем заметно быстрее baseline без кеша на том же CPU — этот разрыв и делает кеширование обязательным.

## Дорожная карта

Примерный порядок, не обещания:

- **RoPE позиционные эмбеддинги** вместо выученных абсолютных, чтобы модель экстраполировала за `context_length`.
- **Опциональное instruction fine-tuning** поверх базовой модели, с подключением заглушки `DialogueDatasetSource` и реальных ролевых токенов `<user>`/`<bot>`.
- **Более длинный контекст** (512+) когда позволит пропускная способность обучения.
- **Команда `sample`** для one-shot продолжения без интерактивного цикла.
- **Вытеснение KV-кеша**, чтобы сессии чата могли идти бесконечно вместо обрезки текста.

## FAQ

**Почему только CPU?** Потому что цель была проверить, как далеко зайдёт from-scratch модель на ноутбуке без GPU. Всё заточено под это ограничение.

**Почему не просто использовать `transformers`?** Собрать детали вручную — и есть упражнение. Вы видите ровно, что делают attention, KV-кеш и цикл обучения.

**Отвечает бредом / повторяется.** Маленькие модели на ограниченных данных так делают. Дайте больше корпуса и больше шагов, понизьте `--temperature` и немного повысьте `--repetition-penalty`. И помните — она *продолжает* текст, а не отвечает на вопросы (см. [Парадигма чата и ограничения](#парадигма-чата-и-ограничения)).

**Можно ли использовать свой текст вместо Gutenberg?** Да. Любые plain `.txt` файлы подойдут; специфичный для Gutenberg шаг вырезания header/footer — no-op на другом тексте. Для другого формата добавьте подкласс `TextCorpusSource` в `data/sources.py`.

**Как сделать больше/меньше?** Правьте дефолты в `config.py` (`d_model`, `n_layers`, `n_heads`, `context_length`). Количество параметров выводится в начале обучения, так что вы увидите, куда попали.

## Участие

Участие приветствуется — см. [CONTRIBUTING.md](CONTRIBUTING.md) про настройку и ожидания, и [CHANGELOG.md](CHANGELOG.md) про историю релизов. Для крупных изменений сначала откройте issue, чтобы согласовать подход.

## Лицензия

[MIT](LICENSE) © 2026 Kronos
