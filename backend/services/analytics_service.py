"""
Analytics Service
Handles analytics event capture, storage, and retrieval for platform usage tracking.
Non-blocking event writes ensure main request flow is not impacted.
"""

import os
import uuid
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from database import get_database
from repositories import AnalyticsRepository, UserProfileRepository

from models.analytics_models import (
    EventType,
    EventStatus,
    DimensionType,
    AnalyticsEvent,
    HourlyAggregate,
    DailyAggregate
)

# Configure logging
logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# Model pricing per 1M tokens (approximate costs in USD)
MODEL_PRICING = {
    # Anthropic Claude models
    "anthropic.claude-3-5-sonnet-20241022-v2:0": {"input": 3.00, "output": 15.00},
    "anthropic.claude-3-5-haiku-20241022-v1:0": {"input": 0.80, "output": 4.00},
    "anthropic.claude-3-opus-20240229-v1:0": {"input": 15.00, "output": 75.00},
    "anthropic.claude-3-sonnet-20240229-v1:0": {"input": 3.00, "output": 15.00},
    "anthropic.claude-3-haiku-20240307-v1:0": {"input": 0.25, "output": 1.25},
    # Amazon models
    "amazon.titan-text-lite-v1": {"input": 0.30, "output": 0.40},
    "amazon.titan-text-express-v1": {"input": 0.80, "output": 1.60},
    # Default fallback
    "default": {"input": 1.00, "output": 3.00}
}


