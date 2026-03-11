"""
Workspace Project Repository for AI Team Workspace Feature

Repository class for managing workspace projects in MongoDB.
Provides methods for CRUD operations with filtering by user, status, and team agents.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class WorkspaceProjectRepository(BaseRepository):
    """
    Repository for workspace projects.

    Manages the 'workspace_projects' collection in MongoDB, providing methods for
    creating, retrieving, updating, and soft-deleting workspace projects.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for workspace projects
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the WorkspaceProjectRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "workspace_projects")

    async def create(
        self,
        user_id: str,
        name: str,
        description: str,
        tech_stack: List[str],
        complexity: str,
        team_agent_ids: List[str],
        template_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        project_type: Optional[str] = None,
        workshop_config: Optional[Dict[str, Any]] = None,
        model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new workspace project.

        Args:
            user_id: ID of the user creating the project
            name: Name of the project
            description: Description of the project
            tech_stack: List of technologies used in the project
            complexity: Project complexity level ('simple', 'moderate', 'complex')
            team_agent_ids: List of agent IDs assigned to the project
            template_id: Optional template ID used to create the project
            config: Optional project configuration
            project_type: Optional project type ('build', 'workshop', etc.)
            workshop_config: Optional workshop-specific configuration
            model_id: Optional Claude model ID for agent execution

        Returns:
            Created project document with id field
        """
        project_data = {
            "project_id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name,
            "title": name,
            "description": description,
            "tech_stack": tech_stack,
            "complexity": complexity,
            "team_agent_ids": team_agent_ids,
            "template_id": template_id,
            "config": config or {},
            "project_type": project_type or "build",
            "workshop_config": workshop_config or {},
            "model_id": model_id,
            "status": "draft",
            "execution_count": 0,
            "last_execution": None,
            "deleted_at": None
        }

        return await super().create(project_data)

    async def get_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a project by its ID.

        Args:
            project_id: The project's unique identifier (project_id field)

        Returns:
            Project document with id field, or None if not found
        """
        # First try by project_id field
        project = await self.get_one({"project_id": project_id, "deleted_at": None})
        if project:
            return project

        # Fall back to MongoDB _id
        try:
            result = await super().get_by_id(project_id)
            if result and result.get("deleted_at") is None:
                return result
            return None
        except ValueError:
            return None

    async def get_user_projects(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve projects for a specific user.

        Args:
            user_id: ID of the user
            status: Optional status filter ('active', 'archived', 'completed')
            limit: Maximum number of projects to return
            offset: Number of projects to skip (for pagination)

        Returns:
            List of project documents sorted by created_at descending
        """
        filter_query: Dict[str, Any] = {"user_id": user_id, "deleted_at": None}

        if status:
            filter_query["status"] = status

        return await self.get_all(
            filter=filter_query,
            skip=offset,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def update(
        self,
        project_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing project.

        Args:
            project_id: The project's unique identifier
            data: Fields to update (partial update supported)

        Returns:
            Updated project document with id field, or None if not found
        """
        # Find the project first
        project = await self.get_one({"project_id": project_id, "deleted_at": None})
        if project:
            return await super().update(project["id"], data)

        # Fall back to MongoDB _id
        try:
            return await super().update(project_id, data)
        except ValueError:
            return None

    async def soft_delete(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Soft delete a project by setting deleted_at timestamp.

        Args:
            project_id: The project's unique identifier

        Returns:
            Updated project document with id field, or None if not found
        """
        project = await self.get_one({"project_id": project_id, "deleted_at": None})
        if project:
            return await super().soft_delete(project["id"])

        # Fall back to MongoDB _id
        try:
            return await super().soft_delete(project_id)
        except ValueError:
            return None

    async def count_by_user(self, user_id: str) -> int:
        """
        Count projects for a specific user.

        Args:
            user_id: ID of the user

        Returns:
            Number of active projects for the user
        """
        return await self.count({"user_id": user_id, "deleted_at": None})

    async def get_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve projects by status.

        Args:
            status: The project status ('active', 'archived', 'completed')
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of project documents matching the status
        """
        return await self.get_all(
            filter={"status": status, "deleted_at": None},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def increment_execution_count(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Increment the execution count and update last_execution timestamp.

        Args:
            project_id: The project's unique identifier

        Returns:
            Updated project document, or None if not found
        """
        project = await self.get_one({"project_id": project_id, "deleted_at": None})
        if not project:
            try:
                project = await super().get_by_id(project_id)
            except ValueError:
                return None

        if not project:
            return None

        mongo_id = project["id"]
        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$inc": {"execution_count": 1},
                "$set": {
                    "last_execution": now,
                    "updated_at": now
                }
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def get_projects_by_agent(
        self,
        agent_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve projects that include a specific agent.

        Args:
            agent_id: ID of the agent
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of project documents using the agent
        """
        return await self.get_all(
            filter={"team_agent_ids": agent_id, "deleted_at": None},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def get_projects_by_template(
        self,
        template_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve projects created from a specific template.

        Args:
            template_id: ID of the template
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of project documents created from the template
        """
        return await self.get_all(
            filter={"template_id": template_id, "deleted_at": None},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )
