"""GitHub API operations for CodeMorph."""
import re
import logging

logger = logging.getLogger(__name__)

def create_pull_request(
    repo_url: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    token: str = None
) -> str:
    """Create a pull request on GitHub.

    Args:
        repo_url: Repository URL (HTTPS)
        head_branch: Branch with changes
        base_branch: Target branch
        title: PR title
        body: PR description
        token: Auth token from Git persona credentials.

    Returns:
        PR URL or error message
    """
    if not token:
        logger.warning("No Git persona token provided, skipping PR creation")
        return ""

    try:
        import httpx

        # Extract owner/repo from URL
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
        if not match:
            return f"Error: Cannot parse GitHub repo from URL: {repo_url}"

        owner, repo = match.groups()

        response = httpx.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
            timeout=30,
        )

        if response.status_code == 201:
            pr_data = response.json()
            return pr_data.get("html_url", "")
        else:
            return f"Error creating PR: {response.status_code} - {response.text}"

    except Exception as e:
        logger.error(f"GitHub PR creation failed: {e}")
        return f"Error: {str(e)}"
