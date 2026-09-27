# EasyDesign Easy

This directory is the canonical, self-contained Easy edition of the
EasyDesign product UI. The default build connects to the same authenticated
Product API and scientific workflow as the Pro Workbench. It is served at
`/easy/`; the Pro Workbench remains at `/`.

The historical deterministic preview is still available explicitly with
`/easy/?mode=demo`. Demo data never appear in the default live application.

A separate, bilingual white/violet frontend preview: target input → one-click demo → progress and structure → six example finalists. The main design surface stays free of research traces; the corner rabbit offers optional quick chat. The existing Pro worktree and its stored projects are unchanged.

The default language is **简体中文**. Use **中文 / EN** at the upper right to switch; the selected language is saved locally. Form inputs, saved designs and demo progress are preserved. Body text and form controls use 16px, with secondary labels at least 14px and a neutral text palette.

The live application creates and resumes native projects, renders
checksum-bound target/candidate structures, shows the real Scientist Gates,
and exposes the server-owned simulated lab-order flow only after Gate 5. It
does not parse model prose, invent scientific state, or auto-approve a Gate.
The optional demo renders the legacy lysozyme/VHH fixture and never invokes
the backend.

The small rabbit in the lower corner is the EasyDesign mascot. Drag it with a mouse or touch to reposition it; the position survives reload and stays within a resized viewport. Click it to chat. Use the small settings icon to pause/resume, reset its position, browse the seven original pictures or minimize it. Its gestures follow the current demo stage, including completed-stage review. The small static rabbit brings it back. It follows system reduced-motion settings by default (with an explicit bunny-only playback option) and pauses in background tabs. The original rabbit artwork is rendered as a continuous deformable mesh, keeping the face and ears connected while they move. Its preferences are saved separately from research data.

Original pictures, the transparent mascot and its generation prompt are in
[public/mascot/rabbit](public/mascot/rabbit/README.md). They are now part of
this repository; the product build has no dependency on the former standalone
Easy UI directory.

## Run

Requires Node.js 22+ and pnpm 11.19.0.

```bash
cd web/easy
pnpm install --frozen-lockfile
pnpm build
```

Start the repository Product service and open `/easy/`. The service uses the
same owner-only access token and same-origin session as Pro. For isolated
visual development, `pnpm dev` still serves port 13190; append `?mode=demo`
when no Product API is present.

If this Mac cannot find Node or pnpm, first run:

```bash
export PATH="/Users/knitua/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/knitua/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH"
```

The Pro edition is maintained in the same repository at `web/workbench/`.

## Input support

| Input               | Frontend intake                                                    |
| ------------------- | ------------------------------------------------------------------ |
| Description         | Target and design goal in plain text                               |
| Protein / Gene name | Name plus organism                                                 |
| UniProt ID          | Accession format validation                                        |
| PDB ID              | Identifier format validation                                       |
| Structure file      | PDB/mmCIF file and coordinate-record check                         |
| Sequence / FASTA    | Paste or upload one canonical protein sequence                     |
| PyMOL session       | Select a PSE file; no execution or scientific validation           |
| Existing target     | Target Bundle JSON with a target_id; dependencies are not resolved |

Files are limited to 2 MiB. Intake processing stays in the browser. When you send a rabbit chat message, the selected design goal (up to 1,200 characters), viewed stage and status are sent with the conversation to DeepSeek. Raw files and sequences are not attached. Only text, normalized FASTA, file name/size and demo progress are persisted; original structure/PSE/bundle bytes are not saved or uploaded. Non-description inputs have a default VHH design goal, editable in **Options**. These checks do not establish scientific validity or imply that all eight inputs are connected to a live API.

## Verify

```bash
pnpm test
pnpm build
pnpm exec playwright install chromium  # first installation only
pnpm test:e2e
pnpm test:production                 # after build; port 13191 must be free
pnpm format:check
```

`pnpm preview` serves the built app at `http://127.0.0.1:13191/`. Browser tests cover desktop and mobile; outside CI they can reuse the dev server on 13190. Use a free port before running with `CI=1`.

## Architecture and storage

- `src/easy/EasyLiveApp.tsx`: live Product API workflow, gates, structures,
  candidates and Gate-5 simulation.
- `src/easy/EasyProductAdapter.ts`: typed Product API transport with bounded,
  serial polling and request idempotency.
- `src/easy/EasyApp.tsx`: optional deterministic demo.
- `src/easy/contracts.ts`: EasyAdapter boundary and product data types.
- `src/easy/EasyDemoAdapter.ts`: finite demo animation and isolated browser persistence; no scheduler or scientific authority.
- `src/easy/inputs.ts`: lightweight intake checks.
- `src/easy/easy.css`: responsive Easy styling.
- `src/easy/i18n.ts`: Chinese/English UI messages and language preference. Stored user content and exported data remain in their original language.
- `src/easy/RabbitMascot.tsx`: pointer/keyboard positioning, isolated preferences, bilingual controls and original-image album. `RabbitActor.tsx` / `rabbit-mascot.css` define six stage gestures and props; `RabbitArt.tsx` continuously deforms the original PNG, with a static-art fallback when WebGL is unavailable. Only `easydesign-rabbit-v1` preferences are stored; no adapter calls.
- `src/easy/RabbitChat.tsx` / `chat.ts`: bilingual, content-only Doudou chat.
  The live Product service exposes the authenticated same-origin
  `/api/rabbit/chat` bridge with bounded concurrency and request rate. It has no
  design adapter, tools or Scientist Gate authority.
- Existing brand, molecular viewer and fixture assets are reused without modifying Pro components. The bundled 1MEL structure works offline; viewer failure does not stop the demo.

Easy uses its own `easydesign-easy-preview-v1` localStorage key on port 13190, plus `easydesign-easy-locale-v1` for the optional language preference. Pro keys are never read or written. Invalid stored data is left untouched, and storage failure falls back to the current tab's memory. Closing the browser pauses the demo animation; reopening resumes it, with no remote job implied.

Both UIs preserve native scientific decision authority. Easy changes the
presentation, not the runtime contract or Gate policy.

See [Easy implementation report and screenshots](docs/easy/README.md), [historical Pro README](docs/PRO_README.md), and [third-party notices](docs/THIRD_PARTY.md).
