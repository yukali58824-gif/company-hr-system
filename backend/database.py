import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is not configured. Create a .env file from .env.example "
                "and set DATABASE_URL to your PostgreSQL connection string."
            )
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
        )
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
