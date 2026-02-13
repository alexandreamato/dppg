"""Automatic diagnostic text generation in Portuguese."""

from typing import Dict, Optional, Tuple
from .classifier import classify_channel, classify_pump, tourniquet_comparison, VenousGrade
from ..analysis import bilateral_asymmetry, tourniquet_effect
from ..models import PPGParameters


# Label byte -> (limb name, has tourniquet)
CHANNEL_INFO = {
    0xDF: ("MIE", False),  # Membro Inferior Esquerdo, sem Tourniquet
    0xE0: ("MIE", True),   # Membro Inferior Esquerdo, com Tourniquet
    0xE1: ("MID", False),  # Membro Inferior Direito, sem Tourniquet
    0xE2: ("MID", True),   # Membro Inferior Direito, com Tourniquet
}

LIMB_FULL = {
    "MIE": "Membro inferior esquerdo",
    "MID": "Membro inferior direito",
}

GRADE_TEXT = {
    VenousGrade.NORMAL: "dentro da normalidade",
    VenousGrade.GRADE_I: "compatível com insuficiência venosa grau I",
    VenousGrade.GRADE_II: "compatível com insuficiência venosa grau II",
    VenousGrade.GRADE_III: "compatível com insuficiência venosa severa (grau III)",
}

# Shorter form for conclusions (avoids "com compatível com...")
GRADE_CONCLUSION = {
    VenousGrade.NORMAL: "função venosa adequada",
    VenousGrade.GRADE_I: "insuficiência venosa grau I",
    VenousGrade.GRADE_II: "insuficiência venosa grau II",
    VenousGrade.GRADE_III: "insuficiência venosa severa (grau III)",
}


