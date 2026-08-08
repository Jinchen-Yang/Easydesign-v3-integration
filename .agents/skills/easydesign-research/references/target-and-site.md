# Target and site preparation

Goal: reach one checksum-verified target and one explicitly approved binding-site foundation.

Start from `project status --json`. For a colored PSE, use `site propose --from-pse-colors`; verify
chain, numbering and red/blue/yellow A/B/C regions in the read-only viewer. For a structure plus text
residues, draft a strict site YAML, run `site propose --input`, and inspect the mapped coloring. With no
site information, run `site scan --method both`; keep SASA and ScanNet proposals separate and never
fuse their scores.

Resolve target identity, structure, chain, residue namespace and any UniProt ambiguity before site
approval. A successful scan is a proposal, not an approval. Approval must cite one proposal and creates
a new immutable foundation identity; never overwrite an older approved site.

Reject unknown chains, unmapped or duplicate residues, ambiguous numbering, checksum drift, and any
proposal that cannot be traced to the current target identity.