class AnalyticsService:
    """
    Service for capturing and storing analytics events.
    Uses non-blocking writes to avoid impacting request latency.
    """

    def __init__(self):
        """Initialize analytics service (repositories are lazily loaded)"""
        self._analytics_repo: Optional[AnalyticsRepository] = None
        self._user_profile_repo: Optional[UserProfileRepository] = None

    async def _get_analytics_repo(self) -> AnalyticsRepository:
        """Get or create the analytics repository instance"""
        if self._analytics_repo is None:
            db = await get_database()
            self._analytics_repo = AnalyticsRepository(db)
        return self._analytics_repo

    async def _get_user_profile_repo(self) -> UserProfileRepository:
        """Get or create the user profile repository instance"""
        if self._user_profile_repo is None:
            db = await get_database()
            self._user_profile_repo = UserProfileRepository(db)
        return self._user_profile_repo

    # =========================================================================
    # Event Capture Methods
    # =========================================================================

    async def capture_event(
        self,
        event_type: EventType,
        user_id: str,
        status: EventStatus = EventStatus.SUCCESS,
        session_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        model_id: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        response_time_ms: Optional[int] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Capture a generic analytics event.

        Args:
            event_type: Type of event (chat_request, session_start, etc.)
            user_id: User who triggered the event
            status: Event status (success, error, timeout)
            session_id: Associated chat session ID
            persona_id: Persona used (if applicable)
            model_id: AI model used (if applicable)
            input_tokens: Token count in request
            output_tokens: Token count in response
            response_time_ms: Request-response latency
            error_type: Error category (if status is error)
            error_message: Error details (if status is error)
            metadata: Additional context-specific data

        Returns:
            event_id if capture succeeded, None otherwise
        """
        try:
            # Get user's department (if available)
            department = await self._get_user_department(user_id)

            # Calculate cost if tokens are provided
            estimated_cost_cents = None
            if input_tokens is not None and output_tokens is not None and model_id:
                estimated_cost_cents = self._calculate_cost_cents(
                    model_id, input_tokens, output_tokens
                )

            # Build event data
            event_data = {
                "session_id": session_id,
                "persona_id": persona_id,
                "model_id": model_id,
                "department": department,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "response_time_ms": response_time_ms,
                "status": status.value,
                "error_type": error_type,
                "error_message": error_message[:1000] if error_message else None,
                "estimated_cost_cents": estimated_cost_cents,
                "metadata": metadata
            }

            # Remove None values
            event_data = {k: v for k, v in event_data.items() if v is not None}

            # Write event asynchronously (non-blocking)
            event_id = await self._write_event_async(
                user_id=user_id,
                event_type=event_type.value,
                data=event_data
            )

            logger.debug(f"Analytics event captured: {event_type.value} for user {user_id}")
            return event_id

        except Exception as e:
            # Log but don't fail - analytics should never break main functionality
            logger.warning(f"Failed to capture analytics event: {e}")
            return None

    async def capture_chat_event(
        self,
        user_id: str,
        session_id: str,
        model_id: str,
        persona_id: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        response_time_ms: Optional[int] = None,
        status: EventStatus = EventStatus.SUCCESS,
        error_message: Optional[str] = None,
        is_streaming: bool = False
    ) -> Optional[str]:
        """
        Capture a chat request/response event with token usage.

        Args:
            user_id: User making the chat request
            session_id: Chat session ID
            model_id: AI model used for response
            persona_id: Persona used (if any)
            input_tokens: Tokens in the request
            output_tokens: Tokens in the response
            response_time_ms: Total request-response time
            status: Success/error status
            error_message: Error details if failed
            is_streaming: Whether streaming was used

        Returns:
            event_id if captured successfully
        """
        metadata = {
            "is_streaming": is_streaming
        }

        return await self.capture_event(
            event_type=EventType.CHAT_REQUEST,
            user_id=user_id,
            session_id=session_id,
            model_id=model_id,
            persona_id=persona_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_time_ms=response_time_ms,
            status=status,
            error_message=error_message,
            metadata=metadata
        )

    async def capture_session_event(
        self,
        user_id: str,
        session_id: str,
        event_type: EventType,
        persona_id: Optional[str] = None,
        model_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Capture a session lifecycle event (start/end).

        Args:
            user_id: User owning the session
            session_id: Session ID
            event_type: SESSION_START or SESSION_END
            persona_id: Associated persona
            model_id: Associated model
            metadata: Additional session data

        Returns:
            event_id if captured successfully
        """
        return await self.capture_event(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            persona_id=persona_id,
            model_id=model_id,
            metadata=metadata
        )

    async def capture_model_invocation(
        self,
        user_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        response_time_ms: int,
        session_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        status: EventStatus = EventStatus.SUCCESS
    ) -> Optional[str]:
        """
        Capture an AI model invocation event for cost tracking.

        Args:
            user_id: User making the request
            model_id: Model invoked
            input_tokens: Input token count
            output_tokens: Output token count
            response_time_ms: Invocation latency
            session_id: Associated session
            persona_id: Associated persona
            status: Invocation status

        Returns:
            event_id if captured successfully
        """
        return await self.capture_event(
            event_type=EventType.MODEL_INVOCATION,
            user_id=user_id,
            model_id=model_id,
            session_id=session_id,
            persona_id=persona_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_time_ms=response_time_ms,
            status=status
        )

    async def capture_error_event(
        self,
        user_id: str,
        error_type: str,
        error_message: str,
        endpoint: Optional[str] = None,
        session_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        model_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Capture an error event for monitoring and alerting.

        Args:
            user_id: User who encountered the error
            error_type: Error category (e.g., "model_error", "timeout", "validation")
            error_message: Error details
            endpoint: API endpoint where error occurred
            session_id: Associated session
            persona_id: Associated persona
            model_id: Associated model

        Returns:
            event_id if captured successfully
        """
        metadata = {}
        if endpoint:
            metadata["endpoint"] = endpoint

        return await self.capture_event(
            event_type=EventType.ERROR,
            user_id=user_id,
            status=EventStatus.ERROR,
            session_id=session_id,
            persona_id=persona_id,
            model_id=model_id,
            error_type=error_type,
            error_message=error_message,
            metadata=metadata
        )

    # =========================================================================
    # Query Methods (for analytics API)
    # =========================================================================

    async def get_events_by_type(
        self,
        event_type: EventType,
        start_time: str,
        end_time: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query events by type within a time range.
        """
        try:
            repo = await self._get_analytics_repo()
            return await repo.get_by_event_type(
                event_type=event_type.value,
                start_date=start_time,
                end_date=end_time,
                limit=limit
            )
        except Exception as e:
            logger.error(f"Failed to query events by type: {e}")
            return []

    async def get_events_by_user(
        self,
        user_id: str,
        start_time: str,
        end_time: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query events by user within a time range.
        """
        try:
            repo = await self._get_analytics_repo()
            return await repo.get_user_events(
                user_id=user_id,
                start_date=start_time,
                end_date=end_time,
                limit=limit
            )
        except Exception as e:
            logger.error(f"Failed to query events by user: {e}")
            return []

    async def get_events_by_department(
        self,
        department: str,
        start_time: str,
        end_time: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query events by department within a time range.
        """
        try:
            repo = await self._get_analytics_repo()
            # Use MongoDB filter for department
            return await repo.get_all(
                filter={
                    "department": department,
                    "timestamp": {
                        "$gte": start_time,
                        "$lte": end_time
                    }
                },
                limit=limit,
                sort=[("timestamp", -1)]
            )
        except Exception as e:
            logger.error(f"Failed to query events by department: {e}")
            return []

    async def get_events_by_model(
        self,
        model_id: str,
        start_time: str,
        end_time: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query events by model within a time range.
        """
        try:
            repo = await self._get_analytics_repo()
            # Use MongoDB filter for model_id
            return await repo.get_all(
                filter={
                    "model_id": model_id,
                    "timestamp": {
                        "$gte": start_time,
                        "$lte": end_time
                    }
                },
                limit=limit,
                sort=[("timestamp", -1)]
            )
        except Exception as e:
            logger.error(f"Failed to query events by model: {e}")
            return []

    # =========================================================================
    # Aggregation Query Methods
    # =========================================================================

    async def get_hourly_aggregates(
        self,
        dimension_type: DimensionType,
        dimension_value: str,
        start_hour: str,
        end_hour: str
    ) -> List[Dict[str, Any]]:
        """
        Query hourly aggregates for a dimension.

        Args:
            dimension_type: Type of dimension (user, department, persona, model)
            dimension_value: Specific value to query
            start_hour: Start hour (ISO format)
            end_hour: End hour (ISO format)
        """
        try:
            repo = await self._get_analytics_repo()
            return await repo.get_aggregates(
                start_date=start_hour[:10],  # Extract date part
                end_date=end_hour[:10],
                group_by="hour"
            )
        except Exception as e:
            logger.error(f"Failed to query hourly aggregates: {e}")
            return []

    async def get_daily_aggregates(
        self,
        dimension_type: DimensionType,
        dimension_value: str,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Query daily aggregates for a dimension.

        Args:
            dimension_type: Type of dimension (user, department, persona, model)
            dimension_value: Specific value to query
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        try:
            repo = await self._get_analytics_repo()
            return await repo.get_aggregates(
                start_date=start_date,
                end_date=end_date,
                group_by="day"
            )
        except Exception as e:
            logger.error(f"Failed to query daily aggregates: {e}")
            return []

    async def get_platform_daily_aggregates(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Query platform-wide daily aggregates.
        """
        return await self.get_daily_aggregates(
            DimensionType.PLATFORM,
            "all",
            start_date,
            end_date
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _write_event_async(
        self,
        user_id: str,
        event_type: str,
        data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Write event to MongoDB asynchronously.
        Uses fire-and-forget pattern to avoid blocking.
        """
        try:
            repo = await self._get_analytics_repo()
            result = await repo.create_event(
                user_id=user_id,
                event_type=event_type,
                data=data
            )
            return result.get("event_id")
        except Exception as e:
            logger.warning(f"Async event write failed: {e}")
            return None

    async def _get_user_department(self, user_id: str) -> Optional[str]:
        """
        Get user's department from user profiles collection.
        Returns None if not found.
        """
        try:
            repo = await self._get_user_profile_repo()
            profile = await repo.get_by_user_id(user_id)
            if profile:
                # Check both 'department' and 'company' fields
                return profile.get("department") or profile.get("company")
            return None
        except Exception as e:
            logger.debug(f"Failed to get user department: {e}")
            return None

    def _calculate_cost_cents(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int
    ) -> int:
        """
        Calculate estimated cost in cents based on token usage.
        Uses MODEL_PRICING lookup table.
        """
        pricing = MODEL_PRICING.get(model_id, MODEL_PRICING["default"])

        # Calculate cost in USD
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_usd = input_cost + output_cost

        # Convert to cents and round
        return int(total_usd * 100)


# Create singleton instance
analytics_service = AnalyticsService()


# =========================================================================
# Convenience Functions (for easy import and use)
# =========================================================================

async def capture_chat_analytics(
    user_id: str,
    session_id: str,
    model_id: str,
    persona_id: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    response_time_ms: Optional[int] = None,
    is_streaming: bool = False,
    status: EventStatus = EventStatus.SUCCESS,
    error_message: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function to capture chat analytics.
    Import and call this from ai_chat.py.
    """
    return await analytics_service.capture_chat_event(
        user_id=user_id,
        session_id=session_id,
        model_id=model_id,
        persona_id=persona_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        response_time_ms=response_time_ms,
        status=status,
        error_message=error_message,
        is_streaming=is_streaming
    )


async def capture_session_analytics(
    user_id: str,
    session_id: str,
    is_start: bool = True,
    persona_id: Optional[str] = None,
    model_id: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function to capture session analytics.
    Import and call this from chat_sessions.py.
    """
    event_type = EventType.SESSION_START if is_start else EventType.SESSION_END
    return await analytics_service.capture_session_event(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        persona_id=persona_id,
        model_id=model_id
    )


async def capture_error_analytics(
    user_id: str,
    error_type: str,
    error_message: str,
    endpoint: Optional[str] = None,
    session_id: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function to capture error analytics.
    Import and call this from any endpoint that encounters errors.
    """
    return await analytics_service.capture_error_event(
        user_id=user_id,
        error_type=error_type,
        error_message=error_message,
        endpoint=endpoint,
        session_id=session_id
    )
