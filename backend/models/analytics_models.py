"""
Pydantic models for Platform Analytics feature
Defines request/response schemas for analytics dashboards and reporting
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime


class EventType(str, Enum):
    """Event types for analytics tracking"""
    CHAT_REQUEST = "chat_request"
    CHAT_RESPONSE = "chat_response"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    AUTOMATION_START = "automation_start"
    AUTOMATION_COMPLETE = "automation_complete"
    AUTOMATION_STEP = "automation_step"
    PERSONA_USED = "persona_used"
    MODEL_INVOCATION = "model_invocation"
    ERROR = "error"


class EventStatus(str, Enum):
    """Status values for analytics events"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class DimensionType(str, Enum):
    """Dimension types for analytics aggregation"""
    USER = "user"
    DEPARTMENT = "department"
    PERSONA = "persona"
    MODEL = "model"
    PLATFORM = "platform"


class TrendDirection(str, Enum):
    """Trend direction indicators"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class UserSegment(str, Enum):
    """User engagement segments"""
    POWER_USER = "power_user"
    REGULAR = "regular"
    OCCASIONAL = "occasional"
    DORMANT = "dormant"


class PersonaCategory(str, Enum):
    """Persona categories for filtering"""
    DATABASE = "database"
    API = "api"
    ENTERPRISE = "enterprise"
    CLOUD = "cloud"


class ModelProvider(str, Enum):
    """AI model providers"""
    ANTHROPIC = "anthropic"
    AMAZON = "amazon"
    DEEPSEEK = "deepseek"


class ReportType(str, Enum):
    """Report generation types"""
    EXECUTIVE_SUMMARY = "executive_summary"
    ADMIN_OPERATIONS = "admin_operations"
    DEPARTMENT_USAGE = "department_usage"
    COST_REPORT = "cost_report"
    ADOPTION_REPORT = "adoption_report"


class ReportFormat(str, Enum):
    """Report export formats"""
    PDF = "pdf"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class AlertType(str, Enum):
    """Alert types for monitoring"""
    PERFORMANCE = "performance"
    COST = "cost"
    ADOPTION = "adoption"
    SECURITY = "security"
    AUTOMATION = "automation"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ReportStatus(str, Enum):
    """Report generation status"""
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# =====================================================================
# Event Models
# =====================================================================

class AnalyticsEvent(BaseModel):
    """Model for individual analytics event"""
    event_id: str = Field(..., description="UUID for the event")
    event_type: EventType = Field(..., description="Type of event")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    user_id: str = Field(..., description="User who triggered event")
    session_id: Optional[str] = Field(None, description="Associated session ID")
    persona_id: Optional[str] = Field(None, description="Persona used if applicable")
    model_id: Optional[str] = Field(None, description="AI model used")
    department: Optional[str] = Field(None, description="User's department")
    input_tokens: Optional[int] = Field(None, ge=0, description="Tokens in request")
    output_tokens: Optional[int] = Field(None, ge=0, description="Tokens in response")
    response_time_ms: Optional[int] = Field(None, ge=0, description="Request-response latency in ms")
    status: EventStatus = Field(..., description="Event status")
    error_type: Optional[str] = Field(None, description="Error category if applicable")
    error_message: Optional[str] = Field(None, max_length=1000, description="Error details")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional context-specific data")
    expires_at: Optional[int] = Field(None, description="TTL epoch timestamp for data retention")

    model_config = {
        "json_schema_extra": {
            "example": {
                "event_id": "evt-550e8400-e29b-41d4-a716-446655440000",
                "event_type": "chat_request",
                "timestamp": "2024-12-01T10:30:00Z",
                "user_id": "user-123",
                "session_id": "session-456",
                "persona_id": "persona-789",
                "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "department": "Engineering",
                "input_tokens": 150,
                "output_tokens": 850,
                "response_time_ms": 2500,
                "status": "success",
                "error_type": None,
                "error_message": None,
                "metadata": {"feature": "code_review"},
                "expires_at": 1735689000
            }
        }
    }


# =====================================================================
# Aggregation Models
# =====================================================================

class HourlyAggregate(BaseModel):
    """Model for hourly aggregated metrics"""
    dimension_key: str = Field(..., description="Composite key: {type}#{value}#{hour}")
    hour: str = Field(..., description="ISO 8601 hour (2024-12-01T14:00:00Z)")
    dimension_type: DimensionType = Field(..., description="Type of dimension")
    dimension_value: str = Field(..., description="Specific value (user_id, dept name, etc.)")
    active_users: int = Field(default=0, ge=0, description="Distinct active users")
    session_count: int = Field(default=0, ge=0, description="Sessions started")
    message_count: int = Field(default=0, ge=0, description="Messages exchanged")
    input_tokens: int = Field(default=0, ge=0, description="Total input tokens")
    output_tokens: int = Field(default=0, ge=0, description="Total output tokens")
    estimated_cost_cents: int = Field(default=0, ge=0, description="Calculated cost in cents")
    avg_response_time_ms: float = Field(default=0.0, ge=0.0, description="Average response latency")
    error_count: int = Field(default=0, ge=0, description="Errors occurred")
    automation_runs: int = Field(default=0, ge=0, description="Automations executed")
    automation_success: int = Field(default=0, ge=0, description="Successful automation runs")
    updated_at: str = Field(..., description="Last aggregation timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "dimension_key": "user#user-123#2024-12-01T14:00:00Z",
                "hour": "2024-12-01T14:00:00Z",
                "dimension_type": "user",
                "dimension_value": "user-123",
                "active_users": 1,
                "session_count": 5,
                "message_count": 45,
                "input_tokens": 2500,
                "output_tokens": 8500,
                "estimated_cost_cents": 350,
                "avg_response_time_ms": 1450.5,
                "error_count": 0,
                "automation_runs": 3,
                "automation_success": 3,
                "updated_at": "2024-12-01T15:00:00Z"
            }
        }
    }


class DailyAggregate(BaseModel):
    """Model for daily aggregated metrics"""
    dimension_key: str = Field(..., description="Composite key: {type}#{value}#{date}")
    date: str = Field(..., description="ISO 8601 date (2024-12-01)")
    dimension_type: DimensionType = Field(..., description="Type of dimension")
    dimension_value: str = Field(..., description="Specific value (user_id, dept name, etc.)")
    active_users: int = Field(default=0, ge=0, description="Distinct active users")
    session_count: int = Field(default=0, ge=0, description="Sessions started")
    message_count: int = Field(default=0, ge=0, description="Messages exchanged")
    input_tokens: int = Field(default=0, ge=0, description="Total input tokens")
    output_tokens: int = Field(default=0, ge=0, description="Total output tokens")
    estimated_cost_cents: int = Field(default=0, ge=0, description="Calculated cost in cents")
    avg_response_time_ms: float = Field(default=0.0, ge=0.0, description="Average response latency")
    error_count: int = Field(default=0, ge=0, description="Errors occurred")
    automation_runs: int = Field(default=0, ge=0, description="Automations executed")
    automation_success: int = Field(default=0, ge=0, description="Successful automation runs")
    updated_at: str = Field(..., description="Last aggregation timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "dimension_key": "department#Engineering#2024-12-01",
                "date": "2024-12-01",
                "dimension_type": "department",
                "dimension_value": "Engineering",
                "active_users": 25,
                "session_count": 125,
                "message_count": 850,
                "input_tokens": 45000,
                "output_tokens": 125000,
                "estimated_cost_cents": 8500,
                "avg_response_time_ms": 1650.5,
                "error_count": 5,
                "automation_runs": 45,
                "automation_success": 42,
                "updated_at": "2024-12-02T00:15:00Z"
            }
        }
    }


# =====================================================================
# Dashboard Response Models
# =====================================================================

class MetricWithTrend(BaseModel):
    """Model for metric with trend comparison"""
    value: float = Field(..., description="Current metric value")
    previous_value: Optional[float] = Field(None, description="Previous period value")
    change_percent: Optional[float] = Field(None, description="Percentage change")
    trend: TrendDirection = Field(..., description="Trend direction indicator")

    model_config = {
        "json_schema_extra": {
            "example": {
                "value": 245.0,
                "previous_value": 210.0,
                "change_percent": 16.7,
                "trend": "up"
            }
        }
    }


class PeriodInfo(BaseModel):
    """Model for time period information"""
    start_date: str = Field(..., description="Period start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Period end date (YYYY-MM-DD)")

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate ISO date format"""
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')


