"""
Agent Builder Service for AI Team Workspace

Pattern-based service that converts natural language descriptions into agent blueprints.
Uses keyword matching for category detection, capability extraction, and system prompt generation.
No LLM dependency - purely deterministic transformation.
"""

from typing import Dict, Any, List, Optional
import re


# =============================================================================
# Category Detection Keywords
# =============================================================================

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "code_quality": [
        "test", "testing", "qa", "quality", "lint", "review", "validate",
        "check", "verify", "audit", "bug", "debug", "coverage", "jest",
        "pytest", "mocha", "cypress", "selenium", "regression"
    ],
    "devops": [
        "deploy", "deployment", "ci", "cd", "ci/cd", "pipeline", "docker",
        "kubernetes", "k8s", "terraform", "ansible", "jenkins", "github actions",
        "gitlab", "infrastructure", "monitoring", "logging", "helm", "aws",
        "azure", "gcp", "cloud", "nginx", "load balancer"
    ],
    "documentation": [
        "document", "documentation", "docs", "readme", "guide", "tutorial",
        "wiki", "api docs", "swagger", "openapi", "jsdoc", "docstring",
        "changelog", "contributing", "specification", "technical writing"
    ],
    "code_generation": [
        "build", "create", "generate", "develop", "implement", "code",
        "api", "frontend", "backend", "fullstack", "full-stack", "component",
        "service", "endpoint", "database", "schema", "model", "controller",
        "react", "vue", "angular", "nextjs", "express", "fastapi", "django",
        "flask", "spring", "graphql", "rest", "crud"
    ],
    "migration": [
        "migrate", "migration", "upgrade", "convert", "transform", "refactor",
        "modernize", "port", "translate", "legacy", "update framework",
        "version upgrade", "rewrite"
    ],
    "design": [
        "ui", "ux", "design", "wireframe", "mockup", "prototype", "figma",
        "layout", "theme", "style", "css", "tailwind", "responsive",
        "accessibility", "a11y"
    ],
    # Business categories
    "c_suite": [
        "ceo", "cfo", "cto", "cmo", "coo", "cpo", "ciso", "executive",
        "chief", "c-suite", "board", "strategic", "vision", "leadership"
    ],
    "startup_venture": [
        "startup", "founder", "venture", "fundraising", "pitch", "seed",
        "series a", "mvp", "growth hack", "lean", "product-market fit",
        "investor", "incubator", "accelerator"
    ],
    "marketing_sales": [
        "marketing", "sales", "seo", "content strategy", "social media",
        "copywriting", "demand generation", "lead", "conversion", "campaign",
        "brand", "advertising", "customer success"
    ],
    "product_management": [
        "product manager", "scrum", "agile", "sprint", "backlog", "roadmap",
        "user story", "requirements", "stakeholder", "program manager",
        "business analyst", "product owner"
    ],
    "finance_operations": [
        "finance", "financial", "accounting", "budget", "forecast", "revenue",
        "pricing", "cost analysis", "operations", "supply chain", "risk",
        "controller", "treasury"
    ],
    "hr_people": [
        "hr", "human resources", "talent", "recruiting", "hiring",
        "compensation", "benefits", "culture", "onboarding", "performance review",
        "employee", "workforce", "people operations", "org development"
    ],
    "legal_compliance": [
        "legal", "compliance", "contract", "privacy", "gdpr", "regulation",
        "intellectual property", "patent", "trademark", "counsel", "attorney",
        "liability", "governance"
    ],
    "it_security": [
        "penetration", "pentest", "soc", "incident response", "threat",
        "vulnerability", "iam", "identity", "network security", "firewall",
        "ransomware", "malware", "cybersecurity"
    ],
    "data_analytics": [
        "data science", "analytics", "bi", "business intelligence",
        "data warehouse", "etl", "machine learning", "statistics",
        "visualization", "tableau", "power bi", "data governance"
    ],
    "specialized": [
        "ethics", "sustainability", "localization", "i18n", "partnerships",
        "competitive intelligence", "customer experience", "developer advocate",
        "solutions architect", "technical account"
    ],
}

