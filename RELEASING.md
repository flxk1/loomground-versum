# Releasing

This document is self-contained: read it without needing any other file to understand
how a release of this repository happens.

## Three independent version axes

This repository carries three version numbers that look similar but answer different
questions, and none of them should be collapsed into another:

1. **Package/release** — `pyproject.toml`'s `version`. This is the version PyPI
   installs and the version this document's release flow manages (currently `0.6.1`).
2. **Plugin/distribution** — `package.json` and `.claude-plugin/plugin.json`'s shared
   `version`. Versum deliberately *aligns* this axis with the package/release axis
   above (both are `0.6.1` today), unlike sibling repositories where the companion
   bundle's version is free to drift from the package version. `tests/test_manifest_coherence.py`
   gates that all three manifests — `pyproject.toml`, `package.json`, and
   `.claude-plugin/plugin.json` — agree on name and version, which is how the
   deliberate alignment choice is enforced.
3. **Contract/protocol** — the claim-axes version and the other frozen wire contracts
   named in [the specification](docs/reference/specification.md). This axis is frozen
   independently of the other two: it changes only when the governed contract itself
   changes, never as a side effect of a package release, and it is never asserted
   equal to either version above.

A release bumps axis 1 and, because of versum's alignment choice, axis 2 along with
it. It must never bump axis 3 as a side effect.

## Release flow (Release Please)

[Release Please](https://github.com/googleapis/release-please) turns conventional
commits on `main` into a reviewed release pull request:

- `fix:` increments the patch version.
- `feat:` increments the minor version.
- `feat!:` or a `BREAKING CHANGE:` footer increments the major version.
- `docs:`, `test:`, `ci:`, and `chore:` do not by themselves trigger a release.

Merging the generated release pull request updates `pyproject.toml` and
`CHANGELOG.md`, and creates a plain tag of the form `vX.Y.Z` (for example, the
existing `v0.6.1` tag) — no component prefix, because this repository publishes a
single package. `package.json` and `.claude-plugin/plugin.json` are bumped by hand
in the same pull request to keep the plugin/distribution axis aligned. Configuration
lives in `release-please-config.json` and `.release-please-manifest.json`; the
workflow is `.github/workflows/release-please.yml`.

Humans approve the version by approving the release pull request; automation only
performs the bookkeeping (computing the version, updating the changelog, creating the
tag).

## Publishing (PyPI Trusted Publishing)

Once the release pull request merges and the tag is created, the `publish` job in
`.github/workflows/release-please.yml` builds the source distribution and wheel once
and publishes them using
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — an OIDC
exchange (`id-token: write`) instead of a long-lived API token stored in the
repository. Publication runs only inside the protected `pypi` GitHub environment and
must pass the RVND governance lane before anything reaches PyPI.

The publish job installs `requirements-dev.txt` before installing the package itself.
`pyproject.toml` declares `loomground-governance>=0.8,<0.9` as an abstract, index-clean
range; `requirements-dev.txt` pins that same range to a tagged Git release so the
range is already satisfied when the range is not yet available from PyPI. This keeps
the wheel's own metadata index-clean (no Git URL in `METADATA`) while still letting
CI resolve and test the package today.

## Ecosystem release order (reference only — not required by this repository alone)

This engine depends on the Loomground language and is consumed as a standalone tool
and companion skill bundle. When a change here needs to reach the wider ecosystem,
the usual order is:

1. Merge and release any required `loomground-governance` change first, so the
   dependency range this repository declares is actually satisfiable from PyPI.
2. Merge the generated release pull request here and publish the new
   `loomground-versum` version.
3. Downstream consumers of this package pick up the new version through their own
   Dependabot pull requests, gated by their own test suites.

This repository's own release does not wait on step 3; it is listed here so a reader
understands what a release here sets in motion.

## Local verification before tagging

```
python -m pytest
reuse lint
python -m build
```

All of the above run in CI (`.github/workflows/ci.yml`) on every push and pull
request; a release pull request must pass them before it merges.
