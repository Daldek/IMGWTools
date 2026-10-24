"""Small texts that other messages embed as values."""

from imgwtools.messages import Text

MESSAGES = {
    "none": Text("(none)", "(brak)"),
    "unknown": Text("unknown", "nieznany"),
    "cancelled": Text(
        "cancelled",
        "anulowano",
    ),
}
