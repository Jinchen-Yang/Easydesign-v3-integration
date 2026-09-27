# Doudou quick chat

Click Doudou (豆豆) to open its white/violet chat panel. The panel chooses free space above, below or beside the full animated rabbit. In compact viewports it temporarily pairs them without overwriting the saved drag position; closing chat restores that position. Visible-viewport changes are tracked for mobile keyboards. The gear opens the existing mascot settings. Chinese/English follows the page language. Replies stream as they arrive; Stop cancels the request. New chat clears the current conversation. Closing the panel stops an in-flight reply and retains the conversation in this tab; reloading clears it. Conversation history is kept in memory, not localStorage.

## Connection

The current product path is:

```text
authenticated browser → same-origin Product service → local bounded Python bridge → DeepSeek
```

The Product service and credential bridge run on the same Suzhou2 product host, so the live
product does not depend on the historical Mac-to-Suzhou2 SSH preview bridge. The bridge starts
only for one request and does not open another server port. It does not provide shell tools to
the model or call EasyDesign's scientific backend. No DSH, GPU job, scheduler, Gate approval or
workflow mutation is involved.

- Endpoint: `POST /api/rabbit/chat`, content-only NDJSON; `GET` reports configuration only, not provider health.
- Model: `deepseek-flash` (the official V4.1 Flash API alias at implementation), thinking disabled, streaming enabled, output capped at 1,024 tokens.
- Conversation: up to 16 prior completed messages plus the current message; 4,000 characters per new message; 32,000 total history characters.
- Page context: viewed stage, selected design status and up to 1,200 characters of the selected goal/description. Raw files, structure coordinates and FASTA input are not automatically attached. Anything the user explicitly types into chat is sent to the model.
- System context explains that chat is separate from the live gated scientific workflow. It cannot launch jobs, approve Gates, place lab orders or change projects. It treats the supplied page summary as untrusted data.
- Product server requires the existing Workbench session, validates same origin, JSON, roles and size, and allows at most two concurrent requests and 20 requests/minute. Browser callers cannot select a host, path, endpoint or model. There are no automatic paid retries.
- The Python bridge emits only answer content, suggested questions, completion and sanitized error codes. Reasoning fields, provider errors and credentials are never relayed. HTTPS certificate verification remains enabled; the host's system CA bundle is used where available.

## Live product setup

The private product `.env.local` may contain `DEEPSEEK_API_KEY=...`; the normal Product service
startup loads only credential names declared in the model configuration. The value remains on
the server and is not returned by the status or streaming endpoint.

## Historical local preview setup

The original standalone demo on port 13190 used the following SSH-only settings. They remain
documented for reproducing that demo and are not part of the canonical live product path.

Keep these server-only settings in the **local frontend's private `.env.local`**, preserving existing entries:

```dotenv
RABBIT_CHAT_SSH_HOST=Suzhou2
RABBIT_CHAT_REMOTE_SCRIPT=/data/easydesign-easy-ui-20260925/server/rabbit_chat.py
RABBIT_CHAT_REMOTE_ENV=/data/easydesign-worktrees/v3-phase1-20260910/.env.local
```

That last path is the existing private credential file on Suzhou2. It must contain a literal `DEEPSEEK_API_KEY=...` or `export DEEPSEEK_API_KEY=...` assignment and should have mode 600. The bridge reads it as data; it does not execute/source the file. Do not put a key in a `VITE_*` variable, browser storage, source control or public assets.

The remote script is supplied in this full source repository under `server/rabbit_chat.py`. Node 22+, pnpm and an already trusted non-interactive SSH connection are required on the preview host; Python 3.10+ is required on Suzhou2. Restart the preview after changing server configuration.

```bash
pnpm install --frozen-lockfile
pnpm dev
```

The same historical middleware is available with `pnpm build && pnpm preview`. A static-only
deployment serves the UI but cannot provide live chat. The canonical Product service supplies
its authenticated same-origin bridge instead.

## Validation

```bash
pnpm test
python3 -m unittest discover -s tests -p 'test_rabbit_bridge.py'
pnpm build
pnpm test:e2e
pnpm test:production
pnpm test:mascot:webkit
# Explicit live smoke: makes three paid model calls using the server key.
node scripts/smoke-rabbit-chat-live.mjs
```