class DashboardSummaryResponse(BaseModel):
    """Model for executive dashboard summary"""
    success: bool = Field(True, description="Request success status")
    period: PeriodInfo = Field(..., description="Time period for metrics")
    metrics: Dict[str, MetricWithTrend] = Field(..., description="Key performance metrics")
    sparklines: Dict[str, List[float]] = Field(
        default_factory=dict,
        description="Trend sparklines for visualization"
    )
    last_updated: str = Field(..., description="Timestamp of last data update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "period": {
                    "start_date": "2024-11-01",
                    "end_date": "2024-11-30"
                },
                "metrics": {
                    "active_users": {
                        "value": 245.0,
                        "previous_value": 210.0,
                        "change_percent": 16.7,
                        "trend": "up"
                    },
                    "total_sessions": {
                        "value": 12500.0,
                        "previous_value": 11200.0,
                        "change_percent": 11.6,
                        "trend": "up"
                    },
                    "platform_health_score": {
                        "value": 98.5,
                        "previous_value": 97.8,
                        "change_percent": 0.7,
                        "trend": "up"
                    }
                },
                "sparklines": {
                    "daily_active_users": [45, 52, 48, 55, 60, 58, 62],
                    "daily_sessions": [450, 520, 480, 550, 600, 580, 620]
                },
                "last_updated": "2024-12-01T10:30:00Z"
            }
        }
    }


