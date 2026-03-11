"""
Source Control Management (SCM) tools for Strands Agent.
Provides GitHub and GitLab operations: repositories, issues, pull requests, file access.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from strands.tools import tool
import httpx

logger = logging.getLogger(__name__)


class SCMTools:
    """
    SCM operation tools for GitHub and GitLab personas.

    Supports:
    - Repository listing and search
    - Issue management (list, create)
    - Pull/Merge request listing
    - File content retrieval
    """

    def __init__(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Initialize SCM tools with persona credentials.

        Args:
            persona_id: Unique persona identifier
            credentials: SCM connection credentials (token, provider, base_url, etc.)
        """
        self.persona_id = persona_id
        self.credentials = credentials
        self.token = credentials.get("token", "")
        self.provider = credentials.get("provider", "github").lower()
        self.timeout = 15

        # Default owner/repo from persona config
        self.default_owner = credentials.get("owner", "")
        self.default_repo = credentials.get("repo", "")

        if self.provider == "gitlab":
            self.base_url = (credentials.get("base_url") or "https://gitlab.com").rstrip("/")
            self.api_url = f"{self.base_url}/api/v4"
            self.headers = {"PRIVATE-TOKEN": self.token}
        else:
            self.api_url = "https://api.github.com"
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

        logger.info(f"SCMTools initialized for persona {persona_id}, provider: {self.provider}")

    def get_tools(self):
        """Return all SCM operation tools as a list for Strands Agent."""
        return [
            self.list_repositories,
            self.get_repository_info,
            self.list_issues,
            self.create_issue,
            self.list_pull_requests,
            self.get_file_content,
        ]

    @tool
    async def list_repositories(
        self,
        query: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        List or search repositories accessible with the configured token.

        Args:
            query: Optional search query to filter repositories
            limit: Maximum number of results (default: 20, max: 100)

        Returns:
            Dictionary with repository list:
            {
                "success": bool,
                "repositories": List of repo objects with name, full_name, description, url, stars, language,
                "count": int,
                "error": Optional[str]
            }
        """
        limit = min(limit, 100)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "gitlab":
                    params = {"per_page": limit, "order_by": "updated_at"}
                    if query:
                        params["search"] = query
                    resp = await client.get(
                        f"{self.api_url}/projects",
                        headers=self.headers,
                        params=params,
                    )
                    resp.raise_for_status()
                    repos = [
                        {
                            "name": r["name"],
                            "full_name": r["path_with_namespace"],
                            "description": r.get("description", ""),
                            "url": r["web_url"],
                            "stars": r.get("star_count", 0),
                            "language": r.get("language") or "",
                            "default_branch": r.get("default_branch", "main"),
                            "visibility": r.get("visibility", ""),
                        }
                        for r in resp.json()
                    ]
                else:
                    if query:
                        resp = await client.get(
                            f"{self.api_url}/search/repositories",
                            headers=self.headers,
                            params={"q": query, "per_page": limit, "sort": "updated"},
                        )
                        resp.raise_for_status()
                        items = resp.json().get("items", [])
                    else:
                        resp = await client.get(
                            f"{self.api_url}/user/repos",
                            headers=self.headers,
                            params={"per_page": limit, "sort": "updated"},
                        )
                        resp.raise_for_status()
                        items = resp.json()

                    repos = [
                        {
                            "name": r["name"],
                            "full_name": r["full_name"],
                            "description": r.get("description", "") or "",
                            "url": r["html_url"],
                            "stars": r.get("stargazers_count", 0),
                            "language": r.get("language") or "",
                            "default_branch": r.get("default_branch", "main"),
                            "visibility": r.get("visibility", ""),
                        }
                        for r in items
                    ]

            return {"success": True, "repositories": repos, "count": len(repos)}

        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"API error {e.response.status_code}: {e.response.text[:300]}", "repositories": [], "count": 0}
        except Exception as e:
            logger.error(f"Error listing repositories: {e}", exc_info=True)
            return {"success": False, "error": str(e), "repositories": [], "count": 0}

    @tool
    async def get_repository_info(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information about a repository including README content.

        Args:
            owner: Repository owner/namespace (uses persona default if not provided)
            repo: Repository name (uses persona default if not provided)

        Returns:
            Dictionary with repository details:
            {
                "success": bool,
                "repository": { name, description, stars, forks, language, default_branch, open_issues, topics, readme },
                "error": Optional[str]
            }
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        if not owner or not repo:
            return {"success": False, "error": "Both 'owner' and 'repo' are required"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "gitlab":
                    project_path = f"{owner}/{repo}".replace("/", "%2F")
                    resp = await client.get(f"{self.api_url}/projects/{project_path}", headers=self.headers)
                    resp.raise_for_status()
                    data = resp.json()
                    info = {
                        "name": data["name"],
                        "full_name": data["path_with_namespace"],
                        "description": data.get("description", ""),
                        "stars": data.get("star_count", 0),
                        "forks": data.get("forks_count", 0),
                        "language": data.get("language") or "",
                        "default_branch": data.get("default_branch", "main"),
                        "open_issues": data.get("open_issues_count", 0),
                        "topics": data.get("topics", []),
                        "url": data["web_url"],
                    }
                    # Try to get README
                    try:
                        readme_resp = await client.get(
                            f"{self.api_url}/projects/{project_path}/repository/files/README.md/raw",
                            headers=self.headers,
                            params={"ref": info["default_branch"]},
                        )
                        if readme_resp.status_code == 200:
                            info["readme"] = readme_resp.text[:5000]
                    except Exception:
                        info["readme"] = None
                else:
                    resp = await client.get(f"{self.api_url}/repos/{owner}/{repo}", headers=self.headers)
                    resp.raise_for_status()
                    data = resp.json()
                    info = {
                        "name": data["name"],
                        "full_name": data["full_name"],
                        "description": data.get("description", "") or "",
                        "stars": data.get("stargazers_count", 0),
                        "forks": data.get("forks_count", 0),
                        "language": data.get("language") or "",
                        "default_branch": data.get("default_branch", "main"),
                        "open_issues": data.get("open_issues_count", 0),
                        "topics": data.get("topics", []),
                        "url": data["html_url"],
                    }
                    # Try to get README
                    try:
                        readme_resp = await client.get(
                            f"{self.api_url}/repos/{owner}/{repo}/readme",
                            headers=self.headers,
                        )
                        if readme_resp.status_code == 200:
                            import base64
                            content = readme_resp.json().get("content", "")
                            info["readme"] = base64.b64decode(content).decode("utf-8", errors="replace")[:5000]
                    except Exception:
                        info["readme"] = None

            return {"success": True, "repository": info}

        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"API error {e.response.status_code}: {e.response.text[:300]}"}
        except Exception as e:
            logger.error(f"Error getting repository info: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @tool
    async def list_issues(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        state: str = "open",
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        List issues for a repository.

        Args:
            owner: Repository owner (uses persona default if not provided)
            repo: Repository name (uses persona default if not provided)
            state: Issue state filter: "open", "closed", or "all" (default: "open")
            limit: Maximum number of results (default: 20, max: 100)

        Returns:
            Dictionary with issue list:
            {
                "success": bool,
                "issues": List with number, title, state, author, labels, created_at, url,
                "count": int,
                "error": Optional[str]
            }
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        if not owner or not repo:
            return {"success": False, "error": "Both 'owner' and 'repo' are required", "issues": [], "count": 0}

        limit = min(limit, 100)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "gitlab":
                    project_path = f"{owner}/{repo}".replace("/", "%2F")
                    gl_state = {"open": "opened", "closed": "closed", "all": "all"}.get(state, "opened")
                    resp = await client.get(
                        f"{self.api_url}/projects/{project_path}/issues",
                        headers=self.headers,
                        params={"state": gl_state, "per_page": limit},
                    )
                    resp.raise_for_status()
                    issues = [
                        {
                            "number": i["iid"],
                            "title": i["title"],
                            "state": i["state"],
                            "author": i.get("author", {}).get("username", ""),
                            "labels": i.get("labels", []),
                            "created_at": i.get("created_at", ""),
                            "url": i["web_url"],
                        }
                        for i in resp.json()
                    ]
                else:
                    resp = await client.get(
                        f"{self.api_url}/repos/{owner}/{repo}/issues",
                        headers=self.headers,
                        params={"state": state, "per_page": limit},
                    )
                    resp.raise_for_status()
                    issues = [
                        {
                            "number": i["number"],
                            "title": i["title"],
                            "state": i["state"],
                            "author": i.get("user", {}).get("login", ""),
                            "labels": [l["name"] for l in i.get("labels", [])],
                            "created_at": i.get("created_at", ""),
                            "url": i["html_url"],
                        }
                        for i in resp.json()
                        if "pull_request" not in i  # GitHub returns PRs in issues endpoint
                    ]

            return {"success": True, "issues": issues, "count": len(issues)}

        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"API error {e.response.status_code}: {e.response.text[:300]}", "issues": [], "count": 0}
        except Exception as e:
            logger.error(f"Error listing issues: {e}", exc_info=True)
            return {"success": False, "error": str(e), "issues": [], "count": 0}

    @tool
    async def create_issue(
        self,
        title: str,
        body: str = "",
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new issue in a repository.

        Args:
            title: Issue title
            body: Issue body/description (markdown supported)
            owner: Repository owner (uses persona default if not provided)
            repo: Repository name (uses persona default if not provided)
            labels: Optional list of label names to apply

        Returns:
            Dictionary with created issue:
            {
                "success": bool,
                "issue": { number, title, url, state },
                "error": Optional[str]
            }
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        if not owner or not repo:
            return {"success": False, "error": "Both 'owner' and 'repo' are required"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "gitlab":
                    project_path = f"{owner}/{repo}".replace("/", "%2F")
                    payload: Dict[str, Any] = {"title": title, "description": body}
                    if labels:
                        payload["labels"] = ",".join(labels)
                    resp = await client.post(
                        f"{self.api_url}/projects/{project_path}/issues",
                        headers=self.headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    issue = {
                        "number": data["iid"],
                        "title": data["title"],
                        "url": data["web_url"],
                        "state": data["state"],
                    }
                else:
                    payload = {"title": title, "body": body}
                    if labels:
                        payload["labels"] = labels
                    resp = await client.post(
                        f"{self.api_url}/repos/{owner}/{repo}/issues",
                        headers=self.headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    issue = {
                        "number": data["number"],
                        "title": data["title"],
                        "url": data["html_url"],
                        "state": data["state"],
                    }

            return {"success": True, "issue": issue}

        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"API error {e.response.status_code}: {e.response.text[:300]}"}
        except Exception as e:
            logger.error(f"Error creating issue: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @tool
    async def list_pull_requests(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        state: str = "open",
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        List pull requests (GitHub) or merge requests (GitLab) for a repository.

        Args:
            owner: Repository owner (uses persona default if not provided)
            repo: Repository name (uses persona default if not provided)
            state: PR state filter: "open", "closed", "merged", or "all" (default: "open")
            limit: Maximum number of results (default: 20, max: 100)

        Returns:
            Dictionary with pull request list:
            {
                "success": bool,
                "pull_requests": List with number, title, state, author, source_branch, target_branch, url,
                "count": int,
                "error": Optional[str]
            }
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        if not owner or not repo:
            return {"success": False, "error": "Both 'owner' and 'repo' are required", "pull_requests": [], "count": 0}

        limit = min(limit, 100)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "gitlab":
                    project_path = f"{owner}/{repo}".replace("/", "%2F")
                    gl_state = {"open": "opened", "closed": "closed", "merged": "merged", "all": "all"}.get(state, "opened")
                    resp = await client.get(
                        f"{self.api_url}/projects/{project_path}/merge_requests",
                        headers=self.headers,
                        params={"state": gl_state, "per_page": limit},
                    )
                    resp.raise_for_status()
                    prs = [
                        {
                            "number": mr["iid"],
                            "title": mr["title"],
                            "state": mr["state"],
                            "author": mr.get("author", {}).get("username", ""),
                            "source_branch": mr.get("source_branch", ""),
                            "target_branch": mr.get("target_branch", ""),
                            "url": mr["web_url"],
                            "created_at": mr.get("created_at", ""),
                        }
                        for mr in resp.json()
                    ]
                else:
                    gh_state = state if state in ("open", "closed", "all") else "open"
                    resp = await client.get(
                        f"{self.api_url}/repos/{owner}/{repo}/pulls",
                        headers=self.headers,
                        params={"state": gh_state, "per_page": limit},
                    )
                    resp.raise_for_status()
                    prs = [
                        {
                            "number": pr["number"],
                            "title": pr["title"],
                            "state": pr["state"],
                            "author": pr.get("user", {}).get("login", ""),
                            "source_branch": pr.get("head", {}).get("ref", ""),
                            "target_branch": pr.get("base", {}).get("ref", ""),
                            "url": pr["html_url"],
                            "created_at": pr.get("created_at", ""),
                        }
                        for pr in resp.json()
                    ]

            return {"success": True, "pull_requests": prs, "count": len(prs)}

        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"API error {e.response.status_code}: {e.response.text[:300]}", "pull_requests": [], "count": 0}
        except Exception as e:
            logger.error(f"Error listing pull requests: {e}", exc_info=True)
            return {"success": False, "error": str(e), "pull_requests": [], "count": 0}

    @tool
    async def get_file_content(
        self,
        path: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the content of a file from a repository.

        Args:
            path: File path relative to repository root (e.g., "src/main.py")
            owner: Repository owner (uses persona default if not provided)
            repo: Repository name (uses persona default if not provided)
            ref: Branch, tag, or commit SHA (default: repository default branch)

        Returns:
            Dictionary with file content:
            {
                "success": bool,
                "path": str,
                "content": str (decoded file text),
                "size": int (bytes),
                "encoding": str,
                "error": Optional[str]
            }
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        if not owner or not repo:
            return {"success": False, "error": "Both 'owner' and 'repo' are required"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "gitlab":
                    project_path = f"{owner}/{repo}".replace("/", "%2F")
                    encoded_path = path.replace("/", "%2F")
                    params = {}
                    if ref:
                        params["ref"] = ref
                    resp = await client.get(
                        f"{self.api_url}/projects/{project_path}/repository/files/{encoded_path}",
                        headers=self.headers,
                        params=params,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    import base64
                    content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
                    return {
                        "success": True,
                        "path": path,
                        "content": content[:50000],  # Limit to ~50KB
                        "size": data.get("size", len(content)),
                        "encoding": data.get("encoding", "base64"),
                    }
                else:
                    params = {}
                    if ref:
                        params["ref"] = ref
                    resp = await client.get(
                        f"{self.api_url}/repos/{owner}/{repo}/contents/{path}",
                        headers=self.headers,
                        params=params,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("type") != "file":
                        return {"success": False, "error": f"Path '{path}' is a {data.get('type', 'unknown')}, not a file"}
                    import base64
                    content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
                    return {
                        "success": True,
                        "path": path,
                        "content": content[:50000],
                        "size": data.get("size", len(content)),
                        "encoding": data.get("encoding", "base64"),
                    }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"success": False, "error": f"File not found: {path}"}
            return {"success": False, "error": f"API error {e.response.status_code}: {e.response.text[:300]}"}
        except Exception as e:
            logger.error(f"Error getting file content: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
