"""Template helpers for rendering event values."""

from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def fmt_value(value: Decimal | None, unit: str = "") -> str:
    """Render an event value with its unit; ``None`` becomes an em dash.

    ``DecimalField`` stores three decimal places ("4.200"); trailing zeros are
    stripped for display. Percent-ish units ("%", "pp") glue to the number
    ("4.2%"); wordy units get a space ("3430 AUD m", "51 index").
    """
    if value is None:
        return "—"
    # format(Decimal, "f") keeps fixed-point notation (never scientific)
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if not unit:
        return text
    if unit.startswith("%") or unit.startswith("pp"):
        return f"{text}{unit}"
    return f"{text} {unit}"
