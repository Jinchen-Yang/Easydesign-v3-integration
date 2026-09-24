# Third-party references and notices

The application uses React/ReactDOM, Lucide, 3Dmol.js and the Inter font. Installed top-level distribution licenses are copied into [licenses](licenses/). Exact dependency versions and transitive dependencies are recorded in `pnpm-lock.yaml`; their package distributions retain their own notices. This document does not assign a new license to the user's EasyDesign source.

The public reference molecule is [RCSB PDB 1MEL](https://www.rcsb.org/structure/1MEL). Original deposited files are bundled at `public/structures/1MEL.pdb` and `public/structures/1MEL.cif`; source URL and integrity/mapping metadata are in `public/structures/SOURCE.json`. They are reference data for the viewer, not generated candidate artifacts. The [3Dmol GLViewer documentation](https://3dmol.org/doc/GLViewer.html) was used for the rendering API.

The supplied Latent-Y screenshots were inspected only to understand visual hierarchy, spacing, restrained colors and panel layout. No screenshot, logo, proprietary copy or other Latent-Y asset is included in the production application. The complete original input pack is retained separately in the review archive so reviewers can compare requirements and implementation. Selected historical EasyDesign/DSH code was read as an adapter/integration reference; no generated historical UI bundle was modified or imported into the app.

Vite reports an upstream `eval` warning in 3Dmol 2.4.2's `makeFunction` helper for string callback support. This application does not pass string callbacks or use that helper. The warning is retained in the build log; a future production deployment with a strict CSP should explicitly validate the chosen 3Dmol distribution. This did not prevent the tested build or reference-viewer flow.
