"""Git operations for CodeMorph."""
import re
import subprocess
import logging
from strands import tool

logger = logging.getLogger(__name__)


def _inject_token(repo_url: str, token: str = None) -> str:
    """Inject token into HTTPS repo URLs for authentication.

    Works for both GitHub and GitLab HTTPS URLs.

    Args:
        repo_url: The repository URL.
        token: Auth token from Git persona credentials.
    """
    if not token:
        return repo_url
    # Inject into any HTTPS URL (GitHub, GitLab, etc.)
    return re.sub(r'^https://', f'https://x-access-token:{token}@', repo_url)


@tool
def git_clone(repo_url: str, target_dir: str, branch: str = "main", token: str = None) -> str:
    """Clone a git repository to the target directory.

    Args:
        repo_url: The git repository URL to clone
        target_dir: Directory to clone into
        branch: Branch to checkout (default: main)
        token: Auth token from Git persona credentials.
    """
    try:
        auth_url = _inject_token(repo_url, token=token)
        result = subprocess.run(
            ["git", "clone", "--branch", branch, "--single-branch", auth_url, target_dir],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            # Sanitize error output to not leak tokens
            stderr = result.stderr.replace(auth_url, repo_url)
            return f"Error (exit code {result.returncode}): {stderr}"
        return f"Successfully cloned {repo_url} to {target_dir}"
    except subprocess.TimeoutExpired:
        return "Error (exit code 1): Clone operation timed out after 300s"
    except Exception as e:
        return f"Error (exit code 1): {str(e)}"


@tool
def git_commit(repo_dir: str, message: str) -> str:
    """Stage all changes and create a git commit.

    Args:
        repo_dir: Path to the git repository
        message: Commit message
    """
    try:
        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=repo_dir, capture_output=True, text=True, timeout=60)
        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_dir, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            # "nothing to commit" is not a real failure — treat as success
            if "nothing to commit" in output:
                logger.info(f"Nothing to commit in {repo_dir} (changes may already be committed)")
                return f"Committed: {message} (no new changes)"
            return f"Error (exit code {result.returncode}): {output}"
        return f"Committed: {message}"
    except Exception as e:
        return f"Error (exit code 1): {str(e)}"


@tool
def git_push(repo_dir: str, branch: str, token: str = None) -> str:
    """Create a new branch and push changes to remote.

    Args:
        repo_dir: Path to the git repository
        branch: Branch name to push to
        token: Auth token from Git persona credentials.
    """
    try:
        # Create and checkout branch BEFORE committing (better flow)
        result = subprocess.run(
            ["git", "checkout", "-b", branch],
            cwd=repo_dir, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return f"Error (exit code {result.returncode}): {result.stderr}"

        # Inject token into the remote URL for push authentication
        if token:
            # Get current remote URL
            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_dir, capture_output=True, text=True, timeout=10
            )
            if remote_result.returncode == 0:
                original_url = remote_result.stdout.strip()
                auth_url = _inject_token(original_url, token=token)
                if auth_url != original_url:
                    subprocess.run(
                        ["git", "remote", "set-url", "origin", auth_url],
                        cwd=repo_dir, capture_output=True, text=True, timeout=10
                    )

        # Push
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=repo_dir, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            # Sanitize error output
            stderr = result.stderr
            if token:
                stderr = stderr.replace(token, "***")
            return f"Error (exit code {result.returncode}): {stderr}"
        return f"Pushed to {branch}"
    except Exception as e:
        return f"Error (exit code 1): {str(e)}"
