"""INI section surgery keeps every byte it was not asked to change."""
from backend.services.configgen.helpers.ini import set_key, set_section


def test_backslashes_in_a_section_survive_a_key_change():
    text = '[A]\nP = "a\\nb"\nW = "C:\\x"\nQ = 1\n'
    assert set_key(text, "A", "Q", "2")[0] == text.replace("Q = 1", "Q = 2")


def test_a_replaced_body_is_written_verbatim():
    assert set_section("[A]\nx = 1\n", "A", 'p = "\\1\\g<0>"\n') == '[A]\np = "\\1\\g<0>"\n'
