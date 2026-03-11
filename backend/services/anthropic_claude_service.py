# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Specialized service for handling Anthropic Claude models via AWS Bedrock.
Based on Amazon's official example and integrated with the existing architecture.
"""

import boto3
import json
import os
import logging
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
import asyncio
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime

# Import our model configuration service
from .model_config_service import model_config_service

logger = logging.getLogger(__name__)

class AnthropicClaudeService:
    """
    Specialized service for Anthropic Claude models with proper message formatting
    and system prompt handling as per Anthropic's API requirements.
    """

    def __init__(self):
        self.region = os.getenv("AWS_BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))
        self.bedrock_runtime_client = None
        self.model_config_service = model_config_service
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Bedrock Runtime client"""
        try:
            self.bedrock_runtime_client = boto3.client(
                service_name='bedrock-runtime',
                region_name=self.region
            )
            print(f"✓ AnthropicClaudeService initialized for region: {self.region}")

        except Exception as e:
            print(f"ERROR: Failed to initialize Anthropic Claude service: {e}")
            raise

    def is_anthropic_model(self, model_id: str) -> bool:
        """Check if the given model_id is an Anthropic Claude model"""
        anthropic_indicators = [
            'anthropic',
            'claude',
            'claude-3',
            'claude-2',
            'claude-instant'
        ]
        
        model_id_lower = model_id.lower()
        return any(indicator in model_id_lower for indicator in anthropic_indicators)

    async def call_anthropic_model(
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
        """
        Call Anthropic Claude model using proper message format and system prompts
        
        Args:
            prompt: User's input message
            model_id: Anthropic Claude model identifier
            persona_context: Persona configuration with system prompt
            conversation_history: Previous messages for context
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0-1)
            stream: Whether to stream the response
            model_config: Model configuration from frontend or DynamoDB
            
        Returns:
            Dict with response content and metadata, or AsyncGenerator for streaming
        """
        try:
            print(f"🤖 Anthropic Claude call - Model: {model_id}, Stream: {stream}")

            # Get model configuration if not provided
            if not model_config:
                model_config = await self.model_config_service.get_model_config(model_id)
                if not model_config:
                    raise ValueError(f"Anthropic model configuration not found for: {model_id}")

            # Build system prompt and messages in Anthropic format
            system_prompt, messages = self._build_anthropic_messages(
                user_prompt=prompt,
                persona_context=persona_context,
                conversation_history=conversation_history
            )

            # Build request body according to Anthropic's requirements
            request_body = self._build_anthropic_request_body(
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

            print(f"✓ Anthropic request built with {len(messages)} messages")
            print(f"✓ System prompt: {system_prompt[:100]}..." if system_prompt else "✓ No system prompt")

            if stream:
                return self._invoke_anthropic_streaming(model_id, request_body)
            else:
                return await self._invoke_anthropic_sync(model_id, request_body)

        except Exception as e:
            print(f"ERROR: Anthropic Claude model invocation failed: {e}")
            raise

    def _build_anthropic_messages(
        self,
        user_prompt: str,
        persona_context: Dict[str, Any] = None,
        conversation_history: List[Dict[str, Any]] = None
    ) -> tuple[Optional[str], List[Dict[str, str]]]:
        """
        Build system prompt and messages array in Anthropic format
        
        Returns:
            Tuple of (system_prompt, messages_array)
        """
        # Extract system prompt from persona context
        system_prompt = None
        if persona_context and persona_context.get("system_prompt"):
            system_prompt = persona_context["system_prompt"]

        # Build messages array
        messages = []

        # Add conversation history if available
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages for context
                if msg.get("message_type") == "user":
                    messages.append({
                        "role": "user",
                        "content": msg.get("content", "")
                    })
                elif msg.get("message_type") == "assistant":
                    messages.append({
                        "role": "assistant", 
                        "content": msg.get("content", "")
                    })

        # Add current user message
        messages.append({
            "role": "user",
            "content": user_prompt
        })

        # Ensure we start with a user message (Anthropic requirement)
        if messages and messages[0]["role"] != "user":
            # Remove the first assistant message if it exists
            messages = [msg for msg in messages if msg["role"] == "user" or 
                       messages.index(msg) > 0]

        return system_prompt, messages

    def _build_anthropic_request_body(
        self,
        system_prompt: Optional[str],
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build request body according to Anthropic's API format
        """
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": messages
        }

        # Add system prompt if provided
        if system_prompt:
            body["system"] = system_prompt

        # Add temperature if different from default
        if temperature != 0.7:
            body["temperature"] = temperature

        # Add other optional parameters
        if "top_p" in kwargs and kwargs["top_p"] != 0.9:
            body["top_p"] = kwargs["top_p"]
            
        if "top_k" in kwargs:
            body["top_k"] = kwargs["top_k"]

        return body

    async def _invoke_anthropic_sync(
        self,
        model_id: str,
        request_body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synchronous Anthropic model invocation"""
        try:
            print(f"📞 Invoking Anthropic model synchronously: {model_id}")

            response = self.bedrock_runtime_client.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )

            # Parse response body
            response_body = json.loads(response['body'].read())
            print(f"✓ Anthropic raw response: {json.dumps(response_body, indent=2)[:300]}...")

            # Extract content from Anthropic response format
            content = self._extract_anthropic_content(response_body)
            usage = self._extract_anthropic_usage(response_body)

            return {
                "content": content,
                "usage": usage,
                "model_id": model_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"ERROR: Anthropic Bedrock ClientError {error_code}: {error_message}")
            raise Exception(f"Anthropic Bedrock API error: {error_message}")

        except Exception as e:
            print(f"ERROR: Anthropic sync invocation failed: {e}")
            raise

    async def _invoke_anthropic_streaming(
        self,
        model_id: str,
        request_body: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming Anthropic model invocation"""
        try:
            print(f"📡 Invoking Anthropic model with streaming: {model_id}")

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

            print(f"✓ Anthropic streaming response received for: {model_id}")

            # Process streaming response
            stream = response.get('body')
            if stream:
                for event in stream:
                    chunk = event.get('chunk')
                    if chunk and chunk.get('bytes'):
                        chunk_data = json.loads(chunk.get('bytes').decode())
                        
                        # Extract content from Anthropic streaming format
                        content = self._extract_anthropic_streaming_content(chunk_data)
                        
                        if content:
                            yield {
                                "content": content,
                                "model_id": model_id,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }

                        # Check for final chunk with usage
                        if self._is_anthropic_final_chunk(chunk_data):
                            usage = self._extract_anthropic_usage(chunk_data)
                            yield {
                                "content": "",
                                "usage": usage,
                                "model_id": model_id,
                                "is_final": True,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }

        except Exception as e:
            print(f"ERROR: Anthropic streaming failed: {e}")
            yield {
                "content": "",
                "error": str(e),
                "model_id": model_id,
                "is_final": True,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    def _extract_anthropic_content(self, response_body: Dict[str, Any]) -> str:
        """Extract text content from Anthropic response"""
        # Anthropic response format: {"content": [{"text": "response", "type": "text"}], ...}
        if "content" in response_body and isinstance(response_body["content"], list):
            for content_block in response_body["content"]:
                if content_block.get("type") == "text" and "text" in content_block:
                    return content_block["text"]
        
        # Fallback for other formats
        if "completion" in response_body:
            return response_body["completion"]
            
        # Last resort
        return str(response_body)

    def _extract_anthropic_streaming_content(self, chunk_data: Dict[str, Any]) -> str:
        """Extract text content from Anthropic streaming chunk"""
        # Check for Anthropic streaming format
        if "delta" in chunk_data and "text" in chunk_data["delta"]:
            return chunk_data["delta"]["text"]
        
        # Check for content_block_delta format
        if "content_block_delta" in chunk_data:
            delta = chunk_data["content_block_delta"]
            if "delta" in delta and "text" in delta["delta"]:
                return delta["delta"]["text"]
        
        # Fallback patterns
        if "completion" in chunk_data:
            return chunk_data["completion"]
            
        return ""

    def _extract_anthropic_usage(self, response_body: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage from Anthropic response"""
        if "usage" in response_body:
            usage = response_body["usage"]
            return {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            }
        
        # Default structure
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }

    def _is_anthropic_final_chunk(self, chunk_data: Dict[str, Any]) -> bool:
        """Check if this is the final chunk in Anthropic streaming response"""
        # Look for Anthropic completion indicators
        if chunk_data.get("type") == "message_stop":
            return True
        if "stop_reason" in chunk_data:
            return True
        if chunk_data.get("type") == "content_block_stop":
            return True
        
        return False

    async def health_check(self) -> Dict[str, Any]:
        """Health check for Anthropic Claude service"""
        try:
            # Test with a simple Anthropic model call
            test_model = "anthropic.claude-3-haiku-20240307-v1:0"
            test_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Hello"}]
            }

            response = self.bedrock_runtime_client.invoke_model(
                modelId=test_model,
                body=json.dumps(test_body),
                contentType='application/json',
                accept='application/json'
            )

            return {
                "status": "healthy",
                "service": "anthropic_claude",
                "region": self.region,
                "test_model": test_model,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "anthropic_claude",
                "error": str(e),
                "region": self.region,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

# Global instance for dependency injection
anthropic_claude_service = AnthropicClaudeService()
