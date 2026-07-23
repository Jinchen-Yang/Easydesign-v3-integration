# Instructions for coding agents

1. Read `PROJECT_CHARTER.md`, `TODO.md`, and `TODO_NOW.md` before work.
2. Treat `workflow/<stage>/CONTRACT.md` as the stage boundary.
3. Never copy code or assets from the legacy repository without an explicit,
   reviewed migration task and provenance record.
4. Keep scientific logic in `src/easydesign/`; scripts, future CLI, and UI are
   adapters only.
5. Do not infer stage outputs by scanning directories. Read declared manifests.
6. Never silently switch a backend, structure source, model, or filter profile.
7. Runs and attempts are immutable. Do not overwrite scientific artifacts.
8. Update tests, TODO state, contracts, and English/Chinese docs together.
9. Do not add a license, Git remote, model weight, secret, or third-party asset
   without explicit authorization.
10. Report engineering validation and scientific validation separately.

See [中文说明](AGENTS.zh-CN.md).
