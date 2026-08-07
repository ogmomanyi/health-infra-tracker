from organisation_resolution.normalizer import normalize_name


def test_lowercase_conversion():
    assert normalize_name("WORLD HEALTH ORGANISATION") == (
        "world health organisation"
    )


def test_punctuation_removal():
    assert normalize_name("WHO (World Health Organisation)") == (
        "who world health organisation"
    )


def test_accent_removal():
    assert normalize_name("Université de Genève") == (
        "universite de geneve"
    )


def test_whitespace_cleanup():
    assert normalize_name("  World   Health   Organization  ") == (
        "world health organization"
    )