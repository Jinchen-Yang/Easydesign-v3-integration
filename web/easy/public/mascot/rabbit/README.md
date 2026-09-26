# EasyDesign rabbit assets

Seven original user-supplied JPGs are preserved byte-for-byte under `originals/`, including their original attribution marks. `manifest.json` maps their source filenames and SHA-256 hashes.

`rabbit-mascot.png` is a separate transparent RGBA derivative of `originals/01-welcome.jpg`, produced on 2026-09-25 with the built-in image_gen tool. Original files were not edited. The web companion uses this PNG; the album exposes all seven original images for viewing and download.

## Exact generation prompt

Edit the supplied image into a production web mascot asset. Isolate ONLY the adorable seated golden lop-eared rabbit scientist holding the sign that reads exactly 'EasyDesign'. Preserve this reference character faithfully: full body including both feet and drooping ears, fluffy golden fur, cream muzzle and belly, large glossy dark brown eyes, white lab coat with teal pen, cute calm expression, cream sign and its exact lettering, illustrated sticker-like rendering and dark brown outlines. Remove ALL the laboratory background, DNA, laptop, glassware, scenery, floor and cast shadow. Output one centered full-body rabbit on a truly transparent RGBA background (real alpha transparency, NOT a painted checkerboard or white backdrop). Remove the broad white sticker halo around the outer silhouette; retain clean smooth antialiased edges. Keep generous small clear padding, approximately 6 percent on each edge, without clipping ears or feet. No other text, no new logos, no new objects. Deliver a single square PNG suitable to display as a floating 130px website pet.

## Integration

- Component: `src/easy/RabbitMascot.tsx`; motion and layout: `src/easy/rabbit-mascot.css`.
- Chinese by default; all controls follow the page language switch.
- Stage-specific head/ear/paw motion and larger hops; the original PNG is continuously deformed in a small local WebGL canvas to avoid cut seams. It pauses in a hidden tab and defaults to system reduced-motion preferences; explicit playback overrides only the bunny.
- Drag with a mouse/touch, or use arrow keys while focused. Normalized position is saved and clamped to the viewport. Click to chat; use the settings icon for pause/resume, position reset, album, and minimize; a small static bunny restores it.
- Preferences use `easydesign-rabbit-v1` localStorage only. No research state, model APIs, scientific jobs, or Pro UI changes.
- UI assets are served locally; there are no external image requests. The source PNG and originals stay unchanged. WebGL failure uses the original PNG with scene animation; image failure uses a rabbit glyph. Controls remain available.
- Suzhou2 source snapshot: `/data/easydesign-easy-ui-20260925/`; assets: `public/mascot/rabbit/`. This snapshot does not start a new server service.
