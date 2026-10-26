import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from signal_quality import evaluate_signal

def samples():
    sig={"time":90000,"confirmed":90900,"direction":"bullish","rvol":2.8}
    bars=[{"time":90000,"open":100,"close":92,"high":101,"low":90},
          {"time":90900,"open":92,"close":104,"high":106,"low":91}]
    five=[{"time":90900+i*300,"close":104} for i in range(3)]
    tape=[{"timestamp":90905,"side":"buy","size":200},
          {"timestamp":91775,"side":"sell","size":50}]
    return sig,bars,five,tape

def test_full_evidence_score():
    signal,bars,five,tape=samples()
    result=evaluate_signal(signal,bars,five,tape,connected_at=90800,now=91800)
    assert result["status"]=="complete"
    assert (result["score"],result["possible"])==(100,100)

def test_incomplete_tape_is_unavailable_not_neutral():
    signal,bars,five,tape=samples()
    result=evaluate_signal(signal,bars,five,tape,connected_at=91000,now=91800)
    assert result["status"]=="partial"
    assert (result["score"],result["possible"])==(70,70)
    assert result["components"][-1]["points"] is None

def test_reconnect_invalidates_flow_score():
    signal,bars,five,tape=samples()
    result=evaluate_signal(signal,bars,five,tape,connected_at=90800,disconnections=1,now=91800)
    assert result["possible"]==70

def test_missing_five_minute_data():
    signal,bars,five,tape=samples()
    result=evaluate_signal(signal,bars,[],tape,connected_at=90800,now=91800)
    assert result["possible"]==80
    assert result["components"][2]["available"] is False

def test_not_yet_confirmed():
    signal,bars,five,tape=samples()
    result=evaluate_signal(signal,bars,five,tape,connected_at=90800,now=91799)
    assert result["status"]=="pending"
