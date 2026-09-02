"""CJK marker-boundary: a \\w word-boundary can never fire between two space-less CJK chars,
so a CJK surface marker must match on real (unspaced) statute prose — while Latin markers keep
their word boundaries (no `might`⊂`mighty` regression)."""
from versum.io.extract import _marker_regex, _is_cjk


def _fires(marker, text):
    return bool(_marker_regex(marker).search(text))


def test_cjk_markers_fire_on_dense_unspaced_prose():
    assert _fires("してはならない", "何人も他人の著作物を無断で複製してはならない。")   # JP
    assert _fires("应当", "作者应当在作品上署名。")                                    # ZH
    assert _fires("不得", "任何人不得擅自复制他人作品。")                              # ZH short marker
    assert _fires("할 수 있다", "이용자는 해당 저작물을 이용할 수 있다.")               # KR


def test_kr_marker_fires_when_glued_to_preceding_verb_stem():
    # the exact case the profile's KNOWN-GAP comment flagged: "표시" + "하여야 한다" glued
    assert _fires("하여야 한다", "저작자는 성명을 표시하여야 한다.")


def test_latin_word_boundaries_still_enforced():
    assert not _fires("may", "maybe later")
    assert _fires("may", "the user may reproduce")
    assert not _fires("means", "this demeans nobody")
    assert not _fires("must", "mustard is yellow")
    assert not _fires("darf", "darfur region")   # German marker, Latin boundary


def test_is_cjk_classifier():
    assert _is_cjk("し") and _is_cjk("应") and _is_cjk("한")
    assert not _is_cjk("a") and not _is_cjk("ä") and not _is_cjk("1")
