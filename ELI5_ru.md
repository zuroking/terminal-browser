# ELI5: `terminal-browser`

*ELI5 = «Explain Like I'm 5» — объяснение простым языком. Технический источник истины — [ARCHITECTURE.md](ARCHITECTURE.md).*

## Что это вообще такое?

Представь маленькую машину для чтения. Ты даёшь ей web address, она забирает страницу, читает текст и печатает чистую страницу в terminal. Она также помнит, где ты был, чтобы можно было перейти назад и вперёд. (§1 G1–G5)

## Что она делает?

Она понимает обычные страницы `http://` и `https://`, читает документированную часть HTML и превращает headings, paragraphs, lists, tables, links и forms в читаемые terminal lines. (§1 G1–G5, §8.3–§8.7)

Если на странице есть form, машина может подготовить GET или POST request для базовых описанных controls. (§1 G3, §8.5, §9.8)

## Чего она не делает?

Она не выполняет JavaScript, не понимает CSS, не показывает загруженные изображения, не использует HTTP/2, не держит WebSocket открытым, не обходит `iframe` pages, не обрабатывает login или proxy, не декодирует Brotli/zstd, не использует keep-alive connections и не разделяет cookies между hosts. (§1 N1–N10)

Эти omissions — не скрытые bugs. Это deliberate scope boundaries. (§1, §12)

## Почему она careful к safety?

Web content — это untrusted text. Reader очищает его один раз при построении страницы и ещё раз непосредственно перед terminal output. Terminal controls удаляются, а финальная line обрезается до доступной terminal width. (§1 G8, §4, §10.7)

Network connections используют TLS certificate и hostname verification, а reads, decompression, parsing, cookies, cache, forms, rendering и history имеют numeric limits. (§1 G7, §2.3 R9, §5 I1–I3, §6)

## Почему страница может быть обрезана?

Очень большие страницы и очень длинные lines не могут потреблять unlimited memory или terminal space. Когда limit достигнут, reader сохраняет bounded work и показывает truncation там, где этого требует architecture. (§1 G7, §5 I12, §6, §8.9)

## Почему при back иногда появляется notice?

Page, полученная через POST, запоминается по final URL. При возврате reader не отправляет старую form автоматически: используется GET и сообщается, что произошёл replay. (§9.7, §12 DD-18)

## Совсем коротко

- Text browser для HTTP(S) pages. (§1 G1–G5)
- Читает HTML, извлекает basic forms и выводит readable terminal output. (§1 G2–G5)
- Имеет bounded memory, time, network, cache, cookie, form и terminal limits. (§1 G7, §6)
- Дважды очищает untrusted text и имеет one terminal output owner. (§4, §10.7)
- Сознательно не пытается быть complete graphical browser. (§1 N1–N10, §12)

Взрослая версия: [ARCHITECTURE.md](ARCHITECTURE.md). На русском: [ELI5_ru.md](ELI5_ru.md).
