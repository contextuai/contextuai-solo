"""
Unified User Management Router
Creates users in both AWS Cognito and MongoDB for complete integration
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, EmailStr
from motor.motor_asyncio import AsyncIOMotorDatabase
import os
import uuid
import secrets
import string
from datetime import datetime

# Import database and repository
from database import get_database
from repositories import UserRepository

try:
    from services.cognito_service import CognitoService
except ImportError:
    CognitoService = None
from services.auth_service import get_current_user, require_admin, require_power_user
from services.password_service import PasswordService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# Initialize services
cognito_service = CognitoService() if CognitoService else None
password_service = PasswordService()


# Dependency function for repository
async def get_user_repository(db: AsyncIOMotorDatabase = Depends(get_database)) -> UserRepository:
    """Get UserRepository instance with database dependency."""
    return UserRepository(db)


# Pydantic models for validation
class UserCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    role: str = Field(..., pattern="^(standardUser|powerUser|admin|engineer|superAdmin)$")
    title: str = Field(..., min_length=1, max_length=100)
    group: str = Field(..., min_length=1, max_length=50)
    department: str = Field(..., min_length=1, max_length=50)
    password: Optional[str] = Field(None, min_length=8, max_length=128)  # Optional password
    organization: Optional[str] = Field(None, min_length=1, max_length=50)

class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    role: Optional[str] = Field(None, pattern="^(standardUser|powerUser|admin|engineer|superAdmin)$")
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    group: Optional[str] = Field(None, min_length=1, max_length=50)
    department: Optional[str] = Field(None, min_length=1, max_length=50)
    status: Optional[str] = Field(None, pattern="^(active|inactive|suspended)$")

class PasswordSetup(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

class UserResponse(BaseModel):
    user_id: str
    email: str
    first_name: str
    last_name: str
    role: str
    title: str
    group: str
    department: str
    status: str
    password_set: bool
    cognito_sub: Optional[str] = None  # Cognito user ID
    in_cognito: bool = False  # Flag to indicate if user exists in Cognito
    created_at: str
    updated_at: str
    last_login: Optional[str] = None

class UsersListResponse(BaseModel):
    success: bool
    users: List[UserResponse]
    total_count: int
    last_updated: str
    source: str = "mongodb"
    error: Optional[str] = None

def generate_temporary_password(length: int = 12) -> str:
    """Generate a secure temporary password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def format_user_response(user_item: Dict[str, Any]) -> UserResponse:
    """Format MongoDB document to UserResponse"""
    return UserResponse(
        user_id=user_item.get("user_id", user_item.get("id", "")),
        email=user_item.get("email", ""),
        first_name=user_item.get("first_name", ""),
        last_name=user_item.get("last_name", ""),
        role=user_item.get("role", "standardUser"),
        title=user_item.get("title", ""),
        group=user_item.get("group", ""),
        department=user_item.get("department", ""),
        status=user_item.get("status", "active"),
        password_set=user_item.get("password_set", False),
        cognito_sub=user_item.get("cognito_sub"),
        in_cognito=user_item.get("in_cognito", False),
        created_at=user_item.get("created_at", ""),
        updated_at=user_item.get("updated_at", ""),
        last_login=user_item.get("last_login")
    )

# OPTIONS handler for CORS preflight - must come before GET
@router.options("")
@router.options("/")
async def users_options():
    """Handle CORS preflight for users endpoint"""
    return {}

