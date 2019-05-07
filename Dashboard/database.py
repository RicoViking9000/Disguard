'''This file manages database operations after data is saved in the web dashboard'''
import pymongo
import oauth
import dns
from flask import request

mongo = pymongo.MongoClient(oauth.mongo()) #Database connection URL in another file so you peeps don't go editing the database ;)
db = mongo.disguard
servers = db.servers

def UpdateMemberWarnings(server: int, warnings: int):
    '''Web dashboard equivalent of ..bot/dashboard's version. More calculations are done here
    server: ID of server
    warnings: dashboard's new warnings variable'''
    serv = servers.find_one({"server_id": server})
    members = serv.get("members")
    for member in members:
        newWarnings = warnings
        if member.get("warnings") == 0:
            newWarnings = 0
        elif member.get("warnings") != serv.get("antispam").get("warn"):
            newWarnings = serv.get("antispam").get("warn") - member.get("warnings")
        servers.update_one({"server_id": server, "members.id": member.get("id")}, {"$set": {"members.$.warnings": newWarnings}})