# =============================================================================
# Capability Keywords
# =============================================================================

CAPABILITY_KEYWORDS: Dict[str, List[str]] = {
    "python": ["python", "django", "flask", "fastapi", "pytest", "pip"],
    "javascript": ["javascript", "js", "node", "nodejs", "npm", "yarn"],
    "typescript": ["typescript", "ts", "tsx"],
    "react": ["react", "reactjs", "react.js", "jsx"],
    "nextjs": ["next", "nextjs", "next.js"],
    "vue": ["vue", "vuejs", "vue.js", "nuxt"],
    "angular": ["angular"],
    "docker": ["docker", "dockerfile", "container", "containerize"],
    "kubernetes": ["kubernetes", "k8s", "helm"],
    "aws": ["aws", "amazon", "s3", "ec2", "lambda", "ecs", "fargate", "bedrock"],
    "azure": ["azure", "microsoft cloud"],
    "gcp": ["gcp", "google cloud"],
    "terraform": ["terraform", "iac", "infrastructure as code"],
    "database": ["database", "db", "sql", "postgresql", "postgres", "mysql", "mongodb", "redis", "dynamodb"],
    "graphql": ["graphql", "gql", "apollo"],
    "rest_api": ["rest", "restful", "api", "endpoint"],
    "testing": ["test", "testing", "unit test", "integration test", "e2e", "tdd"],
    "security": ["security", "auth", "authentication", "authorization", "oauth", "jwt", "encryption"],
    "ci_cd": ["ci/cd", "ci", "cd", "pipeline", "github actions", "gitlab ci", "jenkins"],
    "monitoring": ["monitoring", "logging", "observability", "prometheus", "grafana", "datadog"],
    "documentation": ["documentation", "docs", "readme", "swagger", "openapi"],
    "git": ["git", "github", "gitlab", "version control", "pr", "pull request"],
    "tailwind": ["tailwind", "tailwindcss"],
    "css": ["css", "scss", "sass", "styled-components"],
    "mobile": ["mobile", "react native", "flutter", "ios", "android"],
    "machine_learning": ["ml", "machine learning", "ai", "model training", "data science"],
}

# =============================================================================
# Category to Icon Mapping
# =============================================================================

CATEGORY_ICONS: Dict[str, str] = {
    "code_generation": "code",
    "code_quality": "check-circle",
    "devops": "cloud",
    "documentation": "file-text",
    "migration": "shuffle",
    "design": "layout",
    "c_suite": "crown",
    "startup_venture": "rocket",
    "marketing_sales": "megaphone",
    "product_management": "clipboard",
    "finance_operations": "calculator",
    "hr_people": "users",
    "legal_compliance": "scale",
    "it_security": "shield",
    "data_analytics": "bar-chart-2",
    "social_engagement": "message-circle",
    "specialized": "star",
    "engineering": "cpu",
}

# =============================================================================
# System Prompt Template
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = """You are {name}, a specialized AI agent for the ContextuAI platform.

## Role
{description}

## Category
{category_label}

## Core Capabilities
{capabilities_list}

## Guidelines
- Focus exclusively on tasks within your area of expertise
- Produce high-quality, production-ready output
- Follow established best practices and conventions
- Communicate clearly about what you're doing and why
- If a task falls outside your capabilities, clearly state so
- Always prioritize code safety and security
"""


# =============================================================================
# Builder Functions
# =============================================================================

def detect_category(
    description: str,
    provided_category: Optional[str] = None
) -> str:
    """
    Detect agent category from description keywords.

    Args:
        description: Natural language description
        provided_category: Explicitly provided category (takes priority)

    Returns:
        Category string matching AgentCategory enum values
    """
    if provided_category and provided_category in CATEGORY_KEYWORDS:
        return provided_category

    description_lower = description.lower()
    scores: Dict[str, int] = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            # Count occurrences of each keyword
            count = len(re.findall(r'\b' + re.escape(keyword) + r'\b', description_lower))
            score += count
        if score > 0:
            scores[category] = score

    if not scores:
        return "code_generation"  # Default category

    return max(scores, key=scores.get)