class UserSegmentInfo(BaseModel):
    """Model for user segment information"""
    count: int = Field(..., ge=0, description="Number of users in segment")
    percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of total users")


class UserDetails(BaseModel):
    """Model for detailed user analytics"""
    user_id: str = Field(..., description="User identifier")
    email: str = Field(..., description="User email address")
    department: Optional[str] = Field(None, description="User's department")
    sessions: int = Field(..., ge=0, description="Total sessions")
    messages: int = Field(..., ge=0, description="Total messages")
    last_active: str = Field(..., description="Last activity timestamp")
    personas_used: List[str] = Field(default_factory=list, description="Personas used by user")
    segment: UserSegment = Field(..., description="User engagement segment")


class PaginationInfo(BaseModel):
    """Model for pagination metadata"""
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    total_count: int = Field(..., ge=0, description="Total items count")


class UserAnalyticsSummary(BaseModel):
    """Model for user analytics summary metrics"""
    total_users: int = Field(..., ge=0, description="Total provisioned users")
    active_users: int = Field(..., ge=0, description="Active users in period")
    new_users: int = Field(..., ge=0, description="New users in period")
    churned_users: int = Field(..., ge=0, description="Churned users in period")
    retention_rate: float = Field(..., ge=0.0, le=100.0, description="User retention percentage")
    activation_rate: float = Field(..., ge=0.0, le=100.0, description="User activation percentage")


