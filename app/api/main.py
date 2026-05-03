"""API router composition."""

from fastapi import APIRouter

from app.api.routes import aiops, chat, file, native_agent

api_router = APIRouter()
api_router.include_router(chat.router, tags=["Chat"])
api_router.include_router(file.router, tags=["Files"])
api_router.include_router(aiops.router, tags=["AIOps"])
api_router.include_router(native_agent.router, tags=["NativeAgent"])
