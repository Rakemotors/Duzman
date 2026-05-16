import subprocess
import sys


def test_one_shot_help_runs_with_project_local_python():
    """The documented one-shot command should be importable outside pytest path setup."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "duzman.runtime.run_market_data_collection_once",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Run one Duzman public market-data collection cycle." in result.stdout
    assert "--log-level" in result.stdout
