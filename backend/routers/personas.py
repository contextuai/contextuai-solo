from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid
import time
import logging
import httpx
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

# Import database and repositories
from database import get_database
from repositories import PersonaRepository, PersonaTypeRepository

# Import database connectors
from services.postgres_connector import PostgreSQLConnector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/personas", tags=["personas"])


# Dependency functions for repositories
async def get_persona_repository(db: AsyncIOMotorDatabase = Depends(get_database)) -> PersonaRepository:
    """Get PersonaRepository instance with database dependency."""
    return PersonaRepository(db)


async def get_persona_type_repository(db: AsyncIOMotorDatabase = Depends(get_database)) -> PersonaTypeRepository:
    """Get PersonaTypeRepository instance with database dependency."""
    return PersonaTypeRepository(db)


# Pydantic models for validation
class Persona(BaseModel):
    name: str = Field(..., min_length=1)
    description: str
    persona_type_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    credentials: Dict[str, Any] = Field(default_factory=dict)
    category: Optional[str] = None
    icon: Optional[str] = None
    status: str = Field(default="active", pattern="^(active|inactive)$")


class PersonaResponse(BaseModel):
    success: bool
    personas: List[Dict[str, Any]]
    total_count: int
    last_updated: str
    source: str = "mongodb"
    error: Optional[str] = None


class TestConnectionRequest(BaseModel):
    persona_type_id: str = Field(..., min_length=1, description="Persona type (e.g., postgresql_database, github, gitlab)")
    credentials: Dict[str, Any] = Field(..., description="Connection credentials (DB: host/port/database/username/password, SCM: token)")


@router.get("", response_model=PersonaResponse)
@router.get("/", response_model=PersonaResponse)
async def list_personas(
    user_id: Optional[str] = None,
    persona_type_id: Optional[str] = None,
    status: Optional[str] = None,
    persona_repo: PersonaRepository = Depends(get_persona_repository)
):
    """List all persona instances with optional filtering"""
    try:
        if user_id and persona_type_id:
            # Use repository method for user + persona type filtering
            personas = await persona_repo.get_by_user_and_type(
                user_id=user_id,
                persona_type_id=persona_type_id,
                status=status
            )
        elif user_id:
            # Query by user_id
            personas = await persona_repo.get_by_user(
                user_id=user_id,
                status=status,
                include_credentials=False
            )
        elif persona_type_id:
            # Query by persona type
            personas = await persona_repo.get_by_type(
                persona_type_id=persona_type_id,
                status=status
            )
        else:
            # Get all personas with optional status filter
            filter_query = {}
            if status:
                filter_query["status"] = status.lower()

            personas = await persona_repo.get_all(filter=filter_query if filter_query else None)

            # Mask credentials in response (get_all doesn't mask by default)
            for persona in personas:
                if "credentials" in persona:
                    persona["credentials"] = {"_encrypted": True}

        return PersonaResponse(
            success=True,
            personas=personas,
            total_count=len(personas),
            last_updated=datetime.utcnow().isoformat() + "Z"
        )
    except Exception as e:
        return PersonaResponse(
            success=False,
            personas=[],
            total_count=0,
            last_updated=datetime.utcnow().isoformat() + "Z",
            error=str(e)
        )


