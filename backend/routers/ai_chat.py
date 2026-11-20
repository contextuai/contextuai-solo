from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Dict, Any, Optional, AsyncGenerator, List
from pydantic import BaseModel, Field, ConfigDict
import logging
import os
import json
import asyncio
import uuid
import time
from datetime import datetime
from strands import Agent
from strands.models import BedrockModel

# Import session management functions
from .chat_sessions import get_or_create_session, update_session_stats, update_session_title_from_first_message
from .chat_messages import create_message_dict
from database import get_database
from repositories import MessageRepository

# Import persona service for tools
from services.persona_service import PersonaService

# Import model config service for capability checking
from services.model_config_service import model_config_service

# Import analytics service for event capture
from services.analytics_service import capture_chat_analytics, capture_error_analytics
from models.analytics_models import EventStatus

# Import file storage service for file attachments
from services.file_storage_service import file_storage_service

# Import document extraction tools for PDF/DOCX
from services.tools.document_tools import extract_pdf_text_sync, extract_docx_text_sync
from services.tools.image_tools import is_image_file, get_image_reader_tool, IMAGE_EXTENSIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai-chat", tags=["ai-chat"])

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Pydantic models - Import ChatRequest from chat module
class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    # Core field
    prompt: str = Field(..., min_length=1, max_length=10000, description="User's message/prompt")

    # Support both naming conventions for session
    session: Optional[str] = Field(None, description="Session ID from frontend (camelCase)")
    session_id: Optional[str] = Field(None, description="Session ID (backend preference)")

    # Support both naming conventions for model
    model_name: Optional[str] = Field(None, description="Model name from frontend")
    model_id: Optional[str] = Field(None, description="AI model to use")

    # Model configuration from frontend
    model_configuration: Optional[Dict[str, Any]] = Field(None, description="Complete model config from frontend DynamoDB query")

    # Frontend compatibility fields
    userId: Optional[str] = Field(None, description="User ID from frontend (camelCase)")
    method: Optional[str] = Field(None, description="HTTP method from frontend (ignored)")

    # Chat configuration
    persona_id: Optional[str] = Field(None, description="Persona for context and behavior")
    persona_type: Optional[str] = Field(None, description="Persona type for optimization (e.g., 'postgresql', 'mysql')")
    stream: bool = Field(False, description="Enable streaming response")
    max_tokens: Optional[int] = Field(4096, ge=1, le=8192, description="Maximum tokens in response")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=1.0, description="Response creativity (0-1)")

    # Model behavior control
    model_type: Optional[str] = Field(None, description="Template type: reasoning, direct, hybrid")

    # Dynamic tool loading
    enabled_tools: Optional[List[str]] = Field(
        default=None,
        description="List of tool types to enable: web_search, file_operations, api_integration"
    )

    # File attachments
    file_ids: Optional[List[str]] = Field(
        default=None,
        description="List of uploaded file IDs to include in the conversation context"
    )

    # Knowledge Base (RAG) — when set, retrieved chunks are prepended to the prompt
    knowledge_base_id: Optional[str] = Field(
        default=None,
        description="Attached KB id; top-k retrieved chunks are injected into the prompt"
    )

# Helper function to load file contents for context
async def load_file_contents(file_ids: List[str]) -> tuple[str, List[str]]:
    """
    Load contents of attached files and format them for inclusion in prompt context.

    Returns:
        tuple: (file_context_string, list_of_image_file_paths)
        - file_context_string: Text content from text/PDF/DOCX files
        - list_of_image_file_paths: Paths to image files for vision model processing
    """
    if not file_ids:
        return "", []

    file_contents = []
    image_file_paths = []

    # Define file type categories
    text_extensions = {'.txt', '.md', '.json', '.xml', '.csv', '.yaml', '.yml',
                      '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.sql',
                      '.log', '.conf', '.ini', '.env'}
    pdf_extensions = {'.pdf'}
    docx_extensions = {'.docx', '.doc'}

    for file_id in file_ids:
        try:
            metadata = file_storage_service.get_file_metadata(file_id)
            if not metadata:
                logger.warning(f"File not found: {file_id}")
                continue

            extension = metadata["extension"].lower()
            filename = metadata['original_filename']
            file_path = metadata['path']

            # Handle text-based files
            if extension in text_extensions:
                content = await file_storage_service.get_file_content(file_id)
                if content:
                    try:
                        text = content.decode('utf-8')
                    except UnicodeDecodeError:
                        text = content.decode('latin-1', errors='replace')

                    file_contents.append(
                        f"\n--- File: {filename} ---\n{text}\n--- End of {filename} ---\n"
                    )
                    logger.info(f"Loaded text file: {filename} ({len(text)} chars)")

            # Handle PDF files - extract text on-demand
            elif extension in pdf_extensions:
                logger.info(f"Extracting text from PDF: {filename}")
                try:
                    pdf_text = extract_pdf_text_sync(file_path)
                    if pdf_text and not pdf_text.startswith("[Error"):
                        file_contents.append(
                            f"\n--- PDF: {filename} ---\n{pdf_text}\n--- End of {filename} ---\n"
                        )
                        logger.info(f"Extracted PDF text: {filename} ({len(pdf_text)} chars)")
                    else:
                        file_contents.append(f"\n[PDF attached: {filename} - text extraction failed]\n")
                        logger.warning(f"PDF extraction failed: {filename}")
                except Exception as e:
                    logger.error(f"PDF extraction error for {filename}: {e}")
                    file_contents.append(f"\n[PDF attached: {filename} - extraction error]\n")

            # Handle DOCX files - extract text on-demand
            elif extension in docx_extensions:
                logger.info(f"Extracting text from DOCX: {filename}")
                try:
                    docx_text = extract_docx_text_sync(file_path)
                    if docx_text and not docx_text.startswith("[Error"):
                        file_contents.append(
                            f"\n--- DOCX: {filename} ---\n{docx_text}\n--- End of {filename} ---\n"
                        )
                        logger.info(f"Extracted DOCX text: {filename} ({len(docx_text)} chars)")
                    else:
                        file_contents.append(f"\n[DOCX attached: {filename} - text extraction failed]\n")
                        logger.warning(f"DOCX extraction failed: {filename}")
                except Exception as e:
                    logger.error(f"DOCX extraction error for {filename}: {e}")
                    file_contents.append(f"\n[DOCX attached: {filename} - extraction error]\n")

            # Handle image files - track paths for vision model
            elif extension in IMAGE_EXTENSIONS:
                image_file_paths.append(file_path)
                file_contents.append(f"\n[Image attached: {filename}]\n")
                logger.info(f"Image file detected for vision: {filename}")

            # Other binary files - just note their presence
            else:
                file_contents.append(
                    f"\n[Attached file: {filename} ({metadata['content_type']}, {metadata['size']} bytes)]\n"
                )
                logger.info(f"Binary file attached (metadata only): {filename}")

        except Exception as e:
            logger.error(f"Error loading file {file_id}: {e}")

    return "\n".join(file_contents), image_file_paths


