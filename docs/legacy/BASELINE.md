# Legacy repository baseline

[简体中文](BASELINE.zh-CN.md)

This is an audit record, not a migration authorization.

- Path inspected: `/root/autodl-tmp/Protein_design/easydesign`
- Upstream: `https://github.com/siyuanj/easydesign.git`
- Branch: `main`
- Commit: `bc67fb77fa32b95e609db6a0ca6400946f34f31d`
- Worktree at inspection: clean

Observed risks include duplicated package/UI trees, more than one target/hotspot
implementation, environment-specific execution mixed with domain logic, and legacy
backend naming that can obscure the actual predictor. Existing smoke examples are
evidence that some paths ran, not proof of production readiness or scientific
validity.

Potential ideas, tests, configs, or assets must receive a fresh technical, scientific,
provenance, and rights review. Nothing was copied into this clean repository.