class UserAnalyticsResponse(BaseModel):
    """Model for user analytics dashboard response"""
    success: bool = Field(True, description="Request success status")
    summary: UserAnalyticsSummary = Field(..., description="Summary metrics")
    segments: Dict[str, UserSegmentInfo] = Field(..., description="User segmentation breakdown")
    users: List[UserDetails] = Field(default_factory=list, description="Detailed user list")
    pagination: PaginationInfo = Field(..., description="Pagination information")
    last_updated: str = Field(..., description="Timestamp of last data update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "summary": {
                    "total_users": 500,
                    "active_users": 245,
                    "new_users": 35,
                    "churned_users": 12,
                    "retention_rate": 78.5,
                    "activation_rate": 82.3
                },
                "segments": {
                    "power_users": {"count": 25, "percentage": 10.2},
                    "regular": {"count": 120, "percentage": 49.0},
                    "occasional": {"count": 80, "percentage": 32.6},
                    "dormant": {"count": 20, "percentage": 8.2}
                },
                "users": [],
                "pagination": {
                    "page": 1,
                    "page_size": 20,
                    "total_pages": 13,
                    "total_count": 245
                },
                "last_updated": "2024-12-01T10:30:00Z"
            }
        }
    }


class PersonaMetrics(BaseModel):
    """Model for individual persona metrics"""
    persona_id: str = Field(..., description="Persona identifier")
    name: str = Field(..., description="Persona name")
    category: PersonaCategory = Field(..., description="Persona category")
    connector_type: str = Field(..., description="Connector type")
    sessions: int = Field(..., ge=0, description="Total sessions")
    messages: int = Field(..., ge=0, description="Total messages")
    unique_users: int = Field(..., ge=0, description="Unique users")
    adoption_rate: float = Field(..., ge=0.0, le=100.0, description="Adoption percentage")
    avg_response_time_ms: float = Field(..., ge=0.0, description="Average response time")
    error_rate: float = Field(..., ge=0.0, le=100.0, description="Error rate percentage")
    tokens_used: Dict[str, int] = Field(..., description="Token usage breakdown")
    estimated_cost_usd: float = Field(..., ge=0.0, description="Estimated cost in USD")
    growth_rate: float = Field(..., description="Week-over-week growth percentage")


class PersonaAnalyticsSummary(BaseModel):
    """Model for persona analytics summary"""
    total_personas: int = Field(..., ge=0, description="Total personas configured")
    active_personas: int = Field(..., ge=0, description="Personas used in period")
    total_sessions: int = Field(..., ge=0, description="Total sessions across personas")
    unique_users: int = Field(..., ge=0, description="Unique users across personas")


class CategoryBreakdown(BaseModel):
    """Model for category-level breakdown"""
    sessions: int = Field(..., ge=0, description="Sessions in category")
    percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of total")


class PersonaAnalyticsResponse(BaseModel):
    """Model for persona analytics dashboard response"""
    success: bool = Field(True, description="Request success status")
    summary: PersonaAnalyticsSummary = Field(..., description="Summary metrics")
    personas: List[PersonaMetrics] = Field(default_factory=list, description="Persona metrics list")
    by_category: Dict[str, CategoryBreakdown] = Field(..., description="Category breakdown")
    last_updated: str = Field(..., description="Timestamp of last data update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "summary": {
                    "total_personas": 15,
                    "active_personas": 12,
                    "total_sessions": 12500,
                    "unique_users": 245
                },
                "personas": [],
                "by_category": {
                    "database": {"sessions": 6500, "percentage": 52.0},
                    "enterprise": {"sessions": 3500, "percentage": 28.0}
                },
                "last_updated": "2024-12-01T10:30:00Z"
            }
        }
    }


class ModelMetrics(BaseModel):
    """Model for individual AI model metrics"""
    model_id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Model display name")
    provider: ModelProvider = Field(..., description="Model provider")
    requests: int = Field(..., ge=0, description="Total requests")
    percentage_of_total: float = Field(..., ge=0.0, le=100.0, description="Percentage of all requests")
    input_tokens: int = Field(..., ge=0, description="Total input tokens")
    output_tokens: int = Field(..., ge=0, description="Total output tokens")
    cost_usd: float = Field(..., ge=0.0, description="Total cost in USD")
    cost_per_request: float = Field(..., ge=0.0, description="Average cost per request")
    avg_response_time_ms: float = Field(..., ge=0.0, description="Average response time")
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Success rate percentage")
    streaming_percentage: float = Field(..., ge=0.0, le=100.0, description="Streaming usage percentage")


