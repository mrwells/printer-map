"""Unit tests for printer_map.main."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from printer_map.main import main
from printer_map.models import PrinterRecord


class TestMainHelp:
    """--help and no-command behaviour."""

    def test_help_flag_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "scan" in captured.out

    def test_no_command_shows_help_and_exits_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "scan" in captured.out


class TestMainVersion:
    """--version output."""

    def test_version_flag_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "0.1.0" in captured.out


class TestMainNoPrintersFound:
    """Exit code 0 when no printers are found."""

    def test_no_printers_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_scan = AsyncMock(return_value=[])
        with patch("printer_map.scanner.run_scan", mock_scan):
            with pytest.raises(SystemExit) as exc_info:
                main(["scan", "--target", "192.168.1.1"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No printers found" in captured.err


class TestMainInvalidTargets:
    """Exit code 1 for invalid targets."""

    def test_invalid_target_exits_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["scan", "--target", "not!a!valid!target"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid target" in captured.err


class TestMainMissingDependency:
    """Exit code 1 for missing dependencies."""

    def test_missing_dependency_exits_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.dict(
            "sys.modules",
            {"printer_map.config": None},
        ):
            # Force re-import to trigger ImportError
            import importlib
            import printer_map.main as main_mod

            importlib.reload(main_mod)
            with pytest.raises(SystemExit) as exc_info:
                main_mod.main(["scan"])
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Missing required dependency" in captured.err
