from collections.abc import Sequence

from app.models.trade import Trade


def calculate_discipline_score(trades: Sequence[Trade]) -> int:
    score = 0
    for trade in trades:
        score += 10 if trade.rule_followed else -10

        emotion_name = (trade.emotion_name or "").upper()
        if emotion_name == "FOMO":
            score -= 5
        elif emotion_name == "REVENGE":
            score -= 5
        elif emotion_name == "HESITATION":
            score -= 2

    return score
