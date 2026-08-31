from fastapi import APIRouter

from app.api.routers import auth, jobs, system

api_router = APIRouter()
api_router.include_router(auth.router, tags=["Authentication & WebSocket"])
api_router.include_router(jobs.router, tags=["Enterprise Automation API"])
api_router.include_router(system.router, tags=["System & Infrastructure"])
