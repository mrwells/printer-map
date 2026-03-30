# Feature: printer-scanner-cli, Property 3: CLI argument parsing preserves values
"""
Property 3: CLI argument parsing preserves values

For any valid combination of CLI arguments (--timeout with a positive float,
--community with a non-empty string, --target with valid addresses, --format
with one of "table"/"json"/"csv", --verbose), parsing those arguments into a
ScanConfig should produce a config whose fields exactly match the provided
values.

Validates: Requirements 1.4, 2.3, 4.1, 5.1, 7.3
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from printer_map.config import ScanConfig, load_config


# --- Hypothesis strategies ---

# Positive floats in a reasonable range for timeout
timeouts = st.floats(min_value=0.1, max_value=300.0, allow_nan=False, allow_infinity=False)

# Non-empty community strings using safe printable characters (avoid
# strings that argparse could misinterpret as flags or empty arguments)
_safe_alphabet = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)
communities = st.text(alphabet=_safe_alphabet, min_size=1, max_size=50)

# Valid IP address strings via ip_addresses strategy
ip_addresses = st.ip_addresses(v=4).map(str)

# Output format choices
output_formats = st.sampled_from(["table", "json", "csv"])

# Whether --verbose flag is included
verbose_flags = st.booleans()


@settings(max_examples=100)
@given(
    timeout=timeouts,
    community=communities,
    target=ip_addresses,
    output_format=output_formats,
    verbose=verbose_flags,
)
def test_cli_argument_parsing_preserves_values(
    timeout: float,
    community: str,
    target: str,
    output_format: str,
    verbose: bool,
) -> None:
    """
    **Validates: Requirements 1.4, 2.3, 4.1, 5.1, 7.3**

    For any valid combination of CLI arguments, parsing them into a ScanConfig
    should produce a config whose fields exactly match the provided values.
    """
    argv = [
        "scan",
        "--timeout", str(timeout),
        "--community", community,
        "--target", target,
        "--format", output_format,
    ]
    if verbose:
        argv.append("--verbose")

    config = load_config(argv)

    assert isinstance(config, ScanConfig)
    assert config.timeout == timeout
    assert config.community == community
    assert config.targets == [target]
    assert config.output_format == output_format
    assert config.verbose == verbose
