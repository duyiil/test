from fastapi import APIRouter

from app.api.v1 import admin, auth, dashboard, github, health, platform, projects, testing

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(testing.router, tags=["testing"])
api_router.include_router(platform.router, tags=["platform"])
api_router.include_router(github.router, tags=["github"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
