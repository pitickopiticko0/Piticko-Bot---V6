import re


EMPTY_ANSWERS = {
    "-", "--", ".", "?", "nevím", "nevim", "netuším", "netusim",
    "nic", "n/a", "na", "idk",
}


def validate_advice_answers(
    request_type: str, answers: dict[str, str]
) -> list[str]:
    """Vrátí konkrétní chyby, které má uživatel ve formuláři opravit."""
    errors: list[str] = []

    for label, value in answers.items():
        normalized = " ".join(value.split())
        if len(normalized) < 5 or normalized.casefold() in EMPTY_ANSWERS:
            errors.append(f"**{label}** musí obsahovat konkrétní odpověď.")

    budget_labels = {
        "build": "Rozpočet",
        "upgrade": "Rozpočet a termín",
    }
    budget_label = budget_labels.get(request_type)
    if budget_label:
        budget = answers.get(budget_label, "")
        if not re.search(r"\d", budget):
            errors.append(
                f"**{budget_label}** musí obsahovat částku, například `35 000 Kč`."
            )

    minimum_lengths = {
        "diagnostics": {
            "Popis problému": 15,
            "Konfigurace počítače": 12,
            "Co už jsi vyzkoušel": 10,
        },
        "upgrade": {
            "Současný procesor a deska": 10,
            "Co chceš zlepšit": 10,
        },
    }
    for label, minimum in minimum_lengths.get(request_type, {}).items():
        value = " ".join(answers.get(label, "").split())
        if len(value) < minimum and not any(label in error for error in errors):
            errors.append(
                f"**{label}** je příliš stručné (alespoň {minimum} znaků)."
            )

    return errors
