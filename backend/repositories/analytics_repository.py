"""
Analytics Repository for Analytics Events

Repository class for managing analytics events in MongoDB.
Provides methods for creating events and querying aggregated data.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta
import uuid

from .base_repository import BaseRepository


class AnalyticsRepository(BaseRepository):
    """
    Repository for analytics events.

    Manages the 'analytics_events' collection in MongoDB, providing methods for
    creating analytics events and querying aggregated data.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for analytics events
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the AnalyticsRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "analytics_events")

    async def create_event(
        self,
        user_id: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new analytics event.

        Args:
            user_id: ID of the user associated with the event
            event_type: Type of event (e.g., 'chat_request', 'session_start', etc.)
            data: Additional event data including:
                - session_id: Associated session ID
                - persona_id: Persona used if applicable
                - model_id: AI model used
                - department: User's department
                - input_tokens: Number of input tokens
                - output_tokens: Number of output tokens
                - response_time_ms: Request-response latency
                - status: Event status ('success', 'error', 'timeout')
                - error_type: Error category if applicable
                - error_message: Error details
                - metadata: Additional context-specific data

        Returns:
            Created event document with id field
        """
        event_data = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "session_id": data.get("session_id") if data else None,
            "persona_id": data.get("persona_id") if data else None,
            "model_id": data.get("model_id") if data else None,
            "department": data.get("department") if data else None,
            "input_tokens": data.get("input_tokens") if data else None,
            "output_tokens": data.get("output_tokens") if data else None,
            "response_time_ms": data.get("response_time_ms") if data else None,
            "status": data.get("status", "success") if data else "success",
            "error_type": data.get("error_type") if data else None,
            "error_message": data.get("error_message") if data else None,
            "metadata": data.get("metadata") if data else None
        }

        # Remove None values to save storage
        event_data = {k: v for k, v in event_data.items() if v is not None}

        return await super().create(event_data)

    async def get_user_events(
        self,
        user_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events for a specific user within a date range.

        Args:
            user_id: ID of the user
            start_date: Start date in ISO format (optional)
            end_date: End date in ISO format (optional)
            event_type: Filter by event type (optional)
            limit: Maximum number of events to return

        Returns:
            List of event documents sorted by timestamp descending
        """
        filter_query: Dict[str, Any] = {"user_id": user_id}

        if start_date or end_date:
            filter_query["timestamp"] = {}
            if start_date:
                filter_query["timestamp"]["$gte"] = start_date
            if end_date:
                filter_query["timestamp"]["$lte"] = end_date

        if event_type:
            filter_query["event_type"] = event_type

        return await self.get_all(
            filter=filter_query,
            limit=limit,
            sort=[("timestamp", -1)]
        )

    async def get_aggregates(
        self,
        start_date: str,
        end_date: str,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated analytics data for a date range.

        Args:
            start_date: Start date in ISO format (YYYY-MM-DD)
            end_date: End date in ISO format (YYYY-MM-DD)
            group_by: Grouping level ('hour', 'day', 'week', 'month')

        Returns:
            List of aggregated data dictionaries with metrics per period
        """
        # Build the date format based on grouping
        date_formats = {
            "hour": "%Y-%m-%dT%H:00:00Z",
            "day": "%Y-%m-%d",
            "week": "%Y-W%V",
            "month": "%Y-%m"
        }
        date_format = date_formats.get(group_by, "%Y-%m-%d")

        # Build aggregation pipeline
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": f"{start_date}T00:00:00Z",
                        "$lte": f"{end_date}T23:59:59Z"
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": date_format,
                            "date": {"$dateFromString": {"dateString": "$timestamp"}}
                        }
                    },
                    "active_users": {"$addToSet": "$user_id"},
                    "session_count": {
                        "$sum": {
                            "$cond": [{"$eq": ["$event_type", "session_start"]}, 1, 0]
                        }
                    },
                    "message_count": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$event_type", ["chat_request", "chat_response"]]},
                                1, 0
                            ]
                        }
                    },
                    "input_tokens": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
                    "output_tokens": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
                    "total_response_time_ms": {"$sum": {"$ifNull": ["$response_time_ms", 0]}},
                    "response_count": {
                        "$sum": {
                            "$cond": [{"$ifNull": ["$response_time_ms", False]}, 1, 0]
                        }
                    },
                    "error_count": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "error"]}, 1, 0]
                        }
                    },
                    "automation_runs": {
                        "$sum": {
                            "$cond": [{"$eq": ["$event_type", "automation_start"]}, 1, 0]
                        }
                    },
                    "automation_success": {
                        "$sum": {
                            "$cond": [
                                {"$and": [
                                    {"$eq": ["$event_type", "automation_complete"]},
                                    {"$eq": ["$status", "success"]}
                                ]},
                                1, 0
                            ]
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "period": "$_id",
                    "active_users": {"$size": "$active_users"},
                    "session_count": 1,
                    "message_count": 1,
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "avg_response_time_ms": {
                        "$cond": [
                            {"$gt": ["$response_count", 0]},
                            {"$divide": ["$total_response_time_ms", "$response_count"]},
                            0
                        ]
                    },
                    "error_count": 1,
                    "automation_runs": 1,
                    "automation_success": 1
                }
            },
            {"$sort": {"period": 1}}
        ]

        return await self.aggregate(pipeline, convert_ids=False)

    async def get_by_event_type(
        self,
        event_type: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events of a specific type.

        Args:
            event_type: Type of event to retrieve
            start_date: Start date in ISO format (optional)
            end_date: End date in ISO format (optional)
            limit: Maximum number of events to return

        Returns:
            List of event documents sorted by timestamp descending
        """
        filter_query: Dict[str, Any] = {"event_type": event_type}

        if start_date or end_date:
            filter_query["timestamp"] = {}
            if start_date:
                filter_query["timestamp"]["$gte"] = start_date
            if end_date:
                filter_query["timestamp"]["$lte"] = end_date

        return await self.get_all(
            filter=filter_query,
            limit=limit,
            sort=[("timestamp", -1)]
        )

    async def get_user_activity_summary(
        self,
        user_id: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Get activity summary for a specific user.

        Args:
            user_id: ID of the user
            start_date: Start date in ISO format
            end_date: End date in ISO format

        Returns:
            Dictionary with user activity metrics
        """
        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "timestamp": {
                        "$gte": f"{start_date}T00:00:00Z",
                        "$lte": f"{end_date}T23:59:59Z"
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_events": {"$sum": 1},
                    "sessions": {
                        "$sum": {
                            "$cond": [{"$eq": ["$event_type", "session_start"]}, 1, 0]
                        }
                    },
                    "messages": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$event_type", ["chat_request"]]},
                                1, 0
                            ]
                        }
                    },
                    "automations_run": {
                        "$sum": {
                            "$cond": [{"$eq": ["$event_type", "automation_start"]}, 1, 0]
                        }
                    },
                    "total_input_tokens": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
                    "total_output_tokens": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
                    "personas_used": {"$addToSet": "$persona_id"},
                    "models_used": {"$addToSet": "$model_id"},
                    "first_activity": {"$min": "$timestamp"},
                    "last_activity": {"$max": "$timestamp"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "total_events": 1,
                    "sessions": 1,
                    "messages": 1,
                    "automations_run": 1,
                    "total_input_tokens": 1,
                    "total_output_tokens": 1,
                    "personas_used": {
                        "$filter": {
                            "input": "$personas_used",
                            "as": "p",
                            "cond": {"$ne": ["$$p", None]}
                        }
                    },
                    "models_used": {
                        "$filter": {
                            "input": "$models_used",
                            "as": "m",
                            "cond": {"$ne": ["$$m", None]}
                        }
                    },
                    "first_activity": 1,
                    "last_activity": 1
                }
            }
        ]

        results = await self.aggregate(pipeline, convert_ids=False)

        if results:
            return results[0]

        return {
            "total_events": 0,
            "sessions": 0,
            "messages": 0,
            "automations_run": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "personas_used": [],
            "models_used": [],
            "first_activity": None,
            "last_activity": None
        }

    async def get_model_usage(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Get model usage statistics.

        Args:
            start_date: Start date in ISO format
            end_date: End date in ISO format

        Returns:
            List of model usage statistics
        """
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": f"{start_date}T00:00:00Z",
                        "$lte": f"{end_date}T23:59:59Z"
                    },
                    "model_id": {"$exists": True, "$ne": None}
                }
            },
            {
                "$group": {
                    "_id": "$model_id",
                    "requests": {"$sum": 1},
                    "input_tokens": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
                    "output_tokens": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
                    "total_response_time_ms": {"$sum": {"$ifNull": ["$response_time_ms", 0]}},
                    "response_count": {
                        "$sum": {
                            "$cond": [{"$ifNull": ["$response_time_ms", False]}, 1, 0]
                        }
                    },
                    "unique_users": {"$addToSet": "$user_id"},
                    "error_count": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "error"]}, 1, 0]
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "model_id": "$_id",
                    "requests": 1,
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "avg_response_time_ms": {
                        "$cond": [
                            {"$gt": ["$response_count", 0]},
                            {"$divide": ["$total_response_time_ms", "$response_count"]},
                            0
                        ]
                    },
                    "unique_users": {"$size": "$unique_users"},
                    "error_count": 1,
                    "error_rate": {
                        "$cond": [
                            {"$gt": ["$requests", 0]},
                            {"$multiply": [
                                {"$divide": ["$error_count", "$requests"]},
                                100
                            ]},
                            0
                        ]
                    }
                }
            },
            {"$sort": {"requests": -1}}
        ]

        return await self.aggregate(pipeline, convert_ids=False)

    async def get_persona_usage(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Get persona usage statistics.

        Args:
            start_date: Start date in ISO format
            end_date: End date in ISO format

        Returns:
            List of persona usage statistics
        """
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": f"{start_date}T00:00:00Z",
                        "$lte": f"{end_date}T23:59:59Z"
                    },
                    "persona_id": {"$exists": True, "$ne": None}
                }
            },
            {
                "$group": {
                    "_id": "$persona_id",
                    "sessions": {
                        "$sum": {
                            "$cond": [{"$eq": ["$event_type", "session_start"]}, 1, 0]
                        }
                    },
                    "messages": {
                        "$sum": {
                            "$cond": [{"$eq": ["$event_type", "chat_request"]}, 1, 0]
                        }
                    },
                    "unique_users": {"$addToSet": "$user_id"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "persona_id": "$_id",
                    "sessions": 1,
                    "messages": 1,
                    "unique_users": {"$size": "$unique_users"}
                }
            },
            {"$sort": {"messages": -1}}
        ]

        return await self.aggregate(pipeline, convert_ids=False)

    async def cleanup_old_events(self, days: int = 30) -> int:
        """
        Delete events older than specified days.

        Args:
            days: Number of days to keep events

        Returns:
            Number of deleted events
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

        return await self.delete_many({"timestamp": {"$lt": cutoff_date}})

    async def count_events_by_type(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, int]:
        """
        Count events by type for a date range.

        Args:
            start_date: Start date in ISO format
            end_date: End date in ISO format

        Returns:
            Dictionary with event type counts
        """
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": f"{start_date}T00:00:00Z",
                        "$lte": f"{end_date}T23:59:59Z"
                    }
                }
            },
            {
                "$group": {
                    "_id": "$event_type",
                    "count": {"$sum": 1}
                }
            }
        ]

        results = await self.aggregate(pipeline, convert_ids=False)

        counts = {}
        for item in results:
            counts[item["_id"]] = item["count"]

        return counts
