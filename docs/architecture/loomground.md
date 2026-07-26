# Loomground interoperability

Versum's graph model remains language- and runtime-independent. Its Loomground
interchange boundary uses the `loomground-governance` adoption kit as a required runtime
dependency. The distribution resolves that kit from a tagged release of
[`flxk1/loomground-governance`](https://github.com/flxk1/loomground-governance). Setting
`LOOMGROUND_SOURCE` to a local checkout is a development and verification fallback. No
Loomground evaluator or solver runtime is required.

`versum.loomground` reads language identity and artifacts from the neutral
`loomground-governance` package. It can create a `reasoning.interop` request for
any conforming runtime and preserve the runtime's canonical observation. It
does not parse, validate, evaluate, authorize, or map that observation to graph
truth.

This separation allows Solver, RVND, and other Loomground runtimes to be used
without making any one of them a dependency of Versum. Domain grounding is a
separate explicit step so that a runtime decision is never silently promoted
to a confirmed Versum claim.
