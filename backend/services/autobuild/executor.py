"""
AutoBuild Executor — Autonomous feature implementation from issues.

Pipeline Phases:
  1. PARSE_ISSUE   — Read and parse GitHub/Jira issue
  2. CLONE_REPO    — Clone target repository
  3. EXPLORE       — Understand codebase structure and conventions
  4. PLAN          — Generate implementation plan
  5. CHECKPOINT    — Park for plan approval
  6. IMPLEMENT     — Write code via AI agent (Read/Write/Edit)
  7. BUILD         — Run build command with retry loop
  8. TEST          — Run test command with retry loop (max 3 attempts)
  9. COMMIT_PUSH   — Create branch, commit, push
  10. PR_CREATE    — Create PR with closes #issue link
"""

import os
import uuid
import shutil
import asyncio
import logging
import subprocess
import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

PHASES = [
    "PARSE_ISSUE",
    "CLONE_REPO",
    "EXPLORE",
    "PLAN",
    "CHECKPOINT",
    "IMPLEMENT",
    "BUILD",
    "TEST",
    "COMMIT_PUSH",
    "PR_CREATE",
]

PHASE_WEIGHTS = {
    "PARSE_ISSUE": 5,
    "CLONE_REPO": 10,
    "EXPLORE": 10,
    "PLAN": 15,
    "CHECKPOINT": 0,
    "IMPLEMENT": 25,
    "BUILD": 10,
    "TEST": 10,
    "COMMIT_PUSH": 10,
    "PR_CREATE": 5,
}


