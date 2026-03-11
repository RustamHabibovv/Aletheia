"""v1 API router — aggregates all v1 endpoint routers."""

from fastapi import APIRouter

from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(users_router)
