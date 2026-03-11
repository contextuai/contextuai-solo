import boto3
import json
import os
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
import asyncio
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime

# Import our dynamic model configurations
from .model_config_service import model_config_service, PromptTemplateEngine, DynamicRequestBuilder

# Import specialized services
from .anthropic_claude_service import anthropic_claude_service
from .universal_model_adapter import universal_model_adapter
from .ollama_service import ollama_service, OllamaService

class EnhancedBedrockService:
    """Enhanced AWS Bedrock service with dynamic model configuration support"""

    def __init__(self):
        self.region = os.getenv("AWS_BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))
        self.bedrock_client = None
        self.bedrock_runtime_client = None
        self.model_config_service = model_config_service
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize Bedrock clients with proper error handling"""
        try:
            # Bedrock client for model management
            self.bedrock_client = boto3.client(
                service_name='bedrock',
                region_name=self.region
            )

            # Bedrock Runtime client for model invocation
            self.bedrock_runtime_client = boto3.client(
                service_name='bedrock-runtime',
                region_name=self.region
            )

            print(f"✓ Enhanced Bedrock clients initialized for region: {self.region}")

        except Exception as e:
            print(f"ERROR: Failed to initialize Bedrock clients: {e}")
            raise

    async def call_bedrock_model(
        self,
        prompt: str,
        model_id: str,
        persona_context: Dict[str, Any] = None,
        conversation_history: List[Dict[str, Any]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
        model_config: Dict[str, Any] = None,
        **kwargs
    ) -> Union[Dict[str, Any], AsyncGenerator[Dict[str, Any], None]]:
        
        # print(f"🎯 BEDROCK: {model_id} - stream={stream}")
        """
        Enhanced call to Bedrock model using dynamic configuration

        Args:
            prompt: User's input message
            model_id: Bedrock model identifier
            persona_context: Persona configuration and context
            conversation_history: Previous messages for context
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0-1)
            stream: Whether to stream the response

        Returns:
            Dict with response content and metadata, or AsyncGenerator for streaming
        """
        try:
            print(f"🚀 Enhanced Bedrock call - Model: {model_id}, Stream: {stream}")

            # Get model configuration first
            if not model_config:
                print(f"🔄 CONFIG: No model config from frontend, fetching from DynamoDB...")
                model_config = await self.model_config_service.get_model_config(model_id)
                if not model_config:
                    raise ValueError(f"Model configuration not found for: {model_id}")
            else:
                print(f"✅ CONFIG: Using model config from frontend for {model_config.get('name', model_id)}")

            print(f"✓ Model config loaded for: {model_config.get('name', model_id)}")

            # STEP 0: Check if this is a local Ollama model
            if OllamaService.is_ollama_model(model_config):
                print(f"🏠 ROUTING: Local Ollama model detected, using OllamaService")
                return await ollama_service.call_model(
                    prompt=prompt,
                    model_id=model_id,
                    persona_context=persona_context,
                    conversation_history=conversation_history,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=stream,
                    model_config=model_config,
                    **kwargs
                )

            # STEP 1: Check if model has pipeline configuration (new system)
            if model_config.get("request_pipeline") and model_config.get("response_pipeline"):
                print(f"🌐 ROUTING: Model has pipeline configuration, using Universal Adapter")
                return await universal_model_adapter.invoke_model(
                    model_id=model_id,
                    prompt=prompt,
                    persona_context=persona_context,
                    conversation_history=conversation_history,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=stream,
                    model_config=model_config,
                    **kwargs
                )

            # STEP 2: Fallback to specialized services for legacy configurations
            if anthropic_claude_service.is_anthropic_model(model_id):
                print(f"🤖 ROUTING: Detected Anthropic model, using specialized service (legacy)")
                result = await anthropic_claude_service.call_anthropic_model(
                    prompt=prompt,
                    model_id=model_id,
                    persona_context=persona_context,
                    conversation_history=conversation_history,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=stream,
                    model_config=model_config,
                    **kwargs
                )
                
                # Return the result directly (it's already properly awaited)
                return result

            # STEP 3: For models without pipeline config, continue with existing logic
            print(f"⚠️ ROUTING: No pipeline config found, using legacy template system")

            # Build formatted prompt using model's template
            formatted_prompt = self._build_formatted_prompt(
                model_config=model_config,
                user_prompt=prompt,
                persona_context=persona_context,
                conversation_history=conversation_history,
                model_type_override=kwargs.get("model_type_override")
            )

            print(f"✓ Formatted prompt: {formatted_prompt[:100]}...")

            # Build request body using model's parameter configuration
            request_body = self._build_request_body(
                model_config=model_config,
                formatted_prompt=formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

            print(f"✓ Request body built: {json.dumps(request_body, indent=2)[:200]}...")

            # Check API type and route to appropriate method
            api_type = model_config.get("request_config", {}).get("api_type", "invoke_model")

            if api_type == "converse":
                # Use Converse API for Nova models
                if stream:
                    return await self._converse_streaming(model_id, model_config, request_body)
                else:
                    return await self._converse_sync(model_id, model_config, request_body)
            else:
                # Use InvokeModel API for DeepSeek, Claude, etc.
                if stream:
                    return self._invoke_model_streaming(model_id, model_config, request_body)
                else:
                    return await self._invoke_model_sync(model_id, model_config, request_body)

        except Exception as e:
            print(f"ERROR: Enhanced Bedrock model invocation failed: {e}")
            raise

    # _get_model_config method removed - now using ModelConfigService from DynamoDB

    def _build_formatted_prompt(
        self,
        model_config: Dict[str, Any],
        user_prompt: str,
        persona_context: Dict[str, Any] = None,
        conversation_history: List[Dict[str, Any]] = None,
        model_type_override: str = None
    ) -> str:
        """Build formatted prompt using model's template configuration with dynamic selection"""

        prompt_config = model_config.get("prompt_config", {})
        
        # NEW: Dynamic template selection based on model type
        template = PromptTemplateEngine.select_template(
            prompt_config=prompt_config,
            model_type_override=model_type_override
        )

        # Add system prompt from persona context if available
        system_prompt = None
        if persona_context and persona_context.get("system_prompt"):
            system_prompt = persona_context["system_prompt"]

        # Use template engine to format prompt
        formatted_prompt = PromptTemplateEngine.format_prompt(
            template=template,
            user_message=user_prompt,
            conversation_history=conversation_history,
            system_prompt=system_prompt
        )

        return formatted_prompt

    def _build_request_body(
        self,
        model_config: Dict[str, Any],
        formatted_prompt: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Build request body using model's parameter configuration"""

        # Use dynamic request builder
        request_body = DynamicRequestBuilder.build_request(
            model_config=model_config,
            prompt=formatted_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=kwargs.get("top_p", 0.9),
            **kwargs
        )

        return request_body

    async def _converse_sync(
        self,
        model_id: str,
        model_config: Dict[str, Any],
        request_body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synchronous Converse API invocation for Nova models"""
        try:
            print(f"📞 Invoking model with Converse API: {model_id}")

            # Extract parameters for Converse API
            messages = request_body.get("messages", [])
            inference_config = request_body.get("inferenceConfig", {})

            response = self.bedrock_runtime_client.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig=inference_config
            )

            print(f"✓ Converse response: {json.dumps(response, default=str, indent=2)[:300]}...")

            # Extract content using Nova's response format
            response_config = model_config.get("response_config", {})
            content = self._extract_content_from_converse_response(response_config, response)

            # Extract usage information
            usage = response.get("usage", {})

            return {
                "content": content,
                "usage": usage,
                "model_id": model_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"ERROR: Bedrock Converse ClientError {error_code}: {error_message}")
            raise Exception(f"Bedrock Converse API error: {error_message}")

        except Exception as e:
            print(f"ERROR: Bedrock Converse sync invocation failed: {e}")
            raise

    async def _converse_streaming(
        self,
        model_id: str,
        model_config: Dict[str, Any],
        request_body: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming Converse API invocation for Nova models"""
        try:
            print(f"📡 Invoking model with Converse Stream API: {model_id}")

            # Extract parameters for Converse Stream API
            messages = request_body.get("messages", [])
            inference_config = request_body.get("inferenceConfig", {})

            # Make the actual AWS call in sync mode but wrap in async function
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.bedrock_runtime_client.converse_stream(
                    modelId=model_id,
                    messages=messages,
                    inferenceConfig=inference_config
                )
            )

            print(f"✓ Converse streaming response received for: {model_id}")

            # Get response configuration
            response_config = model_config.get("response_config", {})

            # Process streaming response
            stream = response.get('stream')
            if stream:
                for event in stream:
                    if 'contentBlockDelta' in event:
                        delta = event['contentBlockDelta']['delta']
                        if 'text' in delta:
                            yield {
                                "content": delta['text'],
                                "model_id": model_id,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }

                    # Check for final chunk with usage info
                    elif 'messageStop' in event:
                        usage = event.get('messageStop', {})
                        yield {
                            "content": "",
                            "usage": usage,
                            "model_id": model_id,
                            "is_final": True,
                            "timestamp": datetime.utcnow().isoformat() + "Z"
                        }

        except Exception as e:
            print(f"ERROR: Enhanced Bedrock Converse streaming failed: {e}")
            yield {
                "content": "",
                "error": str(e),
                "model_id": model_id,
                "is_final": True,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    def _extract_content_from_converse_response(self, response_config: Dict[str, Any], response: Dict[str, Any]) -> str:
        """Extract text content from Converse API response"""

        # Try to extract from output.message.content[0].text
        if "output" in response and "message" in response["output"]:
            message = response["output"]["message"]
            if "content" in message and len(message["content"]) > 0:
                first_content = message["content"][0]
                if "text" in first_content:
                    return first_content["text"]

        # Fallback
        return str(response)

    async def _invoke_model_sync(
        self,
        model_id: str,
        model_config: Dict[str, Any],
        request_body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synchronous model invocation with dynamic response parsing"""
        try:
            print(f"📞 Invoking model synchronously: {model_id}")

            response = self.bedrock_runtime_client.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )

            # Parse response body
            response_body = json.loads(response['body'].read())
            print(f"✓ Raw response: {json.dumps(response_body, indent=2)[:300]}...")

            # Extract content using model's response configuration
            response_config = model_config.get("response_config", {})
            content = self._extract_content_from_response(response_config, response_body)

            # Extract usage information
            usage = self._extract_usage_from_response(response_config, response_body)

            return {
                "content": content,
                "usage": usage,
                "model_id": model_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"ERROR: Bedrock ClientError {error_code}: {error_message}")
            raise Exception(f"Bedrock API error: {error_message}")

        except Exception as e:
            print(f"ERROR: Bedrock sync invocation failed: {e}")
            raise

    async def _invoke_model_streaming(
        self,
        model_id: str,
        model_config: Dict[str, Any],
        request_body: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming model invocation with dynamic response parsing"""
        try:
            print(f"📡 Invoking model with streaming: {model_id}")

            # Make the actual AWS call in sync mode but wrap in async function
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.bedrock_runtime_client.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(request_body),
                    contentType='application/json',
                    accept='application/json'
                )
            )

            print(f"✓ Streaming response received for: {model_id}")

            # Process streaming response
            response_config = model_config.get("response_config", {})
            stream = response.get('body')
            
            if stream:
                for event in stream:
                    chunk = event.get('chunk')
                    if chunk and chunk.get('bytes'):
                        chunk_data = json.loads(chunk.get('bytes').decode())
                        
                        # DEBUG: Log actual chunk structure for Llama models
                        if "meta.llama" in model_id:
                            print(f"🐛 LLAMA CHUNK DEBUG: {json.dumps(chunk_data, indent=2)}")
                        
                        content = self._extract_content_from_chunk(response_config, chunk_data)

                        if content:
                            yield {
                                "content": content,
                                "model_id": model_id,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }
                        else:
                            # DEBUG: Log when no content is extracted
                            if "meta.llama" in model_id:
                                print(f"🐛 NO CONTENT EXTRACTED from chunk with keys: {list(chunk_data.keys())}")

                        # Check for final chunk with usage
                        if self._is_final_chunk(response_config, chunk_data):
                            usage = self._extract_usage_from_response(response_config, chunk_data)
                            yield {
                                "content": "",
                                "usage": usage,
                                "model_id": model_id,
                                "is_final": True,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }

        except Exception as e:
            print(f"ERROR: Enhanced Bedrock streaming failed: {e}")
            yield {
                "content": "",
                "error": str(e),
                "model_id": model_id,
                "is_final": True,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    def _extract_content_from_response(self, response_config: Dict[str, Any], response_body: Dict[str, Any]) -> str:
        """Extract text content from model response using configuration"""

        content_path = response_config.get("content_path", "completion")

        # Try configured path first
        if content_path in response_body:
            return response_body[content_path]

        # Fallback to common paths
        common_paths = ["completion", "text", "content", "output"]
        for path in common_paths:
            if path in response_body:
                return response_body[path]

        # Handle nested structures
        if "outputs" in response_body and len(response_body["outputs"]) > 0:
            return response_body["outputs"][0].get("text", "")

        # Default fallback
        return str(response_body)

    def _extract_content_from_chunk(self, response_config: Dict[str, Any], chunk_data: Dict[str, Any]) -> str:
        """Extract text content from streaming chunk using configuration"""

        # Check for DeepSeek format: choices[0].text
        if "choices" in chunk_data and isinstance(chunk_data["choices"], list) and len(chunk_data["choices"]) > 0:
            choice = chunk_data["choices"][0]
            if "text" in choice:
                content = choice["text"]
                # print(f"✅ CONTENT: '{content}'")
                return str(content)

        # Check configured path
        streaming_content_path = response_config.get("streaming_content_path", "completion")
        if streaming_content_path in chunk_data:
            content = chunk_data[streaming_content_path]
            # print(f"✅ CONTENT: '{content}'")
            return str(content)

        # Fallback paths
        for path in ["completion", "text", "delta", "content"]:
            if path in chunk_data:
                content = chunk_data[path]
                # print(f"✅ CONTENT: '{content}'")
                return str(content)

        # print(f"❌ NO CONTENT in: {list(chunk_data.keys())}")
        return ""

    def _extract_usage_from_response(self, response_config: Dict[str, Any], response_body: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage information from response using configuration"""

        usage_path = response_config.get("usage_path", "usage")

        if usage_path in response_body:
            return response_body[usage_path]

        # Default structure
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }

    def _is_final_chunk(self, response_config: Dict[str, Any], chunk_data: Dict[str, Any]) -> bool:
        """Check if this is the final chunk in streaming response"""

        # Look for completion indicators in chunk
        if "stop_reason" in chunk_data:
            return True
        if chunk_data.get("type") == "completion":
            return True
        if "completionReason" in chunk_data:
            return True

        return False

    async def health_check(self) -> Dict[str, Any]:
        """Health check for enhanced Bedrock service"""
        try:
            # Test basic connectivity by listing available models
            response = self.bedrock_client.list_foundation_models()

            available_models = len(response.get('modelSummaries', []))

            # Count configured models
            configured_models = len(self.model_configs)

            return {
                "status": "healthy",
                "available_models": available_models,
                "configured_models": configured_models,
                "region": self.region,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "region": self.region,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }