"""
Analytics Router
Provides API endpoints for platform analytics dashboards and reports.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from database import get_database
from repositories import AnalyticsRepository
from repositories import CodeMorphRepository
from repositories import WorkspaceProjectRepository, WorkspaceExecutionRepository

from models.analytics_models import (
    EventType,
    EventStatus,
    DimensionType,
    TrendDirection,
    MetricWithTrend,
    PeriodInfo,
    DashboardSummaryResponse,
    UserAnalyticsResponse,
    UserAnalyticsSummary,
    UserSegmentInfo,
    PaginationInfo,
    PersonaAnalyticsResponse,
    PersonaAnalyticsSummary,
    CategoryBreakdown,
    ModelAnalyticsResponse,
    ModelAnalyticsSummary,
    CostTrendPoint,
    AutomationAnalyticsResponse,
    AutomationAnalyticsSummary,
    CostAnalyticsResponse,
    CostAnalyticsSummary,
    CostBreakdown,
    CostBreakdownItem,
    CostForecast,
    UsageHeatmapData
)
from services.analytics_service import analytics_service
from services.analytics_aggregation import aggregation_service

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


# Dependency function to get AnalyticsRepository
async def get_analytics_repository() -> AnalyticsRepository:
    """Dependency to get AnalyticsRepository instance"""
    db = await get_database()
    return AnalyticsRepository(db)


def calculate_trend(current: float, previous: float) -> TrendDirection:
    """Calculate trend direction based on change"""
    if previous == 0:
        return TrendDirection.UP if current > 0 else TrendDirection.STABLE
    change = (current - previous) / previous * 100
    if change > 5:
        return TrendDirection.UP
    elif change < -5:
        return TrendDirection.DOWN
    return TrendDirection.STABLE


def calculate_change_percent(current: float, previous: float) -> Optional[float]:
    """Calculate percentage change between periods"""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


# =========================================================================
# Dashboard Summary Endpoint
# =========================================================================

@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    department: Optional[str] = Query(None, description="Filter by department"),
    compare_previous: bool = Query(False, description="Include previous period comparison"),
    repo: AnalyticsRepository = Depends(get_analytics_repository)
):
    """
    Get executive dashboard summary with key metrics.

    Returns high-level platform metrics including:
    - Active users
    - Total sessions
    - Total messages
    - Automation executions
    - Platform health score
    """
    try:
        # Parse dates
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        period_days = (end - start).days + 1

        # Get aggregated data from MongoDB
        aggregates = await repo.get_aggregates(start_date, end_date, group_by="day")

        # Calculate totals from aggregates
        total_users = 0
        total_sessions = 0
        total_messages = 0
        total_automation_runs = 0
        total_errors = 0
        total_cost_cents = 0
        response_times = []

        for agg in aggregates:
            total_users = max(total_users, agg.get("active_users", 0))
            total_sessions += agg.get("session_count", 0)
            total_messages += agg.get("message_count", 0)
            total_automation_runs += agg.get("automation_runs", 0)
            total_errors += agg.get("error_count", 0)
            if agg.get("avg_response_time_ms"):
                response_times.append(agg["avg_response_time_ms"])

        # Calculate averages
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        # Calculate health score (simple calculation based on error rate)
        if total_messages > 0:
            error_rate = total_errors / total_messages * 100
            health_score = max(0, min(100, 100 - error_rate * 10))
        else:
            health_score = 100.0

        # Build metrics with trends
        metrics = {
            "active_users": MetricWithTrend(
                value=float(total_users),
                previous_value=None,
                change_percent=None,
                trend=TrendDirection.STABLE
            ),
            "total_sessions": MetricWithTrend(
                value=float(total_sessions),
                previous_value=None,
                change_percent=None,
                trend=TrendDirection.STABLE
            ),
            "total_messages": MetricWithTrend(
                value=float(total_messages),
                previous_value=None,
                change_percent=None,
                trend=TrendDirection.STABLE
            ),
            "automation_runs": MetricWithTrend(
                value=float(total_automation_runs),
                previous_value=None,
                change_percent=None,
                trend=TrendDirection.STABLE
            ),
            "platform_health_score": MetricWithTrend(
                value=round(health_score, 1),
                previous_value=None,
                change_percent=None,
                trend=TrendDirection.STABLE
            ),
            "total_cost_usd": MetricWithTrend(
                value=round(total_cost_cents / 100, 2),
                previous_value=None,
                change_percent=None,
                trend=TrendDirection.STABLE
            )
        }

        # Compare with previous period if requested
        if compare_previous:
            prev_start = start - timedelta(days=period_days)
            prev_end = start - timedelta(days=1)

            prev_aggregates = await repo.get_aggregates(
                prev_start.strftime("%Y-%m-%d"),
                prev_end.strftime("%Y-%m-%d"),
                group_by="day"
            )

            # Calculate previous totals
            prev_users = 0
            prev_sessions = 0
            prev_messages = 0
            prev_automations = 0
            prev_errors = 0

            for agg in prev_aggregates:
                prev_users = max(prev_users, agg.get("active_users", 0))
                prev_sessions += agg.get("session_count", 0)
                prev_messages += agg.get("message_count", 0)
                prev_automations += agg.get("automation_runs", 0)
                prev_errors += agg.get("error_count", 0)

            # Update metrics with comparison
            metrics["active_users"] = MetricWithTrend(
                value=float(total_users),
                previous_value=float(prev_users),
                change_percent=calculate_change_percent(total_users, prev_users),
                trend=calculate_trend(total_users, prev_users)
            )
            metrics["total_sessions"] = MetricWithTrend(
                value=float(total_sessions),
                previous_value=float(prev_sessions),
                change_percent=calculate_change_percent(total_sessions, prev_sessions),
                trend=calculate_trend(total_sessions, prev_sessions)
            )
            metrics["total_messages"] = MetricWithTrend(
                value=float(total_messages),
                previous_value=float(prev_messages),
                change_percent=calculate_change_percent(total_messages, prev_messages),
                trend=calculate_trend(total_messages, prev_messages)
            )
            metrics["automation_runs"] = MetricWithTrend(
                value=float(total_automation_runs),
                previous_value=float(prev_automations),
                change_percent=calculate_change_percent(total_automation_runs, prev_automations),
                trend=calculate_trend(total_automation_runs, prev_automations)
            )

        # Build sparklines from daily data
        sparklines = {
            "daily_sessions": [a.get("session_count", 0) for a in aggregates],
            "daily_messages": [a.get("message_count", 0) for a in aggregates],
            "daily_users": [a.get("active_users", 0) for a in aggregates]
        }

        return DashboardSummaryResponse(
            success=True,
            period=PeriodInfo(
                start_date=start_date,
                end_date=end_date
            ),
            metrics=metrics,
            sparklines=sparklines,
            last_updated=datetime.utcnow().isoformat() + "Z"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get dashboard summary: {str(e)}"
        )


# =========================================================================
# Events Query Endpoints
# =========================================================================

@router.get("/events/recent")
async def get_recent_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    limit: int = Query(50, ge=1, le=200, description="Number of events to return"),
    repo: AnalyticsRepository = Depends(get_analytics_repository)
) -> Dict[str, Any]:
    """
    Get recent analytics events for debugging and monitoring.
    """
    try:
        end_time = datetime.utcnow().isoformat() + "Z"
        start_time = (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z"

        events = []

        if user_id:
            events = await repo.get_user_events(
                user_id=user_id,
                start_date=start_time,
                end_date=end_time,
                event_type=event_type,
                limit=limit
            )
        elif event_type:
            try:
                # Validate event type
                et = EventType(event_type)
                events = await repo.get_by_event_type(
                    event_type=et.value,
                    start_date=start_time,
                    end_date=end_time,
                    limit=limit
                )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid event type: {event_type}"
                )
        else:
            # Get all recent events
            events = await repo.get_all(
                filter={
                    "timestamp": {
                        "$gte": start_time,
                        "$lte": end_time
                    }
                },
                limit=limit,
                sort=[("timestamp", -1)]
            )

        # Sort by timestamp descending
        events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "success": True,
            "events": events[:limit],
            "count": len(events),
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get recent events: {str(e)}"
        )


@router.get("/events/stats")
async def get_event_stats(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    repo: AnalyticsRepository = Depends(get_analytics_repository)
) -> Dict[str, Any]:
    """
    Get event statistics summary for a date range.
    """
    try:
        # Get counts by event type using repository method
        event_counts = await repo.count_events_by_type(start_date, end_date)

        total_events = sum(event_counts.values())

        return {
            "success": True,
            "period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "total_events": total_events,
            "by_type": event_counts,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get event stats: {str(e)}"
        )


# =========================================================================
# Model Analytics Endpoint
# =========================================================================

@router.get("/models")
async def get_model_analytics(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    repo: AnalyticsRepository = Depends(get_analytics_repository)
) -> Dict[str, Any]:
    """
    Get AI model usage analytics.

    Returns metrics by model including:
    - Request counts
    - Token usage
    - Cost breakdown
    - Response times
    """
    try:
        # Get model usage statistics from repository
        model_stats = await repo.get_model_usage(start_date, end_date)

        # Format for response
        models = []
        for stats in model_stats:
            models.append({
                "model_id": stats.get("model_id", "unknown"),
                "requests": stats.get("requests", 0),
                "input_tokens": stats.get("input_tokens", 0),
                "output_tokens": stats.get("output_tokens", 0),
                "cost_usd": round(stats.get("estimated_cost_cents", 0) / 100, 2) if stats.get("estimated_cost_cents") else 0,
                "avg_response_time_ms": round(stats.get("avg_response_time_ms", 0), 0)
            })

        # Sort by requests descending
        models.sort(key=lambda x: x["requests"], reverse=True)

        # Calculate totals
        total_requests = sum(m["requests"] for m in models)
        total_input_tokens = sum(m["input_tokens"] for m in models)
        total_output_tokens = sum(m["output_tokens"] for m in models)
        total_cost = sum(m["cost_usd"] for m in models)

        return {
            "success": True,
            "summary": {
                "total_requests": total_requests,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_cost_usd": round(total_cost, 2)
            },
            "models": models,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get model analytics: {str(e)}"
        )


# =========================================================================
# User Analytics Endpoint
# =========================================================================

@router.get("/users")
async def get_user_analytics(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    repo: AnalyticsRepository = Depends(get_analytics_repository)
) -> Dict[str, Any]:
    """
    Get user activity analytics.

    Returns user engagement metrics including:
    - Active users count
    - Session counts per user
    - Message counts per user
    """
    try:
        start_time = f"{start_date}T00:00:00Z"
        end_time = f"{end_date}T23:59:59Z"

        # Get all events in the date range
        all_events = await repo.get_all(
            filter={
                "timestamp": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            },
            limit=10000
        )

        # Aggregate by user
        user_stats = {}
        for event in all_events:
            user_id = event.get("user_id", "unknown")

            if user_id not in user_stats:
                user_stats[user_id] = {
                    "user_id": user_id,
                    "sessions": 0,
                    "messages": 0,
                    "last_active": event.get("timestamp", ""),
                    "department": event.get("department"),
                    "personas_used": set()
                }

            if event.get("event_type") == EventType.SESSION_START.value:
                user_stats[user_id]["sessions"] += 1
            elif event.get("event_type") in [EventType.CHAT_REQUEST.value, "chat_request"]:
                user_stats[user_id]["messages"] += 1

            if event.get("persona_id"):
                user_stats[user_id]["personas_used"].add(event["persona_id"])

            # Update last active
            if event.get("timestamp", "") > user_stats[user_id]["last_active"]:
                user_stats[user_id]["last_active"] = event["timestamp"]

        # Convert sets to lists and sort
        users = []
        for user_id, stats in user_stats.items():
            stats["personas_used"] = list(stats["personas_used"])
            users.append(stats)

        users.sort(key=lambda x: x["messages"], reverse=True)

        # Apply pagination
        total_count = len(users)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_users = users[start_idx:end_idx]

        return {
            "success": True,
            "summary": {
                "total_users": total_count,
                "active_users": len([u for u in users if u["messages"] > 0])
            },
            "users": paginated_users,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size,
                "total_count": total_count
            },
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get user analytics: {str(e)}"
        )


# =========================================================================
# Automation Analytics Endpoint
# =========================================================================

@router.get("/automations")
async def get_automation_analytics(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    repo: AnalyticsRepository = Depends(get_analytics_repository)
) -> Dict[str, Any]:
    """
    Get automation execution analytics.

    Returns automation metrics including:
    - Total executions
    - Success rate
    - Average duration
    """
    try:
        start_time = f"{start_date}T00:00:00Z"
        end_time = f"{end_date}T23:59:59Z"

        # Get automation start events
        start_events = await repo.get_by_event_type(
            event_type="automation_start",
            start_date=start_time,
            end_date=end_time,
            limit=1000
        )

        # Get automation complete events
        complete_events = await repo.get_by_event_type(
            event_type="automation_complete",
            start_date=start_time,
            end_date=end_time,
            limit=1000
        )

        # Calculate metrics
        total_executions = len(start_events)
        successful = sum(1 for e in complete_events if e.get("status") == "success")
        failed = total_executions - successful

        durations = [
            e.get("response_time_ms", 0)
            for e in complete_events
            if e.get("response_time_ms")
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0

        success_rate = (successful / total_executions * 100) if total_executions > 0 else 0

        return {
            "success": True,
            "summary": {
                "total_executions": total_executions,
                "successful": successful,
                "failed": failed,
                "success_rate": round(success_rate, 1),
                "avg_duration_ms": round(avg_duration, 0)
            },
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get automation analytics: {str(e)}"
        )


# =========================================================================
# CodeMorph Analytics Endpoint
# =========================================================================

async def get_codemorph_repository() -> CodeMorphRepository:
    """Dependency to get CodeMorphRepository instance"""
    db = await get_database()
    return CodeMorphRepository(db)


@router.get("/codemorph")
async def get_codemorph_analytics(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    repo: CodeMorphRepository = Depends(get_codemorph_repository)
) -> Dict[str, Any]:
    """
    Get CodeMorph job analytics with cost tracking.

    Returns metrics including:
    - Total cost across all jobs
    - Average cost per job
    - Job counts by status
    - Token usage totals
    - Duration statistics
    - Breakdown by migration type and model
    - Per-job detail rows
    """
    try:
        start_time = f"{start_date}T00:00:00Z"
        end_time = f"{end_date}T23:59:59Z"

        # Query all jobs in the date range
        jobs = await repo.get_all(
            filter={
                "created_at": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            },
            limit=1000,
            sort=[("created_at", -1)]
        )

        # Calculate aggregate metrics
        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        total_tokens = 0
        total_duration_ms = 0
        jobs_with_cost = 0
        jobs_completed = 0
        jobs_failed = 0
        jobs_pending = 0

        # Group by migration_type and model_used
        cost_by_type: Dict[str, float] = {}
        cost_by_model: Dict[str, float] = {}

        job_rows = []

        for job in jobs:
            status = job.get("status", "unknown")
            if status == "completed":
                jobs_completed += 1
            elif status == "failed":
                jobs_failed += 1
            elif status in ("pending", "processing", "paused"):
                jobs_pending += 1

            cost = job.get("cost_usd")
            if cost is not None:
                total_cost += cost
                jobs_with_cost += 1

            input_tok = job.get("input_tokens", 0) or 0
            output_tok = job.get("output_tokens", 0) or 0
            total_input_tokens += input_tok
            total_output_tokens += output_tok
            total_tokens += job.get("total_tokens", 0) or 0

            dur = job.get("transform_duration_ms", 0) or 0
            total_duration_ms += dur

            # Group by migration type
            mtype = job.get("migration_type", "unknown")
            if cost is not None:
                cost_by_type[mtype] = cost_by_type.get(mtype, 0) + cost

            # Group by model
            model = job.get("model_used")
            if model and cost is not None:
                cost_by_model[model] = cost_by_model.get(model, 0) + cost

            # Build row for table
            repo_name = job.get("repo_name") or job.get("repo_url", "").split("/")[-1].replace(".git", "")
            job_rows.append({
                "job_id": job.get("job_id"),
                "repo_name": repo_name,
                "migration_type": mtype,
                "status": status,
                "model_used": job.get("model_used"),
                "cost_usd": cost,
                "input_tokens": job.get("input_tokens"),
                "output_tokens": job.get("output_tokens"),
                "total_tokens": job.get("total_tokens"),
                "num_turns": job.get("num_turns"),
                "transform_duration_ms": job.get("transform_duration_ms"),
                "created_at": job.get("created_at"),
                "completed_at": job.get("completed_at"),
            })

        total_jobs = len(jobs)
        avg_cost = (total_cost / jobs_with_cost) if jobs_with_cost > 0 else 0
        avg_duration_ms = (total_duration_ms / jobs_with_cost) if jobs_with_cost > 0 else 0

        # Format distribution data for charts
        type_distribution = [
            {"label": k, "value": round(v, 4)}
            for k, v in sorted(cost_by_type.items(), key=lambda x: x[1], reverse=True)
        ]
        model_distribution = [
            {"label": k, "value": round(v, 4)}
            for k, v in sorted(cost_by_model.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "success": True,
            "summary": {
                "total_jobs": total_jobs,
                "jobs_completed": jobs_completed,
                "jobs_failed": jobs_failed,
                "jobs_pending": jobs_pending,
                "jobs_with_cost_data": jobs_with_cost,
                "total_cost_usd": round(total_cost, 4),
                "avg_cost_per_job": round(avg_cost, 4),
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_tokens,
                "avg_duration_ms": round(avg_duration_ms, 0),
            },
            "cost_by_migration_type": type_distribution,
            "cost_by_model": model_distribution,
            "jobs": job_rows,
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get CodeMorph analytics: {str(e)}"
        )


# =========================================================================
# Workspace Analytics Endpoint
# =========================================================================

async def get_workspace_project_repository() -> WorkspaceProjectRepository:
    """Dependency to get WorkspaceProjectRepository instance"""
    db = await get_database()
    return WorkspaceProjectRepository(db)


async def get_workspace_execution_repository() -> WorkspaceExecutionRepository:
    """Dependency to get WorkspaceExecutionRepository instance"""
    db = await get_database()
    return WorkspaceExecutionRepository(db)


@router.get("/workspace")
async def get_workspace_analytics(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    project_repo: WorkspaceProjectRepository = Depends(get_workspace_project_repository),
    execution_repo: WorkspaceExecutionRepository = Depends(get_workspace_execution_repository),
) -> Dict[str, Any]:
    """
    Get Workspace execution analytics with cost tracking.

    Returns metrics including:
    - Total cost across all executions
    - Average cost per execution
    - Execution counts by status
    - Token usage totals
    - Duration statistics
    - Breakdown by project type and agent
    - Per-execution detail rows
    """
    try:
        start_time = f"{start_date}T00:00:00Z"
        end_time = f"{end_date}T23:59:59Z"

        # Query all executions in the date range
        executions = await execution_repo.get_all(
            filter={
                "created_at": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            },
            limit=1000,
            sort=[("created_at", -1)]
        )

        # Query all projects for name/type enrichment
        all_projects = await project_repo.get_all(filter={}, limit=5000)
        project_lookup: Dict[str, dict] = {}
        for proj in all_projects:
            pid = proj.get("project_id") or proj.get("id")
            if pid:
                project_lookup[pid] = proj

        # Aggregate metrics
        total_cost = 0.0
        total_tokens = 0
        total_duration_ms = 0
        executions_completed = 0
        executions_failed = 0
        executions_running = 0
        executions_with_metrics = 0

        cost_by_project_type: Dict[str, float] = {}
        cost_by_agent: Dict[str, float] = {}

        execution_rows = []

        for exc in executions:
            status = exc.get("status", "unknown")
            if status == "completed":
                executions_completed += 1
            elif status == "failed":
                executions_failed += 1
            elif status in ("running", "pending"):
                executions_running += 1

            metrics = exc.get("metrics") or {}
            cost = metrics.get("total_cost", 0) or 0
            tokens = metrics.get("total_tokens", 0) or 0
            duration = metrics.get("duration_ms", 0) or 0

            total_cost += cost
            total_tokens += tokens
            total_duration_ms += duration
            if cost > 0 or tokens > 0:
                executions_with_metrics += 1

            # Look up project for type enrichment
            project_id = exc.get("project_id", "")
            project = project_lookup.get(project_id, {})
            project_name = project.get("name") or project.get("title") or "Unknown"
            project_type = project.get("project_type") or "build"

            # Group cost by project type
            if cost > 0:
                cost_by_project_type[project_type] = cost_by_project_type.get(project_type, 0) + cost

            # Group cost by agent from steps
            steps = exc.get("steps") or []
            for step in steps:
                agent_name = step.get("agent_name")
                step_cost = step.get("cost_usd", 0) or 0
                if agent_name and step_cost > 0:
                    cost_by_agent[agent_name] = cost_by_agent.get(agent_name, 0) + step_cost

            # Build row for table
            execution_rows.append({
                "execution_id": exc.get("execution_id"),
                "project_id": project_id,
                "project_name": project_name,
                "project_type": project_type,
                "status": status,
                "total_tokens": tokens,
                "total_cost": cost,
                "duration_ms": duration,
                "num_steps": len(steps),
                "started_at": exc.get("started_at"),
                "completed_at": exc.get("completed_at"),
                "created_at": exc.get("created_at"),
            })

        total_executions = len(executions)
        success_rate = (executions_completed / total_executions * 100) if total_executions > 0 else 0
        avg_cost = (total_cost / executions_with_metrics) if executions_with_metrics > 0 else 0
        avg_duration = (total_duration_ms / executions_with_metrics) if executions_with_metrics > 0 else 0

        # Count distinct projects
        distinct_projects = len(set(e.get("project_id", "") for e in executions if e.get("project_id")))

        # Format distribution data for charts
        type_distribution = [
            {"label": k, "value": round(v, 4)}
            for k, v in sorted(cost_by_project_type.items(), key=lambda x: x[1], reverse=True)
        ]
        agent_distribution = [
            {"label": k, "value": round(v, 4)}
            for k, v in sorted(cost_by_agent.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "success": True,
            "summary": {
                "total_projects": distinct_projects,
                "total_executions": total_executions,
                "executions_completed": executions_completed,
                "executions_failed": executions_failed,
                "executions_running": executions_running,
                "success_rate": round(success_rate, 1),
                "total_cost_usd": round(total_cost, 4),
                "avg_cost_per_execution": round(avg_cost, 4),
                "total_tokens": total_tokens,
                "avg_duration_ms": round(avg_duration, 0),
            },
            "cost_by_project_type": type_distribution,
            "cost_by_agent": agent_distribution,
            "executions": execution_rows,
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get Workspace analytics: {str(e)}"
        )


# =========================================================================
# Admin Aggregation Endpoints
# =========================================================================

@router.post("/admin/aggregate/hourly")
async def trigger_hourly_aggregation() -> Dict[str, Any]:
    """
    Trigger hourly aggregation for the previous hour.
    Admin-only endpoint for manual triggers.

    Aggregates raw events into hourly rollups by:
    - User
    - Persona
    - Model
    - Platform-wide

    This improves dashboard query performance by pre-calculating metrics.
    """
    try:
        result = await aggregation_service.run_hourly_aggregation()
        return {
            "success": True,
            "result": result,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger hourly aggregation: {str(e)}"
        )


@router.post("/admin/aggregate/daily")
async def trigger_daily_aggregation() -> Dict[str, Any]:
    """
    Trigger daily aggregation for the previous day.
    Admin-only endpoint for manual triggers.

    Sums up hourly data into daily aggregates for long-term trend analysis.
    Daily data has no TTL and is kept indefinitely.
    """
    try:
        result = await aggregation_service.run_daily_aggregation()
        return {
            "success": True,
            "result": result,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger daily aggregation: {str(e)}"
        )


@router.post("/admin/aggregate/backfill")
async def trigger_backfill(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD")
) -> Dict[str, Any]:
    """
    Backfill aggregations for a date range.
    Admin-only endpoint for historical data processing.

    Use this when:
    - Initially deploying analytics system
    - Recovering from aggregation failures
    - Re-processing data after schema changes

    Warning: Large date ranges may take significant time to process.
    """
    try:
        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # Validate date range
        if start > end:
            raise HTTPException(
                status_code=400,
                detail="Start date must be before or equal to end date"
            )

        # Limit backfill range to prevent timeout
        max_days = 90
        if (end - start).days > max_days:
            raise HTTPException(
                status_code=400,
                detail=f"Date range too large. Maximum {max_days} days allowed."
            )

        result = await aggregation_service.backfill(start, end)
        return {
            "success": True,
            "result": result,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format. Use YYYY-MM-DD: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger backfill: {str(e)}"
        )


# =========================================================================
# Health Check
# =========================================================================

@router.get("/health")
async def analytics_health_check(
    repo: AnalyticsRepository = Depends(get_analytics_repository)
):
    """Health check for analytics service"""
    try:
        # Verify MongoDB connection by performing a simple query
        await repo.get_all(filter={}, limit=1)
        status = "healthy"
    except Exception as e:
        status = f"unhealthy: {str(e)}"

    return {
        "status": status,
        "service": "analytics",
        "database": "mongodb",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
