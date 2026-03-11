"""
Seed Data for AI Team Workspace Feature

Provides predefined agent blueprints and team templates for the AI Team Workspace.
These seed data entries establish the initial catalog of agents and templates
available to users.

Also provides workshop templates for multi-agent discussion sessions and a
``seed_library_agents()`` function that syncs the on-disk markdown agent
library into MongoDB.
"""

import logging
from typing import Dict, Any, List

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# AGENT BLUEPRINTS
# =============================================================================

AGENT_BLUEPRINTS: List[Dict[str, Any]] = [
    # 1. Architect Agent
    {
        "agent_id": "architect-v1",
        "name": "Architect Agent",
        "description": "Plans project structure, defines architecture, creates file organization. Designs system components, API contracts, database schemas, and deployment topology. The first agent in most workflows - establishes the blueprint other agents follow.",
        "category": "code_generation",
        "icon": "building",
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_display_name": "Claude 3.5 Sonnet",
        "system_prompt_template": "prompts/architect.md",
        "estimated_cost_per_run": 0.06,
        "estimated_tokens_input": 4000,
        "estimated_tokens_output": 3000,
        "max_turns": 30,
        "capabilities": ["project_planning", "architecture_design", "file_structure", "api_design", "database_schema"],
        "tools": ["file_write"],
        "config": {
            "requires": [],
            "compatible_with": ["backend-builder-v1", "frontend-builder-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.9
    },

    # 2. Backend Builder Agent
    {
        "agent_id": "backend-builder-v1",
        "name": "Backend Builder",
        "description": "Generates complete backend code including REST/GraphQL APIs, database models, services, middleware, authentication, and business logic. Supports FastAPI, Express, Django, and other frameworks.",
        "category": "code_generation",
        "icon": "server",
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_display_name": "Claude 3.5 Sonnet",
        "system_prompt_template": "prompts/backend_builder.md",
        "estimated_cost_per_run": 0.23,
        "estimated_tokens_input": 15000,
        "estimated_tokens_output": 12000,
        "max_turns": 50,
        "capabilities": ["api_development", "database_design", "backend_logic", "rest_apis", "graphql", "authentication", "middleware"],
        "tools": ["file_read", "file_write", "bash"],
        "config": {
            "requires": ["architect-v1"],
            "compatible_with": ["frontend-builder-v1", "qa-validator-v1", "devops-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.8
    },

    # 3. Frontend Builder Agent
    {
        "agent_id": "frontend-builder-v1",
        "name": "Frontend Builder",
        "description": "Creates complete frontend applications with React/Next.js/Vue components, pages, routing, state management, API integration, and responsive styling. Follows accessibility best practices and modern UI patterns.",
        "category": "code_generation",
        "icon": "layout",
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_display_name": "Claude 3.5 Sonnet",
        "system_prompt_template": "prompts/frontend_builder.md",
        "estimated_cost_per_run": 0.26,
        "estimated_tokens_input": 18000,
        "estimated_tokens_output": 14000,
        "max_turns": 50,
        "capabilities": ["ui_development", "component_design", "styling", "responsive_design", "accessibility", "state_management", "routing"],
        "tools": ["file_read", "file_write", "bash"],
        "config": {
            "requires": ["architect-v1"],
            "compatible_with": ["backend-builder-v1", "qa-validator-v1", "devops-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.7
    },

    # 4. QA Validator Agent
    {
        "agent_id": "qa-validator-v1",
        "name": "QA Validator",
        "description": "Reviews code for bugs, security issues, and anti-patterns. Writes comprehensive unit, integration, and end-to-end tests. Validates implementations against requirements and identifies edge cases.",
        "category": "code_quality",
        "icon": "check-circle",
        "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "model_display_name": "Claude 3 Haiku",
        "system_prompt_template": "prompts/qa_validator.md",
        "estimated_cost_per_run": 0.006,
        "estimated_tokens_input": 8000,
        "estimated_tokens_output": 2000,
        "max_turns": 20,
        "capabilities": ["code_review", "test_writing", "test_execution", "validation", "bug_detection", "edge_case_testing"],
        "tools": ["file_read", "bash"],
        "config": {
            "requires": ["backend-builder-v1", "frontend-builder-v1"],
            "compatible_with": ["devops-v1", "security-auditor-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.9
    },

    # 5. DevOps Agent
    {
        "agent_id": "devops-v1",
        "name": "DevOps Agent",
        "description": "Creates Dockerfiles, Docker Compose configs, CI/CD pipelines (GitHub Actions, GitLab CI), infrastructure as code (Terraform), and deployment scripts. Handles environment configs and monitoring setup.",
        "category": "devops",
        "icon": "cloud",
        "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "model_display_name": "Claude 3 Haiku",
        "system_prompt_template": "prompts/devops.md",
        "estimated_cost_per_run": 0.003,
        "estimated_tokens_input": 4000,
        "estimated_tokens_output": 1000,
        "max_turns": 15,
        "capabilities": ["ci_cd", "deployment", "infrastructure", "containerization", "monitoring", "docker", "kubernetes"],
        "tools": ["file_read", "file_write", "bash", "git_operations"],
        "config": {
            "requires": ["qa-validator-v1"],
            "compatible_with": ["pr-creator-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.6
    },

    # 6. Scanner Agent
    {
        "agent_id": "scanner-v1",
        "name": "Scanner Agent",
        "description": "Scans and analyzes existing codebases to map file structures, detect patterns, identify dependencies, and create comprehensive reports. Essential first step for migration and code review workflows.",
        "category": "code_quality",
        "icon": "search",
        "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "model_display_name": "Claude 3 Haiku",
        "system_prompt_template": "prompts/scanner.md",
        "estimated_cost_per_run": 0.003,
        "estimated_tokens_input": 5000,
        "estimated_tokens_output": 800,
        "max_turns": 10,
        "capabilities": ["code_scanning", "pattern_detection", "dependency_analysis", "codebase_mapping", "tech_stack_detection"],
        "tools": ["file_read", "bash"],
        "config": {
            "requires": [],
            "compatible_with": ["analyzer-v1", "security-auditor-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.7
    },

    # 7. Analyzer Agent
    {
        "agent_id": "analyzer-v1",
        "name": "Analyzer Agent",
        "description": "Performs deep analysis of code for migration planning, impact assessment, and transformation strategies. Evaluates compatibility, identifies breaking changes, and creates detailed migration plans.",
        "category": "migration",
        "icon": "bar-chart",
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_display_name": "Claude 3.5 Sonnet",
        "system_prompt_template": "prompts/analyzer.md",
        "estimated_cost_per_run": 0.17,
        "estimated_tokens_input": 12000,
        "estimated_tokens_output": 8000,
        "max_turns": 25,
        "capabilities": ["code_analysis", "migration_planning", "impact_assessment", "compatibility_check", "breaking_change_detection"],
        "tools": ["file_read", "web_search"],
        "config": {
            "requires": ["scanner-v1"],
            "compatible_with": ["transformer-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.8
    },

    # 8. Transformer Agent
    {
        "agent_id": "transformer-v1",
        "name": "Transformer Agent",
        "description": "Executes large-scale code transformations, framework migrations, syntax upgrades, and refactoring operations. Handles file-by-file transformation with context preservation across the codebase.",
        "category": "migration",
        "icon": "shuffle",
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_display_name": "Claude 3.5 Sonnet",
        "system_prompt_template": "prompts/transformer.md",
        "estimated_cost_per_run": 0.38,
        "estimated_tokens_input": 25000,
        "estimated_tokens_output": 20000,
        "max_turns": 60,
        "capabilities": ["code_transformation", "refactoring", "syntax_migration", "framework_upgrade", "batch_processing"],
        "tools": ["file_read", "file_write", "bash"],
        "config": {
            "requires": ["analyzer-v1"],
            "compatible_with": ["qa-validator-v1", "pr-creator-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.6
    },

    # 9. PR Creator Agent
    {
        "agent_id": "pr-creator-v1",
        "name": "PR Creator",
        "description": "Creates well-structured pull requests with detailed descriptions, proper labels, changelog entries, and review assignments. Summarizes all changes made by previous agents into a reviewable PR.",
        "category": "devops",
        "icon": "git-pull-request",
        "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "model_display_name": "Claude 3 Haiku",
        "system_prompt_template": "prompts/pr_creator.md",
        "estimated_cost_per_run": 0.005,
        "estimated_tokens_input": 6000,
        "estimated_tokens_output": 2000,
        "max_turns": 10,
        "capabilities": ["pr_creation", "documentation", "changelog_generation", "review_assignment", "git_operations"],
        "tools": ["file_read", "git_operations"],
        "config": {
            "requires": ["qa-validator-v1"],
            "compatible_with": []
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.5
    },

    # 10. Security Auditor Agent
    {
        "agent_id": "security-auditor-v1",
        "name": "Security Auditor",
        "description": "Performs comprehensive security audits covering OWASP Top 10, authentication review, authorization checks, secrets detection, dependency vulnerabilities, and compliance validation. Produces prioritized remediation reports.",
        "category": "code_quality",
        "icon": "shield",
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "model_display_name": "Claude 3.5 Sonnet",
        "system_prompt_template": "prompts/security_auditor.md",
        "estimated_cost_per_run": 0.11,
        "estimated_tokens_input": 8000,
        "estimated_tokens_output": 5000,
        "max_turns": 20,
        "capabilities": ["security_scanning", "vulnerability_detection", "compliance_check", "best_practices", "owasp_top_10", "secrets_detection"],
        "tools": ["file_read", "bash", "web_search"],
        "config": {
            "requires": ["scanner-v1"],
            "compatible_with": ["qa-validator-v1", "pr-creator-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.9
    },

    # 11. Documentation Agent
    {
        "agent_id": "documentation-v1",
        "name": "Documentation Agent",
        "description": "Generates comprehensive project documentation including READMEs, API references, architecture guides, development setup instructions, deployment procedures, and contributing guidelines.",
        "category": "documentation",
        "icon": "file-text",
        "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "model_display_name": "Claude 3 Haiku",
        "system_prompt_template": "prompts/documentation.md",
        "estimated_cost_per_run": 0.006,
        "estimated_tokens_input": 7000,
        "estimated_tokens_output": 3000,
        "max_turns": 15,
        "capabilities": ["readme_generation", "api_documentation", "user_guides", "code_comments", "architecture_docs", "deployment_docs"],
        "tools": ["file_read", "file_write"],
        "config": {
            "requires": [],
            "compatible_with": ["backend-builder-v1", "frontend-builder-v1", "pr-creator-v1"]
        },
        "is_active": True,
        "is_system": True,
        "created_by": "system",
        "rating": 4.5
    }
]


# =============================================================================
# TEAM TEMPLATES
# =============================================================================

TEAM_TEMPLATES: List[Dict[str, Any]] = [
    # 1. Migration Squad
    {
        "template_id": "migration-squad",
        "name": "Migration Squad",
        "description": "Complete code migration pipeline with scanning, analysis, transformation, validation, and PR creation",
        "icon": "refresh-cw",
        "category": "migration",
        "agent_ids": [
            "scanner-v1",
            "analyzer-v1",
            "transformer-v1",
            "qa-validator-v1",
            "pr-creator-v1"
        ],
        "recommended_complexity": "complex",
        "estimated_cost_per_run": 0.58,
        "estimated_time_minutes": 20,
        "is_system": True,
        "tags": ["migration", "upgrade", "refactoring"]
    },

    # 2. MVP Builder
    {
        "template_id": "mvp-builder",
        "name": "MVP Builder",
        "description": "Rapid MVP development team with architecture, frontend, backend, QA, and deployment",
        "icon": "rocket",
        "category": "fullstack",
        "agent_ids": [
            "architect-v1",
            "backend-builder-v1",
            "frontend-builder-v1",
            "qa-validator-v1",
            "devops-v1"
        ],
        "recommended_complexity": "medium",
        "estimated_cost_per_run": 0.57,
        "estimated_time_minutes": 25,
        "is_system": True,
        "tags": ["mvp", "startup", "rapid-development"]
    },

    # 3. Code Reviewer
    {
        "template_id": "code-reviewer",
        "name": "Code Reviewer",
        "description": "Comprehensive code review team for quality assurance and security validation",
        "icon": "eye",
        "category": "code_quality",
        "agent_ids": [
            "scanner-v1",
            "analyzer-v1",
            "security-auditor-v1"
        ],
        "recommended_complexity": "simple",
        "estimated_cost_per_run": 0.29,
        "estimated_time_minutes": 10,
        "is_system": True,
        "tags": ["review", "security", "quality"]
    },

    # 4. Full-Stack App
    {
        "template_id": "fullstack-app",
        "name": "Full-Stack App",
        "description": "Complete full-stack application development with documentation and deployment",
        "icon": "layers",
        "category": "fullstack",
        "agent_ids": [
            "architect-v1",
            "backend-builder-v1",
            "frontend-builder-v1",
            "qa-validator-v1",
            "devops-v1",
            "documentation-v1"
        ],
        "recommended_complexity": "complex",
        "estimated_cost_per_run": 0.58,
        "estimated_time_minutes": 35,
        "is_system": True,
        "tags": ["fullstack", "complete", "production"]
    },

    # 5. API Designer
    {
        "template_id": "api-designer",
        "name": "API Designer",
        "description": "Backend API development team with architecture, implementation, testing, and documentation",
        "icon": "code",
        "category": "api",
        "agent_ids": [
            "architect-v1",
            "backend-builder-v1",
            "qa-validator-v1",
            "documentation-v1"
        ],
        "recommended_complexity": "medium",
        "estimated_cost_per_run": 0.30,
        "estimated_time_minutes": 18,
        "is_system": True,
        "tags": ["api", "backend", "rest", "graphql"]
    }
]


# =============================================================================
# WORKSHOP TEMPLATES
# =============================================================================

WORKSHOP_TEMPLATES: List[Dict[str, Any]] = [
    # 1. C-Suite Strategy Session
    {
        "template_id": "c-suite-strategy",
        "name": "C-Suite Strategy Session",
        "description": "Full executive team strategic planning workshop",
        "project_type": "workshop",
        "team_agent_ids": ["ceo", "cfo", "cto", "cmo", "coo", "cpo", "cso"],
        "workshop_config": {
            "topic": "Strategic planning session",
            "workshop_type": "strategy",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["c-suite", "strategy", "executive"],
        "estimated_cost_per_run": 0.45,
        "icon": "crown"
    },

    # 2. Startup Pitch Review
    {
        "template_id": "startup-pitch-review",
        "name": "Startup Pitch Review",
        "description": "Expert panel review of startup pitch and business model",
        "project_type": "workshop",
        "team_agent_ids": ["startup-founder", "fundraising-advisor", "growth-hacker", "business-model-designer"],
        "workshop_config": {
            "topic": "Startup pitch and business model review",
            "workshop_type": "review",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["startup", "pitch", "fundraising"],
        "estimated_cost_per_run": 0.30,
        "icon": "rocket"
    },

    # 3. Marketing Campaign Planning
    {
        "template_id": "marketing-campaign-planning",
        "name": "Marketing Campaign Planning",
        "description": "Cross-functional marketing team brainstorm for campaign strategy",
        "project_type": "workshop",
        "team_agent_ids": ["content-strategist", "seo-specialist", "social-media-manager", "customer-success-manager"],
        "workshop_config": {
            "topic": "Marketing campaign strategy brainstorm",
            "workshop_type": "brainstorm",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["marketing", "campaign", "content"],
        "estimated_cost_per_run": 0.30,
        "icon": "trending-up"
    },

    # 4. Product Roadmap Workshop
    {
        "template_id": "product-roadmap-workshop",
        "name": "Product Roadmap Workshop",
        "description": "Product and agile team workshop for roadmap and sprint planning",
        "project_type": "workshop",
        "team_agent_ids": ["product-manager", "scrum-master", "agile-coach", "ux-designer"],
        "workshop_config": {
            "topic": "Product roadmap and sprint planning",
            "workshop_type": "strategy",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["product", "roadmap", "agile"],
        "estimated_cost_per_run": 0.30,
        "icon": "clipboard"
    },

    # 5. Financial Analysis Session
    {
        "template_id": "financial-analysis-session",
        "name": "Financial Analysis Session",
        "description": "Finance team deep-dive analysis on financial performance and pricing",
        "project_type": "workshop",
        "team_agent_ids": ["financial-analyst", "pricing-strategist", "cfo"],
        "workshop_config": {
            "topic": "Financial performance and pricing analysis",
            "workshop_type": "analysis",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["finance", "analysis", "pricing"],
        "estimated_cost_per_run": 0.25,
        "icon": "dollar-sign"
    },

    # 6. Talent & Culture Review
    {
        "template_id": "talent-culture-review",
        "name": "Talent & Culture Review",
        "description": "HR leadership review of talent acquisition, culture, and organizational development",
        "project_type": "workshop",
        "team_agent_ids": ["talent-acquisition", "org-development", "chro"],
        "workshop_config": {
            "topic": "Talent acquisition and organizational culture review",
            "workshop_type": "review",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["hr", "talent", "culture"],
        "estimated_cost_per_run": 0.25,
        "icon": "users"
    },

    # 7. Legal & Compliance Audit
    {
        "template_id": "legal-compliance-audit",
        "name": "Legal & Compliance Audit",
        "description": "Legal and security team audit of compliance posture and risk exposure",
        "project_type": "workshop",
        "team_agent_ids": ["general-counsel", "compliance-officer", "ciso"],
        "workshop_config": {
            "topic": "Compliance posture and legal risk audit",
            "workshop_type": "audit",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["legal", "compliance", "audit"],
        "estimated_cost_per_run": 0.25,
        "icon": "shield"
    },

    # 8. Data Strategy Workshop
    {
        "template_id": "data-strategy-workshop",
        "name": "Data Strategy Workshop",
        "description": "Data and engineering leadership workshop for data strategy and architecture",
        "project_type": "workshop",
        "team_agent_ids": ["data-scientist", "bi-analyst", "cto", "solutions-architect"],
        "workshop_config": {
            "topic": "Data strategy and architecture planning",
            "workshop_type": "strategy",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["data", "strategy", "analytics"],
        "estimated_cost_per_run": 0.30,
        "icon": "bar-chart-2"
    },

    # 9. Technology Partner Evaluation
    {
        "template_id": "technology-partner-evaluation",
        "name": "Technology Partner Evaluation",
        "description": "Cross-functional assessment of technology implementation partners covering technical capabilities, security posture, cloud approach, and project governance",
        "project_type": "workshop",
        "team_agent_ids": ["cto", "ciso", "cloud-architect", "solutions-architect", "program-manager"],
        "workshop_config": {
            "topic": "Technology implementation partner evaluation and selection",
            "workshop_type": "review",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["vendor", "partner", "evaluation", "implementation", "assessment"],
        "estimated_cost_per_run": 0.40,
        "icon": "search"
    },

    # 10. Custom Workshop
    {
        "template_id": "custom-workshop",
        "name": "Custom Workshop",
        "description": "Build your own workshop team by selecting agents from the catalog below",
        "project_type": "workshop",
        "team_agent_ids": [],
        "workshop_config": {
            "topic": "",
            "workshop_type": "strategy",
            "num_rounds": 2,
            "output_format": "report",
            "export_formats": ["pdf"],
            "facilitation_style": "structured"
        },
        "tags": ["custom", "flexible", "build-your-own"],
        "estimated_cost_per_run": 0.0,
        "icon": "settings"
    },
]


# =============================================================================
# WORKSPACE PROJECT TYPES
# =============================================================================

WORKSPACE_PROJECT_TYPES: List[Dict[str, Any]] = [
    # --- Project Types (category: "project_type") ---
    {
        "key": "build",
        "label": "Build Project",
        "description": "Generate code with an AI engineering team. Produces source code files, configs, and documentation.",
        "icon": "Code",
        "category": "project_type",
        "color": "#3B82F6",
        "sort_order": 1,
        "enabled": True,
    },
    {
        "key": "workshop",
        "label": "Workshop Session",
        "description": "Run a strategy or brainstorming session with AI experts. Produces reports, slide decks, and executive briefs.",
        "icon": "Users",
        "category": "project_type",
        "color": "#8B5CF6",
        "sort_order": 2,
        "enabled": True,
    },

    # --- Workshop Types (category: "workshop_type") ---
    {
        "key": "strategy",
        "label": "Strategy Session",
        "description": "Executive strategic planning",
        "icon": "Target",
        "category": "workshop_type",
        "color": "#EF4444",
        "sort_order": 1,
        "enabled": True,
    },
    {
        "key": "brainstorm",
        "label": "Brainstorm",
        "description": "Creative ideation session",
        "icon": "Lightbulb",
        "category": "workshop_type",
        "color": "#F59E0B",
        "sort_order": 2,
        "enabled": True,
    },
    {
        "key": "analysis",
        "label": "Analysis",
        "description": "Deep-dive analysis",
        "icon": "Search",
        "category": "workshop_type",
        "color": "#10B981",
        "sort_order": 3,
        "enabled": True,
    },
    {
        "key": "review",
        "label": "Review",
        "description": "Structured review session",
        "icon": "CheckCircle",
        "category": "workshop_type",
        "color": "#6366F1",
        "sort_order": 4,
        "enabled": True,
    },
    {
        "key": "audit",
        "label": "Audit",
        "description": "Comprehensive audit",
        "icon": "ClipboardCheck",
        "category": "workshop_type",
        "color": "#EC4899",
        "sort_order": 5,
        "enabled": True,
    },

    # --- Output Formats (category: "output_format") ---
    {
        "key": "report",
        "label": "Report",
        "description": "Comprehensive document",
        "icon": "FileText",
        "category": "output_format",
        "color": "#3B82F6",
        "sort_order": 1,
        "enabled": True,
    },
    {
        "key": "slides",
        "label": "Slide Deck",
        "description": "Presentation slides",
        "icon": "Presentation",
        "category": "output_format",
        "color": "#8B5CF6",
        "sort_order": 2,
        "enabled": True,
    },
    {
        "key": "canvas",
        "label": "Business Canvas",
        "description": "Visual business canvas",
        "icon": "Grid",
        "category": "output_format",
        "color": "#10B981",
        "sort_order": 3,
        "enabled": True,
    },
    {
        "key": "brief",
        "label": "Executive Brief",
        "description": "Concise brief",
        "icon": "File",
        "category": "output_format",
        "color": "#F59E0B",
        "sort_order": 4,
        "enabled": True,
    },
]


# =============================================================================
# SAMPLE PROJECTS
# =============================================================================

SAMPLE_PROJECTS: List[Dict[str, Any]] = [
    # 1. Completed project - E-Commerce API
    {
        "project_id": "proj-demo-ecommerce-api",
        "user_id": "dev-user-123",
        "name": "E-Commerce REST API",
        "title": "E-Commerce REST API",
        "description": "Build a complete REST API for an e-commerce platform with product catalog, user authentication, shopping cart, order management, and Stripe payment integration. Use FastAPI + PostgreSQL with Docker deployment.",
        "tech_stack": ["fastapi", "postgresql", "docker", "stripe", "redis"],
        "complexity": "complex",
        "team_agent_ids": [
            "architect-v1",
            "backend-builder-v1",
            "qa-validator-v1",
            "security-auditor-v1",
            "devops-v1",
            "documentation-v1"
        ],
        "selected_agents": [
            "architect-v1",
            "backend-builder-v1",
            "qa-validator-v1",
            "security-auditor-v1",
            "devops-v1",
            "documentation-v1"
        ],
        "template_id": "fullstack-app",
        "config": {
            "enable_checkpoints": True,
            "auto_create_pr": False,
            "generate_docs": True,
            "generate_tests": True,
            "output_format": "zip"
        },
        "status": "completed",
        "progress_percent": 100,
        "estimated_cost_usd": 0.58,
        "actual_cost_usd": 0.52,
        "estimated_tokens": 52000,
        "actual_tokens": 48500
    },

    # 2. Running project - React Dashboard
    {
        "project_id": "proj-demo-react-dashboard",
        "user_id": "dev-user-123",
        "name": "Analytics Dashboard",
        "title": "Analytics Dashboard",
        "description": "Create a real-time analytics dashboard with React, Next.js, and Tailwind CSS. Features include interactive charts, data tables with filtering/sorting, user management panel, and dark mode support.",
        "tech_stack": ["nextjs", "react", "tailwindcss", "typescript", "recharts"],
        "complexity": "medium",
        "team_agent_ids": [
            "architect-v1",
            "frontend-builder-v1",
            "qa-validator-v1",
            "documentation-v1"
        ],
        "selected_agents": [
            "architect-v1",
            "frontend-builder-v1",
            "qa-validator-v1",
            "documentation-v1"
        ],
        "template_id": None,
        "config": {
            "enable_checkpoints": True,
            "auto_create_pr": False,
            "generate_docs": True,
            "generate_tests": True,
            "output_format": "zip"
        },
        "status": "running",
        "progress_percent": 45,
        "estimated_cost_usd": 0.34,
        "actual_cost_usd": 0.15,
        "estimated_tokens": 32000,
        "actual_tokens": 14200
    },

    # 3. Draft project - Microservices Migration
    {
        "project_id": "proj-demo-microservices",
        "user_id": "dev-user-123",
        "name": "Monolith to Microservices",
        "title": "Monolith to Microservices",
        "description": "Migrate a Django monolith application to microservices architecture using FastAPI. Break down into user service, product service, order service, and notification service with event-driven communication via RabbitMQ.",
        "tech_stack": ["fastapi", "rabbitmq", "docker", "kubernetes", "postgresql"],
        "complexity": "enterprise",
        "team_agent_ids": [
            "scanner-v1",
            "analyzer-v1",
            "architect-v1",
            "transformer-v1",
            "backend-builder-v1",
            "qa-validator-v1",
            "devops-v1",
            "pr-creator-v1"
        ],
        "selected_agents": [
            "scanner-v1",
            "analyzer-v1",
            "architect-v1",
            "transformer-v1",
            "backend-builder-v1",
            "qa-validator-v1",
            "devops-v1",
            "pr-creator-v1"
        ],
        "template_id": "migration-squad",
        "config": {
            "enable_checkpoints": True,
            "auto_create_pr": True,
            "github_repo_url": "https://github.com/acme/legacy-monolith",
            "generate_docs": True,
            "generate_tests": True,
            "output_format": "github_pr"
        },
        "status": "draft",
        "progress_percent": 0,
        "estimated_cost_usd": 1.24,
        "actual_cost_usd": 0.0,
        "estimated_tokens": 95000,
        "actual_tokens": 0
    },

    # 4. Completed project - Code Review
    {
        "project_id": "proj-demo-security-review",
        "user_id": "dev-user-123",
        "name": "Security Audit - Payment Module",
        "title": "Security Audit - Payment Module",
        "description": "Comprehensive security audit of the payment processing module. Check for OWASP Top 10 vulnerabilities, review authentication flows, validate encryption implementations, and scan dependencies for known CVEs.",
        "tech_stack": ["nodejs", "express", "stripe", "jwt"],
        "complexity": "medium",
        "team_agent_ids": [
            "scanner-v1",
            "analyzer-v1",
            "security-auditor-v1"
        ],
        "selected_agents": [
            "scanner-v1",
            "analyzer-v1",
            "security-auditor-v1"
        ],
        "template_id": "code-reviewer",
        "config": {
            "enable_checkpoints": False,
            "auto_create_pr": False,
            "generate_docs": True,
            "generate_tests": False,
            "output_format": "markdown"
        },
        "status": "completed",
        "progress_percent": 100,
        "estimated_cost_usd": 0.29,
        "actual_cost_usd": 0.27,
        "estimated_tokens": 26000,
        "actual_tokens": 24100
    },

    # 5. Paused project - Full Stack SaaS
    {
        "project_id": "proj-demo-saas-mvp",
        "user_id": "dev-user-123",
        "name": "SaaS MVP - Project Tracker",
        "title": "SaaS MVP - Project Tracker",
        "description": "Build a complete SaaS MVP for project management with team collaboration, Kanban boards, time tracking, and reporting. Includes user authentication, billing integration, and admin dashboard.",
        "tech_stack": ["nextjs", "fastapi", "postgresql", "stripe", "tailwindcss"],
        "complexity": "complex",
        "team_agent_ids": [
            "architect-v1",
            "backend-builder-v1",
            "frontend-builder-v1",
            "qa-validator-v1",
            "devops-v1"
        ],
        "selected_agents": [
            "architect-v1",
            "backend-builder-v1",
            "frontend-builder-v1",
            "qa-validator-v1",
            "devops-v1"
        ],
        "template_id": "mvp-builder",
        "config": {
            "enable_checkpoints": True,
            "auto_create_pr": False,
            "generate_docs": True,
            "generate_tests": True,
            "output_format": "zip"
        },
        "status": "paused",
        "progress_percent": 62,
        "estimated_cost_usd": 0.57,
        "actual_cost_usd": 0.35,
        "estimated_tokens": 49000,
        "actual_tokens": 30400
    }
]


# =============================================================================
# SEED FUNCTIONS
# =============================================================================

async def seed_agents(agent_repo) -> Dict[str, Any]:
    """
    Seed agent blueprints into the database.

    Args:
        agent_repo: WorkspaceAgentRepository instance

    Returns:
        Dictionary with seeding results
    """
    try:
        logger.info("Starting agent seeding...")

        # Clear existing agents using delete_many from base repository
        deleted_count = await agent_repo.delete_many({})
        logger.info(f"Cleared {deleted_count} existing agents")

        # Insert all agent blueprints using base repository's create
        inserted_count = 0
        failed_agents = []
        from datetime import datetime

        for agent in AGENT_BLUEPRINTS:
            try:
                # Add timestamps and use collection directly
                agent_data = agent.copy()
                now = datetime.utcnow().isoformat()
                agent_data['created_at'] = now
                agent_data['updated_at'] = now
                agent_data['usage_count'] = 0
                agent_data['last_used'] = None

                result = await agent_repo.collection.insert_one(agent_data)
                if result.inserted_id:
                    inserted_count += 1
                    logger.debug(f"Inserted agent: {agent['name']} ({agent['agent_id']})")
                else:
                    failed_agents.append(agent['agent_id'])
                    logger.warning(f"Failed to insert agent: {agent['agent_id']}")
            except Exception as e:
                failed_agents.append(agent['agent_id'])
                logger.error(f"Error inserting agent {agent['agent_id']}: {e}")

        logger.info(f"Agent seeding complete: {inserted_count}/{len(AGENT_BLUEPRINTS)} agents inserted")

        return {
            "success": len(failed_agents) == 0,
            "total": len(AGENT_BLUEPRINTS),
            "inserted": inserted_count,
            "failed": failed_agents
        }

    except Exception as e:
        logger.error(f"Error during agent seeding: {e}")
        return {
            "success": False,
            "error": str(e),
            "total": len(AGENT_BLUEPRINTS),
            "inserted": 0,
            "failed": []
        }


async def seed_templates(template_repo) -> Dict[str, Any]:
    """
    Seed team templates into the database.

    Args:
        template_repo: WorkspaceTemplateRepository instance

    Returns:
        Dictionary with seeding results
    """
    try:
        logger.info("Starting template seeding...")

        # Clear existing system templates (preserve user templates)
        deleted_count = await template_repo.delete_many({"is_system": True})
        logger.info(f"Cleared {deleted_count} existing system templates")

        # Insert all team templates using collection directly
        inserted_count = 0
        failed_templates = []
        from datetime import datetime

        for template in TEAM_TEMPLATES:
            try:
                # Add timestamps and use collection directly
                template_data = template.copy()
                now = datetime.utcnow().isoformat()
                template_data['created_at'] = now
                template_data['updated_at'] = now
                template_data['usage_count'] = 0
                template_data['last_used'] = None
                template_data['user_id'] = None  # System templates have no user
                template_data['is_active'] = True
                # Rename agent_ids to team_agent_ids for consistency with repository
                if 'agent_ids' in template_data:
                    template_data['team_agent_ids'] = template_data.pop('agent_ids')

                result = await template_repo.collection.insert_one(template_data)
                if result.inserted_id:
                    inserted_count += 1
                    logger.debug(f"Inserted template: {template['name']} ({template['template_id']})")
                else:
                    failed_templates.append(template['template_id'])
                    logger.warning(f"Failed to insert template: {template['template_id']}")
            except Exception as e:
                failed_templates.append(template['template_id'])
                logger.error(f"Error inserting template {template['template_id']}: {e}")

        logger.info(f"Template seeding complete: {inserted_count}/{len(TEAM_TEMPLATES)} templates inserted")

        return {
            "success": len(failed_templates) == 0,
            "total": len(TEAM_TEMPLATES),
            "inserted": inserted_count,
            "failed": failed_templates
        }

    except Exception as e:
        logger.error(f"Error during template seeding: {e}")
        return {
            "success": False,
            "error": str(e),
            "total": len(TEAM_TEMPLATES),
            "inserted": 0,
            "failed": []
        }


async def seed_projects(project_repo) -> Dict[str, Any]:
    """
    Seed sample workspace projects into the database.

    Args:
        project_repo: WorkspaceProjectRepository instance

    Returns:
        Dictionary with seeding results
    """
    try:
        logger.info("Starting project seeding...")

        # Clear existing demo projects only (preserve real user projects)
        deleted_count = await project_repo.delete_many({"project_id": {"$regex": "^proj-demo-"}})
        logger.info(f"Cleared {deleted_count} existing demo projects")

        # Insert sample projects
        inserted_count = 0
        failed_projects = []
        from datetime import datetime, timedelta

        now = datetime.utcnow()

        for i, project in enumerate(SAMPLE_PROJECTS):
            try:
                project_data = project.copy()
                # Stagger timestamps so projects have different dates
                created = now - timedelta(days=len(SAMPLE_PROJECTS) - i, hours=i * 3)
                updated = created + timedelta(hours=i * 2 + 1)

                project_data['created_at'] = created.isoformat() + "Z"
                project_data['updated_at'] = updated.isoformat() + "Z"

                if project_data['status'] in ('running', 'paused', 'completed'):
                    project_data['started_at'] = (created + timedelta(minutes=2)).isoformat() + "Z"

                if project_data['status'] == 'completed':
                    project_data['completed_at'] = updated.isoformat() + "Z"

                result = await project_repo.collection.insert_one(project_data)
                if result.inserted_id:
                    inserted_count += 1
                    logger.debug(f"Inserted project: {project['name']} ({project['project_id']})")
                else:
                    failed_projects.append(project['project_id'])
            except Exception as e:
                failed_projects.append(project['project_id'])
                logger.error(f"Error inserting project {project['project_id']}: {e}")

        logger.info(f"Project seeding complete: {inserted_count}/{len(SAMPLE_PROJECTS)} projects inserted")

        return {
            "success": len(failed_projects) == 0,
            "total": len(SAMPLE_PROJECTS),
            "inserted": inserted_count,
            "failed": failed_projects
        }

    except Exception as e:
        logger.error(f"Error during project seeding: {e}")
        return {
            "success": False,
            "error": str(e),
            "total": len(SAMPLE_PROJECTS),
            "inserted": 0,
            "failed": []
        }


async def seed_library_agents(agent_repo) -> Dict[str, Any]:
    """
    Sync the on-disk markdown agent library into MongoDB.

    Reads .md files from ``projects/agent-library/agents/`` (organised in
    category sub-folders such as ``c-suite/``, ``engineering/``, etc.) and
    upserts them as system agents via ``AgentLibraryService.sync_library_to_db``.

    Args:
        agent_repo: WorkspaceAgentRepository instance.

    Returns:
        Dictionary with sync results (created, updated, skipped, errors).
    """
    try:
        from services.workspace.agent_library_service import AgentLibraryService

        logger.info("Starting agent library sync from .md files...")
        agent_library_service = AgentLibraryService()
        result = await agent_library_service.sync_library_to_db(agent_repo)

        created = result.get("created", 0)
        updated = result.get("updated", 0)
        skipped = result.get("skipped", 0)
        errors = result.get("errors", [])

        logger.info(
            f"Agent library sync complete: created={created}, "
            f"updated={updated}, skipped={skipped}, errors={len(errors)}"
        )

        return {
            "success": result.get("success", False),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error during agent library sync: {e}")
        return {
            "success": False,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [str(e)],
        }


async def seed_workshop_templates(template_repo) -> Dict[str, Any]:
    """
    Seed workshop templates into the database.

    Workshop templates use library agents (by slug) and include a
    ``workshop_config`` with topic, type, rounds, output format, etc.

    Args:
        template_repo: WorkspaceTemplateRepository instance.

    Returns:
        Dictionary with seeding results.
    """
    try:
        logger.info("Starting workshop template seeding...")

        # Clear existing system workshop templates only
        deleted_count = await template_repo.delete_many({
            "is_system": True,
            "project_type": "workshop",
        })
        logger.info(f"Cleared {deleted_count} existing system workshop templates")

        inserted_count = 0
        failed_templates = []
        from datetime import datetime

        for template in WORKSHOP_TEMPLATES:
            try:
                template_data = template.copy()
                now = datetime.utcnow().isoformat()
                template_data["created_at"] = now
                template_data["updated_at"] = now
                template_data["usage_count"] = 0
                template_data["last_used"] = None
                template_data["user_id"] = None  # System templates have no user
                template_data["is_active"] = True
                template_data["is_system"] = True
                # Map estimated_cost_per_run → estimated_cost_usd for API compatibility
                if "estimated_cost_per_run" in template_data:
                    template_data["estimated_cost_usd"] = template_data.pop("estimated_cost_per_run")

                result = await template_repo.collection.insert_one(template_data)
                if result.inserted_id:
                    inserted_count += 1
                    logger.debug(
                        f"Inserted workshop template: {template['name']} "
                        f"({template['template_id']})"
                    )
                else:
                    failed_templates.append(template["template_id"])
                    logger.warning(
                        f"Failed to insert workshop template: {template['template_id']}"
                    )
            except Exception as e:
                failed_templates.append(template["template_id"])
                logger.error(
                    f"Error inserting workshop template {template['template_id']}: {e}"
                )

        logger.info(
            f"Workshop template seeding complete: "
            f"{inserted_count}/{len(WORKSHOP_TEMPLATES)} templates inserted"
        )

        return {
            "success": len(failed_templates) == 0,
            "total": len(WORKSHOP_TEMPLATES),
            "inserted": inserted_count,
            "failed": failed_templates,
        }

    except Exception as e:
        logger.error(f"Error during workshop template seeding: {e}")
        return {
            "success": False,
            "error": str(e),
            "total": len(WORKSHOP_TEMPLATES),
            "inserted": 0,
            "failed": [],
        }


async def seed_workspace_project_types(db) -> Dict[str, Any]:
    """
    Seed workspace project types into the database.

    Inserts predefined project types, workshop types, and output formats
    into the 'workspace_project_types' collection. Only seeds if the
    collection is empty to avoid duplicates.

    Args:
        db: AsyncIOMotorDatabase instance

    Returns:
        Dictionary with seeding results
    """
    try:
        from repositories import WorkspaceProjectTypeRepository

        logger.info("Starting workspace project types seeding...")

        repo = WorkspaceProjectTypeRepository(db)

        # Check if collection already has data
        existing_count = await repo.count()
        if existing_count > 0:
            logger.info(
                f"Workspace project types collection already has {existing_count} records, skipping seed."
            )
            return {
                "success": True,
                "total": len(WORKSPACE_PROJECT_TYPES),
                "inserted": 0,
                "skipped": existing_count,
                "message": "Collection already seeded",
            }

        # Insert all workspace project types
        inserted_count = 0
        failed_types = []
        from datetime import datetime

        for type_def in WORKSPACE_PROJECT_TYPES:
            try:
                type_data = type_def.copy()
                now = datetime.utcnow().isoformat()
                type_data["status"] = "active"
                type_data["created_at"] = now
                type_data["updated_at"] = now

                result = await repo.collection.insert_one(type_data)
                if result.inserted_id:
                    inserted_count += 1
                    logger.debug(
                        f"Inserted workspace project type: {type_def['label']} ({type_def['key']})"
                    )
                else:
                    failed_types.append(type_def["key"])
                    logger.warning(
                        f"Failed to insert workspace project type: {type_def['key']}"
                    )
            except Exception as e:
                failed_types.append(type_def["key"])
                logger.error(
                    f"Error inserting workspace project type {type_def['key']}: {e}"
                )

        logger.info(
            f"Workspace project types seeding complete: "
            f"{inserted_count}/{len(WORKSPACE_PROJECT_TYPES)} types inserted"
        )

        return {
            "success": len(failed_types) == 0,
            "total": len(WORKSPACE_PROJECT_TYPES),
            "inserted": inserted_count,
            "failed": failed_types,
        }

    except Exception as e:
        logger.error(f"Error during workspace project types seeding: {e}")
        return {
            "success": False,
            "error": str(e),
            "total": len(WORKSPACE_PROJECT_TYPES),
            "inserted": 0,
            "failed": [],
        }


async def seed_all(db) -> Dict[str, Any]:
    """
    Seed all workspace data (agents, templates, workshop templates,
    library agents, and sample projects).

    Args:
        db: AsyncIOMotorDatabase instance

    Returns:
        Dictionary with complete seeding results
    """
    from repositories import WorkspaceAgentRepository, WorkspaceTemplateRepository, WorkspaceProjectRepository

    try:
        logger.info("=" * 60)
        logger.info("Starting AI Team Workspace data seeding...")
        logger.info("=" * 60)

        # Create repository instances directly
        agent_repo = WorkspaceAgentRepository(db)
        template_repo = WorkspaceTemplateRepository(db)
        project_repo = WorkspaceProjectRepository(db)

        # Seed agents
        agent_result = await seed_agents(agent_repo)

        # Seed library agents from .md files
        library_result = await seed_library_agents(agent_repo)

        # Seed templates
        template_result = await seed_templates(template_repo)

        # Seed workshop templates
        workshop_result = await seed_workshop_templates(template_repo)

        # Seed sample projects
        project_result = await seed_projects(project_repo)

        # Seed workspace project types
        project_types_result = await seed_workspace_project_types(db)

        # Compile overall result
        overall_success = (
            agent_result.get("success", False)
            and template_result.get("success", False)
            and workshop_result.get("success", False)
            and project_result.get("success", False)
            and library_result.get("success", False)
            and project_types_result.get("success", False)
        )

        logger.info("=" * 60)
        logger.info("AI Team Workspace seeding complete!")
        logger.info(f"  Agents: {agent_result.get('inserted', 0)}/{agent_result.get('total', 0)}")
        logger.info(f"  Library Agents: created={library_result.get('created', 0)}, updated={library_result.get('updated', 0)}, skipped={library_result.get('skipped', 0)}")
        logger.info(f"  Templates: {template_result.get('inserted', 0)}/{template_result.get('total', 0)}")
        logger.info(f"  Workshop Templates: {workshop_result.get('inserted', 0)}/{workshop_result.get('total', 0)}")
        logger.info(f"  Projects: {project_result.get('inserted', 0)}/{project_result.get('total', 0)}")
        logger.info(f"  Project Types: {project_types_result.get('inserted', 0)}/{project_types_result.get('total', 0)}")
        logger.info(f"  Overall Success: {overall_success}")
        logger.info("=" * 60)

        return {
            "success": overall_success,
            "agents": agent_result,
            "library_agents": library_result,
            "templates": template_result,
            "workshop_templates": workshop_result,
            "projects": project_result,
            "project_types": project_types_result
        }

    except Exception as e:
        logger.error(f"Error during workspace seeding: {e}")
        return {
            "success": False,
            "error": str(e),
            "agents": None,
            "library_agents": None,
            "templates": None,
            "workshop_templates": None,
            "projects": None,
            "project_types": None
        }
