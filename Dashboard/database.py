'''This file manages database operations after data is saved in the web dashboard'''
import pymongo
import motor.motor_asyncio
import oauth
import dns
from flask import request

mongo = pymongo.MongoClient(oauth.mongo()) #Database connection URL in another file so you peeps don't go editing the database ;)
db = mongo.disguard
servers = db.servers

def UpdateMemberWarnings(server: int, warnings: int):
    '''Web dashboard equivalent of ../bot/dashboard's version. More calculations are done here
    server: ID of server
    warnings: dashboard's new warnings variable'''
    serv = servers.find_one({'server_id': server})
    members = serv.get('members')
    update_operations = []
    for member_id, member_data in members.items():
        newWarnings = warnings
        if member_data.get('warnings', 3) == 0: newWarnings = 0
        elif member_data.get('warnings') != serv.get('antispam').get('warn'):
            newWarnings = serv.get('antispam').get('warn') - member_data.get('warnings')
        update_operations.append(pymongo.UpdateOne({'server_id': server}, {'$set': {f'members.{member_id}': newWarnings}}))
    servers.bulk_write(update_operations)