@router.get("/{persona_id}", response_model=Dict[str, Any])
async def get_persona(
    persona_id: str,
    include_credentials: bool = False,
    persona_repo: PersonaRepository = Depends(get_persona_repository)
):
    """Get a specific persona instance by ID"""
    try:
        persona = await persona_repo.get_by_id(
            persona_id=persona_id,
            include_credentials=include_credentials
        )

        if persona is None:
            raise HTTPException(status_code=404, detail="Persona not found")

        return persona
    except HTTPException:
        raise
    except ValueError as e:
        # Invalid ObjectId format
        raise HTTPException(status_code=400, detail=f"Invalid persona ID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Dict[str, Any])
async def create_persona(
    persona: Persona,
    background_tasks: BackgroundTasks,
    persona_repo: PersonaRepository = Depends(get_persona_repository),
    persona_type_repo: PersonaTypeRepository = Depends(get_persona_type_repository)
):
    """Create a new persona instance"""
    try:
        # Validate that the persona type exists
        # First try by string ID field, then by ObjectId
        persona_type = await persona_type_repo.get_by_string_id(persona.persona_type_id)
        if persona_type is None:
            try:
                persona_type = await persona_type_repo.get_by_id(persona.persona_type_id)
            except ValueError:
                pass  # Invalid ObjectId format, that's fine

        if persona_type is None:
            raise HTTPException(
                status_code=400,
                detail=f"Persona type '{persona.persona_type_id}' does not exist"
            )

        # Convert Pydantic model to dict
        persona_dict = persona.model_dump()

        # Create the persona using repository (timestamps are handled by BaseRepository)
        created_persona = await persona_repo.create(persona_dict)

        # Auto-initialize business terms for database personas (fire-and-forget)
        persona_type_lower = persona.persona_type_id.lower()
        db_keywords = ["postgresql", "postgres", "mysql", "mssql", "sqlserver", "snowflake"]
        if any(kw in persona_type_lower for kw in db_keywords):
            background_tasks.add_task(
                _auto_init_business_terms,
                str(created_persona.get("id", created_persona.get("_id", ""))),
                persona.name,
                persona.description,
            )

        return created_persona
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{persona_id}", response_model=Dict[str, Any])
async def update_persona(
    persona_id: str,
    updates: Dict[str, Any],
    persona_repo: PersonaRepository = Depends(get_persona_repository)
):
    """Update an existing persona instance"""
    try:
        # Check if persona exists
        existing_persona = await persona_repo.get_by_id(persona_id, include_credentials=True)
        if existing_persona is None:
            raise HTTPException(status_code=404, detail="Persona not found")

        # Don't allow changing id, user_id, or created_at (repository handles this)
        updates.pop("id", None)
        updates.pop("_id", None)

        # Update the persona using repository (updated_at is handled by BaseRepository)
        updated_persona = await persona_repo.update(persona_id, updates)

        if updated_persona is None:
            raise HTTPException(status_code=404, detail="Persona not found")

        return updated_persona
    except HTTPException:
        raise
    except ValueError as e:
        # Invalid ObjectId format
        raise HTTPException(status_code=400, detail=f"Invalid persona ID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{persona_id}")
async def delete_persona(
    persona_id: str,
    persona_repo: PersonaRepository = Depends(get_persona_repository)
):
    """Delete a persona instance"""
    try:
        # Delete using repository
        deleted = await persona_repo.delete(persona_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Persona not found")

        return {"message": "Persona deleted successfully", "id": persona_id}
    except HTTPException:
        raise
    except ValueError as e:
        # Invalid ObjectId format
        raise HTTPException(status_code=400, detail=f"Invalid persona ID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-connection", response_model=Dict[str, Any])
async def test_connection(request: TestConnectionRequest):
    """
    Test database connection before creating a persona.
    Validates credentials and returns connection status without saving to MongoDB.

    Args:
        request: TestConnectionRequest with persona_type_id and credentials

    Returns:
        Connection test result with success status, response time, database version, or error
    """
    try:
        persona_type_lower = request.persona_type_id.lower()

        # --- SCM persona types (GitHub, GitLab) ---
        if "github" in persona_type_lower or "gitlab" in persona_type_lower:
            token = request.credentials.get("token", "")
            if not token:
                return {"success": False, "error": "Token is required"}

            is_github = "github" in persona_type_lower
            api_url = "https://api.github.com/user" if is_github else None

            if not is_github:
                # GitLab: use custom base_url or default to gitlab.com
                base_url = (request.credentials.get("base_url") or "https://gitlab.com").rstrip("/")
                api_url = f"{base_url}/api/v4/user"

            start_time = time.time()
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    headers = {"Authorization": f"Bearer {token}"} if not is_github else {
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    }
                    resp = await client.get(api_url, headers=headers)
                response_time = round((time.time() - start_time) * 1000)

                if resp.status_code == 200:
                    user_data = resp.json()
                    username = user_data.get("login") if is_github else user_data.get("username")
                    provider = "GitHub" if is_github else "GitLab"
                    return {
                        "success": True,
                        "message": f"Connected to {provider} as @{username}",
                        "response_time_ms": response_time,
                        "details": {"username": username, "provider": provider},
                    }
                elif resp.status_code == 401:
                    return {"success": False, "error": "Invalid or expired token"}
                elif resp.status_code == 403:
                    return {"success": False, "error": "Token lacks required permissions"}
                else:
                    return {"success": False, "error": f"API returned HTTP {resp.status_code}: {resp.text[:200]}"}
            except httpx.TimeoutException:
                return {"success": False, "error": "Connection timed out (10s)"}
            except httpx.ConnectError as e:
                return {"success": False, "error": f"Could not connect: {str(e)}"}

        # --- MCP Server persona type ---
        if "mcp" in persona_type_lower:
            endpoint_url = request.credentials.get("endpoint_url", "")
            if not endpoint_url:
                return {"success": False, "error": "MCP Server endpoint URL is required"}

            from services.tools.mcp_tools import MCPTools
            mcp = MCPTools(persona_id=f"test-{uuid.uuid4()}", credentials=request.credentials)
            result = await mcp.discover_tools()
            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Connected to MCP server — discovered {result['tool_count']} tools",
                    "response_time_ms": result.get("response_time_ms", 0),
                    "details": {
                        "server_info": result.get("server_info", {}),
                        "tool_count": result["tool_count"],
                        "tools": [t["name"] for t in result.get("tools", [])[:10]],
                    },
                }
            else:
                return {"success": False, "error": result.get("error", "MCP connection failed")}

        # --- Slack persona type ---
        if "slack" in persona_type_lower:
            bot_token = request.credentials.get("botToken", "")
            if not bot_token:
                return {"success": False, "error": "Slack bot token is required"}

            from services.tools.slack_tools import SlackTools
            slack = SlackTools(persona_id=f"test-{uuid.uuid4()}", credentials=request.credentials)
            result = await slack.test_connection()
            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Connected to Slack as @{result.get('bot_name', '')} in {result.get('team', '')}",
                    "response_time_ms": result.get("response_time_ms", 0),
                    "details": {"bot_name": result.get("bot_name"), "team": result.get("team")},
                }
            else:
                return {"success": False, "error": result.get("error", "Slack connection failed")}

        # --- Email persona type ---
        if "email" in persona_type_lower:
            imap_host = request.credentials.get("imap_host", "")
            email_addr = request.credentials.get("email", "")
            if not imap_host or not email_addr:
                return {"success": False, "error": "IMAP host and email address are required"}

            from services.tools.email_tools import EmailTools
            email_tools = EmailTools(persona_id=f"test-{uuid.uuid4()}", credentials=request.credentials)
            result = await email_tools.test_connection()
            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Connected to {result.get('imap_host', '')} as {result.get('email', '')}",
                    "response_time_ms": result.get("response_time_ms", 0),
                    "details": {"imap_host": result.get("imap_host"), "email": result.get("email")},
                }
            else:
                return {"success": False, "error": result.get("error", "Email connection failed")}

        # --- AWS Services persona type ---
        if "aws" in persona_type_lower:
            access_key = request.credentials.get("access_key_id", "")
            if not access_key:
                return {"success": False, "error": "AWS Access Key ID is required"}

            from services.tools.aws_tools import AWSTools
            aws = AWSTools(persona_id=f"test-{uuid.uuid4()}", credentials=request.credentials)
            result = await aws.test_connection()
            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Connected to AWS account {result.get('account_id', '')}",
                    "response_time_ms": result.get("response_time_ms", 0),
                    "details": {
                        "account_id": result.get("account_id"),
                        "arn": result.get("arn"),
                    },
                }
            else:
                return {"success": False, "error": result.get("error", "AWS connection failed")}

        # --- Database persona types ---

        # Database type mapping - extract db_type from persona_type_id
        db_type_map = {
            "postgresql": "postgresql",
            "postgres": "postgresql",
            "mysql": "mysql",
            "mssql": "mssql",
            "sqlserver": "mssql",
            "snowflake": "snowflake",
            "mongodb": "mongodb",
            "mongo": "mongodb",
        }

        # Find matching database type
        db_type = None
        for key, value in db_type_map.items():
            if key in persona_type_lower:
                db_type = value
                break

        if not db_type:
            return {
                "success": False,
                "error": f"Unsupported persona type '{request.persona_type_id}'. Supported: postgresql, mysql, mssql, snowflake, mongodb, github, gitlab, mcp_server, slack, email, aws_services"
            }

        # Generate temporary persona_id for connection testing
        temp_persona_id = f"test-{uuid.uuid4()}"

        if db_type == "postgresql":
            pg_connector = PostgreSQLConnector()
            test_credentials = {**request.credentials, "db_type": db_type}
            result = await pg_connector.test_connection(
                persona_id=temp_persona_id,
                credentials=test_credentials
            )
            return result

        elif db_type == "mysql":
            from services.mysql_connector import mysql_connector
            test_credentials = {**request.credentials, "db_type": db_type}
            result = await mysql_connector.test_connection(
                persona_id=temp_persona_id,
                credentials=test_credentials
            )
            return result

        elif db_type == "mssql":
            from services.mssql_connector import mssql_connector
            test_credentials = {**request.credentials, "db_type": db_type}
            result = await mssql_connector.test_connection(
                persona_id=temp_persona_id,
                credentials=test_credentials
            )
            return result

        elif db_type == "snowflake":
            from services.snowflake_connector import snowflake_connector
            test_credentials = {**request.credentials, "db_type": db_type}
            result = await snowflake_connector.test_connection(
                persona_id=temp_persona_id,
                credentials=test_credentials
            )
            return result

        elif db_type == "mongodb":
            from services.tools.mongodb_tools import MongoDBTools
            mongo = MongoDBTools(persona_id=temp_persona_id, credentials=request.credentials)
            result = await mongo.test_connection()
            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Connected to MongoDB {result.get('server_version', '')} — database: {result.get('database', '')}",
                    "response_time_ms": result.get("response_time_ms", 0),
                    "details": {
                        "server_version": result.get("server_version"),
                        "database": result.get("database"),
                    },
                }
            else:
                return {"success": False, "error": result.get("error", "MongoDB connection failed")}

        else:
            return {
                "success": False,
                "error": f"Database type '{db_type}' is recognized but connection test is not yet implemented"
            }

    except Exception as e:
        # Return error details
        return {
            "success": False,
            "error": str(e)
        }


