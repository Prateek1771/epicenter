from api.smoke_falkordb import run_all


def test_falkordb_features(falkordb_url):
    failed = [(name, note) for name, ok, note in run_all(falkordb_url) if not ok]
    assert not failed, failed
