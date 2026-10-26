import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flow_interpretation import interpret_trade_window

def tape(start,end,side):
    return [
        {"timestamp":1,"price":start,"size":10,"side":side},
        {"timestamp":2,"price":end,"size":10,"side":side},
    ]

def test_four_cases():
    assert interpret_trade_window(tape(100,98,"sell"))["state"]=="selling_pressure"
    assert interpret_trade_window(tape(100,102,"sell"))["state"]=="buyer_absorption"
    assert interpret_trade_window(tape(100,102,"buy"))["state"]=="buying_pressure"
    assert interpret_trade_window(tape(100,98,"buy"))["state"]=="seller_absorption"

def test_flat_prices_and_missing_data():
    assert interpret_trade_window(tape(100,100,"sell"))["state"]=="buyer_absorption"
    assert interpret_trade_window([])["state"]=="insufficient"
