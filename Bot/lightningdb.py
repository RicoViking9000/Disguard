'''Contains the code for the local MongoDB functionality to replace cached lightningLogging'''
import motor.motor_asyncio
import pymongo

mongo = motor.motor_asyncio.AsyncIOMotorClient()

database:motor.motor_asyncio.AsyncIOMotorDatabase = mongo.database
servers:motor.motor_asyncio.AsyncIOMotorCollection = database.servers
users:motor.motor_asyncio.AsyncIOMotorCollection = database.users

async def wipe():
    '''clears the database'''
    await mongo.drop_database('database')

async def post_server(data: dict):
    '''adds a server to the database'''
    data['_id'] = data['server_id']
    return await servers.insert_one(data)

def prepare_post_server(data: dict):
    '''returns the update operation to add a server to the database'''
    data['_id'] = data['server_id']
    return pymongo.InsertOne(data)

async def get_server(server_id: int):
    '''gets a server from the database'''
    return await servers.find_one({'_id': server_id})

async def patch_server(server_id: int, data: dict):
    '''updates a server in the database'''
    data.pop('_id')
    return await servers.update_one({'_id': server_id}, {'$set': data})

async def post_user(data: dict):
    '''adds a user to the database'''
    data['_id'] = data['user_id']
    return await users.insert_one(data)

def prepare_post_user(data: dict):
    '''returns the update operation to add a user to the database'''
    data['_id'] = data['user_id']
    return pymongo.InsertOne(data)

async def get_user(user_id: int):
    '''gets a user from the database'''
    return await users.find_one({'_id': user_id})

async def patch_user(user_id: int, data: dict):
    '''updates a user in the database'''
    data.pop('_id')
    return await users.update_one({'_id': user_id}, {'$set': data})
