#!/usr/bin/env python3
"""kg_query.py — read-only lens into the Loomground Versum KG (the cockpit's eyes).

Reads the canonical-keyed 5D+nD index at <kg_root>/by-domain/<domain>/
(claims.csv, fingerprints.json, materialize.json, concepts.csv), plus <kg_root>/libraries.json
and the migration's <kg_root>/_progress.json. Stdlib only, read-only, no network. Tolerant of
CSV text fields with embedded newlines / NUL bytes.

Commands:
  status                     health: libraries, domains, works, claims, reuse, concepts
  urn <canonical_urn>        provenance + 5D+nD fingerprint + sample claims for one source
  search <term> [--limit N]  sources whose claims mention <term> (claim-text lookup;
                             concept-level answers come from canon.json + the
                             by-domain concept tables once curation has run)
  libraries                  the configured libraries and their roots
Pass --kg-root or set KG_ROOT; defaults to this file's ../.. if that holds a by-domain/ dir.
"""
import sys, os, csv, json, glob, argparse, io
csv.field_size_limit(10**7)

def _rows(path):
    if not os.path.exists(path): return
    data = open(path, encoding="utf-8", errors="replace").read().replace("\0", "")
    yield from csv.DictReader(io.StringIO(data))

def _load(path, default=None):
    try: return json.load(open(path, encoding="utf-8"))
    except Exception: return default

def _domains(kg):
    return sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(kg, "by-domain", "*", "materialize.json")))

def cmd_status(kg):
    libs = _load(os.path.join(kg, "libraries.json"), {}) or {}
    prog = _load(os.path.join(kg, "_progress.json"), {}) or {}
    doms = _domains(kg)
    claims = works = concepts = 0
    per = []
    for d in doms:
        m = _load(os.path.join(kg, "by-domain", d, "materialize.json"), {}) or {}
        c = int(m.get("n_claims") or 0); w = int(m.get("n_fingerprints") or 0)
        claims += c; works += w; concepts += int(m.get("n_concepts") or 0)
        per.append((d, w, c))
    libstr = ", ".join(f"{k} -> {v.get('root_path')}" for k, v in libs.items()) or "(none)"
    print(f"KG root: {kg}")
    print(f"library:  {libstr}")
    print(f"domains: {len(doms)}   distinct works (canonical_urn): {works}   claims: {claims}")
    if prog:
        r, m2, s = prog.get("reuse", 0), prog.get("mint", 0), prog.get("sources", 0)
        print(f"provenance (last full run): {r} reused / {m2} minted of {s} source files "
              f"({r / max(1, s):.1%} reuse), errors={prog.get('errors', 0)}")
    # The canon (written by coordinate-identity curation) is authoritative for the
    # concept layer; materialize.json's n_concepts predates curation and stays 0.
    canon = _load(os.path.join(kg, "canon.json"), {}) or {}
    n_canon = int(canon.get("n_concepts") or 0)
    if n_canon:
        rate = canon.get("clustered_rate")
        extra = f"   (clustered_rate {rate:.1%})" if isinstance(rate, float) else ""
        print(f"concepts (mental-model layer): {n_canon}{extra}")
    else:
        print(f"concepts (mental-model layer): {concepts}" + ("" if concepts else "   (curation not run yet)"))
    print("top domains by claims:")
    for d, w, c in sorted(per, key=lambda x: -x[2])[:8]:
        print(f"  {c:>7} claims  {w:>4} works  {d}")

def cmd_urn(kg, urn):
    hits = []; dom = None
    for d in _domains(kg):
        for r in _rows(os.path.join(kg, "by-domain", d, "claims.csv")):
            if r.get("canonical_urn") == urn:
                hits.append(r); dom = d
        if hits: break
    if not hits:
        print(f"no claims found for {urn}"); return
    fp = (_load(os.path.join(kg, "by-domain", dom, "fingerprints.json"), {}) or {}).get(urn, {})
    print(f"{urn}   domain={dom}   claims={len(hits)}")
    if fp:
        print("5D:", {a: {k: c for k, c in h.items() if c} for a, h in fp.get("dim5", {}).items()})
        print("nD:", fp.get("nd"))
    print("sample claims:")
    for r in hits[:5]:
        print(f"  [{r.get('polarity')}/{r.get('predicate')}/{r.get('modality')}] "
              f"{(r.get('text', '') or '')[:90].replace(chr(10), ' ')}")

def cmd_search(kg, term, limit):
    t = (term or "").lower(); seen = {}
    for d in _domains(kg):
        for r in _rows(os.path.join(kg, "by-domain", d, "claims.csv")):
            if t in (r.get("text", "") or "").lower():
                u = r.get("canonical_urn", "")
                if u not in seen: seen[u] = [d, 0]
                seen[u][1] += 1
        if len(seen) >= limit: break
    print(f"sources mentioning '{term}': {len(seen)} (showing up to {limit})")
    for u, (d, n) in list(seen.items())[:limit]:
        print(f"  {n:>3}x  {d:<34} {u}")

def cmd_libraries(kg):
    p = os.path.join(kg, "libraries.json")
    print(open(p).read() if os.path.exists(p) else "(no libraries.json)")

def _resolve_kg(a):
    """kg_root from (in order): --kg-root, --config\'s kg_root, $LOOMGROUND_KG_CONFIG,
    ./loomground-kg.config.json, $KG_ROOT, else this file\'s ../.. . Device-neutral: no path
    is baked into the code; machine paths live only in the config."""
    if a.kg_root: return a.kg_root
    for cand in [a.config, os.environ.get("LOOMGROUND_KG_CONFIG"),
                 os.path.join(os.getcwd(), "loomground-kg.config.json")]:
        if not cand:
            continue
        if not os.path.exists(cand):
            if cand == a.config or cand == os.environ.get("LOOMGROUND_KG_CONFIG"):
                sys.exit(f"KG config not found: {cand}")
            continue
        try:
            config = json.load(open(cand, encoding="utf-8"))
            root = config["kg_root"]
            if not isinstance(root, str) or not root:
                raise ValueError("kg_root must be a non-empty string")
            return root
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            sys.exit(f"invalid KG config {cand}: {exc}")
    if os.environ.get("KG_ROOT"): return os.environ["KG_ROOT"]
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["status", "urn", "search", "libraries"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--kg-root", default="")
    ap.add_argument("--config", default=None)
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    if a.cmd in {"urn", "search"} and not a.arg:
        ap.error(f"{a.cmd} requires an argument")
    if a.limit < 1:
        ap.error("--limit must be at least 1")
    kg = _resolve_kg(a)
    if not os.path.isdir(os.path.join(kg, "by-domain")):
        sys.exit(f"KG not found at {kg} (expected a by-domain/ folder). Pass --kg-root.")
    {"status": lambda: cmd_status(kg), "urn": lambda: cmd_urn(kg, a.arg),
     "search": lambda: cmd_search(kg, a.arg, a.limit), "libraries": lambda: cmd_libraries(kg)}[a.cmd]()

if __name__ == "__main__":
    main()
