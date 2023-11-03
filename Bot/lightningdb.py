'''Contains the code for the local MongoDB functionality to replace cached lightningLogging'''
import motor.motor_asyncio
import pymongo
from pymongo import errors
from discord import Message
from discord.utils import utcnow
from typing import List
import datetime

# mongo = motor.motor_asyncio.AsyncIOMotorClient()

database:motor.motor_asyncio.AsyncIOMotorDatabase = None
servers:motor.motor_asyncio.AsyncIOMotorCollection = None
users:motor.motor_asyncio.AsyncIOMotorCollection = None

def initialize():
    global mongo
    global database
    global servers
    global users
    mongo = motor.motor_asyncio.AsyncIOMotorClient()
    database = mongo.database
    servers = database.servers
    users = database.users

async def wipe():
    '''clears the database'''
    await servers.drop()
    await users.drop()
    # await mongo.drop_database(database)

async def post_server(data: dict):
    '''adds a server to the database'''
    data['_id'] = data['server_id']
    return await servers.insert_one(data)

def prepare_post_server(data: dict):
    '''returns the update operation to add a server to the database'''
    data['_id'] = data['server_id']
    return pymongo.InsertOne(data)

async def post_servers(operations: list):
    '''bulk write'''
    return await servers.bulk_write(operations, ordered=False)

async def get_server(server_id: int, return_value=None):
    '''gets a server from the database'''
    return await servers.find_one({'_id': server_id}) or return_value

async def patch_server(server_id: int, data: dict):
    '''updates a server in the database'''
    data.pop('_id', None)
    return await servers.update_one({'_id': server_id}, {'$set': data}, upsert=True)

async def get_member(server_id: int, member_id: int):
    '''gets a member from the the designated server'''
    return await servers.find_one({'_id': server_id, 'members.$.id': member_id})

async def post_user(data: dict):
    '''adds a user to the database'''
    data['_id'] = data['user_id']
    return await users.insert_one(data)

def prepare_post_user(data: dict):
    '''returns the update operation to add a user to the database'''
    data['_id'] = data['user_id']
    return pymongo.InsertOne(data)

async def post_users(operations: list):
    '''bulk write'''
    return await users.bulk_write(operations)

async def get_user(user_id: int):
    '''gets a user from the database'''
    return await users.find_one({'_id': user_id})

async def patch_user(user_id: int, data: dict):
    '''updates a user in the database'''
    data.pop('_id', None)
    return await users.update_one({'_id': user_id}, {'$set': data}, upsert=True)

def message_data(message: Message, index: int = 0):
    return {
        '_id': message.id,
        f'author{index}': message.author.id,
        f'timestamp{index}': message.created_at.isoformat() if index == 0 else utcnow().isoformat(),
        f'content{index}':
            '<Hidden due to channel being NSFW>' if message.channel.is_nsfw()
            else message.content if message.content
            else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f':{message.attachments[0].filename}'}>"if len(message.attachments) > 0
            else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0
            else '<No content>'
    }

async def post_message(message: Message):
    if message.channel.id in (534439214289256478, 910598159963652126): return
    data = message_data(message)
    insertion = await database[str(message.channel.id)].insert_one(data)
    try:
        if 'author0' not in list((await database[str(message.channel.id)].index_information()).keys()):
            await database[str(message.channel.id)].create_index('author0')
    except: 
        await database[str(message.channel.id)].create_index('author0')
    return insertion


async def post_messages(messages: List[Message]):
    if message.channel.id in (534439214289256478, 910598159963652126): return
    operations = []
    for message in messages:
        data = message_data(message)
        operations.append(pymongo.InsertOne(data))
    return await database[str(message.channel.id)].bulk_write(operations)

async def get_message(channel_id: int, message_id: int):
    return await database[str(channel_id)].find_one({'_id': message_id})

async def get_channel_messages(channel_id: int):
    return await database[str(channel_id)].find().to_list(None)

async def get_messages_by_author(author_id: int, channel_ids: List[int] = []):
    results = []
    if channel_ids:
        for channel_id in channel_ids:
            results += await database[str(channel_id)].find({'author0': author_id}).to_list(None)
    else:
        for collection in await database.list_collection_names():
            if collection not in ('servers', 'users'):
                results += await database[collection].find({'author0': author_id}).to_list(None)
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

async def patch_message(message: Message):
    if message.channel.id in (534439214289256478, 910598159963652126): return
    existing_message = await get_message(message.channel.id, message.id)
    index = int(list(existing_message.keys())[-1][-1]) + 1
    data = message_data(message, index=index)
    data.pop('_id')
    return await database[str(message.channel.id)].update_one({'_id': message.id}, {'$set': data})

async def delete_message(channel_id: int, message_id: int):
    return await database[str(channel_id)].delete_one({'_id': message_id})

async def delete_channel(channel_id: int):
    return await database[str(channel_id)].drop()
