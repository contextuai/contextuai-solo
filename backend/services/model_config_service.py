"""
MongoDB Model Configuration Service

Handles fetching and managing model configurations from MongoDB,
replacing the static model_configs.py approach.
"""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from database import get_database
from repositories import ModelRepository

logger = logging.getLogger(__name__)


class ModelConfigService:
    """Service to manage model configurations in MongoDB"""

    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "dev")

        # Cache for model configs to reduce database calls
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes
        self._last_cache_update = 0

        # Repository will be lazily initialized
        self._repo: Optional[ModelRepository] = None

        print(f"ModelConfigService initialized - Environment: {self.environment}")

    async def _get_repo(self) -> ModelRepository:
        """Lazily initialize and return the ModelRepository"""
        if self._repo is None:
            db = await get_database()
            self._repo = ModelRepository(db)
        return self._repo

    async def get_model_config(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get model configuration by model identifier from MongoDB with caching

        Args:
            model_id: The model identifier (e.g., "us.deepseek.r1-v1:0")

        Returns:
            Model configuration dict or None if not found
        """
        try:
            # Check cache first
            if self._is_cache_valid():
                if model_id in self._cache:
                    print(f"CONFIG: Using cached config for {model_id}")
                    return self._cache[model_id]

            # Fetch from MongoDB
            print(f"CONFIG: Fetching {model_id} from MongoDB...")
            repo = await self._get_repo()

            # Look up by the 'model' field which contains the model identifier
            config = await repo.get_one({"model": model_id})

            if config is None:
                # Try fallback patterns for cross-region models
                fallback_config = await self._try_fallback_patterns(model_id)
                if fallback_config:
                    return fallback_config

                print(f"CONFIG: Model {model_id} not found in MongoDB")
                return None

            # Cache the result
            self._cache[model_id] = config
            self._last_cache_update = datetime.utcnow().timestamp()

            print(f"CONFIG: {config.get('name', 'Unknown')} ({config.get('provider', 'Unknown')})")
            return config

        except Exception as e:
            print(f"CONFIG: Error fetching model {model_id}: {e}")
            logger.error(f"Error fetching model config for {model_id}: {e}")
            return None

    async def _try_fallback_patterns(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Try fallback patterns for cross-region models"""
        fallback_patterns = []

        # Add us. prefix if not present
        if not model_id.startswith("us."):
            fallback_patterns.append(f"us.{model_id}")

        # Remove us. prefix if present
        if model_id.startswith("us."):
            fallback_patterns.append(model_id.replace("us.", "", 1))

        # Add anthropic prefix for Claude models
        if not model_id.startswith("anthropic") and "claude" in model_id.lower():
            fallback_patterns.append(f"anthropic.{model_id}")

        repo = await self._get_repo()

        for pattern in fallback_patterns:
            try:
                config = await repo.get_one({"model": pattern})
                if config:
                    print(f"CONFIG: Using fallback config: {pattern} for {model_id}")
                    # Cache both the original and fallback
                    self._cache[model_id] = config
                    self._cache[pattern] = config
                    return config
            except Exception as e:
                print(f"CONFIG: Fallback pattern {pattern} failed: {e}")
                continue

        return None

    async def list_enabled_models(self) -> List[Dict[str, Any]]:
        """Get all enabled models from MongoDB"""
        try:
            repo = await self._get_repo()

            # Use the repository's get_enabled_models method
            models = await repo.get_enabled_models()
            print(f"CONFIG: Found {len(models)} enabled models")

            # Update cache with all models
            for model in models:
                model_identifier = model.get('model')
                if model_identifier:
                    self._cache[model_identifier] = model

            self._last_cache_update = datetime.utcnow().timestamp()

            return models

        except Exception as e:
            print(f"CONFIG: Error listing models: {e}")
            logger.error(f"Error listing enabled models: {e}")
            return []

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        if not self._cache:
            return False

        current_time = datetime.utcnow().timestamp()
        return (current_time - self._last_cache_update) < self._cache_ttl

    def clear_cache(self):
        """Clear the model configuration cache"""
        self._cache.clear()
        self._last_cache_update = 0
        print("CONFIG: Cache cleared")

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the model config service"""
        try:
            repo = await self._get_repo()

            # Count enabled models using repository method
            counts = await repo.count_by_enabled_status()

            return {
                "status": "healthy",
                "database": "mongodb",
                "environment": self.environment,
                "enabled_models": counts.get("enabled", 0),
                "total_models": counts.get("total", 0),
                "cache_size": len(self._cache),
                "cache_valid": self._is_cache_valid()
            }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "database": "mongodb",
                "environment": self.environment
            }


# Template selection utility (moved from model_configs.py)
class PromptTemplateEngine:
    """Dynamic prompt template selection based on model configuration"""

    @staticmethod
    def select_template(prompt_config: dict, model_type_override: str = None) -> str:
        """Select appropriate template based on model type"""

        # Get model type from config or override
        model_type = model_type_override or prompt_config.get("model_type", "direct")

        # Get templates dictionary
        templates = prompt_config.get("templates", {})

        # Select template based on type
        if model_type in templates:
            selected_template = templates[model_type]
            print(f"TEMPLATE: Using '{model_type}' template")
            return selected_template

        # Fallback to default template
        default_template = prompt_config.get("default_template", "direct")
        if default_template in templates:
            print(f"TEMPLATE: Falling back to '{default_template}' template")
            return templates[default_template]

        # Final fallback - use first available template
        if templates:
            first_template = list(templates.values())[0]
            print(f"TEMPLATE: Using first available template")
            return first_template

        # Emergency fallback
        print(f"TEMPLATE: No templates found, using basic format")
        return "{{user_message}}"

    @staticmethod
    def format_prompt(template: str, user_message: str, conversation_history: list = None, system_prompt: str = None) -> str:
        """Format prompt using template with context"""

        # Handle conversation history if provided
        if conversation_history and len(conversation_history) > 0:
            # Build conversation context based on model's format
            conversation_text = ""
            for msg in conversation_history[-10:]:  # Last 10 messages
                if msg.get("message_type") == "user":
                    conversation_text += f"User: {msg.get('content', '')}\n"
                elif msg.get("message_type") == "assistant":
                    conversation_text += f"Assistant: {msg.get('content', '')}\n"

            # If we have conversation history, include it in the template
            if conversation_text:
                template = f"{conversation_text}\nUser: {user_message}\nAssistant: "
                return template

        # Handle system prompt if provided
        if system_prompt:
            template = f"System: {system_prompt}\n\n{template}"

        # Replace template variables
        formatted_prompt = template.replace("{{user_message}}", user_message)

        return formatted_prompt


class DynamicRequestBuilder:
    """Dynamic request builder for different model types"""

    @staticmethod
    def build_request(model_config: dict, prompt: str, max_tokens: int, temperature: float, top_p: float = 0.9, **kwargs) -> dict:
        """Build request body based on model configuration"""

        request_config = model_config.get("request_config", {})
        parameters = request_config.get("parameters", {})
        parameter_mapping = request_config.get("parameter_mapping", {})
        default_values = request_config.get("default_values", {})

        # Start with default values
        request_body = default_values.copy()

        # Apply parameter mapping and values
        for template_key, value_template in parameters.items():
            if isinstance(value_template, str) and "{{" in value_template:
                # Replace template variables
                if "{{formatted_prompt}}" in value_template:
                    request_body[template_key] = value_template.replace("{{formatted_prompt}}", prompt)
                elif "{{max_tokens}}" in value_template:
                    request_body[template_key] = max_tokens
                elif "{{temperature}}" in value_template:
                    request_body[template_key] = temperature
                elif "{{top_p}}" in value_template:
                    request_body[template_key] = top_p
            else:
                # Direct assignment
                request_body[template_key] = value_template

        # Apply parameter mapping for renamed fields
        mapped_body = {}
        for key, value in request_body.items():
            mapped_key = parameter_mapping.get(key, key)
            mapped_body[mapped_key] = value

        return mapped_body

# Global instance for dependency injection
model_config_service = ModelConfigService()
