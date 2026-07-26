# Universal graph–solver interoperability

Versum implements the vendor-neutral `reasoning.interop` 1.0 wire contract in
`versum.interop`. It is one graph implementation, not a privileged protocol peer: any graph,
corpus, retriever, or generator can produce the same JSON-safe records, and any verifier can
consume them.

Versum emits opaque `EvidenceRef` values and untrusted `Candidate` records. A verifier returns
a `ReasoningResult`; Versum alone decides whether and how that result is retained. Search and
similarity scores stay in `rank_metadata` and are never truth or proof weight.

The `Verifier` behavior port in `versum.ports` supports in-process adapters, JSON files,
queues, or services. Versum core imports no solver. Capability and schema negotiation happens
through `ProtocolManifest`, and implementation-specific data belongs only in `extensions`.
