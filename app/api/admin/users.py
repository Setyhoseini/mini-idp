"""Admin user-management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.admin.schemas import (
    CreateUserRequest,
    EffectiveScopesResponse,
    UserResponse,
)
from app.api.deps import get_current_admin
from app.db import get_db
from app.services import realm_service, user_service
from app.services.authorization import compute_effective_scopes

router = APIRouter(prefix="/admin/v1", tags=["admin"])


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _claims: dict = Depends(get_current_admin),
) -> UserResponse:
    realm = realm_service.get_single_realm(db)
    user = user_service.create_user(
        db,
        realm_id=realm.id,
        username=payload.username,
        password=payload.password,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    return UserResponse.model_validate(user)


@router.get(
    "/users/{user_id}/effective-scopes",
    response_model=EffectiveScopesResponse,
)
def get_effective_scopes(
    user_id: int,
    db: Session = Depends(get_db),
    _claims: dict = Depends(get_current_admin),
) -> EffectiveScopesResponse:
    user = user_service.get_user(db, user_id)
    scopes = sorted(compute_effective_scopes(db, user_id))
    return EffectiveScopesResponse(user_id=user.id, username=user.username, scopes=scopes)