class ModelAnalyticsSummary(BaseModel):
    """Model for model analytics summary"""
    total_requests: int = Field(..., ge=0, description="Total model requests")
    total_input_tokens: int = Field(..., ge=0, description="Total input tokens")
    total_output_tokens: int = Field(..., ge=0, description="Total output tokens")
    total_cost_usd: float = Field(..., ge=0.0, description="Total cost in USD")
    avg_response_time_ms: float = Field(..., ge=0.0, description="Average response time")


class CostTrendPoint(BaseModel):
    """Model for cost trend data point"""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    cost_usd: float = Field(..., ge=0.0, description="Cost in USD")


class ModelAnalyticsResponse(BaseModel):
    """Model for AI model analytics dashboard response"""
    success: bool = Field(True, description="Request success status")
    summary: ModelAnalyticsSummary = Field(..., description="Summary metrics")
    models: List[ModelMetrics] = Field(default_factory=list, description="Model metrics list")
    cost_trend: List[CostTrendPoint] = Field(default_factory=list, description="Cost trend over time")
    last_updated: str = Field(..., description="Timestamp of last data update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "summary": {
                    "total_requests": 87500,
                    "total_input_tokens": 12500000,
                    "total_output_tokens": 18500000,
                    "total_cost_usd": 4250.00,
                    "avg_response_time_ms": 1450.0
                },
                "models": [],
                "cost_trend": [
                    {"date": "2024-11-01", "cost_usd": 125.00},
                    {"date": "2024-11-02", "cost_usd": 142.00}
                ],
                "last_updated": "2024-12-01T10:30:00Z"
            }
        }
    }


class AutomationMetrics(BaseModel):
    """Model for individual automation metrics"""
    automation_id: str = Field(..., description="Automation identifier")
    name: str = Field(..., description="Automation name")
    owner: str = Field(..., description="Automation creator user ID")
    status: str = Field(..., description="Automation status")
    executions: int = Field(..., ge=0, description="Total executions")
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Success rate percentage")
    avg_duration_ms: float = Field(..., ge=0.0, description="Average duration")
    personas_used: List[str] = Field(default_factory=list, description="Personas in automation")
    estimated_time_saved_hours: float = Field(..., ge=0.0, description="Time saved estimate")
    last_run: Optional[str] = Field(None, description="Last execution timestamp")


class AutomationAnalyticsSummary(BaseModel):
    """Model for automation analytics summary"""
    total_automations: int = Field(..., ge=0, description="Total automations created")
    active_automations: int = Field(..., ge=0, description="Active automations")
    total_executions: int = Field(..., ge=0, description="Total executions in period")
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Overall success rate")
    avg_duration_ms: float = Field(..., ge=0.0, description="Average execution duration")
    estimated_time_saved_hours: float = Field(..., ge=0.0, description="Total time saved")
    productivity_multiplier: float = Field(..., ge=0.0, description="Productivity multiplier")


class ExecutionTrendPoint(BaseModel):
    """Model for automation execution trend"""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    executions: int = Field(..., ge=0, description="Total executions")
    success: int = Field(..., ge=0, description="Successful executions")
    failed: int = Field(..., ge=0, description="Failed executions")


class FailureReason(BaseModel):
    """Model for automation failure analysis"""
    reason: str = Field(..., description="Failure reason description")
    count: int = Field(..., ge=0, description="Occurrence count")


