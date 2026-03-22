"""User-related endpoints."""

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: CurrentUser) -> UserResponse:
    """Return the currently authenticated user's profile."""
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        image=user.image,
        tier=user.tier,
    )
