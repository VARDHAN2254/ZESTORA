from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cart.router import router as cart_router
from app.catalog.router import router as catalog_router
from app.checkout.router import router as checkout_router
from app.core.config import settings
from app.core.database import close_db_engine
from app.identity.router import router as auth_router
from app.orders.router import router as orders_router
from app.restaurant_orders.router import router as restaurant_orders_router
from app.restaurants.router import router as restaurants_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Startup: Initializes application without forcing an upfront database connection.
    Shutdown: Safely disposes of database connection pools.
    """
    yield
    await close_db_engine()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="ZESTORA Food Delivery Platform API - Minimal Foundation Skeleton",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint verifying API is running."""
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint used by orchestrators and monitoring."""
    return {
        "status": "healthy",
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.API_ENV,
    }


# Feature routers
app.include_router(auth_router)
app.include_router(restaurants_router)
app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(checkout_router)
app.include_router(orders_router)
app.include_router(restaurant_orders_router)
