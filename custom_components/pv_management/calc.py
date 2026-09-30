"""Reine Rechenlogik fuer PV Management.

Bewusst frei von Home-Assistant-Imports, damit die Funktionen ohne laufendes
HA getestet werden koennen (siehe tests/). Der Controller in __init__.py ruft
diese Funktionen auf, statt die Formeln selbst zu duplizieren.
"""

from __future__ import annotations


def total_savings(
    accumulated_self: float,
    accumulated_feed: float,
    offset: float,
    yearly_costs: float,
) -> float:
    """Gesamtersparnis = Eigenverbrauch-Ersparnis + Einspeise-Erloes + Offset - Jahreskosten."""
    return accumulated_self + accumulated_feed + offset - yearly_costs


def helper_offset(helper_value: float, accumulated: float, yearly_costs: float) -> float:
    """Offset, mit dem ``total_savings`` exakt dem Helper-Wert entspricht.

    Der Helper speichert die *Gesamtersparnis* (also bereits abzueglich der
    Jahreskosten). ``total_savings`` zieht die Jahreskosten selbst noch einmal
    ab - deshalb muessen sie hier wieder dazugezaehlt werden, sonst schrumpft
    die Ersparnis bei jedem Neustart um die bis dahin aufgelaufenen Kosten.

    Bei ``restore_from_helper`` ist der Helper die Wahrheit, darum wird der
    Offset nicht auf >= 0 geklemmt.
    """
    return helper_value - accumulated + yearly_costs
