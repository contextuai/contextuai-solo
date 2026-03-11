"""
Model Repository for AI Model Configurations

Repository class for managing AI model configurations in MongoDB.
Provides methods for CRUD operations with filtering by enabled status.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class ModelRepository(BaseRepository):
    """
    Repository for AI model configurations.

    Manages the 'models' collection in MongoDB, providing methods for
    retrieving, creating, updating, and deleting AI model configurations.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for models
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the ModelRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "models")

    async def get_all_models(
        self,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all AI model configurations.

        Args:
            skip: Number of documents to skip (offset)
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting.
                  Direction: 1 for ascending, -1 for descending.
                  Default: sort by name ascending.

        Returns:
            List of model documents with id fields
        """
        if sort is None:
            sort = [("name", 1)]

        return await self.get_all(
            filter={},
            skip=skip,
            limit=limit,
            sort=sort
        )

    async def get_enabled_models(
        self,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all enabled AI model configurations.

        Args:
            skip: Number of documents to skip (offset)
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting.
                  Default: sort by name ascending.

        Returns:
            List of enabled model documents with id fields
        """
        if sort is None:
            sort = [("name", 1)]

        # Handle both boolean and string 'enabled' values for backward compatibility
        filter_query = {
            "$or": [
                {"enabled": True},
                {"enabled": "true"}
            ]
        }

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=sort
        )

    async def get_disabled_models(
        self,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all disabled AI model configurations.

        Args:
            skip: Number of documents to skip (offset)
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting.
                  Default: sort by name ascending.

        Returns:
            List of disabled model documents with id fields
        """
        if sort is None:
            sort = [("name", 1)]

        # Handle both boolean and string 'enabled' values for backward compatibility
        filter_query = {
            "$or": [
                {"enabled": False},
                {"enabled": "false"},
                {"enabled": {"$exists": False}}
            ]
        }

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=sort
        )

    async def get_by_id(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a model configuration by its ID.

        Args:
            model_id: String representation of the model's ObjectId

        Returns:
            Model document with id field, or None if not found

        Raises:
            ValueError: If model_id is not a valid ObjectId string
        """
        return await super().get_by_id(model_id)

    async def get_by_provider(
        self,
        provider: str,
        enabled_only: bool = False,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve models by provider (e.g., 'openai', 'anthropic', 'bedrock').

        Args:
            provider: The model provider name
            enabled_only: If True, return only enabled models
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of model documents matching the provider
        """
        filter_query: Dict[str, Any] = {"provider": provider}

        if enabled_only:
            filter_query["$or"] = [
                {"enabled": True},
                {"enabled": "true"}
            ]

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new model configuration.

        Args:
            data: Model configuration data including:
                - name: Display name of the model
                - provider: Provider name (e.g., 'openai', 'anthropic')
                - model: Model identifier
                - max_tokens: Maximum token limit
                - enabled: Whether the model is enabled
                - description: Model description
                - capabilities: List of model capabilities
                - input_cost: Cost per input token
                - output_cost: Cost per output token
                - context_window: Context window size
                - supports_vision: Whether model supports vision
                - supports_function_calling: Whether model supports function calling
                - prompt_config: Prompt configuration settings
                - request_config: Request configuration settings
                - response_config: Response configuration settings
                - model_metadata: Additional model metadata

        Returns:
            Created model document with id field
        """
        return await super().create(data)

    async def update(self, model_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update a model configuration.

        Args:
            model_id: String representation of the model's ObjectId
            data: Fields to update (partial update supported)

        Returns:
            Updated model document with id field, or None if not found

        Raises:
            ValueError: If model_id is not a valid ObjectId string
        """
        return await super().update(model_id, data)

    async def delete(self, model_id: str) -> bool:
        """
        Delete a model configuration.

        Args:
            model_id: String representation of the model's ObjectId

        Returns:
            True if model was deleted, False if not found

        Raises:
            ValueError: If model_id is not a valid ObjectId string
        """
        return await super().delete(model_id)

    async def set_enabled(self, model_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        """
        Enable or disable a model configuration.

        Args:
            model_id: String representation of the model's ObjectId
            enabled: Whether the model should be enabled

        Returns:
            Updated model document with id field, or None if not found

        Raises:
            ValueError: If model_id is not a valid ObjectId string
        """
        return await self.update(model_id, {"enabled": enabled})

    async def get_by_capability(
        self,
        capability: str,
        enabled_only: bool = True,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve models that have a specific capability.

        Args:
            capability: The capability to filter by (e.g., 'vision', 'function_calling')
            enabled_only: If True, return only enabled models
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of model documents with the specified capability
        """
        filter_query: Dict[str, Any] = {"capabilities": capability}

        if enabled_only:
            filter_query["$or"] = [
                {"enabled": True},
                {"enabled": "true"}
            ]

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )

    async def count_by_enabled_status(self) -> Dict[str, int]:
        """
        Count models by enabled status.

        Returns:
            Dictionary with 'enabled' and 'disabled' counts
        """
        enabled_count = await self.count({
            "$or": [
                {"enabled": True},
                {"enabled": "true"}
            ]
        })

        disabled_count = await self.count({
            "$or": [
                {"enabled": False},
                {"enabled": "false"},
                {"enabled": {"$exists": False}}
            ]
        })

        return {
            "enabled": enabled_count,
            "disabled": disabled_count,
            "total": enabled_count + disabled_count
        }
