from app.aggregator import Vote, aggregate
from app.executors.base import Prediction


def v(eid, w, value, conf=None, error=None):
    return Vote(eid, w, Prediction(value=value, confidence=conf, error=error))


def test_agreement_gives_verdict():
    r = aggregate([v("a", 1.0, "Зима", 0.8), v("b", 0.8, "Зима", 0.6)], 0.4, 0.7)
    assert r.value == "Зима"
    assert round(r.confidence, 3) == round((0.8 + 0.48) / 1.8, 3)
    assert r.agreement == "2/2"


def test_below_threshold_is_undetermined():
    r = aggregate([v("a", 1.0, "Лето", 0.48), v("b", 0.8, "Осень", 0.42), v("c", 0.8, "Лето", 0.39)], 0.4, 0.7)
    assert r.value is None and r.top_value == "Лето"


def test_abstain_stays_in_denominator_error_does_not():
    abstain = aggregate([v("a", 1.0, "Да", 0.9), v("b", 1.0, None)], 0.4, 0.7)
    failed = aggregate([v("a", 1.0, "Да", 0.9), v("b", 1.0, None, error="x")], 0.4, 0.7)
    assert round(abstain.confidence, 2) == 0.45
    assert round(failed.confidence, 2) == 0.9
    assert failed.agreement == "1/1"


def test_llm_without_probability_uses_default():
    r = aggregate([v("giga", 1.2, "Озеро", None)], 0.4, 0.7)
    assert r.value == "Озеро" and round(r.confidence, 2) == 0.7


def test_nothing_answered():
    assert aggregate([v("a", 1.0, None)], 0.4, 0.7).value is None
    assert aggregate([], 0.4, 0.7).agreement == "0/0"
