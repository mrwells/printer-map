"""Unit tests for printer_map.config."""

from __future__ import annotations

import pytest

from printer_map.config import ScanConfig, build_parser, load_config


class TestScanConfigDefaults:
    """ScanConfig default field values."""

    def test_default_targets_empty(self) -> None:
        cfg = ScanConfig()
        assert cfg.targets == []

    def test_default_timeout(self) -> None:
        cfg = ScanConfig()
        assert cfg.timeout == 5.0

    def test_default_community(self) -> None:
        cfg = ScanConfig()
        assert cfg.community == "public"

    def test_default_output_format(self) -> None:
        cfg = ScanConfig()
        assert cfg.output_format == "table"

    def test_default_verbose(self) -> None:
        cfg = ScanConfig()
        assert cfg.verbose is False

    def test_default_version(self) -> None:
        cfg = ScanConfig()
        assert cfg.version is False


class TestBuildParser:
    """build_parser() produces a usable argparse parser."""

    def test_parser_has_scan_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["scan"])
        assert args.command == "scan"

    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "0.1.0" in captured.out

    def test_help_contains_scan(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])
        captured = capsys.readouterr()
        assert "scan" in captured.out

    def test_scan_options_in_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["scan", "--help"])
        captured = capsys.readouterr()
        for opt in ("--target", "--timeout", "--community", "--format", "--verbose"):
            assert opt in captured.out


class TestLoadConfig:
    """load_config() returns a correct ScanConfig."""

    def test_scan_defaults(self) -> None:
        cfg = load_config(["scan"])
        assert cfg.targets == []
        assert cfg.timeout == 5.0
        assert cfg.community == "public"
        assert cfg.output_format == "table"
        assert cfg.verbose is False

    def test_single_target(self) -> None:
        cfg = load_config(["scan", "--target", "192.168.1.1"])
        assert cfg.targets == ["192.168.1.1"]

    def test_multiple_targets(self) -> None:
        cfg = load_config(["scan", "--target", "10.0.0.1", "--target", "10.0.0.2"])
        assert cfg.targets == ["10.0.0.1", "10.0.0.2"]

    def test_timeout_override(self) -> None:
        cfg = load_config(["scan", "--timeout", "10.5"])
        assert cfg.timeout == 10.5

    def test_community_override(self) -> None:
        cfg = load_config(["scan", "--community", "private"])
        assert cfg.community == "private"

    def test_format_json(self) -> None:
        cfg = load_config(["scan", "--format", "json"])
        assert cfg.output_format == "json"

    def test_format_csv(self) -> None:
        cfg = load_config(["scan", "--format", "csv"])
        assert cfg.output_format == "csv"

    def test_verbose_flag(self) -> None:
        cfg = load_config(["scan", "--verbose"])
        assert cfg.verbose is True

    def test_invalid_format_exits(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            load_config(["scan", "--format", "xml"])
        assert exc_info.value.code == 2

    def test_no_command_shows_help_and_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            load_config([])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "scan" in captured.out
