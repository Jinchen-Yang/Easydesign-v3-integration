# Contributing

[简体中文](CONTRIBUTING.zh-CN.md)

## Before changing code

Read the Project Charter, the relevant stage `README.md` and `CONTRACT.md`,
`TODO.md`, and `TODO_NOW.md`. If a change alters a stage boundary, artifact,
status rule, backend capability, or compatibility promise, add an ADR first.

## Workflow

1. Start from a verifiable `main` and use a short-lived branch.
2. Keep one coherent purpose per change and use Conventional Commits.
3. Put domain logic under `src/easydesign/`; scripts may only invoke APIs.
4. Add tests proportional to risk: unit, adapter integration, then end-to-end.
5. Update English and Chinese normative documents together.
6. Update `TODO_NOW` for current work and append the completed event.
7. Run `make check`, `make test`, and, for packaging changes, `make build`.

## Review gates

A change is not mergeable when it introduces duplicated concepts, reads
undeclared upstream files, overwrites run artifacts, hides fallback behavior,
hardcodes a site-specific path in core logic, mislabels scientific evidence,
includes unreviewed third-party assets, or changes only one documentation language.

Scientific output must have an explicit result state. An engineering-complete run
with no candidate passing scientific filters is a valid negative result, not a
failed or successful binder claim.

## Dependencies and environments

The core targets Python 3.11 and remains lightweight. Heavy backends use adapters
and may execute in separate environments. Do not import optional heavy backend
libraries at package import time. Pin backend versions in execution profiles and
capture the resolved version in run provenance.

## Data and assets

Do not commit credentials, patient or confidential data, model weights, generated
run trees, or large datasets. Small fixtures must be redistributable and listed in
the provenance register. A link to an asset is not proof of a license.