class AutomationAnalyticsResponse(BaseModel):
    """Model for automation analytics dashboard response"""
    success: bool = Field(True, description="Request success status")
    summary: AutomationAnalyticsSummary = Field(..., description="Summary metrics")
    automations: List[AutomationMetrics] = Field(default_factory=list, description="Automation metrics list")
    execution_trend: List[ExecutionTrendPoint] = Field(default_factory=list, description="Execution trend")
    failure_reasons: List[FailureReason] = Field(default_factory=list, description="Top failure reasons")
    last_updated: str = Field(..., description="Timestamp of last data update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "summary": {
                    "total_automations": 85,
                    "active_automations": 62,
                    "total_executions": 3200,
                    "success_rate": 92.5,
                    "avg_duration_ms": 15000.0,
                    "estimated_time_saved_hours": 1200.0,
                    "productivity_multiplier": 3.5
                },
                "automations": [],
                "execution_trend": [],
                "failure_reasons": [
                    {"reason": "Database connection timeout", "count": 45}
                ],
                "last_updated": "2024-12-01T10:30:00Z"
            }
        }
    }


class CostBreakdownItem(BaseModel):
    """Model for cost breakdown item"""
    name: str = Field(..., description="Item name (model, department, etc.)")
    cost_usd: float = Field(..., ge=0.0, description="Cost in USD")
    percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of total cost")


class CostForecast(BaseModel):
    """Model for cost forecast projection"""
    cost_usd: float = Field(..., ge=0.0, description="Forecasted cost in USD")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level (0-1)")


class OptimizationSuggestion(BaseModel):
    """Model for cost optimization suggestion"""
    type: str = Field(..., description="Suggestion type")
    description: str = Field(..., description="Detailed suggestion description")
    estimated_savings_usd: float = Field(..., ge=0.0, description="Potential savings in USD")


class CostAnalyticsSummary(BaseModel):
    """Model for cost analytics summary"""
    total_cost_usd: float = Field(..., ge=0.0, description="Total cost in period")
    cost_mtd: float = Field(..., ge=0.0, description="Month-to-date cost")
    cost_ytd: float = Field(..., ge=0.0, description="Year-to-date cost")
    projected_monthly_cost: float = Field(..., ge=0.0, description="Projected monthly cost")
    budget_usd: Optional[float] = Field(None, ge=0.0, description="Allocated budget")
    budget_utilization: Optional[float] = Field(None, ge=0.0, le=100.0, description="Budget usage percentage")
    cost_per_user: float = Field(..., ge=0.0, description="Average cost per active user")
    cost_per_conversation: float = Field(..., ge=0.0, description="Average cost per conversation")


class CostBreakdown(BaseModel):
    """Model for cost breakdown by different dimensions"""
    by_model: List[CostBreakdownItem] = Field(default_factory=list, description="Cost by model")
    by_department: List[CostBreakdownItem] = Field(default_factory=list, description="Cost by department")


class CostAnalyticsResponse(BaseModel):
    """Model for cost analytics dashboard response"""
    success: bool = Field(True, description="Request success status")
    summary: CostAnalyticsSummary = Field(..., description="Summary metrics")
    breakdown: CostBreakdown = Field(..., description="Cost breakdown by dimensions")
    trend: List[CostTrendPoint] = Field(default_factory=list, description="Cost trend over time")
    forecast: Dict[str, CostForecast] = Field(..., description="Cost forecasts (30/60/90 day)")
    optimization_suggestions: List[OptimizationSuggestion] = Field(
        default_factory=list,
        description="Optimization recommendations"
    )
    last_updated: str = Field(..., description="Timestamp of last data update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "summary": {
                    "total_cost_usd": 4250.00,
                    "cost_mtd": 3800.00,
                    "cost_ytd": 42500.00,
                    "projected_monthly_cost": 4500.00,
                    "budget_usd": 5000.00,
                    "budget_utilization": 85.0,
                    "cost_per_user": 17.35,
                    "cost_per_conversation": 0.34
                },
                "breakdown": {
                    "by_model": [],
                    "by_department": []
                },
                "trend": [],
                "forecast": {
                    "30_day": {"cost_usd": 4500.00, "confidence": 0.85},
                    "60_day": {"cost_usd": 9200.00, "confidence": 0.75},
                    "90_day": {"cost_usd": 14000.00, "confidence": 0.65}
                },
                "optimization_suggestions": [],
                "last_updated": "2024-12-01T10:30:00Z"
            }
        }
    }


