"""Negation-aware marker resolution (safety-critical regression guard).

``candidate_items`` scans a unit for every profile marker independently. Before this
fix, a positive-modal marker ("shall", "must", "may", "darf", "kann") that sits as a
PREFIX of a negated clause ("shall not", "darf nicht") ALSO matched on its own, emitting
a second, spurious claim that kept the bare positive modal and silently dropped the
negation — inverting the deontic force (a prohibition surfaced as an obligation or
permission). For a fail-closed legal grounding system this is the worst failure mode.

These tests prove, for every EN/DE negated-modal construction in the law-eu profile:
  * the bare positive-modal claim (predicate imposes/permits) is NEVER emitted, and
  * where the profile's marker table has a dedicated negated-form marker ("shall not",
    "must not", "may not", "darf nicht"), that correctly-typed prohibition claim IS
    emitted;
  * where it does not ("kann nicht" has no dedicated compound marker), the bare match is
    suppressed and no claim is emitted at all — failing closed rather than emitting a
    claim with an inverted deontic force.
plus a regression guard: the corresponding un-negated sentences are extracted unchanged.
"""
import versum.profiles  # noqa: F401 — register built-ins
from versum.io.extract import candidate_items, segment_units
from versum.profiles.law_eu import PROFILE as LAW

URN = "urn:t:negation-test"


def _claims(text):
    units = segment_units(text)
    return [it for u in units for it in candidate_items(u, URN, LAW)]


# ── negated constructions: never a bare-positive imposes/permits claim ────

def test_shall_not_yields_prohibition_never_bare_imposes():
    items = _claims("The processor shall not disclose personal data to third parties.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("imposes", "obliged") not in preds, preds
    assert ("prohibits", "prohibited") in preds, preds


def test_must_not_yields_prohibition_never_bare_imposes():
    items = _claims("The controller must not retain the data beyond the stated period.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("imposes", "obliged") not in preds, preds
    assert ("prohibits", "prohibited") in preds, preds


def test_may_not_yields_prohibition_never_bare_permits():
    items = _claims("The processor may not disclose personal data to third parties.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("permits", "permitted") not in preds, preds
    assert ("prohibits", "prohibited") in preds, preds


def test_darf_nicht_yields_prohibition_never_bare_permits():
    items = _claims("Der Verarbeiter darf nicht personenbezogene Daten weitergeben.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("permits", "permitted") not in preds, preds
    assert ("prohibits", "prohibited") in preds, preds


def test_kann_nicht_never_emits_bare_permits_even_with_no_dedicated_marker():
    # law-eu has no dedicated "kann nicht" compound marker (unlike "darf nicht"), so the
    # correct fail-closed outcome is: no bare-permits claim, and no claim at all — never a
    # wrong-polarity one.
    items = _claims("Der Verarbeiter kann nicht personenbezogene Daten weitergeben.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("permits", "permitted") not in preds, preds
    assert items == [], items


# ── regression guard: un-negated modal sentences are unaffected ───────────

def test_bare_shall_unaffected():
    items = _claims("The processor shall disclose personal data to the supervisory authority.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("imposes", "obliged") in preds, preds


def test_bare_must_unaffected():
    items = _claims("The controller must retain records of processing activities.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("imposes", "obliged") in preds, preds


def test_bare_may_unaffected():
    items = _claims("The processor may disclose personal data to the supervisory authority.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("permits", "permitted") in preds, preds


def test_bare_darf_unaffected():
    items = _claims("Der Verarbeiter darf personenbezogene Daten weitergeben.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("permits", "permitted") in preds, preds


def test_bare_kann_unaffected():
    items = _claims("Der Verarbeiter kann personenbezogene Daten weitergeben.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("permits", "permitted") in preds, preds


def test_shall_ensure_unaffected_by_negation_check():
    # "shall ensure" is itself a marker (imposes/obliged); it must still fire normally —
    # the negation-lookahead only suppresses matches immediately followed by a negation
    # token, and "ensure" is not one.
    items = _claims("The controller shall ensure appropriate technical measures are in place.")
    preds = [(it["predicate"], it["modality"]) for it in items]
    assert ("imposes", "obliged") in preds, preds
