"""
Workspace Usage Repository for AI Team Workspace Feature

Repository class for managing workspace usage tracking in MongoDB.
Provides methods for tracking and managing user usage and billing.
"""

from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class WorkspaceUsageRepository(BaseRepository):
    """
    Repository for workspace usage tracking.

    Manages the 'workspace_usage' collection in MongoDB, providing methods for
    tracking user usage, credits, and costs per billing period.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for workspace usage
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the WorkspaceUsageRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "workspace_usage")

    async def get_user_usage(
        self,
        user_id: str,
        month: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get usage record for a user in a specific month.

        Args:
            user_id: ID of the user
            month: Month in YYYY-MM format

        Returns:
            Usage document with id field, or None if not found
        """
        return await self.get_one({"user_id": user_id, "month": month})

    async def update_usage(
        self,
        user_id: str,
        month: str,
        credits_used: int,
        cost: float
    ) -> Optional[Dict[str, Any]]:
        """
        Update usage for a user in a specific month.

        Increments credits_used and cost. Creates record if it doesn't exist.

        Args:
            user_id: ID of the user
            month: Month in YYYY-MM format
            credits_used: Number of credits to add
            cost: Cost to add

        Returns:
            Updated usage document, or None if failed
        """
        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            {"user_id": user_id, "month": month},
            {
                "$inc": {
                    "credits_used": credits_used,
                    "total_cost": cost,
                    "execution_count": 1
                },
                "$set": {
                    "updated_at": now,
                    "last_execution": now
                },
                "$setOnInsert": {
                    "usage_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "month": month,
                    "credits_allocated": 0,
                    "plan_type": "free",
                    "created_at": now
                }
            },
            upsert=True,
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def initialize_usage(
        self,
        user_id: str,
        plan_type: str,
        credits_allocated: int
    ) -> Dict[str, Any]:
        """
        Initialize usage for a user for the current month.

        Args:
            user_id: ID of the user
            plan_type: User's plan type ('free', 'pro', 'enterprise')
            credits_allocated: Number of credits allocated for the month

        Returns:
            Created or updated usage document with id field
        """
        month = datetime.utcnow().strftime("%Y-%m")
        now = datetime.utcnow().isoformat()

        # Check if record exists
        existing = await self.get_user_usage(user_id, month)
        if existing:
            # Update credits and plan
            return await self.collection.find_one_and_update(
                {"user_id": user_id, "month": month},
                {
                    "$set": {
                        "plan_type": plan_type,
                        "credits_allocated": credits_allocated,
                        "updated_at": now
                    }
                },
                return_document=True
            )

        # Create new record
        usage_data = {
            "usage_id": str(uuid.uuid4()),
            "user_id": user_id,
            "month": month,
            "plan_type": plan_type,
            "credits_allocated": credits_allocated,
            "credits_used": 0,
            "total_cost": 0.0,
            "execution_count": 0,
            "last_execution": None
        }

        return await super().create(usage_data)

    async def get_remaining_credits(
        self,
        user_id: str,
        month: Optional[str] = None
    ) -> int:
        """
        Get remaining credits for a user.

        Args:
            user_id: ID of the user
            month: Optional month in YYYY-MM format (defaults to current month)

        Returns:
            Number of remaining credits (0 if no record found)
        """
        if not month:
            month = datetime.utcnow().strftime("%Y-%m")

        usage = await self.get_user_usage(user_id, month)
        if not usage:
            return 0

        allocated = usage.get("credits_allocated", 0)
        used = usage.get("credits_used", 0)
        return max(0, allocated - used)

    async def has_available_credits(
        self,
        user_id: str,
        credits_needed: int = 1,
        month: Optional[str] = None
    ) -> bool:
        """
        Check if user has enough credits available.

        Args:
            user_id: ID of the user
            credits_needed: Number of credits needed
            month: Optional month in YYYY-MM format

        Returns:
            True if user has enough credits, False otherwise
        """
        remaining = await self.get_remaining_credits(user_id, month)
        return remaining >= credits_needed

    async def get_usage_history(
        self,
        user_id: str,
        limit: int = 12
    ) -> list:
        """
        Get usage history for a user across multiple months.

        Args:
            user_id: ID of the user
            limit: Maximum number of months to return

        Returns:
            List of usage documents sorted by month descending
        """
        return await self.get_all(
            filter={"user_id": user_id},
            limit=limit,
            sort=[("month", -1)]
        )

    async def get_total_cost_for_month(
        self,
        user_id: str,
        month: Optional[str] = None
    ) -> float:
        """
        Get total cost for a user in a specific month.

        Args:
            user_id: ID of the user
            month: Optional month in YYYY-MM format

        Returns:
            Total cost for the month
        """
        if not month:
            month = datetime.utcnow().strftime("%Y-%m")

        usage = await self.get_user_usage(user_id, month)
        return usage.get("total_cost", 0.0) if usage else 0.0

    async def get_execution_count_for_month(
        self,
        user_id: str,
        month: Optional[str] = None
    ) -> int:
        """
        Get execution count for a user in a specific month.

        Args:
            user_id: ID of the user
            month: Optional month in YYYY-MM format

        Returns:
            Number of executions for the month
        """
        if not month:
            month = datetime.utcnow().strftime("%Y-%m")

        usage = await self.get_user_usage(user_id, month)
        return usage.get("execution_count", 0) if usage else 0

    async def reset_monthly_usage(
        self,
        user_id: str,
        month: str,
        credits_allocated: int
    ) -> Optional[Dict[str, Any]]:
        """
        Reset usage for a new billing period.

        Args:
            user_id: ID of the user
            month: Month in YYYY-MM format
            credits_allocated: Credits allocated for the new period

        Returns:
            Usage document for the new period
        """
        # Check if record already exists
        existing = await self.get_user_usage(user_id, month)
        if existing:
            return existing

        # Get plan type from previous month if available
        prev_month = datetime.utcnow().strftime("%Y-%m")
        prev_usage = await self.get_user_usage(user_id, prev_month)
        plan_type = prev_usage.get("plan_type", "free") if prev_usage else "free"

        return await self.initialize_usage(user_id, plan_type, credits_allocated)

    async def upgrade_plan(
        self,
        user_id: str,
        new_plan_type: str,
        additional_credits: int
    ) -> Optional[Dict[str, Any]]:
        """
        Upgrade user's plan and add credits.

        Args:
            user_id: ID of the user
            new_plan_type: New plan type
            additional_credits: Credits to add

        Returns:
            Updated usage document
        """
        month = datetime.utcnow().strftime("%Y-%m")
        now = datetime.utcnow().isoformat()

        # Ensure record exists
        usage = await self.get_user_usage(user_id, month)
        if not usage:
            return await self.initialize_usage(user_id, new_plan_type, additional_credits)

        result = await self.collection.find_one_and_update(
            {"user_id": user_id, "month": month},
            {
                "$set": {
                    "plan_type": new_plan_type,
                    "updated_at": now
                },
                "$inc": {
                    "credits_allocated": additional_credits
                }
            },
            return_document=True
        )

        return self._convert_id(result) if result else None
