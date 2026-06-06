from types import SimpleNamespace

from app.services.scoring import calculate_discipline_score


def _trade(rule_followed: bool, emotion_name: str):
    return SimpleNamespace(rule_followed=rule_followed, emotion_name=emotion_name)


def test_calculate_discipline_score_empty_list() -> None:
    assert calculate_discipline_score([]) == 0


def test_calculate_discipline_score_applies_rule_and_emotion_penalties() -> None:
    trades = [
        _trade(True, "CALM"),  # +10
        _trade(False, "FOMO"),  # -10 -5
        _trade(False, "HESITATION"),  # -10 -2
        _trade(True, "REVENGE"),  # +10 -5
    ]
    assert calculate_discipline_score(trades) == -12


def test_calculate_discipline_score_no_penalty_for_other_emotions() -> None:
    trades = [
        _trade(True, "OTHER"),  # +10
        _trade(False, "CALM"),  # -10
    ]
    assert calculate_discipline_score(trades) == 0
