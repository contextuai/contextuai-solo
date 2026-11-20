"""
ContextuAI Solo — Standalone Desktop Application

Lightweight FastAPI backend for the ContextuAI Solo desktop app.
Uses SQLite for storage and APScheduler for background tasks.
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

import hmac
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import database
from database_factory import get_database_adapter, close_database_adapter
from scheduler_factory import get_scheduler_adapter, stop_scheduler_adapter
from adapters.motor_compat import DatabaseProxy

# ---------------------------------------------------------------------------
# Router imports (desktop-relevant subset)
# ---------------------------------------------------------------------------
from routers.personas import router as personas_router
from routers.persona_types import router as persona_types_router
from routers.chat_sessions import router as chat_sessions_router
from routers.chat_messages import router as chat_messages_router
from routers.ai_chat import router as ai_chat_router
from routers.workspace import router as workspace_router
from routers.workspace_project_types import router as workspace_project_types_router
from routers.crews import router as crews_router
from routers.tools import router as tools_router
from routers.files import router as files_router
from routers.analytics import router as analytics_router
from routers.channels import router as channels_router
from routers.desktop_oauth import router as desktop_oauth_router
from routers.models import router as models_router
from routers.local_models import router as local_models_router
from routers.openai_compat import router as openai_compat_router
from routers.triggers import router as triggers_router
from routers.approvals import router as approvals_router
from routers.blueprints import router as blueprints_router
from routers.scheduled_jobs import router as scheduled_jobs_router
from routers.knowledge_base import router as knowledge_base_router
from routers.personal_docs import router as personal_docs_router
from routers.memory import router as memory_router
from routers.automations import router as automations_router
from routers.cloud_providers import router as cloud_providers_router
from routers.coder_projects import router as coder_projects_router
from routers.coder_roles import router as coder_roles_router
from routers.coder_workflow import router as coder_workflow_router
from routers.privacy import router as privacy_router
from routers.dlp import router as dlp_router
from routers.audit import router as audit_router
from routers.enterprise import router as enterprise_router
import settings as app_settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
APP_START_TIME = time.time()

app = FastAPI(title="ContextuAI Solo")

ALLOWED_CORS_ORIGINS = [
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:3000",
]

# CORS — locked down to Tauri webview + local Vite dev server origins (SPEC-01)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/v1/health",
    "/docs",
    "/openapi.json",
}


@app.middleware("http")
async def sidecar_token_middleware(request: Request, call_next):
    """Require sidecar token on /api/v1/* when CONTEXTUAI_SIDECAR_TOKEN is set."""
    expected_token = (os.getenv("CONTEXTUAI_SIDECAR_TOKEN") or "").strip()
    if not expected_token or request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/v1/"):
        return await call_next(request)

    if path.startswith("/api/v1/"):
        provided = (request.headers.get("X-ContextuAI-Token") or "").strip()
        if not provided:
            auth_header = (request.headers.get("Authorization") or "").strip()
            if auth_header.lower().startswith("bearer "):
                provided = auth_header[7:].strip()

        if not provided or not hmac.compare_digest(provided, expected_token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: invalid or missing sidecar token"},
            )

    return await call_next(request)

# No rate-limiting middleware — single user
# No CORS debug middleware — not needed

# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
app.include_router(personas_router)
app.include_router(persona_types_router)
app.include_router(chat_sessions_router)
app.include_router(chat_messages_router)
app.include_router(ai_chat_router)
app.include_router(workspace_router)
app.include_router(workspace_project_types_router)
app.include_router(crews_router)
app.include_router(tools_router)
app.include_router(files_router)
app.include_router(analytics_router)
app.include_router(channels_router)
app.include_router(desktop_oauth_router)
app.include_router(models_router)
app.include_router(local_models_router)
app.include_router(openai_compat_router)
app.include_router(triggers_router)
app.include_router(approvals_router)
app.include_router(blueprints_router)
app.include_router(scheduled_jobs_router)
app.include_router(knowledge_base_router)
app.include_router(personal_docs_router)
app.include_router(memory_router)
app.include_router(automations_router)
app.include_router(cloud_providers_router)
app.include_router(coder_projects_router)
app.include_router(coder_roles_router)
app.include_router(coder_workflow_router)
app.include_router(privacy_router)
app.include_router(dlp_router)
app.include_router(audit_router)
app.include_router(enterprise_router)


# ---------------------------------------------------------------------------
# Default persona types for desktop mode
# ---------------------------------------------------------------------------
_DEFAULT_PERSONA_TYPES = [
    {
        "id": "generic", "name": "Nexus Agent", "description": "Craft a custom AI persona with unique expertise, personality, and capabilities",
        "category": "general", "icon": "🤖", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "system_instructions", "label": "System Instructions", "placeholder": "You are an expert auditor specializing in financial compliance...", "type": "textarea", "required": True},
            {"name": "expertise_area", "label": "Expertise Area", "placeholder": "e.g., Financial auditing, UX design, Legal compliance", "type": "text", "required": False},
            {"name": "tone", "label": "Response Tone", "type": "select", "required": False, "options": ["Professional", "Casual", "Friendly", "Formal", "Technical"]},
            {"name": "response_style", "label": "Response Style", "type": "select", "required": False, "options": ["Concise", "Detailed", "Balanced"]},
            {"name": "language", "label": "Response Language", "placeholder": "e.g., English, Spanish, French (default: English)", "type": "text", "required": False},
        ],
    },
    {
        "id": "web_search", "name": "Web Researcher", "description": "Search the web, fetch URLs, and extract information",
        "category": "utilities", "icon": "🔍", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "maxResults", "label": "Max Search Results", "placeholder": "10", "type": "number", "required": False},
        ],
    },
    {
        "id": "postgresql", "name": "PostgreSQL", "description": "PostgreSQL relational database",
        "category": "data_analytics", "icon": "🐘", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "host", "label": "Host", "placeholder": "localhost", "type": "text", "required": True},
            {"name": "port", "label": "Port", "placeholder": "5432", "type": "number", "required": True},
            {"name": "database", "label": "Database", "placeholder": "mydb", "type": "text", "required": True},
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "password", "label": "Password", "type": "password", "required": True},
        ],
    },
    {
        "id": "mysql", "name": "MySQL", "description": "MySQL relational database",
        "category": "data_analytics", "icon": "🐬", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "host", "label": "Host", "placeholder": "localhost", "type": "text", "required": True},
            {"name": "port", "label": "Port", "placeholder": "3306", "type": "number", "required": True},
            {"name": "database", "label": "Database", "placeholder": "mydb", "type": "text", "required": True},
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "password", "label": "Password", "type": "password", "required": True},
        ],
    },
    {
        "id": "mssql", "name": "Microsoft SQL Server", "description": "Microsoft SQL Server database",
        "category": "data_analytics", "icon": "🗄️", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "server", "label": "Server", "placeholder": "localhost", "type": "text", "required": True},
            {"name": "port", "label": "Port", "placeholder": "1433", "type": "number", "required": False},
            {"name": "database", "label": "Database", "type": "text", "required": True},
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "password", "label": "Password", "type": "password", "required": True},
            {"name": "encrypt", "label": "Encrypt Connection", "type": "boolean", "required": False},
        ],
    },
    {
        "id": "snowflake", "name": "Snowflake", "description": "Snowflake cloud data warehouse",
        "category": "data_analytics", "icon": "❄️", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "account", "label": "Account", "placeholder": "xy12345.us-east-1", "type": "text", "required": True},
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "password", "label": "Password", "type": "password", "required": True},
            {"name": "warehouse", "label": "Warehouse", "placeholder": "COMPUTE_WH", "type": "text", "required": True},
            {"name": "database", "label": "Database", "type": "text", "required": True},
            {"name": "schema", "label": "Schema", "placeholder": "PUBLIC", "type": "text", "required": False},
            {"name": "role", "label": "Role", "placeholder": "ACCOUNTADMIN", "type": "text", "required": False},
        ],
    },
    {
        "id": "mongodb", "name": "MongoDB", "description": "MongoDB NoSQL database",
        "category": "data_analytics", "icon": "🍃", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "connectionString", "label": "Connection String", "placeholder": "mongodb://localhost:27017", "type": "text", "required": False},
            {"name": "host", "label": "Host", "placeholder": "localhost", "type": "text", "required": False},
            {"name": "port", "label": "Port", "placeholder": "27017", "type": "number", "required": False},
            {"name": "database", "label": "Database", "type": "text", "required": True},
            {"name": "username", "label": "Username", "type": "text", "required": False},
            {"name": "password", "label": "Password", "type": "password", "required": False},
        ],
    },
    {
        "id": "mcp", "name": "MCP Server", "description": "Connect to Model Context Protocol servers for tools and resources",
        "category": "integration", "icon": "🔗", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "endpoint_url", "label": "Endpoint URL", "placeholder": "http://localhost:3000/sse", "type": "text", "required": True},
            {"name": "transport", "label": "Transport", "type": "select", "required": False, "options": ["sse", "streamable-http"]},
            {"name": "headers", "label": "Headers (JSON)", "placeholder": '{"Authorization": "Bearer ..."}', "type": "textarea", "required": False},
        ],
    },
    {
        "id": "api_integration", "name": "API Connector", "description": "Connect to REST APIs, GraphQL, and webhooks",
        "category": "integration", "icon": "🔌", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "baseUrl", "label": "API Base URL", "placeholder": "https://api.example.com", "type": "text", "required": False},
            {"name": "apiKey", "label": "API Key", "placeholder": "Optional API key", "type": "password", "required": False},
        ],
    },
    {
        "id": "file_operations", "name": "File Operations", "description": "Read, write, and manage files",
        "category": "utilities", "icon": "📁", "enabled": True, "status": "active",
        "credentialFields": [
            {"name": "basePath", "label": "Base Directory Path", "placeholder": "/path/to/files", "type": "text", "required": False},
        ],
    },
    # NOTE: Slack and Twitter/X were removed — social channels are managed
    # via Connections (routes/connections.tsx) and crew channel bindings,
    # not as persona types.
]


async def _seed_persona_types(db):
    """Seed default persona types — insert missing, update existing, remove stale."""
    try:
        collection = db["persona_types"]
        valid_ids = {pt["id"] for pt in _DEFAULT_PERSONA_TYPES}
        seeded = 0
        updated = 0

        for pt in _DEFAULT_PERSONA_TYPES:
            existing = await collection.find_one({"_id": pt["id"]})
            if existing is None:
                doc = {**pt, "_id": pt["id"]}
                await collection.insert_one(doc)
                seeded += 1
            else:
                # Update existing types to add credentialFields and other changes
                await collection.update_one({"_id": pt["id"]}, {"$set": pt})
                updated += 1

        # Remove stale types (e.g. github, gitlab) that are no longer in the default set
        all_docs = await collection.find({}).to_list(length=100)
        removed = 0
        for doc in all_docs:
            if doc.get("_id") not in valid_ids and doc.get("id") not in valid_ids:
                await collection.delete_one({"_id": doc["_id"]})
                removed += 1

        logger.info(
            "Persona types: %d seeded, %d updated, %d removed (total: %d)",
            seeded, updated, removed, len(_DEFAULT_PERSONA_TYPES),
        )
    except Exception:
        logger.exception("Failed to seed persona types")


# ---------------------------------------------------------------------------
# Agent library seeding (exclude engineering — desktop doesn't support it)
# ---------------------------------------------------------------------------
_EXCLUDED_AGENT_CATEGORIES = {"engineering"}

# Category icons for display in the agent library UI
_CATEGORY_ICONS = {
    "c_suite": "crown",
    "data_analytics": "bar-chart-2",
    "design": "palette",
    "finance_operations": "calculator",
    "hr_people": "users",
    "it_security": "shield",
    "legal_compliance": "scale",
    "marketing_sales": "megaphone",
    "product_management": "layout",
    "social_engagement": "message-circle",
    "specialized": "star",
    "startup_venture": "rocket",
    "coder_companion": "code",
}


async def _seed_agent_library(db):
    """
    Seed workspace agents from the on-disk markdown library.

    Reads each .md file via AgentLibraryService, skips the 'engineering'
    category, and upserts lightweight catalog entries into the
    ``workspace_agents`` collection.  Missing agents are inserted; existing
    ones are left untouched.
    """
    try:
        collection = db["workspace_agents"]

        # Clean up phase-4 PR 6 stale data: PR 6 added the coder-companion
        # agent folder before its category was registered in CATEGORY_MAP, so
        # early seeds stored the literal "coder-companion" string. That value
        # fails AgentBlueprint enum validation on read.  Purge those rows so
        # the corrected seed below recreates them with the canonical
        # "coder_companion" category.
        try:
            purged = await collection.delete_many({"category": "coder-companion"})
            if getattr(purged, "deleted_count", 0):
                logger.info(
                    "Purged %s stale coder-companion agent rows",
                    purged.deleted_count,
                )
        except Exception:
            logger.exception("Failed to purge stale coder-companion rows")

        from services.workspace.agent_library_service import AgentLibraryService
        library = AgentLibraryService()

        # Use the env var directly (class attr may have been resolved before we set it)
        from pathlib import Path
        library_path = Path(os.environ.get("AGENT_LIBRARY_PATH", library.LIBRARY_PATH))
        if not library_path.exists():
            logger.warning("Agent library not found at %s — skipping seed", library_path)
            return

        seeded = 0
        skipped = 0
        for category_dir in sorted(library_path.iterdir()):
            if not category_dir.is_dir():
                continue

            # Map folder name to category enum
            folder_name = category_dir.name
            category = library.CATEGORY_MAP.get(folder_name, folder_name)

            # Skip excluded categories (engineering)
            if folder_name in _EXCLUDED_AGENT_CATEGORIES or category in _EXCLUDED_AGENT_CATEGORIES:
                continue

            for md_file in sorted(category_dir.glob("*.md")):
                try:
                    parsed = library.parse_agent_md(str(md_file))

                    agent_id = f"{category}-{parsed['slug']}"

                    # Skip if already present
                    existing = await collection.find_one({"_id": agent_id})
                    if existing is not None:
                        skipped += 1
                        continue

                    # Use Role Definition / Identity section as description
                    # if the parser couldn't extract a standalone paragraph
                    description = parsed["description"]
                    if not description:
                        sections = parsed.get("sections", {})
                        for key in ("Role Definition", "Identity", "Overview"):
                            if key in sections:
                                # Take first sentence or first 300 chars
                                raw = sections[key].strip().split("\n\n")[0]
                                import re as _re
                                sentences = _re.split(r'(?<=[.!?])\s+', raw)
                                description = sentences[0] if sentences else raw[:300]
                                break

                    doc = {
                        "_id": agent_id,
                        "agent_id": agent_id,
                        "name": parsed["name"],
                        "slug": parsed["slug"],
                        "description": description[:500],
                        "category": category,
                        "category_label": library.CATEGORY_LABELS.get(category, category),
                        "icon": _CATEGORY_ICONS.get(category, "bot"),
                        "capabilities": parsed.get("capabilities", [])[:10],
                        "frameworks": parsed.get("frameworks", [])[:10],
                        "system_prompt": parsed.get("full_content", ""),
                        "is_active": True,
                        "is_system": True,
                        "source": "library",
                        "created_by": "system",
                        "created_at": datetime.utcnow().isoformat() + "Z",
                        # PR 2 (phase 4): library agents are all prompt-only.
                        # Database / web / mcp / api / file kinds come from
                        # promoted personas (see personas_to_agent_types
                        # migration).
                        "kind": "prompt",
                    }

                    await collection.insert_one(doc)
                    seeded += 1
                except Exception:
                    logger.warning("Failed to parse agent: %s", md_file.name, exc_info=True)

        logger.info("Agent library: seeded %d new, %d existing (excluded: %s)", seeded, skipped, _EXCLUDED_AGENT_CATEGORIES)
    except Exception:
        logger.exception("Failed to seed agent library")


# ---------------------------------------------------------------------------
# Local model seeding — register downloaded GGUFs in the models collection
# ---------------------------------------------------------------------------
async def _seed_blueprints(db):
    """
    Seed blueprints from the on-disk markdown library.

    Reads each .md file via BlueprintLibraryService and upserts into
    the ``blueprints`` collection. Existing blueprints are left untouched.
    """
    try:
        from services.blueprint_library_service import BlueprintLibraryService
        library = BlueprintLibraryService()

        from pathlib import Path as _Path
        library_path = _Path(os.environ.get("BLUEPRINT_LIBRARY_PATH", library.LIBRARY_PATH))
        if not library_path.exists():
            logger.warning("Blueprint library not found at %s — skipping seed", library_path)
            return

        collection = db["blueprints"]
        seeded = await library.sync_library_to_db(collection)
        logger.info("Blueprint library: seeded %d new blueprint(s)", seeded)
    except Exception:
        logger.exception("Failed to seed blueprint library")


async def _seed_local_models(db):
    """Check for downloaded GGUF models and ensure they have DB entries."""
    try:
        from services.local_model_seeder import sync_local_models_to_db
        synced = await sync_local_models_to_db(db)
        if synced:
            logger.info("Seeded %d local model config(s)", synced)
    except Exception:
        logger.exception("Failed to seed local model configs")


async def _seed_cloud_models(db):
    """Register cloud-provider model entries for any connected providers."""
    try:
        from services.cloud_model_seeder import sync_cloud_models_to_db
        synced = await sync_cloud_models_to_db(db)
        if synced:
            logger.info("Seeded %d cloud model entry/entries", synced)
    except Exception:
        logger.exception("Failed to seed cloud model entries")


async def _seed_crew_templates(db):
    """
    Seed crew templates from the on-disk JSON library into the
    ``crew_templates`` collection (separate from user-created ``crews``).
    """
    try:
        from services.crew_template_seeder import CrewTemplateSeeder
        seeder = CrewTemplateSeeder()

        from pathlib import Path as _Path
        library_path = _Path(os.environ.get("CREW_TEMPLATE_LIBRARY_PATH", seeder.LIBRARY_PATH))
        if not library_path.exists():
            logger.warning("Crew template library not found at %s — skipping seed", library_path)
            return

        collection = db["crew_templates"]
        seeded = await seeder.sync_library_to_db(collection)
        logger.info("Crew template library: seeded %d new template(s)", seeded)
    except Exception:
        logger.exception("Failed to seed crew template library")


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    """Initialise database and scheduler adapters."""
    try:
        # Set library paths (defaults to <repo-root>/<library>/)
        _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if "AGENT_LIBRARY_PATH" not in os.environ:
            os.environ["AGENT_LIBRARY_PATH"] = os.path.join(_repo_root, "agent-library")
        if "BLUEPRINT_LIBRARY_PATH" not in os.environ:
            os.environ["BLUEPRINT_LIBRARY_PATH"] = os.path.join(_repo_root, "blueprints")
        if "CREW_TEMPLATE_LIBRARY_PATH" not in os.environ:
            os.environ["CREW_TEMPLATE_LIBRARY_PATH"] = os.path.join(_repo_root, "backend", "crew-templates")

        # Database adapter (SQLite)
        adapter = await get_database_adapter()
        app.state.db_adapter = adapter

        # DatabaseProxy wraps the adapter to look like AsyncIOMotorDatabase
        proxy = DatabaseProxy(adapter)
        app.state.db = proxy

        # Monkey-patch database module so ALL code that calls
        # get_database() / get_db() receives our proxy instead of
        # attempting a real MongoDB connection.
        async def _desktop_get_database():
            return app.state.db

        database.get_database = _desktop_get_database
        database.get_db = _desktop_get_database
        database._async_db = proxy  # module-level cache

        # Scheduler adapter (APScheduler)
        scheduler = await get_scheduler_adapter()
        app.state.scheduler = scheduler

        is_lite = app_settings.get_active_edition() == "lite"

        # Seed default persona types if empty
        await _seed_persona_types(proxy)

        if not is_lite:
            # Seed agent library (business agents, exclude engineering)
            await _seed_agent_library(proxy)

            # Seed blueprint library
            await _seed_blueprints(proxy)

            # Seed crew templates library
            await _seed_crew_templates(proxy)

            # Seed example crews (ready-to-run samples) for the desktop user
            try:
                from services.sample_crew_seeder import seed_sample_crews
                n_samples = await seed_sample_crews(proxy)
                if n_samples:
                    logger.info("Seeded %d sample crew(s)", n_samples)
            except Exception:
                logger.exception("Failed to seed sample crews")
        else:
            logger.info("Lite ('Vesper') edition active — skipping 113-agent & crew seeding for fast startup")

        # Seed model configs for any already-downloaded local GGUF models
        await _seed_local_models(proxy)

        # Background OTA catalog refresh (on startup + every 24h; skips if Airplane Lock is on)
        async def _daily_ota_catalog_loop():
            import asyncio as _asyncio
            from services.hf_hub_discovery import refresh_ota_catalog
            while True:
                try:
                    res = await refresh_ota_catalog()
                    logger.info(
                        "OTA catalog sync (%s): merged %s model(s), total=%s",
                        res.get("source"),
                        res.get("merged_count"),
                        res.get("total_catalog_models"),
                    )
                except Exception as exc:
                    logger.debug("OTA catalog background sync skipped: %s", exc)
                await _asyncio.sleep(86400)

        import asyncio as _asyncio
        app.state.ota_sync_task = _asyncio.create_task(_daily_ota_catalog_loop())

        # Seed cloud model entries for any connected cloud providers
        await _seed_cloud_models(proxy)

        # Phase 3 PR 1: backfill crew.connection_bindings / triggers / approval_required
        try:
            from services.migrations.unify_connections_migration import (
                run_unify_connections_migration,
            )
            await run_unify_connections_migration(proxy)
        except Exception:
            logger.exception("unify_connections migration failed; continuing startup")

        # Phase 4 PR 2: fold personas into workspace_agents with `kind`
        try:
            from services.migrations.personas_to_agent_types_migration import (
                run_personas_to_agent_types_migration,
            )
            await run_personas_to_agent_types_migration(proxy)
        except Exception:
            logger.exception("personas_to_agent_types migration failed; continuing startup")

        # Phase 4 PR 3: collapse workspace_projects → crews(kind=project)
        # and workspace_executions → crew_runs.
        try:
            from services.migrations.workspace_to_crew_runs_migration import (
                run_workspace_to_crew_runs_migration,
            )
            await run_workspace_to_crew_runs_migration(proxy)
        except Exception:
            logger.exception("workspace_to_crew_runs migration failed; continuing startup")

        # PR 14: backfill workflow_mode on coder_projects rows.
        try:
            from services.migrations.coder_workflow_mode_migration import (
                run_coder_workflow_mode_migration,
            )
            await run_coder_workflow_mode_migration(proxy)
        except Exception:
            logger.exception("coder_workflow_mode migration failed; continuing startup")

        # Vesper v1.2: retire legacy social distribution approvals left in approval_queue
        try:
            from services.approval_service import ApprovalService

            retired_approvals = await ApprovalService(proxy).retire_legacy_social_approvals()
            if retired_approvals > 0:
                logger.info(
                    "Retired %d legacy social distribution approval(s)",
                    retired_approvals,
                )
        except Exception:
            logger.exception("Failed retiring legacy social approvals; continuing startup")

        # Attach Local DLP log redaction filter (checks redact_logs dynamically)
        try:
            from services.dlp_service import DlpLogFilter
            root_logger = logging.getLogger()
            if not any(isinstance(f, DlpLogFilter) for f in root_logger.filters):
                root_logger.addFilter(DlpLogFilter())
        except Exception:
            logger.debug("Failed to attach DlpLogFilter", exc_info=True)

        # Personal Docs scheduler — sweeps folder mappings on a fixed tick
        try:
            from repositories.index_job_repository import IndexJobRepository
            from services.personal_docs_scheduler import PersonalDocsScheduler

            await IndexJobRepository(proxy).reset_orphans()
            app.state.personal_docs_scheduler = PersonalDocsScheduler(proxy)
            await app.state.personal_docs_scheduler.start()
        except Exception:
            logger.exception(
                "PersonalDocsScheduler failed to start — continuing startup"
            )

        # Scheduled jobs (cron-based posts + crew runs)
        from services.scheduler_service import SchedulerService
        scheduler_service = SchedulerService(proxy, scheduler)
        await scheduler_service.load_all()
        app.state.scheduler_service = scheduler_service

        # Phase 3 PR 3: scheduled_runner registers crew.triggers[type=scheduled]
        # Only active when UNIFIED_CREWS=on so legacy flows keep running by default.
        try:
            from services.feature_flags import unified_crews_enabled
            if unified_crews_enabled():
                from services.scheduled_runner import ScheduledRunner
                runner = ScheduledRunner(proxy, scheduler)
                await runner.load_all()
                app.state.scheduled_runner = runner
        except Exception:
            logger.exception("ScheduledRunner failed to load — continuing startup")

        logger.info("ContextuAI Solo backend ready")

    except Exception:
        logger.exception("Failed to start ContextuAI Solo backend")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully release database and scheduler resources."""
    try:
        await close_database_adapter()
        logger.info("Database adapter closed")
    except Exception:
        logger.exception("Error closing database adapter")

    try:
        await stop_scheduler_adapter()
        logger.info("Scheduler adapter closed")
    except Exception:
        logger.exception("Error closing scheduler adapter")

    try:
        sched = getattr(app.state, "personal_docs_scheduler", None)
        if sched:
            await sched.stop()
    except Exception:
        logger.exception("Error stopping PersonalDocsScheduler")


# ---------------------------------------------------------------------------
# Dependency override
# ---------------------------------------------------------------------------
from database import get_db  # noqa: E402
from services.auth_service import get_current_user, get_current_user_optional  # noqa: E402


async def _get_desktop_db():
    return app.state.db


# Desktop user — always authenticated as admin, no JWT required
_DESKTOP_USER = {
    "user_id": "desktop-user",
    "email": "user@contextuai-solo.local",
    "role": "admin",
    "organization": "solo",
    "department": None,
    "auth_type": "desktop",
    "scopes": ["*"],
}


async def _desktop_get_current_user():
    return _DESKTOP_USER


app.dependency_overrides[get_db] = _get_desktop_db
app.dependency_overrides[get_current_user] = _desktop_get_current_user
app.dependency_overrides[get_current_user_optional] = _desktop_get_current_user


# ---------------------------------------------------------------------------
# Health & root endpoints
# ---------------------------------------------------------------------------
@app.get("/")
def read_root():
    uptime_seconds = int(time.time() - APP_START_TIME)
    return {
        "service": "contextuai-solo",
        "status": "healthy",
        "mode": "desktop",
        "version": "solo-1.0.0",
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/health")
@app.get("/api/v1/health")
def health_check():
    uptime_seconds = int(time.time() - APP_START_TIME)
    return {
        "status": "healthy",
        "mode": "desktop",
        "version": "solo-1.0.0",
        "service": "contextuai-solo",
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/api/v1/desktop/reseed")
async def reseed_data():
    """
    Re-seed persona types and agent library.
    Drops existing data and re-creates from the on-disk library.
    Useful after updates to agent markdown files or category mappings.
    """
    try:
        db = app.state.db

        # Clear and re-seed persona types
        pt_collection = db["persona_types"]
        await pt_collection.delete_many({})
        for pt in _DEFAULT_PERSONA_TYPES:
            doc = {**pt, "_id": pt["id"]}
            await pt_collection.insert_one(doc)

        # Clear and re-seed agent library
        agent_collection = db["workspace_agents"]
        await agent_collection.delete_many({})
        await _seed_agent_library(db)

        # Clear and re-seed blueprint library
        bp_collection = db["blueprints"]
        await bp_collection.delete_many({})
        await _seed_blueprints(db)

        # Clear and re-seed crew templates library
        ct_collection = db["crew_templates"]
        await ct_collection.delete_many({})
        await _seed_crew_templates(db)

        pt_count = await pt_collection.count_documents({})
        agent_count = await agent_collection.count_documents({})
        bp_count = await bp_collection.count_documents({})
        ct_count = await ct_collection.count_documents({})

        return {
            "status": "success",
            "persona_types_seeded": pt_count,
            "agents_seeded": agent_count,
            "blueprints_seeded": bp_count,
            "crew_templates_seeded": ct_count,
        }
    except Exception as e:
        logger.exception("Reseed failed")
        return {"status": "error", "detail": str(e)}


@app.get("/api/v1/desktop/edition")
async def get_desktop_edition():
    """Return current desktop edition ('lite' = Vesper, 'solo' = ContextuAI Solo) (SPEC-33)."""
    edition = app_settings.get_active_edition()
    is_lite = edition == "lite"
    return {
        "edition": edition,
        "brand_name": "Vesper" if is_lite else "ContextuAI Solo",
        "tagline": (
            "Quiet, sovereign intelligence on your metal."
            if is_lite
            else "Your autonomous AI workforce on your desktop."
        ),
        "features": {
            "crews_enabled": not is_lite,
            "agents_library_enabled": not is_lite,
            "channels_enabled": not is_lite,
            "coder_enabled": not is_lite,
            "local_models_enabled": True,
            "folder_rag_enabled": True,
            "connectors_mcp_enabled": True,
            "local_server_enabled": True,
            "privacy_shield_enabled": True,
        },
    }


@app.post("/api/v1/desktop/unlock-solo")
async def unlock_solo_edition():
    """Graduate from Lite ('Vesper') to full ContextuAI Solo in one click (SPEC-33).

    Flips the active edition to 'solo' and seeds the agent library, blueprints,
    and crew templates if not already present, while preserving all downloaded
    GGUF models and SQLite data.
    """
    previous = app_settings.get_active_edition()
    current = app_settings.set_active_edition("solo")
    seeded_agents = 0
    seeded_blueprints = 0

    db = getattr(app.state, "db", None)
    if db is not None:
        try:
            await _seed_persona_types(db)
            await _seed_agent_library(db)
            await _seed_blueprints(db)
            await _seed_crew_templates(db)
            seeded_agents = await db["workspace_agents"].count_documents({})
            seeded_blueprints = await db["blueprints"].count_documents({})
        except Exception:
            logger.exception("Non-fatal error seeding library during unlock-solo")

    return {
        "status": "unlocked",
        "unlocked": True,
        "previous_edition": previous,
        "edition": current,
        "brand_name": "ContextuAI Solo",
        "agents_available": seeded_agents,
        "blueprints_available": seeded_blueprints,
        "agents_seeded": seeded_agents,
        "blueprints_seeded": seeded_blueprints,
    }


@app.post("/api/v1/desktop/switch-lite")
async def switch_to_lite_edition():
    """Switch active desktop edition to Lite ('Vesper') mode (SPEC-33)."""
    previous = app_settings.get_active_edition()
    current = app_settings.set_active_edition("lite")
    return {
        "status": "switched",
        "previous_edition": previous,
        "edition": current,
        "brand_name": "Vesper",
    }
