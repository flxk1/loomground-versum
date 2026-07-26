<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 flxk1 -->
# Release definition of done

A checklist a repository must satisfy before it is release-grade. Written to be
repo-agnostic: the same checklist applies to this repository and to sibling
repositories in the same ecosystem, so it names no repository by name and no items
specific to any one of them.

## 1. Package metadata

- [ ] The build file declares a homepage, a repository URL, and an issue tracker URL.
- [ ] A `readme` field points at the repository's README.
- [ ] `authors` names the human author(s). Generative-AI tools that assisted are
      acknowledged in prose (NOTICE, README), never listed as an author.

## 2. Versioning and the version-coherence gate

- [ ] Every genuinely stale version string (a bundled grammar's own metadata, a
      companion tool's manifest, and similar) is bumped to match the current release.
- [ ] A checker — run in CI on every push and pull request — asserts that the
      package/release version is identical everywhere it is declared (build
      metadata, any machine-readable summary card, any conformance or compatibility
      manifest, any bundled sub-artifact that carries its own version field).
- [ ] If the repository has more than one genuinely independent version axis (for
      example: the package/release version, a frozen contract/protocol version, and a
      companion plugin/distribution version), the gate keeps each axis internally
      consistent but never asserts equality *across* axes. State the axes explicitly,
      in a comment or docstring, so a future contributor does not "fix" the deliberate
      difference.
- [ ] The gate is wired into CI, not just runnable by hand.

## 3. Licensing

- [ ] The REUSE (or equivalent SPDX) package name matches the repository's actual
      package name.
- [ ] `reuse lint` (or the project's equivalent license-compliance check) passes.
- [ ] Every new file this checklist adds carries a license header, in whichever form
      (inline comment, or a REUSE.toml annotation for formats with no comment syntax)
      the rest of the repository already uses.

## 4. Changelog

- [ ] A `CHANGELOG.md` exists in keep-a-changelog style, with an `## [Unreleased]`
      section and a dated entry for the current release summarizing what that release
      actually contains, in the repository's own vocabulary (not generic filler).
- [ ] Any known, load-bearing limitation of the current release is stated in that
      entry, not left to be discovered later.

## 5. CI gates

- [ ] Every third-party GitHub Action referenced by `uses:` is pinned to a full commit
      SHA, with a trailing comment naming the tag it corresponds to (so a reviewer can
      still tell what version is pinned).
- [ ] Every ad hoc tool invocation in CI (an `npx` package, a `pip install` of a tool
      not already pinned by a lockfile) names an explicit version.
- [ ] All pre-existing CI gates (whatever domain-specific consistency, drift, or
      discipline checks the repository already had) keep passing — hardening supply
      chain and versioning must not silently drop coverage.

## 6. Governance files

- [ ] Dependabot (or equivalent) is configured for both the CI-action ecosystem and
      the language's package ecosystem, on a low-noise (e.g. weekly, grouped) schedule.
- [ ] The RVND governance lane owns automated release review for the repository,
      with stricter checks for normative/contract-bearing paths, package metadata,
      and release automation. No human-review dependency is implied.
- [ ] A `SECURITY.md` states the supported-versions policy and how to report a
      vulnerability privately.
- [ ] Release automation configuration (for example, a Release-Please config and
      manifest) matches the repository's actual package name and tagging scheme —
      copy conventions from a sibling repository only where they actually apply; do
      not carry over a sibling's repo-specific quirks (a component-prefixed tag
      scheme, a different release-type) that do not fit this repository.
- [ ] A release workflow creates the release pull request and, once merged, publishes
      using Trusted Publishing (OIDC) to the package index, gated by a protected
      environment — never a long-lived credential committed to the repository.

## 7. Standalone documentation

- [ ] A `RELEASING.md` at the repository root is self-contained: a reader does not
      need any other document open to understand the versioning rule(s), the release
      pull-request flow, and how publishing is authorized.
- [ ] This checklist itself is present (`docs/RELEASE-DoD.md` or equivalent),
      repository-agnostic, and safe to copy into sibling repositories unchanged.

## 8. Installability

- [ ] The package builds (source distribution and wheel) from a clean checkout.
- [ ] The built wheel installs into a fresh environment and the package's public
      entry points (module import, declared version, or CLI, whichever the package
      exposes) work as expected.

## 9. Universality (third-party implementability)

A repository's interop contracts (companion vocabularies, wire schemas, and the
conformance vectors that define what conforming means) are checked for
implementability, not merely published and left on trust.

- [ ] For each such contract, the published artifact set (schema, any profile or
      choice-set document, and the conformance vectors) is sufficient on its own: a
      party with no access to this repository's product code can implement the
      contract from those files alone.
- [ ] A reference implementation proves this: it imports no product package (the
      language's own package, a solver, a store, or any other first-party
      implementation) — only the standard library and, where genuinely needed, a
      widely available third-party library such as a schema validator. It derives
      the schema, profile, and vectors it checks against by loading the published
      files, never by copying constants out of product source.
- [ ] The reference implementation runs both directions the contract defines,
      where both exist: a consumer side that accepts or rejects a candidate record,
      and a producer side that constructs one — the producer's output round-trips
      through the consumer's acceptance check.
- [ ] The reference implementation passes every published conformance vector: every
      vector marked valid is accepted, every vector marked invalid is rejected.
- [ ] The no-product-import property is itself enforced by a checker (an AST scan
      or equivalent), not left to reviewer attention — the reference's isolation
      would otherwise silently erode the first time someone "helpfully" imports a
      product convenience function into it.
- [ ] CI runs both the conformance check and the import-isolation check on every
      push and pull request; neither is a local-only or manual step.
- [ ] Where a repository's own adapters *select* among implementations of a
      contract (rather than merely implementing one), that selection logic is
      neutral: it carries no vendor-name special-casing, no hardcoded preference
      for a particular product's implementation over another conforming one. The
      selection criterion is the contract itself — conformance — not identity.
