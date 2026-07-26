# ADR-URN: One shared source-URN derivation (option A)

**Status:** Accepted
**Date:** 2026-07-17
**Phase:** 0.5 (urn-join)

Capture (`write.resolve_identity`) and index (`index._urn_for`) each minted the
no-canonical-id source URN independently, and they disagreed: capture slugged the file
**stem** (`urn:<ns>:source:32016r0679`) while the indexer slugged the **full rel_path**,
extension and subdirectory included (`urn:<ns>:source:32016r0679-txt`). For any ordinary
folder carrying no KG sidecar the claims were therefore keyed on a URN the registry never
recorded, so `models_for_source(<registry urn>)` came back empty — the KG-sidecar path was
the only one that joined. We adopt **option A: a single shared derivation.** Both sides now
import the same symbol, `versum.urn.source_urn_for(stem, namespace)`, which slugs the file
**stem only** — no extension, no subdirectory — under one truncation rule and takes the
namespace as an explicit argument (kept domain-neutral for the Phase-1 parameterization).
Capture and index consequently produce byte-identical URNs for the same file, and the
general no-sidecar join resolves end to end (proven live in `tests/test_general_join.py`).
As part of this the domain-specific identity resolvers (CELEX, plus the general DOI/arXiv
schemes) moved out of the neutral `write.py` into `profile.source_identifiers`, so the core
names no domain token (guarded by `tests/test_dependency_inversion.py`).