async def _auto_init_business_terms(persona_id: str, name: str, description: str):
    """Auto-initialize business terminology for a newly created database persona."""
    try:
        from services.terminology_manager import terminology_manager

        # Detect domain from persona name/description
        text = f"{name} {description}".lower()
        domain_keywords = {
            "property": ["property", "real estate", "listing", "tenant", "lease"],
            "sales": ["sales", "order", "revenue", "customer", "invoice", "commerce"],
            "hr": ["hr", "employee", "payroll", "hiring", "human resource", "staff"],
            "finance": ["finance", "accounting", "ledger", "transaction", "budget"],
            "healthcare": ["healthcare", "patient", "medical", "clinic", "diagnosis"],
        }

        detected_domain = None
        for domain, keywords in domain_keywords.items():
            if any(kw in text for kw in keywords):
                detected_domain = domain
                break

        if detected_domain:
            result = await terminology_manager.bulk_create_domain_terms(
                database_id=persona_id,
                domain=detected_domain,
                created_by="system",
            )
            logger.info(
                f"Auto-initialized {result.get('created_count', 0)} business terms "
                f"(domain={detected_domain}) for persona {persona_id}"
            )
        else:
            logger.debug(f"No domain detected for persona {persona_id}, skipping term init")

    except Exception as e:
        logger.warning(f"Failed to auto-init business terms for persona {persona_id}: {e}")