def generate_diagnosis(channels: Dict[int, dict],
                       params_objects: Optional[Dict[int, 'PPGParameters']] = None) -> str:
    """Generate diagnostic text from channel parameters.

    Args:
        channels: dict mapping label_byte -> dict with keys:
            To, Th, Ti, Vo, Fo (float values)
        params_objects: optional dict mapping label_byte -> PPGParameters
            (used for tau, asymmetry, and tourniquet effect calculations)

    Returns:
        Diagnostic text in Portuguese.
    """
    paragraphs = []

    # Group by limb
    for limb in ["MIE", "MID"]:
        without_byte = 0xDF if limb == "MIE" else 0xE1
        with_byte = 0xE0 if limb == "MIE" else 0xE2

        ch_without = channels.get(without_byte)
        ch_with = channels.get(with_byte)

        if not ch_without and not ch_with:
            continue

        limb_full = LIMB_FULL[limb]
        lines = []
        lines.append(f"{limb_full} ({limb}):")

        # Without tourniquet
        if ch_without:
            To = ch_without["To"]
            Vo = ch_without["Vo"]
            grade = classify_channel(To)
            pump = classify_pump(Vo)

            lines.append(
                f"Tempo de reenchimento venoso (To) de {To:.1f} segundos, "
                f"{GRADE_TEXT[grade]}."
            )
            if pump == "normal":
                lines.append(
                    f"Potência da bomba muscular (Vo) de {Vo:.1f}%, adequada."
                )
            else:
                lines.append(
                    f"Potência da bomba muscular (Vo) de {Vo:.1f}%, reduzida (patológica)."
                )

        # Tau (exponential time constant)
        effective_byte = without_byte if ch_without else with_byte
        if params_objects:
            p_obj = params_objects.get(effective_byte)
            if p_obj and p_obj.tau is not None:
                lines.append(
                    f"Constante de tempo (\u03c4) de {p_obj.tau:.1f} segundos."
                )

        # With tourniquet comparison
        if ch_without and ch_with:
            To_s = ch_without["To"]
            To_t = ch_with["To"]
            comp = tourniquet_comparison(To_s, To_t)

            # Quantified tourniquet effect
            tq_pct = ""
            if params_objects:
                p_sem = params_objects.get(without_byte)
                p_com = params_objects.get(with_byte)
                if p_sem and p_com:
                    eff = tourniquet_effect(p_sem, p_com)
                    to_pct = eff.get("To_pct")
                    if to_pct is not None:
                        sign = "+" if to_pct >= 0 else ""
                        tq_pct = f" ({sign}{to_pct}%)"

            if comp == "melhora":
                lines.append(
                    f"Com garrote, melhora significativa "
                    f"(To = {To_t:.1f}s{tq_pct}), "
                    f"sugerindo componente de refluxo em sistema venoso superficial."
                )
            elif comp == "piora":
                lines.append(
                    f"Com garrote, piora do tempo de reenchimento "
                    f"(To = {To_t:.1f}s{tq_pct}), "
                    f"sugerindo insuficiência venosa profunda ou funcional."
                )
            else:
                lines.append(
                    f"Com garrote, sem alteração significativa "
                    f"(To = {To_t:.1f}s{tq_pct})."
                )
        elif ch_with and not ch_without:
            To_t = ch_with["To"]
            grade_t = classify_channel(To_t)
            lines.append(
                f"Com garrote: To de {To_t:.1f}s, {GRADE_TEXT[grade_t]}."
            )

        # Pump effectiveness
        effective_ch = ch_without or ch_with
        if effective_ch:
            Vo = effective_ch["Vo"]
            if Vo >= 3.0:
                lines.append("Bombeamento muscular eficaz.")
            else:
                lines.append("Bombeamento muscular insuficiente.")

        paragraphs.append(" ".join(lines))

    # Bilateral asymmetry
    if params_objects:
        p_mie = params_objects.get(0xDF)
        p_mid = params_objects.get(0xE1)
        if p_mie and p_mid:
            asym = bilateral_asymmetry(p_mie, p_mid)
            sig_parts = []
            for attr, pct in asym.items():
                if pct > 20:
                    label = "\u03c4" if attr == "tau" else attr
                    sig_parts.append(f"{label}: {pct}%")
            if sig_parts:
                paragraphs.append(
                    f"Assimetria significativa entre membros ({', '.join(sig_parts)})."
                )

    # Conclusion
    conclusion_parts = []
    for limb in ["MIE", "MID"]:
        without_byte = 0xDF if limb == "MIE" else 0xE1
        with_byte = 0xE0 if limb == "MIE" else 0xE2
        ch = channels.get(without_byte) or channels.get(with_byte)
        if not ch:
            continue
        To = ch["To"]
        grade = classify_channel(To)
        if grade == VenousGrade.NORMAL:
            conclusion_parts.append(f"função venosa adequada em {limb}")
        else:
            part = f"{GRADE_CONCLUSION[grade]} em {limb}"
            # Add tourniquet info if available
            ch_with = channels.get(with_byte)
            ch_without = channels.get(without_byte)
            if ch_without and ch_with:
                comp = tourniquet_comparison(ch_without["To"], ch_with["To"])
                if comp == "melhora":
                    part += ", com melhora ao garrote indicando refluxo superficial"
                elif comp == "piora":
                    part += ", com piora ao garrote indicando insuficiência profunda"
            conclusion_parts.append(part)

    if conclusion_parts:
        # Capitalize each sentence in the conclusion
        capitalized = [p[0].upper() + p[1:] for p in conclusion_parts]
        paragraphs.append("Conclusão: " + ". ".join(capitalized) + ".")

    return "\n\n".join(paragraphs)


def generate_classification_table(channels: Dict[int, dict]) -> list:
    """Generate classification summary for the report table.

    Returns list of dicts with keys: limb, tourniquet, grade, pump
    """
    rows = []
    for label_byte in [0xDF, 0xE0, 0xE1, 0xE2]:
        ch = channels.get(label_byte)
        if not ch:
            continue
        info = CHANNEL_INFO[label_byte]
        grade = classify_channel(ch["To"])
        pump = classify_pump(ch["Vo"])
        rows.append({
            "limb": info[0],
            "tourniquet": "c/ Tq" if info[1] else "s/ Tq",
            "grade": grade.value,
            "pump": "Adequada" if pump == "normal" else "Patológica",
        })
    return rows
