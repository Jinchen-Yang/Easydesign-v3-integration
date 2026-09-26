# Rabbit companion · 2026-09-25

The Easy frontend uses the original golden lop rabbit artwork, with larger stage-specific movements and mouse/touch dragging. The seven original JPGs and the transparent PNG are unchanged. The [asset record](../../public/mascot/rabbit/README.md) preserves the original generation prompt and file checksums.

## Interaction

- Drag with a mouse or touch. A five-pixel threshold separates dragging from clicking; releasing a drag does not open the menu. Pointer cancellation discards an unfinished move.
- The normalized position survives reload and adapts to viewport resizing. Arrow keys move a focused bunny; Shift makes larger moves. Reset returns it to the lower-right corner.
- Click to open [live rabbit chat](RABBIT_CHAT.md). The settings icon opens pause/resume, position reset, album and minimize. The small static bunny restores it. Controls and descriptions follow Chinese/English selection.
- System reduced-motion settings pause animation by default. Explicit playback opts in for this bunny only. Hidden tabs and dragging pause animation; research state is unchanged.

## Stage gestures

| Stage      | Gesture                                          |
| ---------- | ------------------------------------------------ |
| Idle       | Head tilt, ear sway, paw motion and a larger hop |
| Target     | Lean from side to side and sweep a magnifier     |
| Site       | Point at a pulsing site marker                   |
| Design     | Work at a laptop, with head/paw movement         |
| Pilot      | Move a pipette up and down and release a droplet |
| Scale      | Handle a row of samples with staggered movement  |
| Candidates | Larger celebratory jumps with floating stars     |

The gesture follows the selected run and displayed stage, including reviewing completed stages. These are illustrations of the demo, not claims of actual lab work or scientific validation.

## Rendering

`RabbitMascot.tsx` owns controls and isolated preferences. `RabbitActor.tsx` and `rabbit-mascot.css` define scenes and props. `RabbitArt.tsx` renders the unchanged PNG on a continuous mesh, deforming ears, head and paw without cut-out masks or exposed seams. Rendering is capped near 30 fps and 512 pixels per canvas side. The canvas stays in a bounded HTML layer; SVG props are separate, avoiding Safari compositing problems with a canvas inside `foreignObject`.

WebGL failure falls back to the original PNG while scene motion remains available. Image-load failure leaves a rabbit glyph and working controls. All artwork is local; animation makes no external calls. Optional rabbit chat calls DeepSeek as documented separately. Only `easydesign-rabbit-v1` mascot preferences are saved. There are no adapter calls, scientific jobs or Pro UI changes.

## Validation

- `pnpm test`: 42 passed.
- `pnpm build`: passed; existing 3Dmol eval warning unchanged.
- `pnpm test:e2e`: full 20-case desktop/mobile regression passed.
- After the Safari layer fix, `pnpm test:e2e mascot.spec.ts`: all 12 mascot cases passed again, including live stage tracking, completed-stage review, continuous rendering, mouse/touch positioning, persistence, reduced-motion handling and fallbacks.
- `pnpm test:production`: complete demo, reload and bundled structure passed without external requests or page errors after the layer fix.
- `pnpm test:mascot:webkit`: desktop and mobile WebKit at 2× pixel density passed the complete demo, stage gesture, drag and pause checks. Artwork remained bounded (182 px desktop / 142 px mobile), with no horizontal overflow or page errors. Both screenshots were visually inspected.

Run Safari-engine checks with the dev server on port 13190:

```bash
pnpm exec playwright install webkit  # first installation only
pnpm test:mascot:webkit
```

Stage screenshots are `rabbit-{target,site,design,pilot,scale,candidates}-{desktop,mobile}.png` in this directory. WebKit screenshots are `rabbit-webkit-{desktop,mobile}.png`.

## Locations

- Active Mac source: `/Users/knitua/Documents/Easy Design/easy-ui-20260925/`.
- Active preview: `http://127.0.0.1:13190/`.
- Complete source snapshot on Suzhou2: `/data/easydesign-easy-ui-20260925/`.
- Server assets: `/data/easydesign-easy-ui-20260925/public/mascot/rabbit/`.

The server copy contains full source, tests, lockfile, docs and assets, not a second running deployment. Existing backend and Pro repositories are unchanged.
