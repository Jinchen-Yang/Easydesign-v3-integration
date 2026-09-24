# 05 — Acceptance Checklist

Codex should not return control until all P0 items pass.

## P0 — Must pass

- [ ] `pnpm install` / equivalent succeeds
- [ ] one documented dev command starts the app
- [ ] browser opens to a white EasyDesign landing page
- [ ] user can submit the default lysozyme/VHH prompt
- [ ] Workbench opens without full page reload
- [ ] left column shows Goal / Target / Site / Design / Pilot / Scale / Candidates
- [ ] current phase and subtasks update correctly
- [ ] center column renders user messages, agent summaries, tool cards and specialist states
- [ ] no raw chain-of-thought is displayed
- [ ] right panel changes for every phase
- [ ] Target/Site includes a functioning structure viewer OR a robust viewer adapter with graceful fallback
- [ ] Site A/B/C click changes selection/highlight state
- [ ] Approve Target advances
- [ ] Approve Site B advances
- [ ] Approve Design advances
- [ ] Pilot always produces 8 demo candidates
- [ ] Promote advances
- [ ] Scale simulates 24 candidates only
- [ ] Candidates displays 6 finalists
- [ ] Finalize panel reaches completed state
- [ ] Replay demo works
- [ ] Reset demo works
- [ ] refresh does not corrupt app state
- [ ] no real BoltzGen/AFO/Protenix/GPU job is launched
- [ ] all simulated scientific outputs carry a Demo / Simulated marker
- [ ] page is visually light, white, restrained and consistent with the supplied Latent-Y references
- [ ] no Latent-Y logo or proprietary copy is reused
- [ ] existing scientific backend is not refactored

## P1 — Strongly preferred

- [ ] tool cards expand/collapse
- [ ] selected sentence/card can focus related right-panel content
- [ ] Site selection updates structure
- [ ] candidate selection updates structure
- [ ] keyboard focus states are usable
- [ ] 1366×768 and 1440×900 both work
- [ ] screenshot regression or Playwright smoke test exists
- [ ] adapter boundary is covered by small tests

## Delivery from Codex

Return:
1. exact path of new source project
2. commands to install / run / test
3. short architecture note
4. screenshots of landing, Site, Pilot, Candidates
5. tests run and results
6. any remaining P1 gaps

Do not return merely because of a recoverable build/UI bug. Fix and continue until P0 closes.
