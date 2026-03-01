"""Table selection confirmation UI."""

from knowsql.utils.display import console, display_table_proposal


def confirm_table_selection(proposal) -> tuple[bool, str | None]:
    """Display proposal and get user confirmation. Returns (accepted, correction_or_none)."""
    display_table_proposal(proposal)

    if not proposal.tables:
        return True, None

    response = console.input("[bold]Accept these tables? [Y/n/edit][/bold] ").strip().lower()

    if response in ("", "y", "yes"):
        return True, None
    elif response in ("n", "no", "edit", "e"):
        correction = console.input("Enter correction: ").strip()
        return False, correction if correction else None

    return True, None