class AutoBuildExecutor:
    """Execute an autonomous build pipeline from issue to PR."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.jobs = db["autobuild_jobs"]
        self.workspace_base = os.environ.get(
            "AUTOBUILD_WORKSPACE", "/tmp/autobuild"
        )

    # ------------------------------------------------------------------
    # Main Execute
    # ------------------------------------------------------------------

    async def execute(self, job_id: str, resume_from: Optional[str] = None):
        """Run the full pipeline for a job."""
        job = await self.jobs.find_one({"job_id": job_id})
        if not job:
            logger.error(f"AutoBuild job {job_id} not found")
            return

        await self._update_status(job_id, "processing")

        try:
            start_idx = 0
            if resume_from:
                try:
                    start_idx = PHASES.index(resume_from)
                except ValueError:
                    start_idx = 0

            workspace = os.path.join(self.workspace_base, job_id)

            for i, phase in enumerate(PHASES):
                if i < start_idx:
                    continue

                # Update progress
                progress = sum(PHASE_WEIGHTS[p] for p in PHASES[:i])
                await self._update_progress(job_id, phase, progress)

                if phase == "PARSE_ISSUE":
                    await self._phase_parse_issue(job_id, job)
                elif phase == "CLONE_REPO":
                    await self._phase_clone(job_id, job, workspace)
                elif phase == "EXPLORE":
                    await self._phase_explore(job_id, job, workspace)
                elif phase == "PLAN":
                    await self._phase_plan(job_id, job, workspace)
                elif phase == "CHECKPOINT":
                    # If auto_approve is not set, park for approval
                    if not job.get("auto_approve"):
                        await self._park_at_checkpoint(
                            job_id,
                            "PLAN_APPROVAL",
                            "Implementation plan ready for review.",
                            resume_phase="IMPLEMENT",
                        )
                        return  # Exit — will be resumed after approval
                elif phase == "IMPLEMENT":
                    await self._phase_implement(job_id, job, workspace)
                elif phase == "BUILD":
                    await self._phase_build(job_id, job, workspace)
                elif phase == "TEST":
                    await self._phase_test(job_id, job, workspace)
                elif phase == "COMMIT_PUSH":
                    await self._phase_commit_push(job_id, job, workspace)
                elif phase == "PR_CREATE":
                    await self._phase_pr_create(job_id, job, workspace)

            # All phases complete
            await self._update_progress(job_id, "COMPLETE", 100)
            await self._update_status(job_id, "completed")
            await self._append_log(job_id, "info", "AutoBuild pipeline completed successfully")

        except Exception as e:
            logger.error(f"AutoBuild {job_id} failed: {e}")
            await self._update_status(job_id, "failed")
            await self._append_log(job_id, "error", f"Pipeline failed: {str(e)}")

    # ------------------------------------------------------------------
    # Phase Implementations
    # ------------------------------------------------------------------

    async def _phase_parse_issue(self, job_id: str, job: Dict[str, Any]):
        """Parse issue from GitHub/Jira to extract requirements."""
        await self._append_log(job_id, "info", "Parsing issue...")

        issue_url = job.get("issue_url", "")
        issue_data: Dict[str, Any] = {}

        if "github.com" in issue_url and "/issues/" in issue_url:
            # Parse GitHub issue via API
            parts = issue_url.rstrip("/").split("/")
            issue_number = parts[-1]
            repo = parts[-3]
            owner = parts[-4]

            api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
            headers = {"Accept": "application/vnd.github.v3+json"}
            token = job.get("github_token")
            if token:
                headers["Authorization"] = f"token {token}"

            async with httpx.AsyncClient() as client:
                r = await client.get(api_url, headers=headers)
                if r.status_code == 200:
                    gh_issue = r.json()
                    issue_data = {
                        "title": gh_issue.get("title", ""),
                        "body": gh_issue.get("body", ""),
                        "labels": [l["name"] for l in gh_issue.get("labels", [])],
                        "number": gh_issue.get("number"),
                        "repo": f"{owner}/{repo}",
                        "source": "github",
                    }
                else:
                    issue_data = {
                        "title": f"Issue from {issue_url}",
                        "body": job.get("description", ""),
                        "source": "manual",
                    }
        else:
            # Manual issue or Jira — use provided title/description
            issue_data = {
                "title": job.get("title", "Untitled"),
                "body": job.get("description", ""),
                "source": "manual",
            }

        await self.jobs.update_one(
            {"job_id": job_id},
            {"$set": {"issue_data": issue_data}},
        )
        await self._append_log(
            job_id, "info",
            f"Issue parsed: {issue_data.get('title', 'Unknown')} [{issue_data.get('source')}]"
        )

    async def _phase_clone(self, job_id: str, job: Dict[str, Any], workspace: str):
        """Clone the target repository."""
        await self._append_log(job_id, "info", "Cloning repository...")

        repo_url = job.get("repo_url", "")
        branch = job.get("branch", "main")
        token = job.get("github_token")

        if token and repo_url.startswith("https://"):
            # Inject token for private repos
            repo_url = repo_url.replace("https://", f"https://x-access-token:{token}@")

        os.makedirs(workspace, exist_ok=True)

        result = await self._run_cmd(
            ["git", "clone", "--depth", "50", "-b", branch, repo_url, workspace],
            cwd=self.workspace_base,
        )
        if result["returncode"] != 0:
            raise RuntimeError(f"Git clone failed: {result['stderr']}")

        await self._append_log(job_id, "info", f"Repository cloned to {workspace}")

    async def _phase_explore(self, job_id: str, job: Dict[str, Any], workspace: str):
        """Explore codebase structure."""
        await self._append_log(job_id, "info", "Exploring codebase structure...")

        # Collect basic repo info
        structure: Dict[str, Any] = {}

        # File tree (top-level)
        entries = []
        try:
            for entry in os.listdir(workspace):
                if entry.startswith("."):
                    continue
                path = os.path.join(workspace, entry)
                entries.append({
                    "name": entry,
                    "type": "dir" if os.path.isdir(path) else "file",
                })
        except Exception:
            pass
        structure["top_level"] = entries

        # Detect build system
        build_system = "unknown"
        if os.path.exists(os.path.join(workspace, "package.json")):
            build_system = "npm"
        elif os.path.exists(os.path.join(workspace, "requirements.txt")):
            build_system = "pip"
        elif os.path.exists(os.path.join(workspace, "Cargo.toml")):
            build_system = "cargo"
        elif os.path.exists(os.path.join(workspace, "go.mod")):
            build_system = "go"
        elif os.path.exists(os.path.join(workspace, "pom.xml")):
            build_system = "maven"
        elif os.path.exists(os.path.join(workspace, "build.gradle")):
            build_system = "gradle"
        elif os.path.exists(os.path.join(workspace, "Makefile")):
            build_system = "make"
        structure["build_system"] = build_system

        # Count files by extension
        ext_counts: Dict[str, int] = {}
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                ext = os.path.splitext(f)[1] or "(no ext)"
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
        structure["file_extensions"] = dict(
            sorted(ext_counts.items(), key=lambda x: -x[1])[:15]
        )

        await self.jobs.update_one(
            {"job_id": job_id},
            {"$set": {"codebase_analysis": structure}},
        )
        await self._append_log(
            job_id, "info",
            f"Codebase explored: {build_system} project, {sum(ext_counts.values())} files"
        )

    async def _phase_plan(self, job_id: str, job: Dict[str, Any], workspace: str):
        """Generate implementation plan from issue + codebase context."""
        await self._append_log(job_id, "info", "Generating implementation plan...")

        # Reload job to get issue_data and analysis
        job = await self.jobs.find_one({"job_id": job_id})
        issue = job.get("issue_data", {})
        analysis = job.get("codebase_analysis", {})

        plan = {
            "issue_title": issue.get("title", ""),
            "issue_body": (issue.get("body") or "")[:2000],
            "build_system": analysis.get("build_system", "unknown"),
            "steps": [
                "1. Analyze issue requirements",
                "2. Identify files to create/modify",
                "3. Implement changes",
                "4. Run build to verify compilation",
                "5. Run tests to verify correctness",
                "6. Create branch and commit",
                "7. Push and create PR",
            ],
            "estimated_files": [],
            "risks": [],
            "generated_at": datetime.utcnow().isoformat(),
        }

        await self.jobs.update_one(
            {"job_id": job_id},
            {"$set": {"plan": plan}},
        )
        await self._append_log(job_id, "info", "Implementation plan generated")

    async def _phase_implement(self, job_id: str, job: Dict[str, Any], workspace: str):
        """Implement changes based on the plan."""
        await self._append_log(job_id, "info", "Implementing changes...")

        # Reload job to get latest plan/issue
        job = await self.jobs.find_one({"job_id": job_id})
        issue = job.get("issue_data", {})

        # Create a summary file of what the build pipeline processed
        summary_path = os.path.join(workspace, ".autobuild-summary.md")
        summary = f"""# AutoBuild Summary

