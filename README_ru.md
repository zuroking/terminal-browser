# terminal-browser

**Языки:** [English](README.md) · **Русский**

`terminal-browser` — ограниченный текстовый HTTP/1.1-браузер на Python. Он получает ресурсы `http://` и `https://`, разбирает документированное подмножество HTML, извлекает базовые формы, формирует читаемый текст и направляет вывод терминала через одну очищенную точку выхода. (§1 G1–G8, §2.2)

> **Скоуп:** это текстовый reader, а не полноценный браузер. Он не выполняет JavaScript, не реализует CSS, не загружает и не растрирует изображения, не использует HTTP/2, не открывает WebSocket, не обходит `iframe`-контексты, не предоставляет authentication или proxy support, не декодирует Brotli/zstd, не использует keep-alive pooling и не расширяет cookie scope. (§1 N1–N10)

## Оглавление

- [Назначение](#назначение)
- [Не-цели](#не-цели)
- [Установка](#установка)
- [Использование REPL](#использование-repl)
- [Одноразовый запуск](#одноразовый-запуск)
- [Флаги и коды выхода](#флаги-и-коды-выхода)
- [Обзор ограничений](#обзор-ограничений)
- [Безопасность](#безопасность)
- [Разработка](#разработка)
- [Лицензия](#лицензия)

## Назначение

Проект — образовательная реализация ограниченного браузерного конвейера: сетевой транспорт, детерминированное декодирование, инкрементальный HTML-парсинг, формы, layout, история сессии и вывод в терминал. (§1 G1–G9)

Каждая операция чтения, декодирования, парсинга, формы, рендеринга, кэша, cookie и истории регулируется именованным числовым лимитом. (§1 G7, §6)

## Не-цели

Следующие границы являются нормативными:

- **N1:** JavaScript не выполняется. (§1 N1, §12 DD-01)
- **N2:** нет CSS selection, cascade, colors или visual layout. (§1 N2, §12 DD-02)
- **N3:** изображения не загружаются, не декодируются и не растрируются; используется только `alt`-текст. (§1 N3, §12 DD-03)
- **N4:** нет HTTP/2, ALPN, HPACK, multiplexing или server push. (§1 N4, §12 DD-04)
- **N5:** нет WebSocket или постоянных двунаправленных каналов. (§1 N5, §12 DD-05)
- **N6:** нет browsing context для `iframe`. (§1 N6, §12 DD-06)
- **N7:** нет authentication flows или proxy support. (§1 N7, §12 DD-07)
- **N8:** нет Brotli, zstd и content coding кроме `gzip` и `deflate`. (§1 N8, §12 DD-08)
- **N9:** нет keep-alive connection pooling; каждый запрос отправляет `Connection: close`. (§1 N9, §12 DD-21)
- **N10:** нет расширения cookie через `Domain=`; cookies остаются host-only. (§1 N10, §12 DD-10)

## Установка

Исходное дерево рассчитано на Python 3.12+ и Pydantic v2. (§1, §2.3 R7)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX:   source .venv/bin/activate
python -m pip install "pydantic>=2" pytest mypy
```

Архитектура определяет грамматику CLI, но не задаёт имя packaging entry point. Примеры ниже показывают эту грамматику; launcher должен предоставить application composition root. (§3.16, §10.2)

## Использование REPL

Без `--url` приложение выбирает интерактивный line-based REPL. (§10.1, §10.2)

```text
open https://example.test/
follow 1
back
forward
submit 1 name=value
quit
```

Вход ограничен `MAX_REPL_LINE_BYTES=4_096` и `MAX_REPL_TOKENS=64`; слишком длинная строка отбрасывается и не разбирается. (§6, §10.1)

## Одноразовый запуск

С `--url URL` приложение выполняет одну навигацию и завершает работу вместо запуска REPL. (§10.2)

```bash
python -m terminal_browser.cli --url https://example.test/
```

Результат одноразового запуска равен `0` для завершённой навигации и `1` для обработанной ошибки навигации. (§10.2)

## Флаги и коды выхода

| Флаг | Поведение |
|---|---|
| `--url URL` | Выбирает одноразовую навигацию. (§10.2) |
| `--width N` | Выбирает явную ширину терминала. (§10.2) |
| `--no-cache` | Отключает чтение, revalidation и запись cache. (§10.2) |
| `--debug` | Добавляет очищенный traceback к диагностике неожиданной ошибки. (§7.3, §10.2) |

| Код выхода | Значение |
|---:|---|
| `0` | Нормальный выход, успешная одноразовая навигация или `quit`. (§10.2) |
| `1` | Обработанная ошибка одноразовой навигации или верхнеуровневое неожиданное исключение. (§7.3, §10.2) |
| `2` | Ошибка parsing или validation аргументов. (§10.2) |
| `130` | `KeyboardInterrupt`. (§7.3, §10.2) |

## Обзор ограничений

Значения ниже — предложенные значения §6; каждое значение сопровождается ссылкой на enforcing section.

| Константа | Значение |
|---|---:|
| `CONNECT_TIMEOUT_SEC` | `5.0` (§6) |
| `DNS_TIMEOUT_SEC` | `5.0` (§6) |
| `READ_TIMEOUT_SEC` | `10.0` (§6) |
| `TOTAL_RESPONSE_TIMEOUT_SEC` | `30.0` (§6) |
| `NAVIGATION_TIMEOUT_SEC` | `60.0` (§6) |
| `MAX_REDIRECTS` | `5` (§6) |
| `MAX_HISTORY` | `100` (§6) |
| `MAX_BODY_BYTES` | `2_000_000` (§6) |
| `MAX_DECOMPRESSED_BYTES` | `5_000_000` (§6) |
| `CACHE_BYTE_BUDGET` | `10_000_000` (§6) |
| `MAX_CACHE_ENTRY_BYTES` | `2_500_000` (§6) |
| `MAX_HEADER_SIZE` | `65_536` (§6) |
| `MAX_HEADER_COUNT` | `100` (§6) |
| `MAX_INTERIM_RESPONSES` | `5` (§6) |
| `MAX_DOM_DEPTH` | `64` (§6) |
| `MAX_NODES` | `25_000` (§6, §12 DD-12) |
| `MAX_TOKENS` | `100_000` (§6) |
| `CHUNK_READ_SIZE` | `16_384` (§6) |
| `TERMINAL_WIDTH_FALLBACK` | `80` (§6) |
| `MIN_LAYOUT_WIDTH` | `4` (§6) |
| `MAX_RENDER_LINES` | `5_000` (§6) |
| `MAX_LINE_WIDTH` | `120` (§6) |
| `MAX_URL_LEN` | `8_192` (§6) |
| `MAX_CHARSET_PRESCAN_BYTES` | `1_024` (§6) |
| `MAX_COOKIES_PER_HOST` | `50` (§6) |
| `MAX_COOKIES_TOTAL` | `500` (§6) |
| `MAX_COOKIE_STORE_BYTES` | `65_536` (§6) |
| `MAX_SET_COOKIE_BYTES` | `8_192` (§6) |
| `MAX_FORM_FIELDS` | `256` (§6) |
| `MAX_FORM_BYTES` | `16_384` (§6) |
| `MAX_COOKIE_HEADER_BYTES` | `8_192` (§6) |
| `MAX_REPL_LINE_BYTES` | `4_096` (§6) |
| `MAX_REPL_TOKENS` | `64` (§6) |

## Безопасность

Браузер очищает недоверенный текст при построении и повторно при выводе в терминал; проверка TLS certificate и hostname безусловна. (§4, §5 I1–I2, §10.7)

Только `term/output.py` обращается к stdout, stderr или output stream. (§2.3 R9, §10.7)

См. [SECURITY.md](SECURITY.md) для границ безопасности, ожиданий по reporting и остаточного риска DNS. Для русского текста: [SECURITY_ru.md](SECURITY_ru.md).

## Разработка

Порядок реализации и требуемые доказательства определены в [ARCHITECTURE.md](ARCHITECTURE.md) §11 и [PROTOCOL.md](PROTOCOL.md). После каждого модуля запускай полный test suite и strict type checker и сохраняй сырое terminal evidence. (§11, process constraints в `CLAUDE.md`)

## Лицензия

[MIT](LICENSE) © 2026 Zuro
