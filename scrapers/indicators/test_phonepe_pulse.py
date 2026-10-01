"""Pure-function tests for phonepe_pulse.py (no network, no DB). Run: python scrapers/indicators/test_phonepe_pulse.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scrapers.indicators import phonepe_pulse as pp

# Trimmed real samples (Telangana, 2024-Q4)
MAP_TXN = {"success": True, "data": {"hoverDataList": [
    {"name": "hyderabad district", "metric": [{"type": "TOTAL", "count": 497079422, "amount": 6.01741671786E11}]},
    {"name": "warangal rural district", "metric": [{"type": "TOTAL", "count": 10, "amount": 20.5}]}]}}
MAP_USER = {"data": {"hoverData": {"nalgonda district": {"registeredUsers": 856881, "appOpens": 47490049},
                                   "narayanpet district": {"registeredUsers": 5, "appOpens": 0}}}}
TOP = {"data": {"states": None, "districts": [], "pincodes": [
    {"entityName": "500081", "metric": {"type": "TOTAL", "count": 67246969, "amount": 72596118114.0}}]}}
AGG = {"data": {"transactionData": [
    {"name": "Peer-to-peer payments", "paymentInstruments": [{"type": "TOTAL", "count": 905771898, "amount": 2.97837928469E12}]},
    {"name": "Recharge & bill payments", "paymentInstruments": [{"type": "TOTAL", "count": 1, "amount": 2.0}]}]}}


def test_parsers():
    assert pp.parse_map_txn(MAP_TXN)[0] == ("hyderabad district", 497079422, 6.01741671786E11)
    assert len(pp.parse_map_txn(MAP_TXN)) == 2
    assert ("nalgonda district", 856881, 47490049) in pp.parse_map_user(MAP_USER)
    assert pp.parse_top_pincodes(TOP) == [("500081", 67246969, 72596118114.0)]
    assert pp.parse_agg_txn(AGG)[0][0] == "Peer-to-peer payments"


def test_slugs_and_periods():
    assert pp.district_slug("Hyderabad District") == "hyderabad"
    assert pp.district_slug("jaya shankar bhalupally district") == "jaya-shankar-bhalupally"
    assert pp.slug("Recharge & bill payments") == "recharge-and-bill-payments"
    assert pp.period_of(2024, 4) == "2024-Q4"


def test_path_filter():
    tree = [{"path": "data/map/transaction/hover/country/india/state/telangana/2024/4.json", "sha": "a"},
            {"path": "data/map/transaction/hover/country/india/state/kerala/2024/4.json", "sha": "b"},
            {"path": "data/top/transaction/country/india/2024/4.json", "sha": "c"},
            {"path": "data/map/insurance/country/india/2024/4.json", "sha": "d"},
            {"path": "data/map/transaction/hover/country/india/2017/4.json", "sha": "e"}]
    got = pp.select_files(tree, 2018, "telangana")
    assert [f["sha"] for f in got] == ["a"]
    assert len(pp.select_files(tree, 2018, None)) == 2


def test_blob_sha():
    assert pp.git_blob_sha(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"   # git's empty blob


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
