"""
Enums for AI Team Workspace feature
Defines status values, categories, and action types for workspace operations
"""

from enum import Enum


class ProjectStatus(str, Enum):
    """Status values for workspace projects"""
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    CHECKPOINT = "checkpoint"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(str, Enum):
    """Status values for individual agent execution"""
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ComplexityLevel(str, Enum):
    """Complexity levels for project estimation"""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    ENTERPRISE = "enterprise"


class AgentCategory(str, Enum):
    """Categories for agent classification"""
    # Engineering categories
    CODE_GENERATION = "code_generation"
    CODE_QUALITY = "code_quality"
    DEVOPS = "devops"
    MIGRATION = "migration"
    DOCUMENTATION = "documentation"
    DESIGN = "design"
    # Business categories
    C_SUITE = "c_suite"
    STARTUP_VENTURE = "startup_venture"
    MARKETING_SALES = "marketing_sales"
    PRODUCT_MANAGEMENT = "product_management"
    FINANCE_OPERATIONS = "finance_operations"
    HR_PEOPLE = "hr_people"
    LEGAL_COMPLIANCE = "legal_compliance"
    IT_SECURITY = "it_security"
    DATA_ANALYTICS = "data_analytics"
    SOCIAL_ENGAGEMENT = "social_engagement"
    SPECIALIZED = "specialized"
    ENGINEERING = "engineering"


class ProjectType(str, Enum):
    """Types of workspace projects"""
    BUILD = "build"
    WORKSHOP = "workshop"


class CheckpointAction(str, Enum):
    """Actions that can be taken at a checkpoint"""
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
