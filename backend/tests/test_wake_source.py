"""What woke the box: wakeup counters read from a fake /sys/class/wakeup."""
from backend.services import wake_source


def _source(root, key, name, count, product=None):
    entry = root / key
    (entry / "device").mkdir(parents=True)
    (entry / "name").write_text(f"{name}\n")
    (entry / "event_count").write_text(f"{count}\n")
    if product:
        (entry / "device" / "product").write_text(f"{product}\n")


def test_the_source_whose_count_moved_is_named(tmp_path, caplog):
    _source(tmp_path, "wakeup51", "3-3", 4, product="Bluetooth wireless interface")
    _source(tmp_path, "wakeup32", "LNXPWRBN:00", 0)
    caplog.set_level("INFO")
    wake_source.remember(tmp_path)
    (tmp_path / "wakeup51" / "event_count").write_text("5\n")
    sources = wake_source.report(tmp_path, irq_path=tmp_path / "no-irq")
    assert sources == ["3-3 (Bluetooth wireless interface) +1"]
    assert "woken by 3-3 (Bluetooth wireless interface) +1" in caplog.text


def test_a_source_that_appeared_after_the_sleep_is_not_blamed():
    before = {"wakeup1": ("LNXPWRBN:00", 2)}
    after = {"wakeup1": ("LNXPWRBN:00", 3), "wakeup60": ("3-4", 9)}
    assert wake_source.moved(before, after) == ["LNXPWRBN:00 +1"]


def test_a_wake_without_a_snapshot_says_so(tmp_path, caplog):
    caplog.set_level("INFO")
    wake_source._before = None
    assert wake_source.report(tmp_path) == []
    assert "no snapshot" in caplog.text