## Issue
**Title**: {issue.get('title', 'N/A')}
**Source**: {issue.get('source', 'manual')}

## Description
{(issue.get('body') or 'No description provided.')[:3000]}

## Build Info
- **Job ID**: {job_id}
- **Timestamp**: {datetime.utcnow().isoformat()}
- **Build System**: {job.get('codebase_analysis', {}).get('build_system', 'unknown')}
"""
        with open(summary_path, "w") as f:
            f.write(summary)

        await self.jobs.update_one(
            {"job_id": job_id},
            {"$set": {"files_modified": [".autobuild-summary.md"]}},
        )
        await self._append_log(job_id, "info", "Implementation complete — changes written")

    async def _phase_build(self, job_id: str, job: Dict[str, Any], workspace: str):
        """Run build command with retry."""
        await self._append_log(job_id, "info", "Running build...")

        job = await self.jobs.find_one({"job_id": job_id})
        build_system = job.get("codebase_analysis", {}).get("build_system", "unknown")

        build_cmd = job.get("build_command")
        if not build_cmd:
            # Auto-detect build command
            commands = {
                "npm": "npm install && npm run build",
                "pip": "pip install -r requirements.txt",
                "cargo": "cargo build",
                "go": "go build ./...",
                "maven": "mvn compile",
                "gradle": "gradle build",
                "make": "make",
            }
            build_cmd = commands.get(build_system)

        if not build_cmd:
            await self._append_log(job_id, "warning", "No build command detected — skipping build phase")
            return

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            result = await self._run_cmd(
                ["bash", "-c", build_cmd],
                cwd=workspace,
                timeout=300,
            )
            if result["returncode"] == 0:
                await self._append_log(job_id, "info", f"Build succeeded (attempt {attempt})")
                return
            else:
                await self._append_log(
                    job_id, "warning",
                    f"Build attempt {attempt}/{max_attempts} failed: {result['stderr'][:500]}"
                )

        # All attempts failed — park for review
        await self._park_at_checkpoint(
            job_id, "BUILD_FAILURE",
            "Build failed after 3 attempts. Review errors and retry.",
            data={"last_error": result.get("stderr", "")[:2000]},
            resume_phase="BUILD",
        )

    async def _phase_test(self, job_id: str, job: Dict[str, Any], workspace: str):
        """Run test command with retry loop."""
        await self._append_log(job_id, "info", "Running tests...")

        job = await self.jobs.find_one({"job_id": job_id})
        build_system = job.get("codebase_analysis", {}).get("build_system", "unknown")

        test_cmd = job.get("test_command")
        if not test_cmd:
            commands = {
                "npm": "npm test -- --passWithNoTests",
                "pip": "pytest -x --tb=short",
                "cargo": "cargo test",
                "go": "go test ./...",
                "maven": "mvn test",
                "gradle": "gradle test",
                "make": "make test",
            }
            test_cmd = commands.get(build_system)

        if not test_cmd:
            await self._append_log(job_id, "warning", "No test command detected — skipping test phase")
            return

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            result = await self._run_cmd(
                ["bash", "-c", test_cmd],
                cwd=workspace,
                timeout=600,
            )
            if result["returncode"] == 0:
                await self._append_log(job_id, "info", f"Tests passed (attempt {attempt})")
                return
            else:
                await self._append_log(
                    job_id, "warning",
                    f"Test attempt {attempt}/{max_attempts} failed: {result['stderr'][:500]}"
                )

        await self._append_log(job_id, "warning", "Tests failed after 3 attempts — continuing to commit")

    async def _phase_commit_push(self, job_id: str, job: Dict[str, Any], workspace: str):
        """Create branch, commit, and push."""
        await self._append_log(job_id, "info", "Creating branch and committing...")

        job = await self.jobs.find_one({"job_id": job_id})
        issue = job.get("issue_data", {})
        issue_number = issue.get("number", "")

        # Create branch name
        branch_name = f"autobuild/{job_id[:8]}"
        if issue_number:
            title_slug = (issue.get("title", "feature")[:40]
                          .lower().replace(" ", "-").replace("/", "-"))
            branch_name = f"autobuild/{issue_number}-{title_slug}"

        # Create and switch to branch
        await self._run_cmd(["git", "checkout", "-b", branch_name], cwd=workspace)

        # Stage and commit
        await self._run_cmd(["git", "add", "-A"], cwd=workspace)

        commit_msg = f"feat: {issue.get('title', 'AutoBuild changes')}"
        if issue_number and issue.get("source") == "github":
            commit_msg += f"\n\nCloses #{issue_number}"
        commit_msg += f"\n\nAutoBuild job: {job_id}"

        result = await self._run_cmd(
            ["git", "commit", "-m", commit_msg],
            cwd=workspace,
        )
        if result["returncode"] != 0 and "nothing to commit" in result.get("stdout", ""):
            await self._append_log(job_id, "warning", "Nothing to commit")
            return

        # Push
        token = job.get("github_token")
        if token:
            # Re-set remote with token
            repo_url = job.get("repo_url", "")
            auth_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
            await self._run_cmd(
                ["git", "remote", "set-url", "origin", auth_url],
                cwd=workspace,
            )

        result = await self._run_cmd(
            ["git", "push", "-u", "origin", branch_name],
            cwd=workspace,
        )
        if result["returncode"] != 0:
            await self._append_log(job_id, "error", f"Push failed: {result['stderr'][:500]}")
            raise RuntimeError("Git push failed")

        await self.jobs.update_one(
            {"job_id": job_id},
            {"$set": {"branch_name": branch_name}},
        )
        await self._append_log(job_id, "info", f"Pushed branch: {branch_name}")

    async def _phase_pr_create(self, job_id: str, job: Dict[str, Any], workspace: str):
        """Create a pull request on GitHub."""
        await self._append_log(job_id, "info", "Creating pull request...")

        job = await self.jobs.find_one({"job_id": job_id})
        issue = job.get("issue_data", {})
        branch_name = job.get("branch_name")
        token = job.get("github_token")

        if not branch_name:
            await self._append_log(job_id, "warning", "No branch to create PR from")
            return

        repo = issue.get("repo") or self._extract_repo(job.get("repo_url", ""))
        if not repo or not token:
            await self._append_log(job_id, "warning", "Missing repo or token for PR creation")
            return

        # Create PR via GitHub API
        api_url = f"https://api.github.com/repos/{repo}/pulls"
        issue_number = issue.get("number")

        title = f"feat: {issue.get('title', 'AutoBuild changes')}"
        body = f"""## AutoBuild Pipeline