# =====================================================================
# Request Models
# =====================================================================

class DateRangeParams(BaseModel):
    """Model for date range query parameters"""
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    department: Optional[str] = Field(None, description="Filter by department")
    compare_previous: Optional[bool] = Field(False, description="Include previous period comparison")

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate ISO date format"""
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')

    model_config = {
        "json_schema_extra": {
            "example": {
                "start_date": "2024-11-01",
                "end_date": "2024-11-30",
                "department": "Engineering",
                "compare_previous": True
            }
        }
    }


class ReportDelivery(BaseModel):
    """Model for report delivery configuration"""
    method: str = Field(..., description="Delivery method (email, link)")
    recipients: List[str] = Field(..., min_length=1, description="Recipient email addresses")
    slack_channel: Optional[str] = Field(None, description="Slack channel for notification")


class ReportGenerationRequest(BaseModel):
    """Model for report generation request"""
    report_type: ReportType = Field(..., description="Type of report to generate")
    start_date: str = Field(..., description="Report start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Report end date (YYYY-MM-DD)")
    format: ReportFormat = Field(ReportFormat.PDF, description="Export format")
    include_sections: List[str] = Field(..., min_length=1, description="Sections to include")
    delivery: ReportDelivery = Field(..., description="Delivery configuration")
    department: Optional[str] = Field(None, description="Filter by department")

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate ISO date format"""
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')

    model_config = {
        "json_schema_extra": {
            "example": {
                "report_type": "executive_summary",
                "start_date": "2024-11-01",
                "end_date": "2024-11-30",
                "format": "pdf",
                "include_sections": ["overview", "adoption", "cost", "automations"],
                "delivery": {
                    "method": "email",
                    "recipients": ["ceo@company.com", "cfo@company.com"]
                }
            }
        }
    }


class ReportGenerationResponse(BaseModel):
    """Model for report generation response"""
    success: bool = Field(True, description="Request success status")
    report_id: str = Field(..., description="Report job identifier")
    status: ReportStatus = Field(..., description="Report generation status")
    estimated_completion: str = Field(..., description="Estimated completion time")
    delivery: ReportDelivery = Field(..., description="Delivery configuration")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "report_id": "report-123",
                "status": "generating",
                "estimated_completion": "2024-12-01T10:35:00Z",
                "delivery": {
                    "method": "email",
                    "recipients": ["ceo@company.com"]
                }
            }
        }
    }


class ReportStatusResponse(BaseModel):
    """Model for report status response"""
    success: bool = Field(True, description="Request success status")
    report_id: str = Field(..., description="Report identifier")
    status: ReportStatus = Field(..., description="Current status")
    download_url: Optional[str] = Field(None, description="S3 download URL if completed")
    expires_at: Optional[str] = Field(None, description="Download URL expiration time")
    generated_at: Optional[str] = Field(None, description="Generation completion time")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "report_id": "report-123",
                "status": "completed",
                "download_url": "https://s3.amazonaws.com/...",
                "expires_at": "2024-12-08T10:30:00Z",
                "generated_at": "2024-12-01T10:33:00Z",
                "error_message": None
            }
        }
    }


class AlertCondition(BaseModel):
    """Model for alert condition configuration"""
    metric: str = Field(..., description="Metric to monitor")
    operator: str = Field(..., description="Comparison operator (greater_than, less_than, equals)")
    threshold: float = Field(..., description="Threshold value")

    @field_validator('operator')
    @classmethod
    def validate_operator(cls, v: str) -> str:
        """Validate operator is supported"""
        valid_operators = ['greater_than', 'less_than', 'equals', 'not_equals']
        if v not in valid_operators:
            raise ValueError(f'Operator must be one of: {", ".join(valid_operators)}')
        return v


