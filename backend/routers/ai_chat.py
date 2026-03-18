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

        # Load conversation history for context
        history_messages = []
        if not is_first_message:
            try:
                db = await get_database()
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

        # Resolve the actual Bedrock model identifier from model config
        # The model_id from frontend could be MongoDB ObjectId, Bedrock model ID, or display name
        bedrock_model_id = model_id  # Default to what was passed

        try:
            # First, try to get model config by MongoDB _id
            db = await get_database()
            from repositories import ModelRepository
            model_repo = ModelRepository(db)

            model_config = None

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
                # Normalize the search term: replace dashes/underscores with spaces for flexible matching
                search_term = model_id.replace("-", " ").replace("_", " ")
                # Try to match any model name that contains similar words
                model_config = await model_repo.get_one({
                    "name": {"$regex": search_term.replace(" ", ".*"), "$options": "i"},
                    "enabled": True  # Prefer enabled models
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

                    # Check if search term words appear in name
                    search_words = search_lower.split()
                    if all(word in name_lower for word in search_words):
                        model_config = m
                        logger.info(f"✅ Found model by word matching: {model_id} -> {m.get('name')}")
                        break

                    # Check model field contains search term
                    if search_lower.replace(" ", "-") in model_field or search_lower.replace(" ", ".") in model_field:
                        model_config = m
                        logger.info(f"✅ Found model by model field: {model_id} -> {m.get('model')}")
                        break

            if model_config:
                # Use the actual Bedrock model identifier from the 'model' field
                resolved_model = model_config.get("model")
                if resolved_model and resolved_model.strip():
                    bedrock_model_id = resolved_model
                    logger.info(f"✅ Resolved model: {model_id} -> {bedrock_model_id}")
                else:
                    # Model field is empty, try bedrock_model_id from metadata
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

        # ── Local GGUF model intercept ─────────────────────────────────
        # If the resolved model config is a local GGUF model, use
        # LocalModelService (llama-cpp-python) directly.
        from services.local_model_service import LocalModelService, local_model_service
        if model_config and LocalModelService.is_local_model(model_config):
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
                            prompt=request.prompt,
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
                    except (GeneratorExit, asyncio.CancelledError):
                        disconnected = True
                        logger.info("Client disconnected during local model streaming")
                    except Exception as e:
                        logger.error(f"❌ Local model streaming error: {e}")
                        yield f"data: {json.dumps({'chunk': f'Error: {e}', 'error': True})}\n\n"

                    if not disconnected:
                        yield "data: [DONE]\n\n"

                    # Always store what we have so far
                    full_response = "".join(collected_response)
                    try:
                        if full_response:
                            await store_message(session_id, "assistant", full_response)
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
                    prompt=request.prompt,
                    model_id=model_id,
                    persona_context=persona_context,
                    conversation_history=simple_history,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    stream=False,
                    model_config=model_config,
                )
                response_str = result.get("content", "")
                await store_message(session_id, "assistant", response_str)
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
                    },
                })

        # ── Ollama local model intercept ──────────────────────────────
        # If the resolved model config is an Ollama model, bypass Strands
        # Agent and use OllamaService directly.
        from services.ollama_service import OllamaService, ollama_service
        if model_config and OllamaService.is_ollama_model(model_config):
            logger.info(f"🏠 ROUTING: Ollama model detected ({model_config.get('name')}), using OllamaService")

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
                        gen = await ollama_service.call_model(
                            prompt=request.prompt,
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
                        yield f"data: {json.dumps({'chunk': f'Error: {e}', 'error': True})}\n\n"

                    yield "data: [DONE]\n\n"

                    full_response = "".join(collected_response)
                    await store_message(session_id, "assistant", full_response)
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
                result = await ollama_service.call_model(
                    prompt=request.prompt,
                    model_id=model_id,
                    persona_context=persona_context,
                    conversation_history=simple_history,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    stream=False,
                    model_config=model_config,
                )
                response_str = result.get("content", "")
                await store_message(session_id, "assistant", response_str)
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
                    },
                })
        # ── End Ollama intercept ──────────────────────────────────────

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

        # Load file contents if file_ids are provided
        file_context = ""
        image_file_paths = []
        if request.file_ids:
            file_context, image_file_paths = await load_file_contents(request.file_ids)
            if file_context:
                logger.info(f"📎 Loaded {len(request.file_ids)} file(s) for context")
            if image_file_paths:
                logger.info(f"🖼️ {len(image_file_paths)} image(s) detected for vision processing")

                # Auto-add image_reader tool if images are attached and model supports tools
                if model_supports_tools:
                    image_reader = get_image_reader_tool()
                    if image_reader:
                        # Check if image_reader is not already in tools list
                        if image_reader not in tools:
                            tools.append(image_reader)
                            logger.info("✅ Auto-added image_reader tool for vision processing")

                        # Re-initialize agent with updated tools if we added image_reader
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

        # Build the full prompt with file context if available
        if file_context:
            full_prompt = f"{request.prompt}\n\n[Attached Files]\n{file_context}"
            # If images are present, add hint about image paths for the agent
            if image_file_paths:
                image_paths_str = ", ".join(image_file_paths)
                full_prompt += f"\n\n[Image file paths for analysis: {image_paths_str}]"
        else:
            full_prompt = request.prompt

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
                    yield f"data: {json.dumps({'chunk': f'Error: {e}', 'error': True})}\n\n"

                if not disconnected:
                    yield "data: [DONE]\n\n"

                # Always store what we have so far
                full_response = ''.join(collected_response)
                try:
                    if full_response:
                        await store_message(session_id, "assistant", full_response)
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
            assistant_message_id = await store_message(session_id, "assistant", response_str)

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
                "assistant_message_id": assistant_message_id
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

