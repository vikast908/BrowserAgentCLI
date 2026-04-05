"""CLI entry points — agent run, history, replay, config commands."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console

from browseagent.config import Settings, load_settings, save_settings

console = Console()


@click.group()
@click.version_option(package_name="browseagent")
def cli() -> None:
    """BrowseAgent — autonomous browser automation from the command line."""
    pass


@cli.command()
@click.argument("task")
@click.option("--model", "-m", default=None, help="LLM model to use (e.g., qwen3-8b)")
@click.option("--provider", "-p", default=None, help="LLM provider: lm_studio, openai, anthropic")
@click.option("--output", "-o", default=None, help="Save results to file (CSV or JSON)")
@click.option("--headless/--no-headless", default=None, help="Run browser in headless mode")
@click.option("--max-steps", default=None, type=int, help="Maximum execution steps")
@click.option("--screenshot", is_flag=True, default=None, help="Save screenshots of each step")
def run(
    task: str,
    model: str | None,
    provider: str | None,
    output: str | None,
    headless: bool | None,
    max_steps: int | None,
    screenshot: bool | None,
) -> None:
    """Execute a browser automation task.

    Example: agent run "get software engineer leads from LinkedIn in Mumbai"
    """
    settings = load_settings()

    from browseagent.agent.executor import AgentExecutor
    from browseagent.cli.display import (
        show_completion,
        show_data_table,
        show_error,
        show_failure,
        show_plan,
        show_saved_file,
        show_step,
    )

    executor = AgentExecutor(
        settings=settings,
        provider=provider,
        model=model,
        headless=headless,
        max_steps=max_steps,
        take_screenshots=screenshot,
    )

    # Wire up display callbacks
    def on_plan(plan):
        show_plan(plan.goal, plan.steps_estimate, plan.first_url, plan.plan_summary)

    def on_step(step_num, max_s, desc):
        show_step(step_num, max_s, desc)

    def on_error(step_num, error_msg):
        show_error(step_num, error_msg)

    executor.on_plan = on_plan
    executor.on_step = on_step
    executor.on_error = on_error

    # Run the agent
    result = asyncio.run(executor.run(task))

    # Display results
    if result.status == "completed":
        show_completion(result.total_steps, result.elapsed_seconds, len(result.data))
    else:
        show_failure(result.status, result.total_steps, result.elapsed_seconds)

    if result.data:
        show_data_table(result.data)

    # Save results
    if output:
        _save_output(result, output)
        show_saved_file(output)

    # Always save to run history
    _save_run(result, settings)


@cli.command()
@click.option("--limit", "-n", default=20, help="Number of recent runs to show")
def history(limit: int) -> None:
    """List past agent runs."""
    settings = load_settings()

    from browseagent.cli.display import show_history_table
    from browseagent.storage.runs import RunStore

    store = RunStore(settings.runs_dir)
    runs = store.list_runs(limit=limit)
    show_history_table(runs)


@cli.command()
@click.argument("run_id")
def replay(run_id: str) -> None:
    """Show details of a past run."""
    settings = load_settings()

    from browseagent.cli.display import show_data_table, show_plan
    from browseagent.storage.runs import RunStore

    store = RunStore(settings.runs_dir)
    run_data = store.get_run(run_id)

    if not run_data:
        console.print(f"[red]Run '{run_id}' not found.[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Run {run_id}[/bold] — {run_data.get('task', '')}")
    console.print(f"Status: {run_data.get('status', '')}")
    console.print(f"Steps: {run_data.get('total_steps', 0)}")
    console.print(f"Time: {run_data.get('elapsed_seconds', 0):.1f}s")
    console.print()

    data = run_data.get("data", [])
    if data:
        show_data_table(data)


@cli.group()
def config() -> None:
    """View or modify BrowseAgent configuration."""
    pass


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value.

    Example: agent config set default-model qwen3-8b
    """
    settings = load_settings()

    # Normalize key: lm-studio-url → lm_studio_url
    attr_key = key.replace("-", "_")

    if not hasattr(settings, attr_key):
        console.print(f"[red]Unknown config key: {key}[/red]")
        console.print(f"Valid keys: {', '.join(f.name for f in settings.__dataclass_fields__.values())}")
        sys.exit(1)

    # Type-cast the value based on the field type
    current = getattr(settings, attr_key)
    if isinstance(current, bool):
        value = value.lower() in ("true", "1", "yes")
    elif isinstance(current, int):
        value = int(value)

    setattr(settings, attr_key, value)
    save_settings(settings)
    console.print(f"[green]✓[/green] Set {key} = {value}")


@config.command("get")
@click.argument("key", required=False)
def config_get(key: str | None) -> None:
    """Show configuration values.

    Example: agent config get default-model
    """
    settings = load_settings()

    if key:
        attr_key = key.replace("-", "_")
        if hasattr(settings, attr_key):
            console.print(f"{key} = {getattr(settings, attr_key)}")
        else:
            console.print(f"[red]Unknown config key: {key}[/red]")
            sys.exit(1)
    else:
        # Show all config
        from dataclasses import fields

        for f in fields(settings):
            if "api_key" in f.name:
                val = "***" if getattr(settings, f.name) else "(not set)"
            else:
                val = getattr(settings, f.name)
            console.print(f"  {f.name} = {val}")


def _save_output(result, output_path: str) -> None:
    """Save results to CSV or JSON file."""
    from browseagent.storage.export import export_csv, export_json

    path = Path(output_path)
    if path.suffix == ".csv":
        export_csv(result.data, path)
    else:
        export_json(result.data, path)


def _save_run(result, settings: Settings) -> None:
    """Persist run metadata to SQLite."""
    from browseagent.storage.runs import RunStore

    store = RunStore(settings.runs_dir)
    store.save_run(result)


if __name__ == "__main__":
    cli()