@router.get("", response_model=UsersListResponse)
@router.get("/", response_model=UsersListResponse)
async def list_users(
    department: Optional[str] = None,
    status: Optional[str] = None,
    role: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """List all users with optional filtering"""
    try:
        logger.info("[DEBUG Users Router] list_users called")
        logger.info(f"[DEBUG Users Router] Current user from auth: {current_user}")
        logger.info(f"[DEBUG Users Router] Email: {current_user.get('email')}")
        logger.info(f"[DEBUG Users Router] Initial role: {current_user.get('role')}")

        user_role = current_user.get("role", "standardUser")
        logger.info(f"[DEBUG Users Router] Role from token: {user_role}")

        # If role is standardUser (default when custom attributes missing), try to get from MongoDB
        if user_role == "standardUser":
            user_email = current_user.get("email")
            logger.info(f"[DEBUG Users Router] Role is standardUser, checking MongoDB for email: {user_email}")

            if user_email:
                try:
                    # Query MongoDB for user's actual role
                    db_user = await user_repo.get_by_email(user_email)
                    logger.info(f"[DEBUG Users Router] MongoDB query result: {'user found' if db_user else 'not found'}")

                    if db_user:
                        user_role = db_user.get('role', 'standardUser')
                        logger.info(f"[DEBUG Users Router] Found user in MongoDB:")
                        logger.info(f"  - DB User ID: {db_user.get('id')}")
                        logger.info(f"  - DB Email: {db_user.get('email')}")
                        logger.info(f"  - DB Role: {user_role}")
                        logger.info(f"Fetched role from MongoDB for {user_email}: {user_role}")
                    else:
                        logger.warning(f"[DEBUG Users Router] User {user_email} NOT found in MongoDB!")
                except Exception as e:
                    logger.error(f"[DEBUG Users Router] Error fetching from MongoDB: {str(e)}")
                    logger.warning(f"Failed to fetch role from MongoDB: {e}")

        logger.info(f"[DEBUG Users Router] Final role for permission check: {user_role}")

        # Check if user has permission to list users
        if user_role not in ["admin", "superAdmin", "powerUser"]:
            logger.error(f"[DEBUG Users Router] Access DENIED - role {user_role} not in allowed roles")
            raise HTTPException(status_code=403, detail=f"Insufficient permissions to list users. Your role: {user_role}")

        logger.info(f"[DEBUG Users Router] Access GRANTED - role {user_role} is allowed")

        # Build filter query
        filter_query = {}
        if role:
            filter_query["role"] = role
        if department:
            filter_query["department"] = department
        if status:
            filter_query["status"] = status

        # Get users from MongoDB
        users = await user_repo.get_all(filter=filter_query if filter_query else None)

        # Format response
        formatted_users = [format_user_response(user) for user in users]

        return UsersListResponse(
            success=True,
            users=formatted_users,
            total_count=len(formatted_users),
            last_updated=datetime.utcnow().isoformat() + "Z"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return UsersListResponse(
            success=False,
            users=[],
            total_count=0,
            last_updated=datetime.utcnow().isoformat() + "Z",
            error=str(e)
        )

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Get a specific user by ID"""
    try:
        # Allow users to get their own info, admins can get anyone
        if user_id != current_user.get("user_id") and current_user.get("role") not in ["admin", "superAdmin", "powerUser"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        user = await user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return format_user_response(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/email/{email}")
async def get_user_by_email(
    email: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Get a user by email address"""
    try:
        # Check permissions
        if current_user.get("role") not in ["admin", "superAdmin", "powerUser"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        user = await user_repo.get_by_email(email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return format_user_response(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user by email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=UserResponse)
async def create_user(
    user: UserCreate,
    current_user: Dict[str, Any] = Depends(require_power_user),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Create a new user in both Cognito and MongoDB"""
    try:
        logger.info(f"Creating user: {user.email}")

        # Check if user already exists in MongoDB
        existing = await user_repo.get_by_email(user.email)
        if existing:
            raise HTTPException(status_code=409, detail="User with this email already exists")

        # Generate password if not provided
        password = user.password if user.password else generate_temporary_password()

        # Step 1: Create user in Cognito
        cognito_user = None
        cognito_sub = None
        try:
            cognito_user = cognito_service.create_user(
                email=user.email,
                password=password,
                user_attributes={
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role,
                    'department': user.department,
                    'organization': user.organization or current_user.get("organization", "default")
                }
            )
            cognito_sub = cognito_user.get('cognito_sub')
            logger.info(f"Created Cognito user with sub: {cognito_sub}")
        except Exception as e:
            logger.error(f"Failed to create Cognito user: {str(e)}")
            # Continue without Cognito if it fails (backward compatibility)

        # Hash password for local auth storage
        password_hash = password_service.hash_password(password)

        # Step 2: Create user in MongoDB
        user_data = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "title": user.title,
            "group": user.group,
            "department": user.department,
            "organization": user.organization or "default",
            "status": "active",
            "password_set": bool(user.password),
            "password_hash": password_hash,  # Store hashed password for local auth
            "cognito_sub": cognito_sub,
            "in_cognito": bool(cognito_sub),
        }

        created_user = await user_repo.create(email=user.email, data=user_data)
        logger.info(f"Created MongoDB user: {created_user.get('user_id')}")

        # Prepare response
        response = format_user_response(created_user)

        # Add temporary password to response if generated
        if not user.password:
            return {
                **response.dict(),
                "temporary_password": password,
                "message": "User created with temporary password. User must change password on first login."
            }

        return response

    except HTTPException:
        raise
    except ValueError as e:
        # UserRepository raises ValueError for duplicate email
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Update an existing user in both Cognito and MongoDB"""
    try:
        # Check permissions (users can update themselves, admins can update anyone)
        if user_id != current_user.get("user_id") and current_user.get("role") not in ["admin", "superAdmin", "powerUser"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        # Get current user from MongoDB
        current_user_data = await user_repo.get_by_id(user_id)
        if not current_user_data:
            raise HTTPException(status_code=404, detail="User not found")

        # Update Cognito if user exists there
        if current_user_data.get('in_cognito'):
            email = current_user_data['email']
            cognito_updates = {}

            if user_update.first_name:
                cognito_updates['first_name'] = user_update.first_name
            if user_update.last_name:
                cognito_updates['last_name'] = user_update.last_name
            if user_update.role:
                cognito_updates['role'] = user_update.role
            if user_update.department:
                cognito_updates['department'] = user_update.department

            if cognito_updates:
                try:
                    cognito_service.update_user(email, cognito_updates)
                    logger.info(f"Updated Cognito user: {email}")
                except Exception as e:
                    logger.error(f"Failed to update Cognito user: {str(e)}")
                    # Continue even if Cognito update fails

        # Handle status changes in Cognito
        if user_update.status:
            if current_user_data.get('in_cognito'):
                email = current_user_data['email']
                try:
                    if user_update.status == 'inactive' or user_update.status == 'suspended':
                        cognito_service.disable_user(email)
                    elif user_update.status == 'active':
                        cognito_service.enable_user(email)
                except Exception as e:
                    logger.error(f"Failed to update Cognito user status: {str(e)}")

        # Update MongoDB
        update_data = user_update.dict(exclude_unset=True)
        updated_user = await user_repo.update(user_id, update_data)

        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"Updated MongoDB user: {user_id}")
        return format_user_response(updated_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_admin),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Delete a user (soft delete in MongoDB, disable in Cognito)"""
    try:
        # Get user from MongoDB
        user_data = await user_repo.get_by_id(user_id)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        # Disable in Cognito if user exists there
        if user_data.get('in_cognito'):
            email = user_data['email']
            try:
                cognito_service.disable_user(email)
                logger.info(f"Disabled Cognito user: {email}")
            except Exception as e:
                logger.error(f"Failed to disable Cognito user: {str(e)}")
                # Continue even if Cognito operation fails

        # Soft delete in MongoDB (update status to inactive)
        deleted = await user_repo.delete(user_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"Soft deleted user: {user_id}")
        return {"message": "User deleted successfully", "user_id": user_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Password management endpoints
@router.post("/{user_id}/setup-password")
async def setup_password(
    user_id: str,
    password_data: PasswordSetup,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Set up password for a user in Cognito"""
    try:
        # Users can set their own password, admins can set anyone's
        if user_id != current_user.get("user_id") and current_user.get("role") not in ["admin", "superAdmin"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        if password_data.password != password_data.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        # Get user from MongoDB
        user_data = await user_repo.get_by_id(user_id)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        email = user_data['email']

        # Hash password for local storage
        password_hash = password_service.hash_password(password_data.password)

        # Update MongoDB with hashed password
        await user_repo.set_password_hash(user_id, password_hash)

        # Also set password in Cognito (optional, for backward compatibility)
        try:
            cognito_service.reset_password(email, password_data.password)
        except Exception as e:
            logger.warning(f"Failed to set password in Cognito: {str(e)}")

        logger.info(f"Password set for user: {user_id}")
        return {"message": "Password set successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting password: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_power_user),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Reset user password and generate a temporary one"""
    try:
        # Get user from MongoDB
        user_data = await user_repo.get_by_id(user_id)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        email = user_data['email']

        # Generate temporary password
        temp_password = generate_temporary_password()

        # Hash password for local storage
        password_hash = password_service.hash_password(temp_password)

        # Update MongoDB with hashed password
        await user_repo.set_password_hash(user_id, password_hash)

        # Also reset in Cognito (optional, for backward compatibility)
        try:
            cognito_service.reset_password(email, temp_password)
        except Exception as e:
            logger.warning(f"Cognito password reset failed for {email}: {str(e)}")

        logger.info(f"Password reset for user: {user_id}")
        return {
            "message": "Password reset successfully",
            "temporary_password": temp_password,
            "note": "User should change this password on first login"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting password: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync-from-cognito")
async def sync_users_from_cognito(
    current_user: Dict[str, Any] = Depends(require_admin),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Sync users from Cognito to MongoDB (for migration)"""
    try:
        # Get all users from Cognito
        cognito_users = cognito_service.list_users(limit=60)

        synced_count = 0
        skipped_count = 0
        errors = []

        for cognito_user in cognito_users:
            try:
                email = cognito_user.get('email')
                cognito_sub = cognito_user.get('cognito_sub')

                if not email or not cognito_sub:
                    continue

                # Check if user exists in MongoDB by cognito_sub
                existing = await user_repo.get_by_cognito_sub(cognito_sub)
                if existing:
                    skipped_count += 1
                    continue

                # Also check by email
                existing_by_email = await user_repo.get_by_email(email)
                if existing_by_email:
                    # Link cognito_sub to existing user
                    await user_repo.link_cognito(existing_by_email.get('user_id'), cognito_sub)
                    skipped_count += 1
                    continue

                # Create user in MongoDB
                attributes = cognito_user.get('attributes', {})
                user_data = {
                    "first_name": attributes.get('given_name', ''),
                    "last_name": attributes.get('family_name', ''),
                    "role": attributes.get('custom:role', 'standardUser'),
                    "title": attributes.get('custom:title', ''),
                    "group": attributes.get('custom:group', ''),
                    "department": attributes.get('custom:department', ''),
                    "organization": attributes.get('custom:organization', 'default'),
                    "status": "active" if cognito_user.get('status') == 'CONFIRMED' else "inactive",
                    "password_set": True,
                    "cognito_sub": cognito_sub,
                    "in_cognito": True,
                }

                await user_repo.create(email=email, data=user_data)
                synced_count += 1
                logger.info(f"Synced user from Cognito: {email}")

            except Exception as e:
                errors.append(f"{email}: {str(e)}")
                logger.error(f"Failed to sync user {email}: {str(e)}")

        return {
            "message": "Cognito sync completed",
            "synced": synced_count,
            "skipped": skipped_count,
            "errors": errors if errors else None
        }

    except Exception as e:
        logger.error(f"Error syncing from Cognito: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
