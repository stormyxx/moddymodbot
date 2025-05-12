import os
from typing import TypeVar, Union, List, Optional

import attrs
import motor.motor_asyncio as motor
from pymongo.server_api import ServerApi

from model import Player

Item = TypeVar("Item")

SUPPORTED_CLASSES = {"player": Player}


def get_db() -> motor.AsyncIOMotorDatabase:
    uri = f"mongodb+srv://stormyskies:{os.environ['DB_PASSWORD']}@stabbystabbot.ibtm0.mongodb.net/?retryWrites=true&w=majority&appName=stabbystabbot"
    client = motor.AsyncIOMotorClient(uri, server_api=ServerApi("1"))
    db = client["game"]
    return db


class DBClient:
    def __init__(self, user: str = "stormyskies", password: str = os.environ['DB_PASSWORD']):
        uri = f"mongodb+srv://{user}:{password}@stabbystabbot.ibtm0.mongodb.net/?retryWrites=true&w=majority&appName=stabbystabbot"
        self.client = motor.AsyncIOMotorClient(uri, server_api=ServerApi("1"))
        self.db = self.client["game"]

    async def list(self, n): ...

    async def select(self, table: str, query: dict, **query_kwargs) -> Optional[Item]:
        query = query | query_kwargs
        item = await self.db[table].find_one(query)
        if not item:
            return None
        if "_class" in item:
            return SUPPORTED_CLASSES[item["_class"]].from_dict({k: v for k, v in item.items() if not k.startswith("_")})
        return item

    async def insert(self, table: str, items: Union[List[Item], Item], _id: int = None):
        if not isinstance(items, list):
            items = [items]
        processed_items = []
        for item in items:
            if attrs.has(item.__class__):
                d = attrs.asdict(item)
                d["_class"] = item.__class__.__name__
            else:
                d = item
            if _id:
                d["_id"] = _id
            processed_items.append(d)
        await self.db[table].insert_many(processed_items)

    async def upsert(self, table: str, item: Item, _id: int = None, **query_kwargs):
        if attrs.has(item.__class__):
            d = attrs.asdict(item)
            d["_class"] = item.__class__.__name__
        else:
            d = item
        if _id:
            d["_id"] = _id
        await self.db[table].find_one_and_replace(query_kwargs or {"_id": _id}, replacement=d, upsert=True)


if __name__ == "__main__":
    c = DBClient()
