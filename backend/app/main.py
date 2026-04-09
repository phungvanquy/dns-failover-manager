import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import engine, Base
from app.health_checker import health_check_loop, cleanup_loop
from app.routers import domains

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    # Start health check background worker
    task = asyncio.create_task(health_check_loop())
    logger.info("Health check worker scheduled")

    # Start cleanup background worker
    cleanup_task = asyncio.create_task(cleanup_loop())
    logger.info("Cleanup worker scheduled")

    yield

    # Shutdown
    task.cancel()
    cleanup_task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="DNS Failover Manager", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(domains.router, prefix="/api")


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Resource already exists or constraint violated"})


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
