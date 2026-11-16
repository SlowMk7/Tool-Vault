"""Plain-English error reporting.

The generator collects every problem it can find and reports them together,
so a design can be fixed in one pass instead of one error at a time.
"""

from __future__ import annotations


class DesignError(Exception):
    """A design that cannot be generated. `problems` is a list of messages."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("\n".join(f"- {p}" for p in self.problems))


class Problems:
    """Collects problems, then raises them all at once."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def __bool__(self) -> bool:
        return bool(self.items)

    def raise_if_any(self) -> None:
        if self.items:
            raise DesignError(self.items)
