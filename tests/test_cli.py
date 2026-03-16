"""Unit tests for click-based agentctl CLI command surface."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from KubeAI.cli import main


class TestCLI:
    def test_help_lists_core_commands(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "run" in result.output
        assert "blueprints" in result.output
        assert "templates" in result.output
        assert "mcps" in result.output
        assert "status" in result.output

    def test_run_command_with_flags(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["run", "Summarize docs", "--rag", "basic", "--memory", "summarizing"],
        )

        assert result.exit_code == 0
        assert "RAG template: basic" in result.output
        assert "Memory template: summarizing" in result.output

    def test_run_command_json_output(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["run", "Write tests", "--rag", "hybrid", "--json-output"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["task"] == "Write tests"
        assert payload["rag_template"] == "hybrid"

    def test_blueprint_register_and_list(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            blueprint = Path("research_agent.yaml")
            blueprint.write_text("name: research_agent\nversion: 1.2.0\n", encoding="utf-8")

            register = runner.invoke(main, ["blueprints", "register", str(blueprint)])
            assert register.exit_code == 0
            assert "Registered blueprint" in register.output

            listed = runner.invoke(main, ["blueprints", "list"])
            assert listed.exit_code == 0
            assert "research_agent" in listed.output
            assert "1.2.0" in listed.output

    def test_mcp_register_from_yaml_and_list(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            mcp = Path("postgres.yaml")
            mcp.write_text(
                "name: postgres\nendpoint: http://localhost:8090\ncapabilities:\n  - db_query\n",
                encoding="utf-8",
            )

            register = runner.invoke(main, ["mcps", "register", str(mcp)])
            assert register.exit_code == 0
            assert "Registered MCP postgres" in register.output

            listed = runner.invoke(main, ["mcps", "list"])
            assert listed.exit_code == 0
            assert "postgres" in listed.output
            assert "db_query" in listed.output

    def test_mcp_register_url(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            register = runner.invoke(main, ["mcps", "register", "https://example.com/mcp/web-search"])
            assert register.exit_code == 0
            assert "Registered MCP web-search" in register.output

            listed = runner.invoke(main, ["mcps", "list"])
            assert listed.exit_code == 0
            assert "web-search" in listed.output

    def test_mcp_register_file_requires_endpoint(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            bad = Path("bad.yaml")
            bad.write_text("name: broken_mcp\n", encoding="utf-8")

            result = runner.invoke(main, ["mcps", "register", str(bad)])
            assert result.exit_code != 0
            assert "endpoint" in result.output

    def test_status_reflects_registrations(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            blueprint = Path("coding_agent.yaml")
            blueprint.write_text("name: coding_agent\nversion: 2.0.0\n", encoding="utf-8")
            mcp = Path("web.yaml")
            mcp.write_text(
                "name: web\nendpoint: http://localhost:8081\ncapabilities:\n  - web_search\n",
                encoding="utf-8",
            )

            runner.invoke(main, ["blueprints", "register", str(blueprint)])
            runner.invoke(main, ["mcps", "register", str(mcp)])

            status = runner.invoke(main, ["status"])
            assert status.exit_code == 0
            assert "Registered blueprints: 1" in status.output
            assert "Registered MCP servers: 1" in status.output
