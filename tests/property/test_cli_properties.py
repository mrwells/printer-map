# Feature: printer-scanner-cli, Property 11: Invalid target rejection
"""
Property 11: Invalid target rejection

For any string that is not a valid IP address, CIDR range, or resolvable
hostname, the CLI should exit with code 1 and produce an error message on
stderr.

Validates: Requirements 9.3
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from printer_map.main import main


# Strategy: generate strings that are clearly not valid IPs, CIDRs, or hostnames.
# We avoid characters that could form valid IPv6 (colons, hex digits) and ensure
# the strings contain at least one character that makes them invalid.
_invalid_chars = st.sampled_from(
    "!@#$%^&*()+={}[]|\\;\"'<>,? "
)
invalid_targets = st.text(alphabet=_invalid_chars, min_size=2, max_size=30)


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(target=invalid_targets)
def test_invalid_target_rejection(target: str, capsys) -> None:
    """
    **Validates: Requirements 9.3**

    For any string that is not a valid IP address, CIDR range, or resolvable
    hostname, the CLI should exit with code 1 and produce an error on stderr.
    """
    try:
        main(["scan", "--target", target])
        # If main returns normally, that's also acceptable (no printers found)
        # but we expect SystemExit(1) for invalid targets.
        assert False, f"Expected SystemExit(1) for invalid target {target!r}"
    except SystemExit as exc:
        assert exc.code == 1, f"Expected exit code 1, got {exc.code} for target {target!r}"
    captured = capsys.readouterr()
    assert "Invalid target" in captured.err, (
        f"Expected 'Invalid target' in stderr for {target!r}, got: {captured.err!r}"
    )
