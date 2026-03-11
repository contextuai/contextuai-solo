"""
Universal Model Adapter - Configuration-driven model invocation system.
This adapter can handle any model by using transformation pipelines defined in configuration.
"""

import boto3
import json
import os
import asyncio
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
from datetime import datetime
from botocore.exceptions import ClientError

from .pipeline_engine import PipelineExecutor
from .model_config_service import model_config_service

class UniversalModelAdapter:
    """
    Universal adapter that can invoke any model using configuration-driven pipelines.
    No code changes needed for new models - just update the configuration.
    """
    
    def __init__(self):
        self.region = os.getenv("AWS_BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))
        self.model_config_service = model_config_service
        
        # Initialize AWS clients
        self.bedrock_runtime_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=self.region
        )
        
        # Cache for pipeline executors
        self._pipeline_cache = {}
        
        print(f"🌐 UNIVERSAL ADAPTER: Initialized for region {self.region}")
    
    async def invoke_model(
        self,
        model_id: str,
        prompt: str,
        persona_context: Dict[str, Any] = None,
        conversation_history: List[Dict[str, Any]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
        model_config: Dict[str, Any] = None,
        **kwargs
    ) -> Union[Dict[str, Any], AsyncGenerator[Dict[str, Any], None]]:
        """
        Universal model invocation method that works with any configured model.
        
        Args:
            model_id: The model identifier
            prompt: User's input message
            persona_context: Persona configuration with system prompt
            conversation_history: Previous messages for context
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0-1)
            stream: Whether to stream the response
            model_config: Model configuration (if not provided, fetched from DynamoDB)
            **kwargs: Additional parameters
            
        Returns:
            Dict with response content and metadata, or AsyncGenerator for streaming
        """
        try:
            print(f"🌐 UNIVERSAL: Invoking {model_id} (stream={stream})")
            
            # Get model configuration
            if not model_config:
                model_config = await self.model_config_service.get_model_config(model_id)
                if not model_config:
                    raise ValueError(f"Model configuration not found for: {model_id}")
            
            # Get or create pipeline executor for this model
            executor = await self._get_pipeline_executor(model_id, model_config)
            
            # Prepare base request data
            request_data = {
                "model_id": model_id,
                "prompt": prompt,
                "persona_context": persona_context or {},
                "conversation_history": conversation_history or [],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": stream,
                **kwargs
            }
            
            # Transform request through pipeline
            transformed_request = await executor.transform_request(request_data)
            print(f"✅ UNIVERSAL: Request transformed for {model_id}")
            
            # Determine API type and invoke accordingly
            api_type = executor.get_api_type()
            
            if stream and executor.supports_streaming():
                return self._invoke_streaming(model_id, transformed_request, executor, api_type)
            else:
                return await self._invoke_sync(model_id, transformed_request, executor, api_type)
                
        except Exception as e:
            print(f"❌ UNIVERSAL: Failed to invoke {model_id}: {e}")
            raise
    
    async def _get_pipeline_executor(self, model_id: str, model_config: Dict[str, Any]) -> PipelineExecutor:
        """Get or create a pipeline executor for the model"""
        if model_id not in self._pipeline_cache:
            print(f"🏗️ UNIVERSAL: Creating pipeline executor for {model_id}")
            self._pipeline_cache[model_id] = PipelineExecutor(model_config)
        
        return self._pipeline_cache[model_id]
    
    async def _invoke_sync(
        self,
        model_id: str,
        transformed_request: Dict[str, Any],
        executor: PipelineExecutor,
        api_type: str
    ) -> Dict[str, Any]:
        """Synchronous model invocation"""
        try:
            print(f"📞 UNIVERSAL: Sync invocation of {model_id} via {api_type}")
            
            if api_type == "bedrock_converse":
                response = await self._call_converse_api(model_id, transformed_request)
            else:
                response = await self._call_invoke_model_api(model_id, transformed_request)
            
            # Add metadata
            response["model_id"] = model_id
            response["timestamp"] = datetime.utcnow().isoformat() + "Z"
            
            # Transform response through pipeline
            transformed_response = await executor.transform_response(response)
            
            print(f"✅ UNIVERSAL: Sync response transformed for {model_id}")
            return transformed_response
            
        except Exception as e:
            print(f"❌ UNIVERSAL: Sync invocation failed for {model_id}: {e}")
            raise
    
    async def _invoke_streaming(
        self,
        model_id: str,
        transformed_request: Dict[str, Any],
        executor: PipelineExecutor,
        api_type: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming model invocation"""
        try:
            print(f"📡 UNIVERSAL: Streaming invocation of {model_id} via {api_type}")
            
            if api_type == "bedrock_converse":
                stream_generator = self._call_converse_stream_api(model_id, transformed_request)
            else:
                stream_generator = self._call_invoke_model_stream_api(model_id, transformed_request)
            
            # Process streaming chunks through pipeline
            async for chunk in stream_generator:
                # Add metadata to chunk
                chunk["model_id"] = model_id
                chunk["timestamp"] = datetime.utcnow().isoformat() + "Z"
                
                # Transform chunk through streaming pipeline
                transformed_chunk = await executor.transform_streaming_chunk(chunk)
                
                yield transformed_chunk
                
        except Exception as e:
            print(f"❌ UNIVERSAL: Streaming invocation failed for {model_id}: {e}")
            yield {
                "content": "",
                "error": str(e),
                "model_id": model_id,
                "is_final": True,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    
    async def _call_invoke_model_api(self, model_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Call Bedrock InvokeModel API"""
        # Remove non-API fields
        api_request = {k: v for k, v in request_data.items() 
                      if k not in ['model_id', 'stream', 'persona_context', 'conversation_history']}
        
        # Debug: Log the actual request being sent to AWS
        print(f"🐛 DEBUG: Final API request for {model_id}:")
        print(f"🐛 DEBUG: {json.dumps(api_request, indent=2)}")
        
        response = self.bedrock_runtime_client.invoke_model(
            modelId=model_id,
            body=json.dumps(api_request),
            contentType='application/json',
            accept='application/json'
        )
        
        return json.loads(response['body'].read())
    
    async def _call_invoke_model_stream_api(self, model_id: str, request_data: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Call Bedrock InvokeModelWithResponseStream API"""
        # Remove non-API fields
        api_request = {k: v for k, v in request_data.items() 
                      if k not in ['model_id', 'stream', 'persona_context', 'conversation_history']}
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.bedrock_runtime_client.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(api_request),
                contentType='application/json',
                accept='application/json'
            )
        )
        
        stream = response.get('body')
        if stream:
            for event in stream:
                chunk = event.get('chunk')
                if chunk and chunk.get('bytes'):
                    chunk_data = json.loads(chunk.get('bytes').decode())
                    
                    # DEBUG: Log raw chunk data for Llama models
                    if "meta.llama" in model_id:
                        print(f"🔍 RAW LLAMA CHUNK: {json.dumps(chunk_data, indent=2)}")
                    
                    yield chunk_data
    
    async def _call_converse_api(self, model_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Call Bedrock Converse API"""
        # Extract Converse API parameters
        messages = request_data.get("messages", [])
        inference_config = request_data.get("inferenceConfig", {})
        system_prompts = request_data.get("system", [])
        
        # Format system prompts for Converse API
        system = []
        if isinstance(system_prompts, str):
            system = [{"text": system_prompts}]
        elif isinstance(system_prompts, list):
            system = system_prompts
        
        converse_params = {
            "modelId": model_id,
            "messages": messages,
            "inferenceConfig": inference_config
        }
        
        if system:
            converse_params["system"] = system
        
        return self.bedrock_runtime_client.converse(**converse_params)
    
    async def _call_converse_stream_api(self, model_id: str, request_data: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Call Bedrock Converse Stream API"""
        # Extract Converse API parameters
        messages = request_data.get("messages", [])
        inference_config = request_data.get("inferenceConfig", {})
        system_prompts = request_data.get("system", [])
        
        # Format system prompts for Converse API
        system = []
        if isinstance(system_prompts, str):
            system = [{"text": system_prompts}]
        elif isinstance(system_prompts, list):
            system = system_prompts
        
        converse_params = {
            "modelId": model_id,
            "messages": messages,
            "inferenceConfig": inference_config
        }
        
        if system:
            converse_params["system"] = system
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.bedrock_runtime_client.converse_stream(**converse_params)
        )
        
        stream = response.get('stream')
        if stream:
            for event in stream:
                yield event
    
    def clear_cache(self):
        """Clear the pipeline executor cache"""
        self._pipeline_cache.clear()
        print("🔄 UNIVERSAL: Pipeline cache cleared")
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for universal adapter"""
        try:
            # Test basic connectivity
            models = self.bedrock_runtime_client.list_foundation_models()
            
            return {
                "status": "healthy",
                "service": "universal_model_adapter",
                "region": self.region,
                "cached_pipelines": len(self._pipeline_cache),
                "available_foundation_models": len(models.get('modelSummaries', [])),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "universal_model_adapter",
                "error": str(e),
                "region": self.region,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

# Global instance for dependency injection
universal_model_adapter = UniversalModelAdapter()
