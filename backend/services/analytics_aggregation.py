"""
Analytics Aggregation Service
Provides hourly and daily rollup of analytics events for efficient dashboard queries.
Aggregates events by dimension (user, persona, model, platform) to enable fast analytics queries.
"""

import boto3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
from collections import defaultdict
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# DynamoDB table names
EVENTS_TABLE = f"contextuai-backend-analytics-events-{ENVIRONMENT}"
HOURLY_TABLE = f"contextuai-backend-analytics-hourly-{ENVIRONMENT}"
DAILY_TABLE = f"contextuai-backend-analytics-daily-{ENVIRONMENT}"

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)


class AnalyticsAggregationService:
    """
    Service for aggregating analytics events into hourly and daily rollups.
    Enables efficient dashboard queries without scanning raw event tables.
    """

    def __init__(self):
        self.events_table = dynamodb.Table(EVENTS_TABLE)
        self.hourly_table = dynamodb.Table(HOURLY_TABLE)
        self.daily_table = dynamodb.Table(DAILY_TABLE)
        self._executor = ThreadPoolExecutor(max_workers=3)

    async def aggregate_hourly(self, hour: datetime) -> Dict[str, Any]:
        """
        Aggregate events for a specific hour into hourly rollups.
        Creates aggregates by: user, persona, model, platform-wide

        Args:
            hour: The hour to aggregate (will be truncated to hour boundary)

        Returns:
            Summary of aggregation results
        """
        try:
            # Truncate to hour boundary
            hour_start = hour.replace(minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)
            hour_key = hour_start.isoformat() + "Z"

            # Format time strings for query
            start_time = hour_start.isoformat() + "Z"
            end_time = hour_end.isoformat() + "Z"

            logger.info(f"Starting hourly aggregation for {hour_key}")

            # Query events for this hour
            events = await self._query_events_by_time(start_time, end_time)

            if not events:
                logger.warning(f"No events found for hour {hour_key}")
                return {
                    "hour": hour_key,
                    "events_processed": 0,
                    "aggregates_written": 0,
                    "status": "no_data"
                }

            logger.info(f"Found {len(events)} events for hour {hour_key}")

            # Group events by dimensions
            aggregates = self._group_events_by_dimension(events, hour_key)

            # Write aggregates to hourly table
            written_count = await self._write_hourly_aggregates(aggregates)

            logger.info(f"Hourly aggregation complete: {written_count} aggregates written")

            return {
                "hour": hour_key,
                "events_processed": len(events),
                "aggregates_written": written_count,
                "dimensions": list(aggregates.keys()),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Failed to aggregate hourly data: {e}")
            return {
                "hour": hour_key if 'hour_key' in locals() else "unknown",
                "status": "error",
                "error": str(e)
            }

    async def aggregate_daily(self, date: datetime) -> Dict[str, Any]:
        """
        Aggregate hourly data for a specific date into daily rollups.

        Args:
            date: The date to aggregate

        Returns:
            Summary of aggregation results
        """
        try:
            # Get date boundaries
            date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = date_start + timedelta(days=1)
            date_key = date_start.strftime("%Y-%m-%d")

            logger.info(f"Starting daily aggregation for {date_key}")

            # Query all hourly data for this date
            hourly_aggregates = await self._query_hourly_data_for_date(date_start)

            if not hourly_aggregates:
                logger.warning(f"No hourly data found for date {date_key}")
                return {
                    "date": date_key,
                    "hourly_records_processed": 0,
                    "daily_aggregates_written": 0,
                    "status": "no_data"
                }

            logger.info(f"Found {len(hourly_aggregates)} hourly records for {date_key}")

            # Group hourly data by dimension
            daily_aggregates = self._sum_hourly_to_daily(hourly_aggregates, date_key)

            # Write daily aggregates
            written_count = await self._write_daily_aggregates(daily_aggregates)

            logger.info(f"Daily aggregation complete: {written_count} aggregates written")

            return {
                "date": date_key,
                "hourly_records_processed": len(hourly_aggregates),
                "daily_aggregates_written": written_count,
                "dimensions": list(daily_aggregates.keys()),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Failed to aggregate daily data: {e}")
            return {
                "date": date_key if 'date_key' in locals() else "unknown",
                "status": "error",
                "error": str(e)
            }

    async def run_hourly_aggregation(self) -> Dict[str, Any]:
        """Run aggregation for the previous hour."""
        previous_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        return await self.aggregate_hourly(previous_hour)

    async def run_daily_aggregation(self) -> Dict[str, Any]:
        """Run aggregation for the previous day."""
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        return await self.aggregate_daily(datetime.combine(yesterday, datetime.min.time()))

    async def backfill(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Backfill aggregations for a date range.

        Args:
            start_date: Start of backfill period
            end_date: End of backfill period

        Returns:
            Summary of backfill operation
        """
        try:
            logger.info(f"Starting backfill from {start_date} to {end_date}")

            hourly_results = []
            daily_results = []

            # Backfill hourly aggregates
            current = start_date
            while current < end_date:
                result = await self.aggregate_hourly(current)
                hourly_results.append(result)
                current += timedelta(hours=1)

            # Backfill daily aggregates
            current_date = start_date.date()
            end_date_date = end_date.date()
            while current_date <= end_date_date:
                result = await self.aggregate_daily(datetime.combine(current_date, datetime.min.time()))
                daily_results.append(result)
                current_date += timedelta(days=1)

            total_hourly = sum(r.get("aggregates_written", 0) for r in hourly_results)
            total_daily = sum(r.get("daily_aggregates_written", 0) for r in daily_results)

            logger.info(f"Backfill complete: {total_hourly} hourly, {total_daily} daily aggregates")

            return {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "hourly_aggregates_written": total_hourly,
                "daily_aggregates_written": total_daily,
                "hourly_periods_processed": len(hourly_results),
                "daily_periods_processed": len(daily_results),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Backfill failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    # =========================================================================
    # Helper Methods - Event Querying
    # =========================================================================

    async def _query_events_by_time(self, start_time: str, end_time: str) -> List[Dict[str, Any]]:
        """Query all events within a time range."""
        try:
            loop = asyncio.get_event_loop()

            # Use scan with filter for time range (no direct time-only GSI)
            # In production, you might want to query by event_type and aggregate results
            def scan_events():
                items = []
                response = self.events_table.scan(
                    FilterExpression="timestamp BETWEEN :start AND :end",
                    ExpressionAttributeValues={
                        ":start": start_time,
                        ":end": end_time
                    }
                )
                items.extend(response.get("Items", []))

                # Handle pagination
                while "LastEvaluatedKey" in response:
                    response = self.events_table.scan(
                        FilterExpression="timestamp BETWEEN :start AND :end",
                        ExpressionAttributeValues={
                            ":start": start_time,
                            ":end": end_time
                        },
                        ExclusiveStartKey=response["LastEvaluatedKey"]
                    )
                    items.extend(response.get("Items", []))

                return items

            events = await loop.run_in_executor(self._executor, scan_events)
            return events

        except Exception as e:
            logger.error(f"Failed to query events by time: {e}")
            return []

    async def _query_hourly_data_for_date(self, date: datetime) -> List[Dict[str, Any]]:
        """Query all hourly aggregates for a specific date."""
        try:
            loop = asyncio.get_event_loop()

            # Build hour range for the date
            hours = []
            for h in range(24):
                hour_time = date.replace(hour=h, minute=0, second=0, microsecond=0)
                hours.append(hour_time.isoformat() + "Z")

            def scan_hourly():
                items = []
                response = self.hourly_table.scan(
                    FilterExpression="hour BETWEEN :start AND :end",
                    ExpressionAttributeValues={
                        ":start": hours[0],
                        ":end": hours[-1]
                    }
                )
                items.extend(response.get("Items", []))

                # Handle pagination
                while "LastEvaluatedKey" in response:
                    response = self.hourly_table.scan(
                        FilterExpression="hour BETWEEN :start AND :end",
                        ExpressionAttributeValues={
                            ":start": hours[0],
                            ":end": hours[-1]
                        },
                        ExclusiveStartKey=response["LastEvaluatedKey"]
                    )
                    items.extend(response.get("Items", []))

                return items

            aggregates = await loop.run_in_executor(self._executor, scan_hourly)
            return aggregates

        except Exception as e:
            logger.error(f"Failed to query hourly data: {e}")
            return []

    # =========================================================================
    # Helper Methods - Aggregation Logic
    # =========================================================================

    def _group_events_by_dimension(self, events: List[Dict[str, Any]], hour: str) -> Dict[str, Dict[str, Any]]:
        """
        Group events by different dimensions and calculate metrics.

        Returns dict with keys like:
        - "user#user-123"
        - "persona#persona-456"
        - "model#model-789"
        - "platform#all"
        """
        aggregates = defaultdict(lambda: {
            "active_users": set(),
            "session_count": 0,
            "message_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_cents": 0,
            "response_times": [],
            "error_count": 0,
            "unique_sessions": set()
        })

        for event in events:
            # Convert Decimal to native types
            event = self._decimal_to_native(event)

            user_id = event.get("user_id")
            persona_id = event.get("persona_id")
            model_id = event.get("model_id")
            session_id = event.get("session_id")
            event_type = event.get("event_type")
            status = event.get("status")

            # Platform-wide aggregate
            platform_key = "platform#all"
            self._add_event_to_aggregate(aggregates[platform_key], event)

            # User aggregate
            if user_id:
                user_key = f"user#{user_id}"
                self._add_event_to_aggregate(aggregates[user_key], event)

            # Persona aggregate
            if persona_id:
                persona_key = f"persona#{persona_id}"
                self._add_event_to_aggregate(aggregates[persona_key], event)

            # Model aggregate
            if model_id:
                model_key = f"model#{model_id}"
                self._add_event_to_aggregate(aggregates[model_key], event)

        # Convert to final format
        result = {}
        for dim_key, agg in aggregates.items():
            dim_type, dim_value = dim_key.split("#", 1)

            # Calculate averages
            avg_response_time = (
                sum(agg["response_times"]) / len(agg["response_times"])
                if agg["response_times"] else 0.0
            )

            result[dim_key] = {
                "dimension_key": dim_key,
                "hour": hour,
                "dimension_type": dim_type,
                "dimension_value": dim_value,
                "active_users": len(agg["active_users"]),
                "session_count": len(agg["unique_sessions"]),
                "message_count": agg["message_count"],
                "input_tokens": agg["input_tokens"],
                "output_tokens": agg["output_tokens"],
                "estimated_cost_cents": agg["estimated_cost_cents"],
                "avg_response_time_ms": round(avg_response_time, 2),
                "error_count": agg["error_count"],
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }

        return result

    def _add_event_to_aggregate(self, agg: Dict[str, Any], event: Dict[str, Any]) -> None:
        """Add event data to aggregate metrics."""
        event_type = event.get("event_type")
        status = event.get("status")
        user_id = event.get("user_id")
        session_id = event.get("session_id")

        # Track unique users and sessions
        if user_id:
            agg["active_users"].add(user_id)
        if session_id:
            agg["unique_sessions"].add(session_id)

        # Count messages
        if event_type in ["chat_request", "chat_response"]:
            agg["message_count"] += 1

        # Sum tokens and costs
        if event.get("input_tokens"):
            agg["input_tokens"] += event["input_tokens"]
        if event.get("output_tokens"):
            agg["output_tokens"] += event["output_tokens"]
        if event.get("estimated_cost_cents"):
            agg["estimated_cost_cents"] += event["estimated_cost_cents"]

        # Track response times
        if event.get("response_time_ms"):
            agg["response_times"].append(event["response_time_ms"])

        # Count errors
        if status == "error":
            agg["error_count"] += 1

    def _sum_hourly_to_daily(self, hourly_data: List[Dict[str, Any]], date: str) -> Dict[str, Dict[str, Any]]:
        """Sum hourly aggregates into daily aggregates."""
        daily_aggregates = defaultdict(lambda: {
            "active_users": set(),
            "session_count": 0,
            "message_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_cents": 0,
            "response_times": [],
            "error_count": 0
        })

        for hourly in hourly_data:
            hourly = self._decimal_to_native(hourly)
            dim_key = hourly.get("dimension_key")

            if not dim_key:
                continue

            agg = daily_aggregates[dim_key]

            # Sum metrics
            agg["session_count"] += hourly.get("session_count", 0)
            agg["message_count"] += hourly.get("message_count", 0)
            agg["input_tokens"] += hourly.get("input_tokens", 0)
            agg["output_tokens"] += hourly.get("output_tokens", 0)
            agg["estimated_cost_cents"] += hourly.get("estimated_cost_cents", 0)
            agg["error_count"] += hourly.get("error_count", 0)

            # Track max active users (not sum)
            agg["active_users"] = max(
                len(agg["active_users"]) if isinstance(agg["active_users"], set) else agg["active_users"],
                hourly.get("active_users", 0)
            )

            # Collect response times for averaging
            if hourly.get("avg_response_time_ms"):
                agg["response_times"].append(hourly["avg_response_time_ms"])

        # Convert to final format
        result = {}
        for dim_key, agg in daily_aggregates.items():
            dim_type, dim_value = dim_key.split("#", 1)

            # Calculate weighted average response time
            avg_response_time = (
                sum(agg["response_times"]) / len(agg["response_times"])
                if agg["response_times"] else 0.0
            )

            # Convert active_users set to int
            active_users = len(agg["active_users"]) if isinstance(agg["active_users"], set) else agg["active_users"]

            result[dim_key] = {
                "dimension_key": dim_key,
                "date": date,
                "dimension_type": dim_type,
                "dimension_value": dim_value,
                "active_users": active_users,
                "session_count": agg["session_count"],
                "message_count": agg["message_count"],
                "input_tokens": agg["input_tokens"],
                "output_tokens": agg["output_tokens"],
                "estimated_cost_cents": agg["estimated_cost_cents"],
                "avg_response_time_ms": round(avg_response_time, 2),
                "error_count": agg["error_count"],
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }

        return result

    # =========================================================================
    # Helper Methods - Database Writes
    # =========================================================================

    async def _write_hourly_aggregates(self, aggregates: Dict[str, Dict[str, Any]]) -> int:
        """Write hourly aggregates to DynamoDB."""
        try:
            if not aggregates:
                return 0

            loop = asyncio.get_event_loop()

            def batch_write():
                # Calculate TTL (90 days from now)
                ttl = int((datetime.utcnow() + timedelta(days=90)).timestamp())

                written = 0
                with self.hourly_table.batch_writer() as batch:
                    for dim_key, agg in aggregates.items():
                        # Add TTL
                        item = {**agg, "expires_at": ttl}
                        # Convert to Decimal
                        item = self._native_to_decimal(item)
                        batch.put_item(Item=item)
                        written += 1

                return written

            count = await loop.run_in_executor(self._executor, batch_write)
            logger.debug(f"Wrote {count} hourly aggregates")
            return count

        except Exception as e:
            logger.error(f"Failed to write hourly aggregates: {e}")
            return 0

    async def _write_daily_aggregates(self, aggregates: Dict[str, Dict[str, Any]]) -> int:
        """Write daily aggregates to DynamoDB."""
        try:
            if not aggregates:
                return 0

            loop = asyncio.get_event_loop()

            def batch_write():
                written = 0
                with self.daily_table.batch_writer() as batch:
                    for dim_key, agg in aggregates.items():
                        # No TTL for daily (keep forever)
                        item = self._native_to_decimal(agg)
                        batch.put_item(Item=item)
                        written += 1

                return written

            count = await loop.run_in_executor(self._executor, batch_write)
            logger.debug(f"Wrote {count} daily aggregates")
            return count

        except Exception as e:
            logger.error(f"Failed to write daily aggregates: {e}")
            return 0

    # =========================================================================
    # Helper Methods - Type Conversion
    # =========================================================================

    def _decimal_to_native(self, obj: Any) -> Any:
        """Convert DynamoDB Decimal types to native Python types."""
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        elif isinstance(obj, dict):
            return {k: self._decimal_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._decimal_to_native(i) for i in obj]
        return obj

    def _native_to_decimal(self, obj: Any) -> Any:
        """Convert native Python types to DynamoDB-compatible Decimal."""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self._native_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._native_to_decimal(i) for i in obj]
        return obj


# Singleton instance
aggregation_service = AnalyticsAggregationService()
