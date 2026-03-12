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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from routers.users import router as users_router
from routers.analytics import router as analytics_router
from routers.channels import router as channels_router
from routers.distribution import router as distribution_router
from routers.desktop_oauth import router as desktop_oauth_router
from routers.models import router as models_router
from routers.local_models import router as local_models_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
APP_START_TIME = time.time()

app = FastAPI(title="ContextuAI Solo")

# CORS — allow all origins (desktop app, no security risk)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(users_router)
app.include_router(analytics_router)
app.include_router(channels_router)
app.include_router(distribution_router)
app.include_router(desktop_oauth_router)
app.include_router(models_router)
app.include_router(local_models_router)


# ---------------------------------------------------------------------------
# Default persona types for desktop mode
# ---------------------------------------------------------------------------
_DEFAULT_PERSONA_TYPES = [
    {"id": "generic", "name": "Nexus Agent", "description": "General-purpose AI assistant", "category": "general", "icon": "🤖", "enabled": True, "status": "active"},
    {"id": "web_search", "name": "Web Researcher", "description": "Search the web and extract information", "category": "utilities", "icon": "🔍", "enabled": True, "status": "active"},
    {"id": "postgresql", "name": "PostgreSQL", "description": "PostgreSQL relational database", "category": "data_analytics", "icon": "🐘", "enabled": True, "status": "active"},
    {"id": "mysql", "name": "MySQL", "description": "MySQL relational database", "category": "data_analytics", "icon": "🐬", "enabled": True, "status": "active"},
    {"id": "mssql", "name": "Microsoft SQL Server", "description": "Microsoft SQL Server database", "category": "data_analytics", "icon": "🗄️", "enabled": True, "status": "active"},
    {"id": "snowflake", "name": "Snowflake", "description": "Snowflake cloud data warehouse", "category": "data_analytics", "icon": "❄️", "enabled": True, "status": "active"},
    {"id": "mongodb", "name": "MongoDB", "description": "MongoDB NoSQL database", "category": "data_analytics", "icon": "🍃", "enabled": True, "status": "active"},
    {"id": "mcp", "name": "MCP Server", "description": "Connect to Model Context Protocol servers for tools and resources", "category": "integration", "icon": "🔗", "enabled": True, "status": "active"},
    {"id": "api_integration", "name": "API Connector", "description": "Connect to REST APIs, GraphQL, and webhooks", "category": "integration", "icon": "🔌", "enabled": True, "status": "active"},
    {"id": "file_operations", "name": "File Operations", "description": "Read, write, and manage files", "category": "utilities", "icon": "📁", "enabled": True, "status": "active"},
    {"id": "slack", "name": "Slack", "description": "Slack messaging platform", "category": "communication", "icon": "💬", "enabled": True, "status": "active"},
    {"id": "twitter", "name": "Twitter / X", "description": "Post and manage content on Twitter/X", "category": "communication", "icon": "🐦", "enabled": True, "status": "active"},
]


async def _seed_persona_types(db):
    """Seed default persona types, inserting any that are missing."""
    try:
        collection = db["persona_types"]
        seeded = 0
        for pt in _DEFAULT_PERSONA_TYPES:
            existing = await collection.find_one({"_id": pt["id"]})
            if existing is None:
                doc = {**pt, "_id": pt["id"]}
                await collection.insert_one(doc)
                seeded += 1

        if seeded:
            logger.info("Seeded %d missing persona types (total: %d)", seeded, len(_DEFAULT_PERSONA_TYPES))
        else:
            logger.info("All %d persona types already present", len(_DEFAULT_PERSONA_TYPES))
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
    "specialized": "star",
    "startup_venture": "rocket",
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
async def _seed_local_models(db):
    """Check for downloaded GGUF models and ensure they have DB entries."""
    try:
        from routers.local_models import AVAILABLE_MODELS, CHAT_DIR
        collection = db["models"]
        seeded = 0
        for model in AVAILABLE_MODELS:
            file_path = CHAT_DIR / model["file"]
            if not file_path.is_file():
                continue
            model_id = f"local-{model['id']}"
            existing = await collection.find_one({"_id": model_id})
            if existing:
                continue
            doc = {
                "_id": model_id,
                "name": model["name"],
                "provider": "local",
                "model": model_id,
                "max_tokens": "4096",
                "enabled": True,
                "description": f"Local {model['name']} model (GGUF, runs on CPU)",
                "capabilities": ["chat"],
                "input_cost": 0,
                "output_cost": 0,
                "context_window": 4096,
                "supports_vision": False,
                "supports_function_calling": model.get("supports_tools", False),
                "model_metadata": {
                    "runtime": "local",
                    "local_model_file": model["file"],
                    "ram_gb": model.get("ram_gb"),
                    "tier": model.get("tier"),
                },
            }
            await collection.insert_one(doc)
            seeded += 1
        if seeded:
            logger.info("Seeded %d local model config(s)", seeded)
    except Exception:
        logger.exception("Failed to seed local model configs")


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    """Initialise database and scheduler adapters."""
    try:
        # Set agent library path (defaults to <repo-root>/agent-library/)
        if "AGENT_LIBRARY_PATH" not in os.environ:
            _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            os.environ["AGENT_LIBRARY_PATH"] = os.path.join(_repo_root, "agent-library")

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

        # Seed default persona types if empty
        await _seed_persona_types(proxy)

        # Seed agent library (business agents, exclude engineering)
        await _seed_agent_library(proxy)

        # Seed model configs for any already-downloaded local GGUF models
        await _seed_local_models(proxy)

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

        pt_count = await pt_collection.count_documents({})
        agent_count = await agent_collection.count_documents({})

        return {
            "status": "success",
            "persona_types_seeded": pt_count,
            "agents_seeded": agent_count,
        }
    except Exception as e:
        logger.exception("Reseed failed")
        return {"status": "error", "detail": str(e)}