async def load_file_items(file_ids: List[str]) -> tuple[List[Dict[str, Any]], List[str]]:
    """Load attached files as structured dicts for smart-context injection.

    Returns:
        (file_items, image_file_paths) where each item in ``file_items`` has
        ``{"file_id": ..., "filename": ..., "text": ..., "page": None}``.
    """
    if not file_ids:
        return [], []

    file_items: List[Dict[str, Any]] = []
    image_file_paths: List[str] = []

    text_extensions = {
        ".txt", ".md", ".json", ".xml", ".csv", ".yaml", ".yml",
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".sql",
        ".log", ".conf", ".ini", ".env",
    }
    pdf_extensions = {".pdf"}
    docx_extensions = {".docx", ".doc"}

    for file_id in file_ids:
        try:
            metadata = file_storage_service.get_file_metadata(file_id)
            if not metadata:
                logger.warning(f"File not found: {file_id}")
                continue

            extension = metadata["extension"].lower()
            filename = metadata["original_filename"]
            file_path = metadata["path"]

            if extension in text_extensions:
                content = await file_storage_service.get_file_content(file_id)
                if content:
                    if isinstance(content, bytes):
                        try:
                            text = content.decode("utf-8")
                        except UnicodeDecodeError:
                            text = content.decode("latin-1", errors="replace")
                    else:
                        text = str(content)
                    if text.strip():
                        file_items.append({
                            "file_id": file_id,
                            "filename": filename,
                            "text": text,
                            "page": None,
                        })
                        logger.info(f"Loaded text file item: {filename} ({len(text)} chars)")

            elif extension in pdf_extensions:
                try:
                    pdf_text = extract_pdf_text_sync(file_path)
                    if pdf_text and not pdf_text.startswith("[Error"):
                        file_items.append({
                            "file_id": file_id,
                            "filename": filename,
                            "text": pdf_text,
                            "page": None,
                        })
                    else:
                        file_items.append({
                            "file_id": file_id,
                            "filename": filename,
                            "text": f"[PDF attached: {filename} - text extraction failed]",
                            "page": None,
                        })
                except Exception as e:
                    logger.error(f"PDF extraction error for {filename}: {e}")
                    file_items.append({
                        "file_id": file_id,
                        "filename": filename,
                        "text": f"[PDF attached: {filename} - extraction error]",
                        "page": None,
                    })

            elif extension in docx_extensions:
                try:
                    docx_text = extract_docx_text_sync(file_path)
                    if docx_text and not docx_text.startswith("[Error"):
                        file_items.append({
                            "file_id": file_id,
                            "filename": filename,
                            "text": docx_text,
                            "page": None,
                        })
                    else:
                        file_items.append({
                            "file_id": file_id,
                            "filename": filename,
                            "text": f"[DOCX attached: {filename} - text extraction failed]",
                            "page": None,
                        })
                except Exception as e:
                    logger.error(f"DOCX extraction error for {filename}: {e}")
                    file_items.append({
                        "file_id": file_id,
                        "filename": filename,
                        "text": f"[DOCX attached: {filename} - extraction error]",
                        "page": None,
                    })

            elif extension in IMAGE_EXTENSIONS:
                image_file_paths.append(file_path)
                file_items.append({
                    "file_id": file_id,
                    "filename": filename,
                    "text": f"[Image attached: {filename}]",
                    "page": None,
                })

            else:
                file_items.append({
                    "file_id": file_id,
                    "filename": filename,
                    "text": f"[Attached file: {filename} ({metadata.get('content_type', 'application/octet-stream')}, {metadata.get('size', 0)} bytes)]",
                    "page": None,
                })
        except Exception as e:
            logger.error(f"Error loading file item {file_id}: {e}")

    return file_items, image_file_paths


# Helper function to store messages
async def store_message(session_id: str, message_type: str, content: str, metadata: Dict[str, Any] = None) -> str:
    """Store a message in MongoDB and return message_id"""
    try:
        message_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"

        from .chat_messages import MessageCreate
        message_data = MessageCreate(
            content=content,
            message_type=message_type,
            metadata=metadata
        )

        message_dict = create_message_dict(session_id, message_data, message_id)

        # Use MongoDB repository instead of DynamoDB
        db = await get_database()
        message_repo = MessageRepository(db)
        await message_repo.create(message_dict)

        logger.info(f"💾 Stored {message_type} message: {message_id} (session: {session_id})")
        return message_id
    except Exception as e:
        logger.error(f"❌ Failed to store message: {e}")
        # Don't fail the chat if message storage fails
        return None

