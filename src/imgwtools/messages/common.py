"""Small texts that other messages embed as values."""

from imgwtools.messages import Text

MESSAGES = {
    "none": Text("(none)", "(brak)"),
    "cancelled": Text(
        "cancelled",
        "anulowano",
    ),
    "unpublished": Text(
        "not published",
        "nieopublikowany",
    ),
}
