"""
Repositories Package

This package contains repository classes for MongoDB operations.
All repositories inherit from BaseRepository for common CRUD functionality.
"""

from .base_repository import BaseRepository
from .model_repository import ModelRepository
from .persona_repository import PersonaRepository
from .persona_type_repository import PersonaTypeRepository
from .persona_access_repository import PersonaAccessRepository
from .session_repository import SessionRepository
from .message_repository import MessageRepository
from .user_repository import UserRepository
from .user_profile_repository import UserProfileRepository
from .user_settings_repository import UserSettingsRepository
from .analytics_repository import AnalyticsRepository
from .codemorph_repository import CodeMorphRepository
from .workspace_project_repository import WorkspaceProjectRepository
from .workspace_execution_repository import WorkspaceExecutionRepository
from .workspace_agent_repository import WorkspaceAgentRepository
from .workspace_template_repository import WorkspaceTemplateRepository
from .workspace_checkpoint_repository import WorkspaceCheckpointRepository
from .workspace_usage_repository import WorkspaceUsageRepository
from .workspace_job_repository import WorkspaceJobRepository
from .workspace_project_type_repository import WorkspaceProjectTypeRepository

__all__ = [
    "BaseRepository",
    "ModelRepository",
    "PersonaRepository",
    "PersonaTypeRepository",
    "PersonaAccessRepository",
    "SessionRepository",
    "MessageRepository",
    "UserRepository",
    "UserProfileRepository",
    "UserSettingsRepository",
    "AnalyticsRepository",
    "CodeMorphRepository",
    "WorkspaceProjectRepository",
    "WorkspaceExecutionRepository",
    "WorkspaceAgentRepository",
    "WorkspaceTemplateRepository",
    "WorkspaceCheckpointRepository",
    "WorkspaceUsageRepository",
    "WorkspaceJobRepository",
    "WorkspaceProjectTypeRepository",
]
