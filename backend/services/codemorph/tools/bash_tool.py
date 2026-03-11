"""Sandboxed shell execution for CodeMorph builds and tests."""
import subprocess
import logging
from strands import tool

logger = logging.getLogger(__name__)

# Commands that are never allowed
BLOCKED_COMMANDS = ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb"]


@tool
def run_command(command: str, working_dir: str, timeout: int = 300) -> str:
    """Execute a shell command in the working directory.

    Args:
        command: Shell command to execute
        working_dir: Directory to run the command in
        timeout: Maximum execution time in seconds (default: 300)
    """
    # Basic safety check
    cmd_lower = command.lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return f"Error: Command blocked for safety: {command}"

    try:
        result = subprocess.run(
            command, shell=True, cwd=working_dir,
            capture_output=True, text=True, timeout=timeout,
            env={**dict(__import__("os").environ), "CI": "true"}
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        return output[:5000]  # Limit output size
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {str(e)}"
