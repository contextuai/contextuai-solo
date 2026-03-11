"""
Pipeline engine for executing transformation chains on model requests and responses.
This allows for dynamic, configuration-driven model adaptation without code changes.
"""

from typing import Dict, Any, List, Optional, Callable, AsyncGenerator
import asyncio
from datetime import datetime

from .transformers.request_transformers import REQUEST_TRANSFORMER_REGISTRY
from .transformers.response_transformers import RESPONSE_TRANSFORMER_REGISTRY

class TransformationStep:
    """Represents a single transformation step in a pipeline"""
    
    def __init__(self, step_config: Dict[str, Any]):
        self.name = step_config.get("name", "unknown")
        self.transformer_name = step_config.get("transformer")
        self.parameters = step_config.get("parameters", {})
        self.condition = step_config.get("condition")  # Optional condition for conditional execution
        
        # Get the transformer function
        self.transformer_func = self._get_transformer_function()
    
    def _get_transformer_function(self) -> Callable:
        """Get the transformer function from the registry"""
        # Try request transformers first
        if self.transformer_name in REQUEST_TRANSFORMER_REGISTRY:
            return REQUEST_TRANSFORMER_REGISTRY[self.transformer_name]
        
        # Try response transformers
        if self.transformer_name in RESPONSE_TRANSFORMER_REGISTRY:
            return RESPONSE_TRANSFORMER_REGISTRY[self.transformer_name]
        
        # If not found, create a no-op transformer
        print(f"⚠️ PIPELINE: Transformer '{self.transformer_name}' not found, using no-op")
        return lambda data: data
    
    def should_execute(self, data: Dict[str, Any]) -> bool:
        """Check if this step should be executed based on conditions"""
        if not self.condition:
            return True
        
        # Simple condition evaluation (can be extended)
        if self.condition.get("field_exists"):
            return self.condition["field_exists"] in data
        
        if self.condition.get("field_equals"):
            field, value = list(self.condition["field_equals"].items())[0]
            return data.get(field) == value
            
        return True
    
    async def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute this transformation step"""
        if not self.should_execute(data):
            print(f"⏭️ PIPELINE: Skipping step '{self.name}' due to condition")
            return data
        
        try:
            print(f"🔄 PIPELINE: Executing step '{self.name}' ({self.transformer_name})")
            
            # Apply parameters if any
            if self.parameters:
                # This is a simple parameter injection - can be made more sophisticated
                data.update(self.parameters)
            
            # Execute the transformation
            result = self.transformer_func(data)
            
            # Handle async transformers if needed (future extension)
            if asyncio.iscoroutine(result):
                result = await result
            
            print(f"✅ PIPELINE: Step '{self.name}' completed")
            return result
            
        except Exception as e:
            print(f"❌ PIPELINE: Step '{self.name}' failed: {e}")
            # Decide whether to continue or fail the pipeline
            if self.parameters.get("optional", False):
                print(f"⚠️ PIPELINE: Optional step failed, continuing...")
                return data
            else:
                raise Exception(f"Pipeline step '{self.name}' failed: {e}")

class TransformationPipeline:
    """Executes a series of transformation steps in sequence"""
    
    def __init__(self, pipeline_config: List[Dict[str, Any]], pipeline_name: str = "unnamed"):
        self.pipeline_name = pipeline_name
        self.steps = [TransformationStep(step_config) for step_config in pipeline_config]
        print(f"🏗️ PIPELINE: Created '{pipeline_name}' with {len(self.steps)} steps")
    
    async def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute all steps in the pipeline"""
        print(f"🚀 PIPELINE: Starting '{self.pipeline_name}' pipeline")
        
        current_data = data.copy()  # Don't modify original data
        
        for i, step in enumerate(self.steps):
            try:
                current_data = await step.execute(current_data)
            except Exception as e:
                print(f"💥 PIPELINE: '{self.pipeline_name}' failed at step {i+1}: {e}")
                raise
        
        print(f"🎯 PIPELINE: '{self.pipeline_name}' completed successfully")
        return current_data

class StreamingTransformationPipeline:
    """Special pipeline for streaming responses that processes chunks"""
    
    def __init__(self, pipeline_config: List[Dict[str, Any]], pipeline_name: str = "streaming"):
        self.pipeline_name = pipeline_name
        self.steps = [TransformationStep(step_config) for step_config in pipeline_config]
        print(f"🏗️ STREAMING PIPELINE: Created '{pipeline_name}' with {len(self.steps)} steps")
    
    async def execute_chunk(self, chunk_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute pipeline on a single streaming chunk"""
        current_data = chunk_data.copy()
        
        for step in self.steps:
            try:
                current_data = await step.execute(current_data)
            except Exception as e:
                print(f"💥 STREAMING PIPELINE: '{self.pipeline_name}' failed: {e}")
                # For streaming, we might want to continue even if a step fails
                continue
        
        return current_data

class PipelineFactory:
    """Factory for creating pipelines from configuration"""
    
    @staticmethod
    def create_request_pipeline(config: Dict[str, Any]) -> TransformationPipeline:
        """Create a request transformation pipeline"""
        pipeline_config = config.get("request_pipeline", [])
        return TransformationPipeline(pipeline_config, "request")
    
    @staticmethod
    def create_response_pipeline(config: Dict[str, Any]) -> TransformationPipeline:
        """Create a response transformation pipeline"""
        pipeline_config = config.get("response_pipeline", [])
        return TransformationPipeline(pipeline_config, "response")
    
    @staticmethod
    def create_streaming_pipeline(config: Dict[str, Any]) -> StreamingTransformationPipeline:
        """Create a streaming response pipeline"""
        pipeline_config = config.get("streaming_pipeline", [])
        return StreamingTransformationPipeline(pipeline_config, "streaming")

class PipelineExecutor:
    """Main executor that manages all pipelines for a model"""
    
    def __init__(self, model_config: Dict[str, Any]):
        self.model_id = model_config.get("id", "unknown")
        self.model_config = model_config
        
        # Create pipelines from config
        self.request_pipeline = PipelineFactory.create_request_pipeline(model_config)
        self.response_pipeline = PipelineFactory.create_response_pipeline(model_config)
        self.streaming_pipeline = PipelineFactory.create_streaming_pipeline(model_config)
        
        print(f"🎛️ EXECUTOR: Created pipeline executor for {self.model_id}")
    
    async def transform_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform request using the request pipeline"""
        return await self.request_pipeline.execute(request_data)
    
    async def transform_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform response using the response pipeline"""
        return await self.response_pipeline.execute(response_data)
    
    async def transform_streaming_chunk(self, chunk_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform streaming chunk using the streaming pipeline"""
        return await self.streaming_pipeline.execute_chunk(chunk_data)
    
    def get_api_type(self) -> str:
        """Get the API type for this model"""
        return self.model_config.get("api_config", {}).get("type", "bedrock_invoke_model")
    
    def supports_streaming(self) -> bool:
        """Check if this model supports streaming"""
        return self.model_config.get("api_config", {}).get("supports_streaming", True)
