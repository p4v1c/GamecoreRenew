"""`out()` takes an explicit file= like print() does.

gamescrape.py reports "ScreenScraper returned nothing" with file=sys.stderr;
out() also set file itself, and print() raised TypeError. The scraper crashed
precisely on a box whose ScreenScraper credentials were wrong.
"""
import io

from backend.services.gamemedia import common


def test_an_explicit_file_is_honoured(monkeypatch):
    buf = io.StringIO()
    common.out("rejected", file=buf)
    assert buf.getvalue() == "rejected\n"


def test_the_default_stream_is_still_stdout(capsys):
    common.out("hello")
    assert capsys.readouterr().out == "hello\n"