@router.post("/")
async def ai_chat(request: ChatRequest, http_request: Request = None):
    """
    AI chat endpoint with streaming support using Strands Agent.
    Returns streaming or non-streaming response based on request.stream flag.

    Supports parameterized model configuration following Strands Agents patterns.
    """
    # Track request start time for analytics
    request_start_time = time.time()

    try:
        # Log the request
        logger.info(f"\n🔥 AI-CHAT ENDPOINT HIT! Time: {datetime.utcnow().isoformat()}Z")
        logger.info(f"   Model: {request.model_name or request.model_id}")
        logger.info(f"   Prompt: {request.prompt[:100]}...")
        logger.info(f"   Stream: {request.stream}")
        logger.info(f"   Temperature: {request.temperature}")
        logger.info(f"   Max Tokens: {request.max_tokens}")
        logger.info(f"   User: {request.userId}")
        logger.info(f"   persona Id: {request.persona_id}")
        logger.info(f"   persona type: {request.persona_type}")

        # Normalize field names
        model_id = request.model_id or request.model_name
        session_id_input = request.session_id or request.session
        user_id = request.userId

        # Validate required fields
        if not model_id:
            raise HTTPException(
                status_code=400,
                detail="model_id or model_name is required"
            )

        if not user_id:
            user_id = "desktop-user"  # Default for desktop app (single user)

        # Get or create session
        session = await get_or_create_session(
            user_id=user_id,
            session_id=session_id_input,
            persona_id=request.persona_id,
            model_id=model_id
        )
        session_id = session.session_id

        # Check if this is the first message (for title generation)
        is_first_message = session.message_count == 0

        logger.info(f"✅ Session ready: {session_id} (first_message: {is_first_message})")

        # Resolve model config & effective n_ctx before RAG / attached-file injection
        db = await get_database()
        bedrock_model_id = model_id  # Default to what was passed
        model_config = None

        try:
            from repositories import ModelRepository
            model_repo = ModelRepository(db)

            # Try direct _id lookup first (works for local:* IDs and MongoDB ObjectIds)
            try:
                model_config = await model_repo.get_by_id(model_id)
                if model_config:
                    logger.info(f"✅ Found model by _id: {model_id}")
            except Exception:
                pass

            # If not found by ID, try by model field (Bedrock model ID)
            if not model_config:
                model_config = await model_repo.get_one({"model": model_id})
                if model_config:
                    logger.info(f"✅ Found model by Bedrock model ID: {model_id}")

            # If still not found, try by exact name match (case-insensitive)
            if not model_config:
                model_config = await model_repo.get_one({"name": {"$regex": f"^{model_id}$", "$options": "i"}})
                if model_config:
                    logger.info(f"✅ Found model by exact name: {model_id}")

            # If still not found, try flexible name matching (contains, with word boundaries)
            if not model_config:
                search_term = model_id.replace("-", " ").replace("_", " ")
                model_config = await model_repo.get_one({
                    "name": {"$regex": search_term.replace(" ", ".*"), "$options": "i"},
                    "enabled": True
                })
                if model_config:
                    logger.info(f"✅ Found model by flexible name match: {model_id} -> {model_config.get('name')}")

            # Last resort: get all enabled models and find best match
            if not model_config:
                all_models = await model_repo.get_enabled_models()
                search_lower = model_id.lower().replace("-", " ").replace("_", " ")

                for m in all_models:
                    name_lower = m.get("name", "").lower()
                    model_field = m.get("model", "").lower()

                    search_words = search_lower.split()
                    if all(word in name_lower for word in search_words):
                        model_config = m
                        logger.info(f"✅ Found model by word matching: {model_id} -> {m.get('name')}")
                        break

                    if search_lower.replace(" ", "-") in model_field or search_lower.replace(" ", ".") in model_field:
                        model_config = m
                        logger.info(f"✅ Found model by model field: {model_id} -> {m.get('model')}")
                        break

            if model_config:
                resolved_model = model_config.get("model")
                if resolved_model and resolved_model.strip():
                    bedrock_model_id = resolved_model
                    logger.info(f"✅ Resolved model: {model_id} -> {bedrock_model_id}")
                else:
                    metadata_model = model_config.get("model_metadata", {}).get("bedrock_model_id")
                    if metadata_model:
                        bedrock_model_id = metadata_model
                        logger.info(f"✅ Resolved model from metadata: {model_id} -> {bedrock_model_id}")
                    else:
                        logger.warning(f"⚠️ Model found but has no Bedrock model ID: {model_config.get('name')}")
            else:
                logger.warning(f"⚠️ Model config not found for {model_id}, using as-is")
        except Exception as e:
            logger.warning(f"⚠️ Error resolving model config: {e}, using model_id as-is")

        from services.local_model_service import LocalModelService, local_model_service
        _is_local = (model_config and LocalModelService.is_local_model(model_config)) or \
            str(model_id).startswith("local:") or str(model_id).startswith("local-")
        _default_n_ctx = 8192 if _is_local else 32768
        _cfg_n_ctx = None
        if isinstance(model_config, dict):
            _cfg_n_ctx = (
                model_config.get("context_window")
                or (model_config.get("model_metadata") or {}).get("context_window")
            )
        if _is_local:
            n_ctx = local_model_service.get_loaded_n_ctx(
                fallback=int(_cfg_n_ctx) if _cfg_n_ctx else _default_n_ctx
            )
        else:
            n_ctx = int(_cfg_n_ctx) if _cfg_n_ctx else _default_n_ctx

        # ── Knowledge Base (Smart Context + Hybrid RAG) retrieval ──────
        rag_citations: List[Dict[str, Any]] = []
        rag_mode: Optional[str] = None
        rag_context = ""
        if request.knowledge_base_id:
            try:
                from services.rag_service import RAGService
                from repositories.knowledge_base_repository import KnowledgeBaseRepository
                from repositories.document_repository import DocumentRepository
                from repositories.chunk_repository import ChunkRepository

                _rag = RAGService(
                    KnowledgeBaseRepository(db),
                    DocumentRepository(db),
                    ChunkRepository(db),
                )
                rag_res = await _rag.smart_retrieve(
                    request.knowledge_base_id,
                    request.prompt,
                    n_ctx=n_ctx,
                    top_k=5,
                )
                rag_citations = list(rag_res.get("citations") or [])
                rag_context = rag_res.get("context_block") or ""
                if rag_citations or rag_context:
                    rag_mode = rag_res.get("mode")
                    logger.info(
                        f"📚 KB smart_retrieve ({rag_mode}): {len(rag_citations)} citation(s) (kb={request.knowledge_base_id})"
                    )
                else:
                    logger.info(f"📚 KB {request.knowledge_base_id} returned no matches")
            except Exception as e:
                logger.warning(f"⚠️ KB retrieval failed (continuing without): {e}")

        # ── Attached Files (Smart Context / BM25) across ALL paths ─────
        file_citations: List[Dict[str, Any]] = []
        file_context = ""
        image_file_paths: List[str] = []
        if request.file_ids:
            try:
                from services.rag_service import build_attached_files_context

                file_items, image_file_paths = await load_file_items(request.file_ids)
                if file_items:
                    files_res = build_attached_files_context(
                        file_items,
                        request.prompt,
                        n_ctx=n_ctx,
                    )
                    file_context = files_res.get("context_block") or ""
                    file_citations = list(files_res.get("citations") or [])
                    file_mode = files_res.get("mode")
                    if file_citations or file_context:
                        if rag_mode is None:
                            rag_mode = file_mode
                        elif file_mode and rag_mode != file_mode:
                            rag_mode = "hybrid_rag"
                        logger.info(
                            f"📎 Attached files ({file_mode}): {len(file_citations)} citation(s)"
                        )
            except Exception as e:
                logger.warning(f"⚠️ Attached files context failed (continuing without): {e}")

        merged_citations: List[Dict[str, Any]] = [
            {**cit, "index": idx}
            for idx, cit in enumerate([*rag_citations, *file_citations], start=1)
        ]

        # ── Unified Memory Layer Auto-Recall (SPEC-14 PR-B) ────────────
        mem_block = ""
        try:
            from repositories.memory_repository import MemoryRepository
            from repositories.memory_settings_repository import MemorySettingsRepository
            from services.memory_service import MemoryService

            _mem_svc = MemoryService(
                MemoryRepository(db),
                MemorySettingsRepository(db),
            )
            mem_block = await _mem_svc.recall_for_prompt(
                query=request.prompt,
                surface="chat",
                scopes=["global"],
            )
            if mem_block:
                logger.info("🧠 Unified Memory recall injected into chat prompt")
        except Exception as e:
            logger.warning(f"⚠️ Memory recall failed (continuing without): {e}")

        # Build effective prompt for all 4 inference paths (local, Ollama, cloud dispatcher, Bedrock)
        _context_parts = [p for p in (mem_block, rag_context, file_context) if p]
        if rag_context or file_context:
            effective_prompt = "\n\n".join(_context_parts) + f"\n\nUser question: {request.prompt}"
        elif mem_block:
            effective_prompt = f"{mem_block}\n\n{request.prompt}"
        else:
            effective_prompt = request.prompt

        base_metadata: Dict[str, Any] = {}
        if merged_citations:
            base_metadata["citations"] = merged_citations
        if rag_mode:
            base_metadata["rag_mode"] = rag_mode

        def _build_response_metadata(dlp_redaction: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            meta = dict(base_metadata)
            if dlp_redaction:
                meta["dlp_redaction"] = dlp_redaction
            return meta

        # Load conversation history for context
        history_messages = []
        if not is_first_message:
            try:
                message_repo = MessageRepository(db)
                context_messages = await message_repo.get_context_messages(session_id, limit=10)
                for msg in context_messages:
                    role = msg.get("message_type", "user")
                    if role in ("user", "assistant") and msg.get("content"):
                        history_messages.append({
                            "role": role,
                            "content": [{"text": msg["content"]}]
                        })
                logger.info(f"📜 Loaded {len(history_messages)} history messages for context")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load conversation history: {e}")

        # ── Local GGUF model intercept ─────────────────────────────────
        # If the resolved model config is a local GGUF model, use
        # LocalModelService (llama-cpp-python) directly.
        # Also detect by model_id prefix when model_config lookup failed.
        if _is_local:
            # If model_config is missing (sync not yet run), build a minimal
            # config from the catalog so LocalModelService can resolve the file.
            if not model_config:
                from services.model_catalog import get_model as get_catalog_model
                catalog_id = model_id.replace("local:", "").replace("local-", "")
                catalog_entry = get_catalog_model(catalog_id)
                if catalog_entry:
                    model_config = {
                        "id": model_id,
                        "name": catalog_entry.get("name", model_id),
                        "provider": "local",
                        "model_metadata": {
                            "runtime": "llama-cpp",
                            "hf_filename": catalog_entry.get("hf_filename"),
                            "gguf_path": None,
                        },
                    }
                    logger.info(f"🖥️ Built model_config from catalog for {model_id}")
                else:
                    # No catalog entry — still try with minimal config
                    model_config = {
                        "id": model_id,
                        "name": model_id,
                        "provider": "local",
                        "model_metadata": {"runtime": "llama-cpp"},
                    }
                    logger.warning(f"⚠️ No catalog entry for {catalog_id}, using minimal config")
            logger.info(f"🖥️ ROUTING: Local model detected ({model_config.get('name')}), using LocalModelService")

            # Store user message
            user_message_id = await store_message(session_id, "user", request.prompt)

            # Build persona context
            persona_context = None
            if request.persona_id:
                try:
                    persona_service = PersonaService()
                    persona_context = await persona_service.build_persona_context(request.persona_id)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to build persona context: {e}")

            # Convert history_messages from Strands format to simple format
            simple_history = []
            for msg in history_messages:
                role = msg.get("role", "user")
                content_parts = msg.get("content", [])
                text = content_parts[0].get("text", "") if content_parts else ""
                if text:
                    simple_history.append({"role": role, "content": text})

            if request.stream:
                logger.info("🚀 Starting Local model streaming response...")

                async def local_event_generator() -> AsyncGenerator[str, None]:
                    collected_response = []
                    disconnected = False
                    try:
                        gen = await local_model_service.call_model(
                            prompt=effective_prompt,
                            model_id=model_id,
                            persona_context=persona_context,
                            conversation_history=simple_history,
                            max_tokens=request.max_tokens,
                            temperature=request.temperature,
                            stream=True,
                            model_config=model_config,
                        )
                        async for chunk in gen:
                            text = chunk.get("chunk", "")
                            thinking = chunk.get("thinking", "")
                            if text or thinking:
                                if text:
                                    collected_response.append(text)
                                payload: dict = {}
                                if text:
                                    payload["chunk"] = text
                                if thinking:
                                    payload["thinking"] = thinking
                                yield f"data: {json.dumps(payload)}\n\n"
                    except (GeneratorExit, asyncio.CancelledError):
                        disconnected = True
                        logger.info("Client disconnected during local model streaming")
                    except Exception as e:
                        logger.error(f"❌ Local model streaming error: {e}")
                        yield f"data: {json.dumps({'status': 'error', 'error': True, 'message': str(e)})}\n\n"

                    local_meta = _build_response_metadata()
                    if not disconnected:
                        if local_meta:
                            yield f"data: {json.dumps({'is_final': True, 'metadata': local_meta})}\n\n"
                        yield "data: [DONE]\n\n"

                    # Always store what we have so far
                    full_response = "".join(collected_response)
                    try:
                        if full_response:
                            await store_message(
                                session_id,
                                "assistant",
                                full_response,
                                metadata=local_meta or None,
                            )
                        await update_session_stats(session_id)
                        if is_first_message and full_response:
                            await update_session_title_from_first_message(session_id, request.prompt, max_length=20)
                    except Exception:
                        pass

                    try:
                        response_time_ms = int((time.time() - request_start_time) * 1000)
                        await capture_chat_analytics(
                            user_id=user_id, session_id=session_id, model_id=model_id,
                            persona_id=request.persona_id,
                            input_tokens=len(request.prompt.split()) * 2,
                            output_tokens=len(full_response.split()) * 2,
                            response_time_ms=response_time_ms, is_streaming=True,
                            status=EventStatus.SUCCESS,
                        )
                    except Exception:
                        pass

                return StreamingResponse(local_event_generator(), media_type="text/plain")
            else:
                result = await local_model_service.call_model(
                    prompt=effective_prompt,
                    model_id=model_id,
                    persona_context=persona_context,
                    conversation_history=simple_history,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    stream=False,
                    model_config=model_config,
                )
                response_str = result.get("content", "")
                ollama_meta = _build_response_metadata()
                await store_message(
                    session_id,
                    "assistant",
                    response_str,
                    metadata=ollama_meta or None,
                )
                await update_session_stats(session_id)
                if is_first_message and response_str:
                    try:
                        await update_session_title_from_first_message(session_id, request.prompt, max_length=20)
                    except Exception:
                        pass

                response_time_ms = int((time.time() - request_start_time) * 1000)
                tokens_used = result.get("tokens_used", {})
                await capture_chat_analytics(
                    user_id=user_id, session_id=session_id, model_id=model_id,
                    persona_id=request.persona_id,
                    input_tokens=tokens_used.get("input_tokens", 0),
                    output_tokens=tokens_used.get("output_tokens", 0),
                    response_time_ms=response_time_ms, is_streaming=False,
                    status=EventStatus.SUCCESS,
                )

                return JSONResponse(content={
                    "result": response_str,
                    "session": session_id,
                    "status": "success",
                    "user_message_id": user_message_id,
                    "metadata": {
                        "model_id": model_id,
                        "response_time_ms": response_time_ms,
                        "tokens_used": tokens_used,
                        **ollama_meta,
                    },
                })

        # ── Ollama local model intercept ──────────────────────────────
        # If the resolved model config is an Ollama model, bypass Strands
        # Agent and use OllamaService directly.
        from services.ollama_service import OllamaService, ollama_service
        if model_config and OllamaService.is_ollama_model(model_config):
            logger.info(f"🏠 ROUTING: Ollama model detected ({model_config.get('name')}), using OllamaService")

            # Honor the base_url saved in Settings -> AI Providers (falls back
            # to the localhost default). Without this the singleton would use
            # the env default and could fail to reach a custom Ollama host.
            ollama_svc = ollama_service
            try:
                from services.cloud_provider_service import CloudProviderService
                _creds = await CloudProviderService(db).get_credentials("ollama")
                _base_url = (_creds or {}).get("base_url")
                if _base_url:
                    ollama_svc = OllamaService(base_url=_base_url)
            except Exception as _e:
                logger.warning(f"⚠️ Could not resolve saved Ollama base_url: {_e}")

            # Store user message
            user_message_id = await store_message(session_id, "user", request.prompt)

            # Build persona context
            persona_context = None
            if request.persona_id:
                try:
                    persona_service = PersonaService()
                    persona_context = await persona_service.build_persona_context(request.persona_id)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to build persona context: {e}")

            # Convert history_messages from Strands format to simple format
            simple_history = []
            for msg in history_messages:
                role = msg.get("role", "user")
                content_parts = msg.get("content", [])
                text = content_parts[0].get("text", "") if content_parts else ""
                if text:
                    simple_history.append({"role": role, "content": text})

            if request.stream:
                logger.info("🚀 Starting Ollama streaming response...")

                async def ollama_event_generator() -> AsyncGenerator[str, None]:
                    collected_response = []
                    try:
                        gen = await ollama_svc.call_model(
                            prompt=effective_prompt,
                            model_id=model_id,
                            persona_context=persona_context,
                            conversation_history=simple_history,
                            max_tokens=request.max_tokens,
                            temperature=request.temperature,
                            stream=True,
                            model_config=model_config,
                        )
                        async for chunk in gen:
                            text = chunk.get("chunk", "")
                            if text:
                                collected_response.append(text)
                                yield f"data: {json.dumps({'chunk': text})}\n\n"
                    except Exception as e:
                        logger.error(f"❌ Ollama streaming error: {e}")
                        yield f"data: {json.dumps({'status': 'error', 'error': True, 'message': str(e)})}\n\n"

                    ollama_meta = _build_response_metadata()
                    if ollama_meta:
                        yield f"data: {json.dumps({'is_final': True, 'metadata': ollama_meta})}\n\n"
                    yield "data: [DONE]\n\n"

                    full_response = "".join(collected_response)
                    await store_message(
                        session_id,
                        "assistant",
                        full_response,
                        metadata=ollama_meta or None,
                    )
                    await update_session_stats(session_id)
                    if is_first_message and full_response:
                        try:
                            await update_session_title_from_first_message(session_id, request.prompt, max_length=20)
                        except Exception:
                            pass

                    response_time_ms = int((time.time() - request_start_time) * 1000)
                    await capture_chat_analytics(
                        user_id=user_id, session_id=session_id, model_id=model_id,
                        persona_id=request.persona_id,
                        input_tokens=len(request.prompt.split()) * 2,
                        output_tokens=len(full_response.split()) * 2,
                        response_time_ms=response_time_ms, is_streaming=True,
                        status=EventStatus.SUCCESS,
                    )

                return StreamingResponse(ollama_event_generator(), media_type="text/plain")
            else:
                result = await ollama_svc.call_model(
                    prompt=effective_prompt,
                    model_id=model_id,
                    persona_context=persona_context,
                    conversation_history=simple_history,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    stream=False,
                    model_config=model_config,
                )
                response_str = result.get("content", "")
                ollama_meta = _build_response_metadata()
                await store_message(
                    session_id,
                    "assistant",
                    response_str,
                    metadata=ollama_meta or None,
                )
                await update_session_stats(session_id)
                if is_first_message and response_str:
                    try:
                        await update_session_title_from_first_message(session_id, request.prompt, max_length=20)
                    except Exception:
                        pass

                response_time_ms = int((time.time() - request_start_time) * 1000)
                tokens_used = result.get("tokens_used", {})
                await capture_chat_analytics(
                    user_id=user_id, session_id=session_id, model_id=model_id,
                    persona_id=request.persona_id,
                    input_tokens=tokens_used.get("input_tokens", 0),
                    output_tokens=tokens_used.get("output_tokens", 0),
                    response_time_ms=response_time_ms, is_streaming=False,
                    status=EventStatus.SUCCESS,
                )

                return JSONResponse(content={
                    "result": response_str,
                    "session": session_id,
                    "status": "success",
                    "user_message_id": user_message_id,
                    "metadata": {
                        "model_id": model_id,
                        "response_time_ms": response_time_ms,
                        "tokens_used": tokens_used,
                        **ollama_meta,
                    },
                })
        # ── End Ollama intercept ──────────────────────────────────────

        # ── Cloud provider intercept (OpenAI / OpenAI-compatible / Anthropic / Google) ──
        # These route through the unified model_dispatcher (direct provider APIs
        # using saved keys / base_url), instead of the Bedrock/Strands path below
        # which only speaks AWS Bedrock. Tool-calling is not applied on this path.
        from services.model_dispatcher import (
            _parse_provider as _dispatch_parse,
            stream_chat as _dispatch_stream,
        )
        _disp_provider, _ = _dispatch_parse(model_id)
        if _disp_provider in ("openai", "openai_compat", "anthropic", "google"):
            logger.info(f"🌐 ROUTING: {_disp_provider} via model_dispatcher ({model_id})")

            user_message_id = await store_message(session_id, "user", request.prompt)

            sys_prompt = None
            if request.persona_id:
                try:
                    persona_service = PersonaService()
                    pctx = await persona_service.build_persona_context(request.persona_id)
                    sys_prompt = (pctx or {}).get("system_prompt")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to build persona context: {e}")

            disp_messages: list = []
            if sys_prompt:
                disp_messages.append({"role": "system", "content": sys_prompt})
            for _m in history_messages:
                _role = _m.get("role", "user")
                _cp = _m.get("content", [])
                _txt = _cp[0].get("text", "") if _cp else ""
                if _txt:
                    disp_messages.append({"role": _role, "content": _txt})
            disp_messages.append({"role": "user", "content": effective_prompt})

            if request.stream:
                async def dispatcher_event_generator() -> AsyncGenerator[str, None]:
                    collected: list = []
                    dlp_redaction: Optional[Dict[str, Any]] = None
                    try:
                        async for evt in _dispatch_stream(
                            model_id, disp_messages, db=db,
                            temperature=request.temperature, max_tokens=request.max_tokens,
                        ):
                            if evt.get("type") == "dlp_redacted":
                                dlp_redaction = evt.get("summary")
                            elif evt.get("type") == "delta":
                                t = evt.get("content", "")
                                if t:
                                    collected.append(t)
                                    yield f"data: {json.dumps({'chunk': t})}\n\n"
                    except Exception as e:
                        logger.error(f"❌ Dispatcher streaming error: {e}")
                        yield f"data: {json.dumps({'status': 'error', 'error': True, 'message': str(e)})}\n\n"

                    disp_meta = _build_response_metadata(dlp_redaction)
                    if disp_meta:
                        yield f"data: {json.dumps({'is_final': True, 'metadata': disp_meta})}\n\n"
                    yield "data: [DONE]\n\n"

                    full_response = "".join(collected)
                    if full_response:
                        await store_message(
                            session_id,
                            "assistant",
                            full_response,
                            metadata=disp_meta or None,
                        )
                    await update_session_stats(session_id)
                    if is_first_message and full_response:
                        try:
                            await update_session_title_from_first_message(session_id, request.prompt, max_length=20)
                        except Exception:
                            pass

                return StreamingResponse(dispatcher_event_generator(), media_type="text/plain")
            else:
                parts: list = []
                dlp_redaction: Optional[Dict[str, Any]] = None
                try:
                    async for evt in _dispatch_stream(
                        model_id, disp_messages, db=db,
                        temperature=request.temperature, max_tokens=request.max_tokens,
                    ):
                        if evt.get("type") == "dlp_redacted":
                            dlp_redaction = evt.get("summary")
                        elif evt.get("type") == "delta":
                            parts.append(evt.get("content", ""))
                except Exception as e:
                    logger.error(f"❌ Dispatcher error ({_disp_provider}): {e}")
                    return JSONResponse(
                        status_code=502,
                        content={
                            "result": "",
                            "session": session_id,
                            "status": "error",
                            "error": True,
                            "message": str(e),
                            "user_message_id": user_message_id,
                            "metadata": {"model_id": model_id},
                        },
                    )
                response_str = "".join(parts)
                disp_meta = _build_response_metadata(dlp_redaction)
                if response_str:
                    await store_message(
                        session_id,
                        "assistant",
                        response_str,
                        metadata=disp_meta or None,
                    )
                await update_session_stats(session_id)
                return JSONResponse(content={
                    "result": response_str,
                    "session": session_id,
                    "status": "success",
                    "user_message_id": user_message_id,
                    "metadata": {"model_id": model_id, **disp_meta},
                })

        bedrock_model = BedrockModel(
            model_id=bedrock_model_id,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            streaming=request.stream,
        )

        logger.info(f"✅ BedrockModel configured: {bedrock_model_id}")
        logger.info(f"   - Temperature: {request.temperature}")
        logger.info(f"   - Max Tokens: {request.max_tokens}")
        logger.info(f"   - Streaming: {request.stream}")

        # Load tools from persona (existing logic)
        tools = []
        if request.persona_id:
            try:
                persona_service = PersonaService()
                tools = await persona_service.get_persona_tools(
                    request.persona_id,
                    persona_type=request.persona_type
                )
                logger.info(f"✅ Loaded {len(tools)} tools for persona: {request.persona_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load tools for persona: {e}")

        # NEW: Dynamic tool addition based on enabled_tools parameter
        # First, check if model supports function calling (tool use)
        model_supports_tools = True  # Default to true for backwards compatibility
        if request.enabled_tools:
            try:
                # Get model configuration to check capabilities
                model_config = await model_config_service.get_model_config(model_id)
                if model_config:
                    # Check supports_function_calling field (Tavily/tools require this)
                    model_supports_tools = model_config.get("supports_function_calling", True)
                    if not model_supports_tools:
                        logger.warning(f"⚠️ Model {model_id} does not support function calling (tools disabled)")
                        logger.warning(f"   Tools requested: {request.enabled_tools}")
                        # Clear enabled_tools since model doesn't support them
                        request.enabled_tools = []
                    else:
                        logger.info(f"✅ Model {model_id} supports function calling")
            except Exception as e:
                logger.warning(f"⚠️ Could not check model capabilities: {e} - proceeding with tools")

        if request.enabled_tools:
            from services.tools.web_tools import WebTools
            from services.tools.api_tools import APITools
            from services.tools.file_tools import FileTools

            # Map tool types to classes
            tool_map = {
                "web_search": WebTools,
                "api_integration": APITools,
                "file_operations": FileTools
            }

            # Load requested tools
            for tool_type in request.enabled_tools:
                if tool_type in tool_map:
                    # Check if this tool class is already loaded (avoid duplicates)
                    tool_class = tool_map[tool_type]
                    tool_class_name = tool_class.__name__
                    already_loaded = any(
                        hasattr(t, '__self__') and t.__self__.__class__.__name__ == tool_class_name
                        for t in tools
                    )

                    if not already_loaded:
                        tool_instance = tool_class()
                        new_tools = tool_instance.get_tools()
                        tools.extend(new_tools)
                        logger.info(f"✅ Dynamically added {len(new_tools)} {tool_type} tools")
                    else:
                        logger.info(f"⏭️ Skipping {tool_type} - already loaded from persona")
                else:
                    logger.warning(f"⚠️ Unknown tool type requested: {tool_type}")

        # Initialize Strands Agent with tools
        try:
            if tools:
                agent = Agent(
                    model=bedrock_model,
                    tools=tools,
                    messages=history_messages if history_messages else None
                )
                logger.info(f"✅ Strands Agent initialized with {len(tools)} tools, {len(history_messages)} history messages")
            else:
                agent = Agent(
                    model=bedrock_model,
                    messages=history_messages if history_messages else None
                )
                logger.info(f"✅ Strands Agent initialized without tools, {len(history_messages)} history messages")
        except Exception as e:
            logger.error(f"❌ Error initializing Strands Agent: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Error initializing AI agent"
            )

        # Store user message before processing
        user_message_id = await store_message(session_id, "user", request.prompt)

        # Auto-add image_reader tool if attached images are present on Bedrock path
        if image_file_paths:
            logger.info(f"🖼️ {len(image_file_paths)} image(s) detected for vision processing")
            if model_supports_tools:
                image_reader = get_image_reader_tool()
                if image_reader:
                    if image_reader not in tools:
                        tools.append(image_reader)
                        logger.info("✅ Auto-added image_reader tool for vision processing")

                    try:
                        agent = Agent(
                            model=bedrock_model,
                            tools=tools,
                            messages=history_messages if history_messages else None
                        )
                        logger.info(f"✅ Re-initialized Strands Agent with {len(tools)} tools (including image_reader)")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not re-initialize agent with image_reader: {e}")
                else:
                    logger.warning("⚠️ image_reader tool not available - image analysis may be limited")

        # Build the full prompt (file_context is already included in effective_prompt)
        full_prompt = effective_prompt
        if image_file_paths:
            image_paths_str = ", ".join(image_file_paths)
            full_prompt += f"\n\n[Image file paths for analysis: {image_paths_str}]"

        # Local DLP redaction before sending to non-loopback Bedrock cloud
        bedrock_dlp_redaction: Optional[Dict[str, Any]] = None
        try:
            from services import dlp_service

            dlp_settings = dlp_service.get_dlp_settings()
            if dlp_settings.get("enabled", True):
                dlp_res = dlp_service.scan_and_redact(full_prompt, policy=dlp_settings)
                if dlp_res.total_redactions > 0:
                    full_prompt = dlp_res.redacted_text
                    bedrock_dlp_redaction = dlp_res.to_summary()
                    try:
                        from models.audit_models import AuditAction
                        from services.audit_service import audit_log

                        await audit_log(
                            getattr(AuditAction, "DLP_REDACTED", "dlp.redacted"),
                            resource_type="chat",
                            resource_id=model_id,
                            details={
                                "provider": "bedrock",
                                "total_redactions": dlp_res.total_redactions,
                                "categories": dlp_res.categories,
                                "counts_by_category": dlp_res.counts_by_category,
                            },
                        )
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("Bedrock DLP check failed (non-fatal): %s", exc)

        bedrock_meta = _build_response_metadata(bedrock_dlp_redaction)

        # Handle streaming response
        if request.stream:
            logger.info("🚀 Starting streaming response...")

            # Collect full response for storage
            collected_response = []

            async def event_generator() -> AsyncGenerator[str, None]:
                """Async generator to stream response chunks."""
                nonlocal collected_response
                disconnected = False
                prompt = full_prompt

                try:
                    agent_stream = agent.stream_async(prompt)

                    async for event in agent_stream:
                        if "data" in event:
                            collected_response.append(event['data'])
                            yield f"data: {json.dumps({'chunk': event['data']})}\n\n"
                        elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                            yield f"data: [Tool use delta for: {event['current_tool_use']['name']}]\n\n"
                except (GeneratorExit, asyncio.CancelledError):
                    disconnected = True
                    logger.info("Client disconnected during cloud model streaming")
                except Exception as e:
                    logger.error(f"❌ Cloud model streaming error: {e}")
                    yield f"data: {json.dumps({'status': 'error', 'error': True, 'message': str(e)})}\n\n"

                if not disconnected:
                    if bedrock_meta:
                        yield f"data: {json.dumps({'is_final': True, 'metadata': bedrock_meta})}\n\n"
                    yield "data: [DONE]\n\n"

                # Always store what we have so far
                full_response = ''.join(collected_response)
                try:
                    if full_response:
                        await store_message(
                            session_id,
                            "assistant",
                            full_response,
                            metadata=bedrock_meta or None,
                        )
                    await update_session_stats(session_id)
                    if is_first_message and full_response:
                        await update_session_title_from_first_message(session_id, request.prompt, max_length=20)
                except Exception:
                    pass

                try:
                    response_time_ms = int((time.time() - request_start_time) * 1000)
                    input_tokens = len(request.prompt.split()) * 2
                    output_tokens = len(full_response.split()) * 2 if full_response else 0
                    await capture_chat_analytics(
                        user_id=user_id, session_id=session_id, model_id=model_id,
                        persona_id=request.persona_id,
                        input_tokens=input_tokens, output_tokens=output_tokens,
                        response_time_ms=response_time_ms, is_streaming=True,
                        status=EventStatus.SUCCESS,
                    )
                except Exception:
                    pass

            return StreamingResponse(event_generator(),
                                     media_type="text/plain")
        else:
            response = agent(full_prompt)
            response_str = str(response)
            logger.info(f"✅ Model response generated: {response_str[:100]}...")

            # Store assistant message
            assistant_message_id = await store_message(
                session_id,
                "assistant",
                response_str,
                metadata=bedrock_meta or None,
            )

            # Update session stats (message_count += 2 for user + assistant)
            await update_session_stats(session_id)

            # Generate title if first message
            if is_first_message and response_str:
                try:
                    await update_session_title_from_first_message(session_id, request.prompt, max_length=20)
                    logger.info(f"✅ Session title generated for first message")
                except Exception as e:
                    logger.error(f"⚠️ Title generation failed (non-critical): {e}")

            # Capture chat analytics (non-blocking)
            response_time_ms = int((time.time() - request_start_time) * 1000)
            # Estimate tokens (rough calculation - actual would come from model response)
            input_tokens = len(request.prompt.split()) * 2  # Rough estimate
            output_tokens = len(response_str.split()) * 2 if response_str else 0

            await capture_chat_analytics(
                user_id=user_id,
                session_id=session_id,
                model_id=model_id,
                persona_id=request.persona_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                response_time_ms=response_time_ms,
                is_streaming=False,
                status=EventStatus.SUCCESS
            )
            logger.debug(f"📊 Analytics captured for non-streaming chat request")

            response_data = {
                "response": response_str,
                "message": "Response generated successfully",
                "session_id": session_id,
                "model_id": model_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
                "metadata": {"model_id": model_id, **bedrock_meta},
            }

            return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"❌ Error in AI-CHAT endpoint: {str(e)}")

        # Capture error analytics (non-blocking)
        response_time_ms = int((time.time() - request_start_time) * 1000)
        error_user_id = request.userId if hasattr(request, 'userId') and request.userId else "unknown"
        error_session_id = request.session_id or request.session if hasattr(request, 'session_id') else None

        await capture_error_analytics(
            user_id=error_user_id,
            error_type="chat_error",
            error_message=str(e),
            endpoint="/api/v1/ai-chat",
            session_id=error_session_id
        )
        logger.debug(f"📊 Error analytics captured for failed chat request")

@router.post("")
async def ai_chat_no_slash(request: ChatRequest, http_request: Request = None):
    """AI-Chat endpoint without trailing slash (compatibility)"""
    logging.info(f"\n🔄 AI-CHAT REQUEST (NO SLASH) - REDIRECTING TO MAIN HANDLER")
    logging.info(f"   Request Body: {request.json()}")
    
    return await ai_chat(request, http_request)

