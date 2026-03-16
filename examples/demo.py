"""Demo script is the kubectl quickstart analogue that exercises the public CLI command flow."""

from __future__ import annotations

from click.testing import CliRunner

from KubeAI.cli import main as cli_main


def run_demo() -> str:
    """Execute the CLI demo command and return the rendered walkthrough text."""
    runner = CliRunner()
    result = runner.invoke(cli_main, ["demo"])
    if result.exit_code != 0:
        raise RuntimeError(result.output.strip() or "CLI demo execution failed")
    return result.output.rstrip()


def main() -> None:
    """Print the runnable KubeAI demo flow to stdout."""
    print(run_demo())


if __name__ == "__main__":
    main()
