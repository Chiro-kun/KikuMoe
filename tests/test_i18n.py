from core.i18n import I18N, I18n


def test_i18n_languages_have_matching_keys():
    """Ensure that all supported languages have all required translation keys."""
    it_keys = set(I18N["it"].keys())
    en_keys = set(I18N["en"].keys())

    missing_in_en = it_keys - en_keys
    missing_in_it = en_keys - it_keys

    assert not missing_in_en, f"Keys present in Italian but missing in English: {missing_in_en}"
    assert not missing_in_it, f"Keys present in English but missing in Italian: {missing_in_it}"


def test_i18n_lookup_and_fallback():
    """Test standard translation lookup and fallback behavior."""
    i18n = I18n("it")
    assert i18n.t("status_stopped") == "Fermo."

    i18n.set_lang("en")
    assert i18n.t("status_stopped") == "Stopped."

    # Non-existent key returns key itself
    assert i18n.t("non_existent_key_xyz") == "non_existent_key_xyz"
