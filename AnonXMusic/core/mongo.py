from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from typing import Optional

import config
from ..logging import LOGGER

MONGO_URI = "mongodb+srv://Billa20:uAJc5rGK18FzOiJz@cluster0.ul24roe.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "MusicBot"

try:
    if config.MONGO_DB_URI is None:
        LOGGER(__name__).warning(
            "No MongoDB URL found in config. Using default MusicBot database."
        )
        mongo_async = AsyncIOMotorClient(MONGO_URI)
        mongo_sync = MongoClient(MONGO_URI)
        mongodb = mongo_async[DB_NAME]
        pymongodb = mongo_sync[DB_NAME]
    else:
        LOGGER(__name__).info(
            "Using MusicBot database with provided MONGO_DB_URI for consistency."
        )
        mongo_async = AsyncIOMotorClient(MONGO_URI)  
        mongo_sync = MongoClient(MONGO_URI)
        mongodb = mongo_async[DB_NAME]
        pymongodb = mongo_sync[DB_NAME]
except Exception as e:
    LOGGER(__name__).error(f"Failed to initialize MongoDB clients: {e}")
    raise RuntimeError(f"MongoDB initialization failed: {str(e)}") from e

class Database:
    def __init__(self):
        self.mongo_async = mongo_async
        self.mongo_sync = mongo_sync
        self.db_async = mongodb
        self.db_sync = pymongodb
        # Collections
        self.chat_db = self.db_async["chats"]
        self.users_db = self.db_async["users"]
        self.bot_db = self.db_async["bot"]

    async def ping(self) -> bool:
        """Test database connection."""
        try:
            await self.db_async.command("ping")
            LOGGER(__name__).info("Database connection successful.")
            return True
        except ConnectionFailure as e:
            LOGGER(__name__).error(f"Database connection failed: {e}")
            return False
        except Exception as e:
            LOGGER(__name__).error(f"Database ping failed: {e}")
            return False

    async def verify_data(self) -> dict:
        """Verify that data is accessible from all collections."""
        try:
            stats = {
                "chats_count": await self.chat_db.count_documents({}),
                "users_count": await self.users_db.count_documents({}),
                "bot_count": await self.bot_db.count_documents({})
            }
            LOGGER(__name__).info(f"Database stats: {stats}")
            return stats
        except Exception as e:
            LOGGER(__name__).error(f"Failed to verify data: {e}")
            return {}

    async def get_chat(self, chat_id: int) -> Optional[dict]:
        """Retrieve a chat document by ID."""
        try:
            chat = await self.chat_db.find_one({"_id": chat_id})
            return chat
        except Exception as e:
            LOGGER(__name__).warning(f"Error getting chat {chat_id}: {e}")
            return None

    async def add_chat(self, chat_id: int) -> None:
        """Add a new chat if it doesn't exist."""
        if await self.get_chat(chat_id) is None:
            try:
                await self.chat_db.update_one(
                    {"_id": chat_id}, {"$setOnInsert": {}}, upsert=True
                )
                LOGGER(__name__).info(f"Added chat: {chat_id}")
            except Exception as e:
                LOGGER(__name__).error(f"Error adding chat {chat_id}: {e}")

    async def close(self) -> None:
        """Close MongoDB connections."""
        try:
            self.mongo_async.close()
            self.mongo_sync.close()
            LOGGER(__name__).info("Database connections closed.")
        except Exception as e:
            LOGGER(__name__).error(f"Error closing database connections: {e}")

db = Database()
