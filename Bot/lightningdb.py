"""Contains the code for the local MongoDB functionality to replace cached lightningLogging"""

import datetime
import logging
from typing import List

import motor.motor_asyncio
import pymongo
from bson.codec_options import CodecOptions
from discord import Message
from discord.utils import utcnow
from motor.motor_asyncio import AsyncIOMotorClient

import models

logger = logging.getLogger('discord')

# mongo = motor.motor_asyncio.AsyncIOMotorClient()

database: motor.motor_asyncio.AsyncIOMotorDatabase = None
servers: motor.motor_asyncio.AsyncIOMotorCollection = None
users: motor.motor_asyncio.AsyncIOMotorCollection = None


def initialize():
    global mongo
    global database
    global servers
    global users
    mongo = AsyncIOMotorClient()
    database = mongo.database.with_options(codec_options=CodecOptions(tz_aware=True))
    servers = database.servers
    users = database.users


async def wipe():
    """clears the database"""
    await servers.drop()
    await users.drop()
    # await mongo.drop_database(database)


async def post_server(data: dict):
    """adds a server to the database"""
    data['_id'] = data['server_id']
    return await servers.insert_one(data)


def prepare_post_server(data: dict):
    """returns the update operation to add a server to the database"""
    data['_id'] = data['server_id']
    return pymongo.InsertOne(data)


async def post_servers(operations: list):
    """bulk write"""
    return await servers.bulk_write(operations, ordered=False)


async def get_server(server_id: int, return_value=None):
    """gets a server from the database"""
    return await servers.find_one({'_id': server_id}) or return_value


async def patch_server(server_id: int, data: dict):
    """updates a server in the database"""
    data.pop('_id', None)
    return await servers.update_one({'_id': server_id}, {'$set': data}, upsert=True)


async def get_member(server_id: int, member_id: int):
    """gets a member from the the designated server"""
    return await servers.find_one({'_id': server_id, 'members.$.id': member_id})


async def post_user(data: dict):
    """adds a user to the database"""
    data['_id'] = data['user_id']
    return await users.insert_one(data)


def prepare_post_user(data: dict):
    """returns the update operation to add a user to the database"""
    data['_id'] = data['user_id']
    return pymongo.InsertOne(data)


async def post_users(operations: list):
    """bulk write"""
    return await users.bulk_write(operations)


async def get_user(user_id: int):
    """gets a user from the database"""
    return await users.find_one({'_id': user_id})


async def patch_user(user_id: int, data: dict):
    """updates a user in the database"""
    data.pop('_id', None)
    return await users.update_one({'_id': user_id}, {'$set': data}, upsert=True)


def message_data(message: Message, index: int = 0):
    return {
        '_id': message.id,
        f'author{index}': message.author.id,
        f'timestamp{index}': message.created_at.isoformat() if index == 0 else utcnow().isoformat(),
        f'content{index}': '<Hidden due to channel being NSFW>'
        if message.channel.is_nsfw()
        else message.content
        if message.content
        else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>"
        if len(message.attachments) > 0
        else f'<{len(message.embeds)} embed>'
        if len(message.embeds) > 0
        else '<No content>',
    }


async def is_channel_empty(channel_id: int):
    """checks if a channel is empty"""
    return database.get_collection(str(channel_id)) is None or await database[str(channel_id)].count_documents({}) == 0


# async def post_message(message: Message):
#     # if message.channel.id in (534439214289256478, 910598159963652126):
#     #     return
#     data = message_data(message)
#     insertion = await database[str(message.channel.id)].insert_one(data)
#     try:
#         if 'author0' not in list((await database[str(message.channel.id)].index_information()).keys()):
#             await database[str(message.channel.id)].create_index('author0')
#     except:
#         await database[str(message.channel.id)].create_index('author0')
#     return insertion


async def post_message_2024(message_data: models.MessageIndex):
    # if message.channel.id in (534439214289256478, 910598159963652126):
    #     return

    message_dict = message_data.model_dump()
    # Pydantic doesn't support parameters in models that start with underscores.
    # Manually shift the id field to the MongoDB id field here
    message_dict['_id'] = message_dict['id']
    message_dict.pop('id')
    insertion = await database[str(message_data.channel_id)].insert_one(message_dict)
    author_index = pymongo.IndexModel([('author_id')])
    channel_index = pymongo.IndexModel([('channel_id')])
    try:
        if 'author_id' not in list((await database[str(message_data.channel_id)].index_information()).keys()):
            await database[str(message_data.channel_id)].create_indexes([author_index, channel_index])
    except Exception:
        logger.error('Encountered error checking for author index keys; shifting to creating them anyway', exc_info=True)
        await database[str(message_data.channel_id)].create_indexes([author_index, channel_index])
    return insertion


# async def post_messages(messages: List[Message]):
#     if messages[0].channel.id in (534439214289256478, 910598159963652126):
#         return
#     operations = []
#     for message in messages:
#         data = message_data(message)
#         operations.append(pymongo.InsertOne(data))
#     return await database[str(message.channel.id)].bulk_write(operations)


# good for 2025
async def get_message(channel_id: int, message_id: int):
    return await database[str(channel_id)].find_one({'_id': message_id})


# good for 2025
async def get_channel_messages(channel_id: int):
    return await database[str(channel_id)].find_many({}).to_list(None)


async def get_messages_by_author(author_id: int, channel_ids: List[int] = []):
    results = []
    if channel_ids:
        for channel_id in channel_ids:
            results += await database[str(channel_id)].find({'author_id': author_id}).to_list(None)
    else:
        for collection in await database.list_collection_names():
            if collection not in ('servers', 'users'):
                results += await database[collection].find({'author_id': author_id}).to_list(None)
    return results


async def get_messages_by_timestamp(after: datetime.datetime = None, before: datetime.datetime = None, channel_ids: List[int] = []):
    results = []
    if channel_ids:
        for channel_id in channel_ids:
            results += await database[str(channel_id)].find({'timestamp0': {'$gte': after, '$lte': before}}).to_list(None)
    else:
        for collection in await database.list_collection_names():
            if collection not in ('servers', 'users'):
                results += await database[collection].find({'timestamp0': {'$gte': after, '$lte': before}}).to_list(None)
    return results


# async def patch_message(message: Message):
#     if message.channel.id in (534439214289256478, 910598159963652126):
#         return
#     existing_message = await get_message(message.channel.id, message.id)
#     if not existing_message:
#         return
#     index = int(list(existing_message.keys())[-1][-1]) + 1
#     data = message_data(message, index=index)
#     data.pop('_id')
#     return await database[str(message.channel.id)].update_one({'_id': message.id}, {'$set': data})


async def patch_message_2024(channel_id: int, message_id: int, new_edition: models.MessageEdition):
    return await database[str(channel_id)].update_one({'_id': message_id}, {'$push': {'editions': new_edition.model_dump()}})


async def delete_message(channel_id: int, message_id: int):
    return await database[str(channel_id)].delete_one({'_id': message_id})


async def delete_channel(channel_id: int):
    logger.info(f'Dropping channel by id {channel_id}')
    return await database[str(channel_id)].drop()


async def delete_all_channels():
    for collection in await database.list_collection_names():
        if collection not in ('servers', 'users'):
            await database[collection].drop()
            logger.info(f'Dropped collection {collection}')
