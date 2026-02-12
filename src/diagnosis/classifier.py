"""Classification of D-PPG results into diagnostic grades."""

from enum import Enum
from typing import Optional


class VenousGrade(Enum):
    NORMAL = "Normal"
    GRADE_I = "Grau I"
    GRADE_II = "Grau II"
    GRADE_III = "Grau III"


def classify_channel(To: float) -> VenousGrade:
    """Classify venous function based on To (refilling time).

    Criteria from VASOSCREEN standard:
        To > 25s  -> Normal
        20 < To <= 25s -> Grade I
        10 < To <= 20s -> Grade II
        To <= 10s -> Grade III
    """
    if To > 25:
        return VenousGrade.NORMAL
    elif To > 20:
        return VenousGrade.GRADE_I
    elif To > 10:
        return VenousGrade.GRADE_II
    else:
        return VenousGrade.GRADE_III


def classify_pump(Vo: float) -> str:
    """Classify muscular pump function based on Vo (pump power).

    Criteria:
        Vo >= 3% -> Normal
        Vo < 3%  -> Pathological
    """
    if Vo >= 3.0:
        return "normal"
    else:
        return "patológica"


def tourniquet_comparison(To_without: float, To_with: float) -> str:
    """Compare To values with and without tourniquet.

    Returns interpretation string:
    - Improvement with tourniquet -> superficial reflux
    - Worsening with tourniquet -> deep insufficiency
    - No significant change -> mixed or normal
    """
    diff = To_with - To_without
    pct = abs(diff / To_without) * 100 if To_without > 0 else 0

    if diff > 3 and pct > 15:
        return "melhora"
    elif diff < -3 and pct > 15:
        return "piora"
    else:
        return "sem_alteracao"
