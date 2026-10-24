"""The plan of a plain write: one action per target (DEV-19.10, ADR-007 D4)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from imgwtools.messages import message
from imgwtools.output import plan_plain
from imgwtools.store.types import PlanAction

__all__ = ["plain_actions"]

# Texts of the targets of a plain plan, by action or by the reason of a conflict.
_TEXTS = {
    "write": "plain.write",
    "replace": "plain.replace",
    "output_exists": "plain.output_exists",
    "duplicate_output_name": "plain.duplicate_output_name",
    "output_in_store": "plain.output_in_store",
}


def plain_actions(
    command: str,
    directory: Path,
    targets: Sequence[tuple[str, str]],
    *,
    force: bool,
    single: bool = False,
) -> list[PlanAction]:
    """
    Plan a plain write without writing anything.

    A conflict is an entry of the plan like any other, so a plan that lists
    conflicts is a successful result and only the real run fails (DEV-19.10).

    Parameters
    ----------
    command : str
        Name of the command the actions refer to.
    directory : pathlib.Path
        Absolute output directory (it need not exist).
    targets : sequence of (str, str)
        The relative POSIX name of each target and what is written there
        (a URL or a description).
    force : bool
        Whether existing targets are replaced.
    single : bool, optional
        The one file of an export: a store conflict says the export goes outside
        every store instead of naming ``--root``.

    Returns
    -------
    list of PlanAction
        One action per target, in the order of ``targets``: status
        ``"missing"`` for ``write``, ``"unverifiable"`` for ``replace`` and
        ``conflict``; ``action``, ``path`` and, for a conflict, ``reason`` set.
    """
    entries = plan_plain(directory, [name for name, _ in targets], force=force)
    return [
        PlanAction(
            command,
            "missing" if entry.action == "write" else "unverifiable",
            message(
                "plain.output_file_in_store"
                if single and entry.reason == "output_in_store"
                else _TEXTS[entry.reason or entry.action],
                what=what,
                target=entry.path,
            ),
            action=entry.action,
            path=entry.path,
            reason=entry.reason,
        )
        for entry, (_, what) in zip(entries, targets, strict=True)
    ]
