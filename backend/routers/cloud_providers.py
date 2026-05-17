"""Cloud LLM Provider onboarding REST API (Phase 4 PR 4.5).

Endpoints
---------
- GET    /api/v1/cloud-providers                — list (sensitive keys masked)
- POST   /api/v1/cloud-providers                — create or upsert
- GET    /api/v1/cloud-providers/{provider_id}  — fetch one (masked)
- PUT    /api/v1/cloud-providers/{provider_id}  — update
- DELETE /api/v1/cloud-providers/{provider_id}  — remove
- POST   /api/v1/cloud-providers/test           — probe an arbitrary config (no save)
- POST   /api/v1/cloud-providers/{provider_id}/test — probe a saved provider
"""

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from database import get_database
from models.cloud_provider_models import (
    CloudProviderCreate,
    CloudProviderListResponse,
    CloudProviderResponse,
    CloudProviderTestRequest,
    CloudProviderTestResponse,
    CloudProviderUpdate,
)
from services.cloud_provider_service import CloudProviderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cloud-providers", tags=["cloud-providers"])


def _svc(db=Depends(get_database)) -> CloudProviderService:
    return CloudProviderService(db)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=CloudProviderListResponse)
async def list_providers(
    svc: CloudProviderService = Depends(_svc),
) -> CloudProviderListResponse:
    return await svc.list_with_masked_keys()


@router.post(
    "",
    response_model=CloudProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider(
    payload: CloudProviderCreate,
    svc: CloudProviderService = Depends(_svc),
) -> CloudProviderResponse:
    return await svc.create_or_update(payload)


@router.get("/{provider_id}", response_model=CloudProviderResponse)
async def get_provider(
    provider_id: str,
    svc: CloudProviderService = Depends(_svc),
) -> CloudProviderResponse:
    return await svc.get(provider_id)


@router.put("/{provider_id}", response_model=CloudProviderResponse)
async def update_provider(
    provider_id: str,
    payload: CloudProviderUpdate,
    svc: CloudProviderService = Depends(_svc),
) -> CloudProviderResponse:
    return await svc.update(provider_id, payload)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: str,
    svc: CloudProviderService = Depends(_svc),
) -> Response:
    await svc.delete(provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Test connection
# ---------------------------------------------------------------------------

@router.post("/test", response_model=CloudProviderTestResponse)
async def test_arbitrary(
    payload: CloudProviderTestRequest,
    svc: CloudProviderService = Depends(_svc),
) -> CloudProviderTestResponse:
    return await svc.test_connection(payload.provider_type.value, payload.config)


@router.post("/{provider_id}/test", response_model=CloudProviderTestResponse)
async def test_existing(
    provider_id: str,
    svc: CloudProviderService = Depends(_svc),
) -> CloudProviderTestResponse:
    return await svc.test_existing(provider_id)
