"""Size the concept-layer cleanup: how much of the 26,635 concept vocabulary is noise?

Four categories, each a defensible number the engine-owner can use to scope extraction work:
  1. morphology-collapse  — distinct concepts that merge once declensions are lemmatised.
  2. discourse/stopword    — the object is only function words / demonstrative filler.
  3. entity-name          — the object is a named place/org, not a mental model.
  4. hapax                — concepts grounded by exactly one source (over-minting tail).
"""
import glob, csv, re
from collections import defaultdict, Counter

BASE = "by-domain"; DROP = {"_archive", "unsorted"}
# concept_id -> object label; concept_id -> set(sources)
obj_of = {}; srcs = defaultdict(set)
for f in glob.glob(f"{BASE}/*/concepts.csv"):
    d = f.split("/")[1]
    if d in DROP:
        continue
    for row in csv.DictReader(open(f)):
        c = row["concept_id"]; u = row["canonical_urn"]
        if not c:
            continue
        lab = row.get("label", "")
        obj = lab.split(" — ")[0].strip().lower() if " — " in lab else ""
        obj_of[c] = obj; srcs[c].add(u)
N = len(obj_of)
print(f"total distinct concept-ids: {N}")

# ── 1. morphology collapse ──────────────────────────────────────
# crude German+English lemmatiser: lowercase, strip common declension endings per token.
_END = ("ungen", "enen", "eren", "erem", "eren", "en", "em", "er", "es", "e", "n", "s")
def lemma_tok(t):
    for suf in _END:
        if len(t) > len(suf) + 2 and t.endswith(suf):
            return t[: -len(suf)]
    return t
def norm(obj):
    toks = re.findall(r"[a-z0-9äöü]+", obj)
    return " ".join(lemma_tok(t) for t in toks)
groups = defaultdict(list)
for c, obj in obj_of.items():
    groups[norm(obj)].append(c)
merged = sum(len(v) - 1 for v in groups.values() if len(v) > 1)
print(f"1. morphology-collapse : {merged:5d} concepts merge into "
      f"{sum(1 for v in groups.values() if len(v)>1)} lemma-groups  "
      f"({merged/N:.1%} of vocabulary is a declension duplicate)")

# ── 2. discourse / stopword fragments ───────────────────────────
STOP = set("""der die das den dem des ein eine einen einem einer und oder aber auch
diesem diesen dieser dieses jenem jedem jeder jede jedes fall falle sinne grund grunde
grundlage basis zusammenhang hintergrund weiteres weitere rahmen bezug hinsicht art weise
auf aus bei mit nach von vor zu zum zur im in an als ob dass weil da so nur noch schon
the a an and or but of to in on at for with by this that these those such case ground
basis context regard respect view light term terms""".split())
def is_discourse(obj):
    toks = re.findall(r"[a-z0-9äöü]+", obj)
    return bool(toks) and all(t in STOP for t in toks)
discourse = [c for c, o in obj_of.items() if is_discourse(o)]
print(f"2. discourse/stopword  : {len(discourse):5d}  ({len(discourse)/N:.1%})  "
      f"e.g. {[obj_of[c] for c in discourse[:5]]}")

# ── 3. entity-name concepts (small gazetteer of obvious ones) ───
ENT = ["united states", "european union", "member states", "european commission",
       "european parliament", "united kingdom", "beck online", "germany", "france",
       "california", "supreme court", "artificial intelligence act", "general data"]
entity = [c for c, o in obj_of.items() if any(e in o for e in ENT)]
print(f"3. entity-name (sample gazetteer) : {len(entity):5d}  ({len(entity)/N:.1%})")

# ── 4. hapax (single-source) concepts ───────────────────────────
hapax = [c for c in obj_of if len(srcs[c]) == 1]
print(f"4. hapax (1 source)    : {len(hapax):5d}  ({len(hapax)/N:.1%})  — over-minting tail")

# combined unique-noise (union of 2+3, plus morphology as separate reducible mass)
noisy = set(discourse) | set(entity)
print(f"\ndiscourse∪entity noise : {len(noisy)} ({len(noisy)/N:.1%}); "
      f"morphology would additionally fold {merged/N:.1%}; "
      f"hapax tail {len(hapax)/N:.1%}")
print(f"back-of-envelope: a clean pass could shrink the vocabulary by roughly "
      f"{(len(noisy)+merged)/N:.0%} before touching the hapax tail.")