def extract_capabilities(
    description: str,
    provided_capabilities: Optional[List[str]] = None
) -> List[str]:
    """
    Extract capabilities from description keywords.

    Args:
        description: Natural language description
        provided_capabilities: Explicitly provided capabilities (merged with detected)

    Returns:
        List of capability strings
    """
    description_lower = description.lower()
    detected: List[str] = []

    for capability, keywords in CAPABILITY_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', description_lower):
                detected.append(capability)
                break

    # Merge with provided capabilities (deduplicate)
    if provided_capabilities:
        for cap in provided_capabilities:
            cap_lower = cap.lower().strip()
            if cap_lower and cap_lower not in detected:
                detected.append(cap_lower)

    return detected


def suggest_icon(category: str) -> str:
    """
    Suggest an icon based on category.

    Args:
        category: Agent category string

    Returns:
        Icon identifier string
    """
    return CATEGORY_ICONS.get(category, "bot")


def generate_system_prompt(
    name: str,
    description: str,
    category: str,
    capabilities: List[str]
) -> str:
    """
    Generate a system prompt from agent metadata.

    Args:
        name: Agent display name
        description: Agent description
        category: Agent category
        capabilities: List of capabilities

    Returns:
        Formatted system prompt string
    """
    category_labels = {
        "code_generation": "Code Generation & Development",
        "code_quality": "Code Quality & Testing",
        "devops": "DevOps & Infrastructure",
        "documentation": "Documentation & Technical Writing",
        "migration": "Migration & Transformation",
        "design": "UI/UX Design",
        "c_suite": "C-Suite Executive",
        "startup_venture": "Startup & Venture",
        "marketing_sales": "Marketing & Sales",
        "product_management": "Product Management",
        "finance_operations": "Finance & Operations",
        "hr_people": "HR & People",
        "legal_compliance": "Legal & Compliance",
        "it_security": "IT & Security",
        "data_analytics": "Data & Analytics",
        "social_engagement": "Social Engagement",
        "specialized": "Specialized",
        "engineering": "Engineering",
    }

    category_label = category_labels.get(category, category.replace("_", " ").title())
    capabilities_list = "\n".join(f"- {cap.replace('_', ' ').title()}" for cap in capabilities)

    if not capabilities_list:
        capabilities_list = "- General purpose assistance"

    return SYSTEM_PROMPT_TEMPLATE.format(
        name=name,
        description=description,
        category_label=category_label,
        capabilities_list=capabilities_list,
    ).strip()


def build_agent_blueprint(
    name: str,
    description: str,
    category: Optional[str] = None,
    capabilities: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convert a natural language description into a full agent blueprint.

    This is the main entry point for the agent builder service. It takes a
    name and description and generates all required fields for an agent.

    Args:
        name: Agent display name
        description: Natural language description of what the agent should do
        category: Optional explicit category (auto-detected if not provided)
        capabilities: Optional explicit capabilities (auto-extracted if not provided)

    Returns:
        Dictionary containing all agent blueprint fields
    """
    detected_category = detect_category(description, category)
    extracted_capabilities = extract_capabilities(description, capabilities)
    icon = suggest_icon(detected_category)
    system_prompt = generate_system_prompt(
        name=name,
        description=description,
        category=detected_category,
        capabilities=extracted_capabilities,
    )

    return {
        "name": name,
        "description": description,
        "category": detected_category,
        "icon": icon,
        "capabilities": extracted_capabilities,
        "system_prompt": system_prompt,
        "model_id": "claude-sonnet",
        "estimated_tokens": 2000,
        "estimated_cost_usd": 0.02,
    }
