"""v1 API router — aggregates all v1 endpoint routers."""

from fastapi import APIRouter

from app.api.v1.analysis import router as analysis_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(users_router)
router.include_router(conversations_router)
router.include_router(chat_router)
router.include_router(analysis_router)
