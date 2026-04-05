"""Rich terminal UI helpers — spinners, progress, tables, step display."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()


def show_step(step_number: int, max_steps: int, description: str) -> None:
    """Display a single execution step."""
    console.print(f"  [cyan]◎[/cyan] Step {step_number}/{max_steps} → {description}")


def show_plan(goal: str, steps_estimate: int, first_url: str, summary: str) -> None:
    """Display the task plan."""
    console.print()
    console.print(f"  [bold green]◎[/bold green] [bold]Planning task...[/bold]")
    console.print(f"    Goal: {goal}")
    console.print(f"    Strategy: {summary}")
    console.print(f"    Start URL: [underline]{first_url}[/underline]")
    console.print(f"    Estimated steps: {steps_estimate}")
    console.print()


def show_launching_browser(headless: bool) -> None:
    """Display browser launch message."""
    mode = "headless" if headless else "visible"
    console.print(f"  [cyan]◎[/cyan] Launching browser ({mode})...")


def show_completion(total_steps: int, elapsed: float, items_count: int) -> None:
    """Display task completion summary."""
    console.print()
    console.print(
        f"  [bold green]✓[/bold green] Task complete in {total_steps} steps ({elapsed:.1f}s)"
    )
    if items_count > 0:
        console.print(f"    Extracted {items_count} items")
    console.print()


def show_failure(status: str, total_steps: int, elapsed: float) -> None:
    """Display task failure message."""
    console.print()
    if status == "max_steps_reached":
        console.print(
            f"  [bold yellow]⚠[/bold yellow] Max steps reached ({total_steps} steps, {elapsed:.1f}s)"
        )
    else:
        console.print(
            f"  [bold red]✗[/bold red] Task failed after {total_steps} steps ({elapsed:.1f}s)"
        )
    console.print()


def show_error(step_number: int, error_msg: str) -> None:
    """Display a step error."""
    console.print(f"  [red]✗[/red] Step {step_number} failed: {error_msg}")


def show_data_table(data: list[dict[str, Any]]) -> None:
    """Display extracted data as a Rich table."""
    if not data:
        console.print("  [dim]No data extracted.[/dim]")
        return

    # Get column headers from the first record
    headers = list(data[0].keys())

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    for header in headers:
        table.add_column(header, overflow="fold")

    for row in data:
        table.add_row(*[str(row.get(h, "")) for h in headers])

    console.print(table)


def show_saved_file(filepath: str) -> None:
    """Display where results were saved."""
    console.print(f"\n  Saved to: [underline]{filepath}[/underline]")


def show_history_table(runs: list[dict[str, Any]]) -> None:
    """Display run history as a table."""
    if not runs:
        console.print("  [dim]No runs found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("Run ID", style="bold")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("Steps")
    table.add_column("Time")
    table.add_column("Date")

    for run in runs:
        status_style = {
            "completed": "green",
            "failed": "red",
            "max_steps_reached": "yellow",
        }.get(run.get("status", ""), "white")

        table.add_row(
            run.get("run_id", ""),
            run.get("task", "")[:60],
            f"[{status_style}]{run.get('status', '')}[/{status_style}]",
            str(run.get("total_steps", "")),
            f"{run.get('elapsed_seconds', 0):.1f}s",
            run.get("started_at", ""),
        )

    console.print(table)
