"""API v1 router — aggregates all route modules."""

from fastapi import APIRouter

from app.api.v1.routes import admin, auth, chat, progress, resume, roadmaps, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roadmaps.router)
api_router.include_router(progress.router)
api_router.include_router(chat.router)
api_router.include_router(admin.router)
api_router.include_router(resume.router)
