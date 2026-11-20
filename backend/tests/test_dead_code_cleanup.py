"""Regression tests verifying Issue #80 and Issue #75 Wave-1 dead code cleanup."""

from pathlib import Path
import re

import pytest


BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

RETIRED_ISSUE_80_PATHS = [
    "services/snowflake_connector.py",
    "services/mssql_connector.py",
    "services/mysql_connector.py",
    "services/postgres_connector.py",
    "services/connection_pool_manager.py",
    "services/database_metadata_service.py",
    "services/query_executor.py",
    "services/nlp_to_sql_parser.py",
    "services/sql_validator.py",
    "services/query_cache_service.py",
    "services/database_security.py",
    "services/bedrock_service.py",
    "services/enhanced_bedrock_service.py",
    "services/autobuild",
    "services/codemorph",
    "services/slack",
    "models/codemorph_models.py",
    "repositories/codemorph_repository.py",
]

RETIRED_FRONTEND_PATHS = [
    "routes/connections.tsx",
    "routes/distribution.tsx",
    "routes/schedule.tsx",
    "lib/api/connections-client.ts",
    "lib/api/distribution-client.ts",
    "lib/api/reddit-client.ts",
    "lib/api/twitter-client.ts",
]

RETIRED_ISSUE_75_BACKEND_PATHS = [
    "routers/distribution.py",
    "services/distribution_service.py",
    "routers/reddit.py",
    "services/reddit_client.py",
    "services/reddit_poller.py",
    "models/reddit_models.py",
    "routers/twitter.py",
    "services/twitter_client.py",
    "services/twitter_poller.py",
    "models/twitter_models.py",
    "routers/connections.py",
    "services/connection_service.py",
    "models/connection_models.py",
    "tests/test_reddit.py",
    "tests/test_connections_aggregator.py",
]

REMOVED_REQUIREMENTS = [
    "praw",
    "asyncpg",
    "psycopg2-binary",
    "aiomysql",
    "sqlparse",
    "slack-bolt",
]

RETAINED_REQUIREMENTS = [
    "motor",
    "pymongo",
    "aiosqlite",
    "strands-agents",
    "boto3",
]


@pytest.mark.parametrize("rel_path", RETIRED_ISSUE_80_PATHS)
def test_issue_80_backend_files_deleted(rel_path: str):
    assert not (BACKEND_ROOT / rel_path).exists(), f"Retired path still exists: {rel_path}"


@pytest.mark.parametrize("rel_path", RETIRED_FRONTEND_PATHS)
def test_issue_75_frontend_files_deleted(rel_path: str):
    assert not (FRONTEND_SRC / rel_path).exists(), f"Retired frontend path still exists: {rel_path}"


@pytest.mark.parametrize("rel_path", RETIRED_ISSUE_75_BACKEND_PATHS)
def test_issue_75_backend_files_deleted(rel_path: str):
    assert not (BACKEND_ROOT / rel_path).exists(), f"Retired backend path still exists: {rel_path}"


def test_requirements_excludes_removed_packages_and_keeps_core():
    req_text = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")
    pkg_names = {
        re.split(r"[=<>!~\[]", line.strip(), maxsplit=1)[0].strip().lower()
        for line in req_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for removed in REMOVED_REQUIREMENTS:
        assert removed.lower() not in pkg_names, f"Removed package still in requirements.txt: {removed}"
    for kept in RETAINED_REQUIREMENTS:
        assert kept.lower() in pkg_names, f"Retained package missing from requirements.txt: {kept}"


def test_pyinstaller_spec_excludes_asyncpg():
    spec_text = (BACKEND_ROOT / "contextuai-solo-backend.spec").read_text(encoding="utf-8")
    assert "asyncpg" not in spec_text


def test_codemorph_removed_from_repositories_and_analytics():
    import repositories
    from routers import analytics

    assert not hasattr(repositories, "CodeMorphRepository")
    assert "CodeMorphRepository" not in getattr(repositories, "__all__", [])
    route_paths = {getattr(r, "path", "") for r in analytics.router.routes}
    assert "/api/v1/analytics/codemorph" not in route_paths
    assert "/codemorph" not in route_paths


def test_workspace_git_helpers_relocated_from_codemorph():
    from services.workspace.git_tool import git_clone, git_commit, git_push
    from services.workspace.github_tool import create_pull_request

    assert callable(git_clone)
    assert callable(git_commit)
    assert callable(git_push)
    assert callable(create_pull_request)


@pytest.mark.asyncio
async def test_retired_callers_return_clean_messages(db_proxy):
    from routers.personas import TestConnectionRequest, test_connection as persona_test_connection
    from services.approval_service import ApprovalService
    from services.automation_output_service import AutomationOutputService
    from services.crew_orchestrator import CrewOrchestrator
    from services.persona_service import PersonaService
    from services.tools.database_tools import DatabaseTools
    from models.automation_models import AutomationExecutionResponse, ExecutionStatus

    # PersonaService schema summary
    ps = PersonaService()
    assert await ps._build_schema_summary("p-1", {}) == ""

    # Personas test-connection for retired warehouse types
    for db_type in ("postgresql", "mysql", "mssql", "snowflake"):
        res = await persona_test_connection(
            TestConnectionRequest(persona_type_id=db_type, credentials={})
        )
        assert res["success"] is False
        assert "retired" in res["error"].lower()

    # DatabaseTools stub
    db_tools = DatabaseTools(persona_id="p-1", credentials={"db_type": "postgresql"})
    assert len(db_tools.get_tools()) == 7
    tool_res = await db_tools.test_connection()
    assert tool_res["success"] is False
    assert "retired" in tool_res["error"].lower()

    # ApprovalService social distribution branch
    app_svc = ApprovalService(db_proxy)
    with pytest.raises(RuntimeError, match="retired"):
        await app_svc._send_via_channel("linkedin", "chan-1", "hello")

    # AutomationOutputService distribute branch
    out_svc = AutomationOutputService()
    fake_exec = AutomationExecutionResponse(
        execution_id="ex-1",
        automation_id="auto-1",
        status=ExecutionStatus.SUCCESS,
        started_at="2026-11-19T00:00:00Z",
    )
    dist_res = await out_svc._distribute(fake_exec, {"connection_id": "c-1"}, db_proxy)
    assert dist_res["status"] == "failed"
    assert "retired" in dist_res["error"].lower()

    # CrewOrchestrator non-dry-run social/distribution branches return retired status
    orch = CrewOrchestrator(crew_repo=None, run_repo=None, memory_repo=None, agent_repo=None)
    non_dry = await orch._publish_to_bound_channels(
        {"crew_id": "c1", "name": "Test", "channel_bindings": [{"channel_type": "linkedin", "enabled": True}]},
        "hello",
        run_id="r1",
        dry_run=False,
    )
    assert non_dry[0]["status"] == "retired"
    assert "retired" in non_dry[0]["error"].lower()

    conn_non_dry = await orch._publish_via_connection_bindings(
        {"crew_id": "c1", "name": "Test", "connection_bindings": [{"platform": "linkedin", "direction": "outbound"}]},
        "hello",
        run_id="r1",
        dry_run=False,
    )
    assert conn_non_dry[0]["status"] == "retired"
    assert "retired" in conn_non_dry[0]["error"].lower()
