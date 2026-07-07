"""
database.py — MongoDB connection manager using Motor.

Provides an asynchronous connection to MongoDB and a dependency
for routing database injection in FastAPI.
"""

from collections.abc import AsyncGenerator
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

# Global client singleton
_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """Get or initialize the global Motor MongoDB client."""
    global _client
    if _client is None:
        logger.info("Initializing MongoDB client with URL: %s", settings.mongodb_url)
        # dnspython must be installed for +srv connection strings
        _client = AsyncIOMotorClient(settings.mongodb_url)
    return _client


async def get_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Dependency that yields the async Motor database instance.

    Yields
    ------
    AsyncIOMotorDatabase
        Motor database database connection.
    """
    cli = get_client()
    yield cli[settings.mongodb_db_name]


def close_db() -> None:
    """Close the global MongoDB client connection."""
    global _client
    if _client is not None:
        logger.info("Closing MongoDB client connection.")
        _client.close()
        _client = None
