# Easy frontend delivery — 2026-09-25

Source: `/Users/knitua/Documents/Easy Design/easy-ui-20260925`
Branch: `codex/easydesign-easy-ui-20260925`
Base: Pro commit `0189931e328a75e6b11f35ac9e9d30f1fd83cd7f`

## Product

Eight input choices lead into one automatic **demo** journey with a six-stage progress bar and interactive molecular structure. On completion, the page shows six example finalists and a result download. Pause/resume, saved drafts, searchable/filterable history and browser refresh recovery work without a backend. The original Pro worktree, branch, application source and project storage remain separate.

Following the copy review, the main page omits the marketing eyebrow, subtitle, three-step instruction strip, repeated input hints, run explanation, history description and footer slogan. Stage titles are short; the run view prioritizes the structure. Quick guide and expandable Input details retain explanations. The mobile Quick guide uses an accessible question-mark icon.

Completed stage labels are interactive: Target, Site, Design, Pilot and Scale show concise read-only summaries beside the corresponding reference view. Candidates returns to the final panel. Review selection is transient UI state; persisted run status and progress are unchanged, and unreached stages stay disabled.

## Bilingual readability update

Default Chinese, with a persistent 中文 / EN switch at the upper right. Navigation, forms, validation, progress, review summaries, history, help and structure-viewer controls are translated. User-entered text and stored run data are never rewritten by language switching. The shared viewer accepts an optional translator while retaining English as its default for the preserved Pro surface.

Form controls and body text are 16px; secondary labels are at least 14px. Neutral dark text replaces pale purple text; violet is reserved for actions and selection. Mobile navigation and phase controls wrap to maintain readable sizing. Browser checks measure computed text sizes and a minimum 4.5:1 contrast for the main secondary note on white.

## Architecture

`EasyApp → EasyAdapter → EasyDemoAdapter` separates the product view from a finite local animation. `inputs.ts` checks intake formats; it does not resolve identifiers or establish scientific validity. The existing molecular viewer and bundled PDB 1MEL are reused. No scientific kernels, stages, DSH runtime, compute queues or real approval semantics are changed.

The DemoAdapter records the original input but always returns the fixed lysozyme/VHH fixture. Pilot/scale/finalist counts are 8/24/6. Every candidate uses the same public reference structure, with illustrative scores. No generated structures, full synthesis-ready sequences, real model calls, GPU jobs or lab orders are produced.

Run/install/test commands are in the [root README](../../README.md). Easy dev/preview ports are 13190/13191; Pro remains on 13180. Easy browser persistence uses `easydesign-easy-preview-v1`. Original file bytes are neither retained nor uploaded; only file metadata and normalized FASTA/text are retained.

## Validation

- TypeScript and production build pass. The inherited 3Dmol package emits its existing eval warning.
- 42 unit tests pass, including 6 Easy intake/lifecycle tests and 36 inherited regressions.
- 8 browser tests pass across 1440×1000 desktop and 390×844 mobile: all eight inputs, invalid files, type switching, one-click completion, pause/reload/resume, candidate and chain selection, JSON download, drafts and history, viewer failure, keyboard dismissal of the guide, completed-stage navigation with unchanged stored run data, locked future stages, Chinese defaults, bilingual validation, persisted language selection, and unchanged drafts/results during switching.
- Production smoke passes: bundled reference renders, automatic completion and refresh recovery succeed, no page errors or external requests.
- Visual inspection covers the empty input page, progress view and results at desktop/mobile sizes.

## Screenshots

| View         | Desktop                                   | Mobile                                   |
| ------------ | ----------------------------------------- | ---------------------------------------- |
| Input        | [Screenshot](landing-desktop.png)         | [Screenshot](landing-mobile.png)         |
| Progress     | [Screenshot](running-desktop.png)         | [Screenshot](running-mobile.png)         |
| Results      | [Screenshot](results-desktop.png)         | [Screenshot](results-mobile.png)         |
| Stage review | [Screenshot](review-site-desktop.png)     | [Screenshot](review-site-mobile.png)     |
| File upload  | [Screenshot](structure-input-desktop.png) | [Screenshot](structure-input-mobile.png) |

## Remaining integration work

This is a usable frontend prototype, with **no live Easy scientific adapter**. Real identifier resolution, uploaded artifact persistence, PSE/Target Bundle dependency validation, job submission and authoritative approvals require future backend integration. A live adapter must preserve scientific decision gates even when their default presentation is concise. Browser history is device-local and has no account sync, server backup or cross-tab coordination. Open Pro currently targets the local development port.