Tests cover validation, role injection, same-origin boundaries, streaming, UTF-8 chunk boundaries, disconnect cancellation, request limits, sanitized errors, reasoning exclusion, history, language, reset, stop/recovery and text-only rendering. Ordinary browser regressions mock chat and make no model calls.

Verified on 2026-09-25:

- 49 Vitest tests and 3 Python bridge tests passed.
- All 24 browser regression scenarios passed, including focused reruns after fixing draft context and a resize assertion race. The 4 chat scenarios passed again after the final typography adjustment.
- Production build and automatic six-finalist demo smoke passed; the existing 3Dmol eval warning is unchanged.
- Desktop/mobile WebKit at 2× pixel density passed the mascot journey, drag, pause and bounded-size checks.
- A real two-turn DeepSeek conversation in WebKit retained the supplied design nickname and accurately described the demo's compute boundary. First visible answer text arrived in about 1.1 seconds in this sample; latency is not guaranteed. Research storage was unchanged and there were no page errors.
- Screenshots: `rabbit-chat-{desktop,mobile}.png` (mocked interaction regression) and `rabbit-chat-live-webkit-{desktop,mobile}.png` (real two-turn API conversation). Both layouts were visually inspected.

Source: `src/easy/RabbitChat.tsx`, `src/easy/chat.ts`, `server/rabbit-chat.ts`, `server/rabbit_chat.py`. Existing mascot drag, stage animation and reduced-motion controls remain available.

Official API contract: https://api-docs.deepseek.com/api/create-chat-completion/

## Chat placement follow-up

The six desktop/mobile chat tests pass, including real dragging to four positions, non-overlap, hit testing, saved-position preservation and resizing to 320×500, 390×360 and 650×360. A separate WebKit smoke on desktop and mobile at 2× pixel density also passes, with screenshots `rabbit-chat-visible-webkit-{desktop,mobile}.png`. Build and formatting checks pass. This layout-only follow-up makes no model calls.

```bash
pnpm test:e2e chat.spec.ts
node scripts/smoke-rabbit-chat-layout.mjs
```

## Doudou and conversational follow-ups

The mascot is named **豆豆** in Chinese and **Doudou** in English, including its chat header, input, accessible labels, settings and model persona. Every completed answer offers two (at most three) related questions. Clicking one sends it as the next user message with the existing conversation history. The next completed answer replaces the suggestions; starting a reply or a new conversation clears them. Failed, stopped or incomplete replies do not show follow-ups.

The same DeepSeek call streams the answer and then generates a small `<doudou_questions>` JSON footer. The Python bridge removes this footer from answer text and emits a separate `suggestions` event. Split markers, fenced arrays, closing tags and malformed metadata are handled without an extra model request. If the model omits valid questions, two generic prompts for elaboration keep the conversation usable. Suggestions are bounded, deduplicated and rendered as text; they are never tools or instructions executed by the application. They follow the language selected when sending the message, while existing conversation text remains unchanged.

Validation for this change (2026-09-25):

- 50 Vitest tests and 5 Python bridge tests passed, including marker splits at every position, UTF-8 streaming, malformed metadata, completion ordering and interrupted responses.
- All 18 desktop/mobile chat and mascot regression scenarios passed. Multi-turn tests click a suggestion, verify conversation history, replace the next suggestions, switch to English, clear the chat and check error/stop behavior.
- TypeScript and production build passed. The pre-existing 3Dmol eval warning remains.
- Real DeepSeek testing initially encountered a fallback; metadata parsing was made tolerant of fenced arrays and trailing closing tags. The final three-call WebKit smoke passed: Chinese self-introduction as 豆豆, a clickable VHH follow-up with fresh related questions, and English basil-care suggestions for a casual topic. First visible text arrived in 1.01 seconds in this sample; latency varies. No page errors or changes to research storage occurred.
- Desktop/mobile screenshots: `rabbit-chat-live-webkit-{desktop,mobile}.png`; English: `doudou-followups-english.png`. These were visually checked with Doudou remaining visible outside the chat panel.