class AlertNotification(BaseModel):
    """Model for alert notification configuration"""
    channels: List[str] = Field(..., min_length=1, description="Notification channels")
    recipients: List[str] = Field(..., min_length=1, description="Email recipients")
    slack_channel: Optional[str] = Field(None, description="Slack channel for notifications")

    @field_validator('channels')
    @classmethod
    def validate_channels(cls, v: List[str]) -> List[str]:
        """Validate notification channels are supported"""
        valid_channels = ['email', 'slack', 'in_app']
        for channel in v:
            if channel not in valid_channels:
                raise ValueError(f'Channel must be one of: {", ".join(valid_channels)}')
        return v


class AlertConfigRequest(BaseModel):
    """Model for alert configuration request"""
    name: str = Field(..., min_length=1, max_length=100, description="Alert name")
    type: AlertType = Field(..., description="Alert type")
    condition: AlertCondition = Field(..., description="Alert trigger condition")
    notification: AlertNotification = Field(..., description="Notification settings")
    enabled: bool = Field(True, description="Whether alert is active")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "High Cost Alert",
                "type": "cost",
                "condition": {
                    "metric": "daily_cost_usd",
                    "operator": "greater_than",
                    "threshold": 200.00
                },
                "notification": {
                    "channels": ["email", "slack"],
                    "recipients": ["admin@company.com"],
                    "slack_channel": "#platform-alerts"
                },
                "enabled": True
            }
        }
    }


class AlertConfigResponse(BaseModel):
    """Model for alert configuration response"""
    success: bool = Field(True, description="Request success status")
    alert_id: str = Field(..., description="Alert identifier")
    name: str = Field(..., description="Alert name")
    status: str = Field(..., description="Alert status (active, inactive)")
    created_at: str = Field(..., description="Creation timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "alert_id": "alert-123",
                "name": "High Cost Alert",
                "status": "active",
                "created_at": "2024-12-01T10:30:00Z"
            }
        }
    }


class AlertInfo(BaseModel):
    """Model for alert information"""
    alert_id: str = Field(..., description="Alert identifier")
    name: str = Field(..., description="Alert name")
    type: AlertType = Field(..., description="Alert type")
    enabled: bool = Field(..., description="Whether alert is active")
    last_triggered: Optional[str] = Field(None, description="Last trigger timestamp")
    trigger_count: int = Field(default=0, ge=0, description="Total trigger count")


class AlertListResponse(BaseModel):
    """Model for alert list response"""
    success: bool = Field(True, description="Request success status")
    alerts: List[AlertInfo] = Field(default_factory=list, description="List of configured alerts")
    last_updated: str = Field(..., description="Timestamp of last update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "alerts": [
                    {
                        "alert_id": "alert-123",
                        "name": "High Cost Alert",
                        "type": "cost",
                        "enabled": True,
                        "last_triggered": "2024-11-28T15:30:00Z",
                        "trigger_count": 3
                    }
                ],
                "last_updated": "2024-12-01T10:30:00Z"
            }
        }
    }


class UsageHeatmapData(BaseModel):
    """Model for usage heatmap data"""
    success: bool = Field(True, description="Request success status")
    metric: str = Field(..., description="Metric being visualized")
    timezone: str = Field("UTC", description="Timezone for data")
    data: Dict[str, List[float]] = Field(..., description="Heatmap data by day of week")
    peak_hour: Dict[str, Any] = Field(..., description="Peak usage information")
    last_updated: str = Field(..., description="Timestamp of last update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "metric": "sessions",
                "timezone": "UTC",
                "data": {
                    "Monday": [12, 15, 8, 5, 3, 2, 5, 25, 85, 120, 135, 145, 140, 130, 125, 115, 95, 65, 45, 35, 28, 22, 18, 15]
                },
                "peak_hour": {"day": "Wednesday", "hour": 11, "value": 152},
                "last_updated": "2024-12-01T10:30:00Z"
            }
        }
    }
