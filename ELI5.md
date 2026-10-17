# ELI5: `terminal-browser`

*ELI5 = “Explain Like I'm 5” — a plain-language explanation. The technical source of truth is [ARCHITECTURE.md](ARCHITECTURE.md).*

## What is this thing?

Imagine a small reading machine. You give it a web address, and it goes to fetch a page, reads the text, and prints a clean page in your terminal. It also remembers where you have been so you can go back and forward. (§1 G1–G5)

## What does it do?

It understands ordinary `http://` and `https://` pages, reads a carefully documented part of HTML, and turns headings, paragraphs, lists, tables, links, and forms into readable terminal lines. (§1 G1–G5, §8.3–§8.7)

When a page has a form, the machine can prepare a GET or POST request for the basic controls it documents. (§1 G3, §8.5, §9.8)

## What does it not do?

It does not run JavaScript, understand CSS, display downloaded images, speak HTTP/2, keep a WebSocket open, browse `iframe` pages, handle logins or proxies, decode Brotli/zstd, reuse keep-alive connections, or share cookies across hosts. (§1 N1–N10)

Those omissions are not hidden bugs. They are deliberate scope boundaries. (§1, §12)

## Why is it careful about safety?

Web content is untrusted text. The reader cleans it once while building the page and again immediately before terminal output. Terminal controls are removed, and the final line is cut to the available terminal width. (§1 G8, §4, §10.7)

Network connections use TLS certificate and hostname verification, and reads, decompression, parsing, cookies, cache, forms, rendering, and history all have numeric limits. (§1 G7, §2.3 R9, §5 I1–I3, §6)

## Why can a page be cut short?

Very large pages and very long lines are not allowed to consume unlimited memory or terminal space. When a limit is reached, the reader keeps the work bounded and makes truncation visible where the architecture requires it. (§1 G7, §5 I12, §6, §8.9)

## Why does back sometimes show a notice?

A page reached by POST is remembered by its final URL. Going back does not silently submit the old form again; the reader uses GET and tells you that this replay happened. (§9.7, §12 DD-18)

## TL;DR

- A text browser for HTTP(S) pages. (§1 G1–G5)
- It reads HTML, extracts basic forms, and renders readable terminal output. (§1 G2–G5)
- It has bounded memory, time, network, cache, cookie, form, and terminal limits. (§1 G7, §6)
- It cleans untrusted text twice and has one terminal output owner. (§4, §10.7)
- It deliberately does not try to be a complete graphical browser. (§1 N1–N10, §12)

For the grown-up version, see [ARCHITECTURE.md](ARCHITECTURE.md). На русском: [ELI5_ru.md](ELI5_ru.md).
