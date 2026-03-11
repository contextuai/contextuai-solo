import boto3
import json
import os
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
import asyncio
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime

class BedrockService:
    """AWS Bedrock service integration for AI model invocation"""
    
    def __init__(self):
        self.region = os.getenv("AWS_BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))
        self.bedrock_client = None
        self.bedrock_runtime_client = None
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
        **kwargs
    ) -> Union[Dict[str, Any], AsyncGenerator[Dict[str, Any], None]]:
        """
        Call Bedrock model with proper prompt formatting and context
        
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
            # Build the complete prompt with context
            formatted_prompt = self._build_prompt(
                user_prompt=prompt,
                persona_context=persona_context,
                conversation_history=conversation_history
            )
            
            # Prepare model-specific request body
            request_body = self._prepare_request_body(
                model_id=model_id,
                prompt=formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            
            if stream:
                return self._invoke_model_streaming(model_id, request_body)
            else:
                return await self._invoke_model_sync(model_id, request_body)
                
        except Exception as e:
            print(f"ERROR: Bedrock model invocation failed: {e}")
            raise
    
    def _build_prompt(
        self,
        user_prompt: str,
        persona_context: Dict[str, Any] = None,
        conversation_history: List[Dict[str, Any]] = None
    ) -> str:
        """Build complete prompt with system context and conversation history"""
        
        prompt_parts = []
        
        # Add persona system prompt if available
        if persona_context and persona_context.get("system_prompt"):
            prompt_parts.append(f"System: {persona_context['system_prompt']}")
        
        # Add conversation history for context
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages for context
                role = "Human" if msg.get("message_type") == "user" else "Assistant"
                content = msg.get("content", "")
                prompt_parts.append(f"{role}: {content}")
        
        # Add current user prompt
        prompt_parts.append(f"Human: {user_prompt}")
        prompt_parts.append("Assistant:")
        
        return "\n\n".join(prompt_parts)
    
    def _prepare_request_body(
        self,
        model_id: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Prepare model-specific request body"""
        
        if "anthropic.claude" in model_id:
            # Claude models format
            return {
                "prompt": prompt,
                "max_tokens_to_sample": max_tokens,
                "temperature": temperature,
                "top_p": kwargs.get("top_p", 0.9),
                "stop_sequences": kwargs.get("stop_sequences", ["\n\nHuman:"])
            }
        
        elif "amazon.titan" in model_id:
            # Titan models format
            return {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": max_tokens,
                    "temperature": temperature,
                    "topP": kwargs.get("top_p", 0.9),
                    "stopSequences": kwargs.get("stop_sequences", [])
                }
            }
        
        elif "ai21.j2" in model_id:
            # AI21 Jurassic models format
            return {
                "prompt": prompt,
                "maxTokens": max_tokens,
                "temperature": temperature,
                "topP": kwargs.get("top_p", 0.9),
                "stopSequences": kwargs.get("stop_sequences", [])
            }
        
        elif "cohere.command" in model_id:
            # Cohere Command models format
            return {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "p": kwargs.get("top_p", 0.9),
                "stop_sequences": kwargs.get("stop_sequences", [])
            }
        
        elif "meta.llama" in model_id:
            # Llama models format
            return {
                "prompt": prompt,
                "max_gen_len": max_tokens,
                "temperature": temperature,
                "top_p": kwargs.get("top_p", 0.9)
            }
        
        else:
            # Default format (Claude-like)
            return {
                "prompt": prompt,
                "max_tokens_to_sample": max_tokens,
                "temperature": temperature,
                "top_p": kwargs.get("top_p", 0.9),
                "stop_sequences": kwargs.get("stop_sequences", ["\n\nHuman:"])
            }
    
    async def _invoke_model_sync(self, model_id: str, request_body: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous model invocation"""
        try:
            response = self.bedrock_runtime_client.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )
            
            # Parse response body
            response_body = json.loads(response['body'].read())
            
            # Extract content based on model type
            content = self._extract_content_from_response(model_id, response_body)
            
            # Extract usage information
            usage = self._extract_usage_from_response(model_id, response_body)
            
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
            print(f"ERROR: Bedrock invocation failed: {e}")
            raise
    
    async def _invoke_model_streaming(
        self,
        model_id: str,
        request_body: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming model invocation"""
        try:
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

            # Process streaming response
            stream = response.get('body')
            if stream:
                for event in stream:
                    chunk = event.get('chunk')
                    if chunk:
                        chunk_data = json.loads(chunk.get('bytes').decode())

                        # Extract content from chunk
                        content = self._extract_content_from_chunk(model_id, chunk_data)

                        if content:
                            yield {
                                "content": content,
                                "model_id": model_id,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }

                        # Check if this is the final chunk with usage info
                        if self._is_final_chunk(model_id, chunk_data):
                            usage = self._extract_usage_from_response(model_id, chunk_data)
                            yield {
                                "content": "",
                                "usage": usage,
                                "model_id": model_id,
                                "is_final": True,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }

        except Exception as e:
            print(f"ERROR: Bedrock streaming failed: {e}")
            yield {
                "content": "",
                "error": str(e),
                "model_id": model_id,
                "is_final": True,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    
    def _extract_content_from_response(self, model_id: str, response_body: Dict[str, Any]) -> str:
        """Extract text content from model response"""
        
        if "anthropic.claude" in model_id:
            return response_body.get("completion", "")
        
        elif "amazon.titan" in model_id:
            results = response_body.get("results", [])
            return results[0].get("outputText", "") if results else ""
        
        elif "ai21.j2" in model_id:
            completions = response_body.get("completions", [])
            return completions[0].get("data", {}).get("text", "") if completions else ""
        
        elif "cohere.command" in model_id:
            generations = response_body.get("generations", [])
            return generations[0].get("text", "") if generations else ""
        
        elif "meta.llama" in model_id:
            return response_body.get("generation", "")
        
        else:
            # Default extraction
            return response_body.get("completion", response_body.get("text", ""))
    
    def _extract_content_from_chunk(self, model_id: str, chunk_data: Dict[str, Any]) -> str:
        """Extract text content from streaming chunk"""
        
        if "anthropic.claude" in model_id:
            return chunk_data.get("completion", "")
        
        elif "amazon.titan" in model_id:
            return chunk_data.get("outputText", "")
        
        else:
            # Default chunk extraction
            return chunk_data.get("completion", chunk_data.get("text", ""))
    
    def _extract_usage_from_response(self, model_id: str, response_body: Dict[str, Any]) -> Dict[str, Any]:
        """Extract token usage information from response"""
        
        if "anthropic.claude" in model_id:
            return {
                "input_tokens": response_body.get("usage", {}).get("input_tokens", 0),
                "output_tokens": response_body.get("usage", {}).get("output_tokens", 0),
                "total_tokens": response_body.get("usage", {}).get("input_tokens", 0) + 
                               response_body.get("usage", {}).get("output_tokens", 0)
            }
        
        elif "amazon.titan" in model_id:
            return {
                "input_tokens": response_body.get("inputTextTokenCount", 0),
                "output_tokens": response_body.get("results", [{}])[0].get("tokenCount", 0),
                "total_tokens": response_body.get("inputTextTokenCount", 0) + 
                               response_body.get("results", [{}])[0].get("tokenCount", 0)
            }
        
        else:
            # Default usage extraction
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0
            }
    
    def _is_final_chunk(self, model_id: str, chunk_data: Dict[str, Any]) -> bool:
        """Check if this is the final chunk in streaming response"""
        
        # Look for completion indicators in chunk
        if "stop_reason" in chunk_data:
            return True
        if chunk_data.get("type") == "completion":
            return True
        if "amazon.titan" in model_id and "completionReason" in chunk_data:
            return True
        
        return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for Bedrock service"""
        try:
            # Test basic connectivity by listing available models
            response = self.bedrock_client.list_foundation_models()
            
            available_models = len(response.get('modelSummaries', []))
            
            return {
                "status": "healthy",
                "available_models": available_models,
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
    
    async def list_available_models(self) -> List[Dict[str, Any]]:
        """List available Bedrock models"""
        try:
            response = self.bedrock_client.list_foundation_models()
            
            models = []
            for model in response.get('modelSummaries', []):
                models.append({
                    "model_id": model.get('modelId'),
                    "model_name": model.get('modelName'),
                    "provider_name": model.get('providerName'),
                    "input_modalities": model.get('inputModalities', []),
                    "output_modalities": model.get('outputModalities', []),
                    "supported_inference_types": model.get('inferenceTypesSupported', [])
                })
            
            return models
            
        except Exception as e:
            print(f"ERROR: Failed to list Bedrock models: {e}")
            return []
