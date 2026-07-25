from disc_goblin.discovery import parse_blkid_label


def test_parse_blkid_label() -> None:
    output = '/dev/sr0: LABEL="THE_BATMAN" TYPE="udf"\n'

    assert parse_blkid_label(output) == "THE_BATMAN"
    assert parse_blkid_label('/dev/sr2: TYPE="udf"\n') == ""
