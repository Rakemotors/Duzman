import subprocess
import sys


def test_read_only_api_runtime_check_command_succeeds():
    """The offline API smoke check should run without DB, network, or scheduler work."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "duzman.runtime.verify_read_only_api",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "READ_ONLY_API_RUNTIME_CHECK_OK" in result.stdout