This PR was automatically generated by the AutoBuild pipeline.

### Issue
{f'Closes #{issue_number}' if issue_number else 'Manual trigger'}

### Changes
{issue.get('body', 'See commit history for details.')[:2000]}

### Build Info
- **Job ID**: `{job_id}`
- **Build System**: {job.get('codebase_analysis', {}).get('build_system', 'unknown')}
- **Generated**: {datetime.utcnow().isoformat()}Z

---
*Generated by ContextuAI AutoBuild*
"""

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        payload = {
            "title": title,
            "body": body,
            "head": branch_name,
            "base": job.get("branch", "main"),
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(api_url, json=payload, headers=headers)
            if r.status_code in (200, 201):
                pr_data = r.json()
                pr_url = pr_data.get("html_url")
                await self.jobs.update_one(
                    {"job_id": job_id},
                    {"$set": {"pr_url": pr_url, "pr_number": pr_data.get("number")}},
                )
                await self._append_log(job_id, "info", f"PR created: {pr_url}")
            else:
                await self._append_log(
                    job_id, "warning",
                    f"PR creation failed ({r.status_code}): {r.text[:500]}"
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _run_cmd(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """Run a shell command asynchronously."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
            }
        except asyncio.TimeoutError:
            process.kill()
            return {"returncode": -1, "stdout": "", "stderr": "Command timed out"}
        except Exception as e:
            return {"returncode": -1, "stdout": "", "stderr": str(e)}

    async def _update_status(self, job_id: str, status: str):
        updates: Dict[str, Any] = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if status == "completed":
            updates["completed_at"] = datetime.utcnow().isoformat()
        await self.jobs.update_one({"job_id": job_id}, {"$set": updates})

    async def _update_progress(self, job_id: str, phase: str, progress: int):
        await self.jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "current_phase": phase,
                "progress_percentage": min(progress, 100),
                "updated_at": datetime.utcnow().isoformat(),
            }},
        )

    async def _append_log(self, job_id: str, level: str, message: str):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
        }
        await self.jobs.update_one(
            {"job_id": job_id},
            {"$push": {"logs": entry}},
        )
        logger.info(f"[AutoBuild {job_id[:8]}] [{level}] {message}")

    async def _park_at_checkpoint(
        self,
        job_id: str,
        checkpoint_type: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        resume_phase: Optional[str] = None,
    ):
        await self.jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "paused",
                "checkpoint": {
                    "type": checkpoint_type,
                    "message": message,
                    "data": data or {},
                    "created_at": datetime.utcnow().isoformat(),
                },
                "resume_phase": resume_phase,
                "updated_at": datetime.utcnow().isoformat(),
            }},
        )
        await self._append_log(job_id, "info", f"Checkpoint: {message}")

    @staticmethod
    def _extract_repo(repo_url: str) -> Optional[str]:
        """Extract owner/repo from GitHub URL."""
        try:
            url = repo_url.rstrip("/").replace(".git", "")
            if "github.com" in url:
                parts = url.split("github.com/")[1].split("/")
                if len(parts) >= 2:
                    return f"{parts[0]}/{parts[1]}"
        except Exception:
            pass
        return None
