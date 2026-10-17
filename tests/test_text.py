from terminal_browser.core.text import display_width


def test_ascii_width_equals_length() -> None:
    assert display_width("abc") == 3


def test_cjk_wide_characters_are_two_cells_each() -> None:
    assert display_width("中文") == 4


def test_combining_mark_does_not_add_width() -> None:
    assert display_width("e\u0301") == display_width("e") == 1


def test_emoji_skin_tone_modifier_does_not_add_width() -> None:
    assert display_width("👍🏽") == display_width("👍") == 2


def test_regional_indicator_pair_is_four_cells() -> None:
    assert display_width("🇺🇸") == 4


def test_non_breaking_space_is_one_cell() -> None:
    assert display_width("\u00a0") == 1


def test_mixed_width_string_sums_each_scalar_policy() -> None:
    assert display_width("A中e\u0301👍🏽\u00a0") == 7


def test_empty_string_has_zero_width() -> None:
    assert display_width("") == 0


def test_stray_format_control_does_not_raise() -> None:
    # This should never happen in the real pipeline; it is a crash-safety check, not a policy statement.
    assert display_width("\u200b") == 0
