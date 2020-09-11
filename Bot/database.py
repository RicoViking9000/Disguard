'''This file creates, verifies, and manages database entries as necessary during Disguard's operation
   This file also houses various useful methods that can be used across multiple files'''
import motor.motor_asyncio
import dns
import secure
import discord
import profanityfilter
import datetime
import asyncio
import faulthandler
import copy
import os
import json
import pymongo
from discord.ext import commands

#mongo = pymongo.MongoClient(secure.mongo()) #Database connection URL stored in another file for security reasons
mongo = motor.motor_asyncio.AsyncIOMotorClient(secure.mongo())
db = None
servers = None
users = None
disguard = None

def getDatabase(): return db

verifications = {}
defaultAgeKickDM = ''''You have been kicked from **{}** temporarily due to their antispam configuration: Your account must be {} days old for you to join the server. You can rejoin the server **{} {}**.'.format(member.guild.name,
                    ageKick, canRejoin.strftime(formatter), timezone)'''

class LogModule(object):
    '''Used for consistent controlling of logging'''
    def __init__(self, name, description, embed=True, audit=True, enabled=True, summarize=0, channelID=None, embedColor=None, advanced=False):
        self.name = name #name of module
        self.description = description #description of module
        self.embed = embed #send logs in embed form? [ENABLED BY DEFAULT, CUSTOMIZABLE LATER]
        self.read = audit #read audit logs to post who did the action (such as who created the channel)? [ENABLED BY DEFAULT, CUSTOMIZABLE LATER]
        self.enabled = enabled #is this module enabled?
        self.summarize = summarize #summarize logging (overwrite)
        self.channel = channelID #which channel is this sent to?
        self.color = embedColor #custom color used for embed [LATER]
        self.advanced = advanced #enable advanced mode? [LATER]
        self.lastUpdate = datetime.datetime.utcnow()
    def update(self, entry): #Shorten database code line - input data from database, return updated object, updated object goes into database
        self.read = entry.get('read')
        self.enabled = entry.get('enabled')
        self.summarize = entry.get('summarize')
        self.channel = entry.get('channel')
        return self

def Initialize(token):
    '''Configure the database based on if bot is Disguard or Disguard Beta'''
    global db
    global servers
    global users
    global disguard
    if token == secure.token():
        db = mongo.disguard
    elif token == secure.beta():
        db = mongo.disguard_beta
    servers = db.servers
    users = db.users
    disguard = db.disguard


'''Checking events'''
async def Verification(b: commands.Bot):
    '''Longest operation. Checks entire usable database *twice*, and verifies it's as it should be, creating entries as necessary'''
    await VerifyServers(b)
    await VerifyUsers(b)
    #await VerifyUsers(b)

async def VerifyServers(b: commands.Bot, newOnly = False):
    '''Ensures all servers have database entries; adding and removing as necessary'''
    '''First: Index all bot servers, and verify them'''
    await asyncio.gather(*[VerifyServer(s, b) for s in b.guilds])

async def VerifyServer(s: discord.Guild, b: commands.Bot, newOnly = False):
    '''Ensures that an individual server has a database entry, and checks all its variables'''
    '''First: Update operation verifies that server's variables are standard and up to date; no channels that no longer exist, for example, in the database'''
    print('Verifying server: {} - {}'.format(s.name, s.id))
    #started = datetime.datetime.now()
    serv = await servers.find_one({"server_id": s.id})
    if b.get_guild(s.id) is None: 
        await servers.delete_one({'server_id': s.id})
        return
    spam = None
    log = None
    if serv is not None:
        if newOnly: return
        spam = serv.get("antispam") #antispam object from database
        log = serv.get("cyberlog") #cyberlog object from database
    #membIDs = [memb.id for memb in s.members]
    serverChannels = []
    for c in [channel for channel in s.by_category() if not channel[0] and type(channel) is discord.TextChannel]:
        if len(serverChannels) == 0: serverChannels.append({'name': '-----NO CATEGORY-----', 'id': 0})
        serverChannels.append({'name': c.name, 'id': c.id})
    for c in s.categories:
        serverChannels.append({'name': f'-----{c.name.upper()}-----', 'id': c.id})
        for channel in c.text_channels: serverChannels.append({'name': channel.name, 'id': channel.id})
    if not serv: 
        await servers.update_one({'server_id': s.id}, {"$set": { #add entry for new servers
        "name": s.name,
        "prefix": "." if serv is None or serv.get('prefix') is None else serv.get('prefix'),
        "thumbnail": str(s.icon_url),
        'offset': -4 if serv is None or serv.get('offset') is None else serv.get('offset'), #Distance from UTC time
        'tzname': 'EST' if serv is None or serv.get('tzname') is None else serv.get('tzname'), #Custom timezone name (EST by default)
        'jumpContext': True if serv is None or serv.get('jumpContext') is None else serv.get('jumpContext'), #Whether to provide context for posted message jump URL links
        'birthday': 0 if serv is None or serv.get('birthday') is None else serv.get('birthday'), #Channel to send birthday announcements to
        'birthdate': datetime.datetime(2020, 1, 1, 12 + (-5 if serv is None or serv.get('offset') is None else serv.get('offset'))) if serv is None or serv.get('birthdate') is None else serv.get('birthdate'), #When to send bday announcements
        'birthdayMode': 2 if serv is None or serv.get('birthdayMode') is None else serv.get('birthdayMode'), #How to respond to automatic messages
        "channels": serverChannels,
        'server_id': s.id,
        "roles": [{"name": role.name, "id": role.id} for role in iter(s.roles) if not role.managed and not role.is_default()],
        'summaries': [] if serv is None or serv.get('summaries') is None else serv.get('summaries'),
        "antispam": { #This part is complicated. So if this variable (antispam) doesn't exist, default values are assigned, otherwise, keep the current ones
            "enabled": False if serv is None or spam.get('enabled') is None else spam.get('enabled'), #Is the general antispam module enabled?
            "whisper": False if serv is None or spam.get('whisper') is None else spam.get('whisper'), #when a member is flagged, whisper a notice to them in DM instead of current channel?
            "log": [None, None] if serv is None or spam.get('log') is None or not b.get_channel(spam.get('log')[1]) else spam.get('log'), #display detailed message to server's log channel? if None, logging is disabled, else, Name | ID of log channel
            "warn": 3 if serv is None or spam.get('warn') is None else spam.get('warn'), #number of warnings before the <action> is imposed
            "delete": True if serv is None or spam.get('delete') is None else spam.get('delete'), #if a message is flagged, delete it?
            "muteTime": 300 if serv is None or spam.get('muteTime') is None else spam.get('muteTime'), #if action is <1> or <4>, this is the length, in seconds, to keep that member with the role
            "action": 1 if serv is None or spam.get('action') is None else spam.get('action'), #action imposed upon spam detection: 0=nothing, 1=automute, 2=kick, 3=ban, 4=custom role
            "customRoleID": None if serv is None or spam.get('customRoleID') is None or not b.get_guild(s.id).get_role(spam.get('customRoleID')) else spam.get('customRoleID'), #if action is 4 (custom role), this is the ID of that role
            "congruent": [4, 7, 300] if serv is None or spam.get('congruent') is None else spam.get('congruent'), #flag if [0]/[1] of user's last messages sent in [2] seconds contain equivalent content
            "profanityThreshold": 0 if serv is None or spam.get('profanityThreshold') is None else spam.get('profanityThreshold'), #Profanity to tolerate - 0=nothing tolerated, int=# of words>=value, double=% of words/whole message
            "emoji": 0 if serv is None or spam.get('emoji') is None else spam.get('emoji'), #Emoji to tolerate - 0=no filter, int=value, double=percentage
            "mentions": 3 if serv is None or spam.get('mentions') is None else spam.get('mentions'), #max @<user> mentions allowed
            "selfbot": True if serv is None or spam.get('selfbot') is None else spam.get('selfbot'), #Detect possible selfbots or spam advertisers?
            "caps": 0.0 if serv is None or spam.get('caps') is None else spam.get('caps'), #Caps to tolerate - 0=no filter, int=value, double=percentage
            "links": True if serv is None or spam.get('links') is None else spam.get('links'), #URLs allowed?
            'attachments': [False, False, False, False, False, False, False, False, False] if serv is None or spam.get('attachments') is None else spam.get('attachments'), #[All attachments, media attachments, non-common attachments, pics, audio, video, static pictures, gifs, tie with flagging system]
            "invites": True if serv is None or spam.get('invites') is None else spam.get('invites'), #Discord.gg invites allowed?
            "everyoneTags": 2 if serv is None or spam.get('everyoneTags') is None else spam.get('everyoneTags'), #Max number of @everyone, if it doesn't actually tag; 0=anything tolerated
            "hereTags": 2 if serv is None or spam.get('hereTags') is None else spam.get('hereTags'), #Max number of @here, if it doesn't actually tag; 0=anything tolerated
            "roleTags": 3 if serv is None or spam.get('roleTags') is None else spam.get('roleTags'), #Max number of <role> mentions tolerated (0 = anything tolerated)
            "quickMessages": [5, 10] if serv is None or spam.get('quickMessages') is None else spam.get('quickMessages'), #If [0] messages sent in [1] seconds, flag message ([0]=0: disabled)
            'consecutiveMessages': [10, 120] if serv is None or spam.get('consecutiveMessages') is None else spam.get('consecutiveMessages'), #If this many messages in a row are sent by the same person, flag them
            'repeatedJoins': [0, 300, 86400] if serv is None or spam.get('repeatedJoins') is None else spam.get('repeatedJoins'), #If user joins [0] times in [1] seconds, ban them for [2] seconds
            "ignoreRoled": False if serv is None or spam.get('ignoreRoled') is None else spam.get('ignoreRoled'), #Ignore people with a role?
            "exclusionMode": 1 if serv is None or spam.get('exclusionMode') is None else spam.get('exclusionMode'), #Blacklist (0) or Whitelist(1) the channel exclusions
            "channelExclusions": await DefaultChannelExclusions(s) if serv is None or spam.get('channelExclusions') is None else spam.get('channelExclusions'), #Don't filter messages in channels in this list
            "roleExclusions": await DefaultRoleExclusions(s) if serv is None or spam.get('roleExclusions') is None else spam.get('roleExclusions'), #Don't filter messages sent by members with a role in this list
            "memberExclusions": await DefaultMemberExclusions(s) if serv is None or spam.get('memberExclusions') is None else spam.get('memberExclusions'), #Don't filter messages sent by a member in this list
            "profanityEnabled": False if serv is None or spam.get("profanityEnabled") is None else spam.get('profanityEnabled'), #Is the profanity filter enabled
            "profanityTolerance": 0.25 if serv is None or spam.get('profanityTolerance') is None else spam.get('profanityTolerance'), #% of message to be profanity to be flagged
            "filter": [] if serv is None or spam.get("filter") is None else spam.get("filter"), #Profanity filter list
            'ageKick': None if serv is None or spam.get('ageKick') is None else spam.get('ageKick'), #NEED TO REDO DATABASE ALGORITHM SO ON DEMAND VARIABLES ARENT OVERWRITTEN
            'ageKickDM': defaultAgeKickDM if serv is None or spam.get('ageKickDM') is None else spam.get('ageKickDM'),
            'ageKickOwner': False if serv is None or spam.get('ageKickOwner') is None else spam.get('ageKickOwner'),
            'ageKickWhitelist': [] if serv is None or spam.get('ageKickWhitelist') is None else spam.get('ageKickWhitelist'),
            'timedEvents': [] if serv is None or spam.get('timedEvents') is None else spam.get('timedEvents')}, #Bans, mutes, etc
        "cyberlog": {
            # 'globalSettings': vars(loggingHome),
            "enabled": False if log is None or log.get('enabled') is None else log.get('enabled'),
            "image": False if log is None or log.get('image') is None else log.get('enabled'),
            "defaultChannel": None if log is None or log.get('defaultChannel') is None else log.get('defaultChannel'),
            'memberGlobal': 2 if log is None or log.get('memberGlobal') is None else log.get('memberGlobal'),
            "channelExclusions": [] if log is None or log.get('channelExclusions') is None else log.get('channelExclusions'),
            'roleExclusions': [] if log is None or log.get('roleExclusions') is None else log.get('roleExclusions'),
            'memberExclusions': [] if log is None or log.get('memberExclusions') is None else log.get('memberExclusions'),
            'summarize': 0,# if log is None or log.get('summarize') is None else log.get('summarize'),
            'lastUpdate': datetime.datetime.utcnow() if serv is None or serv.get('lastUpdate') is None else serv.get('lastUpdate'),
            "message": vars(LogModule("message", "Send logs when a message is edited or deleted")) if log is None or log.get('message') is None else vars(LogModule("message", "Send logs when a message is edited or deleted").update(await GetCyberMod(s, 'message'))),
            "doorguard": vars(LogModule("doorguard", "Send logs when a member joins or leaves server")) if log is None or log.get('doorguard') is None else vars(LogModule("doorguard", "Send logs when a member joins or leaves server").update(await GetCyberMod(s, 'doorguard'))),
            "channel": vars(LogModule("channel", "Send logs when channel is created, edited, or deleted")) if log is None or log.get('channel') is None else vars(LogModule("channel", "Send logs when channel is created, edited, or deleted").update(await GetCyberMod(s, 'channel'))),
            "member": vars(LogModule("member", "Send logs when member changes username or nickname, has roles added or removed, changes avatar, or changes discriminator")) if log is None or log.get('member') is None else vars(LogModule("member", "Send logs when member changes username or nickname, has roles added or removed, changes avatar, or changes discriminator").update(await GetCyberMod(s, 'member'))),
            "role": vars(LogModule("role", "Send logs when a role is created, edited, or deleted")) if log is None or log.get('role') is None else vars(LogModule("role", "Send logs when a role is created, edited, or deleted").update(await GetCyberMod(s, 'role'))),
            "emoji": vars(LogModule("emoji", "Send logs when emoji is created, edited, or deleted")) if log is None or log.get('emoji') is None else vars(LogModule("emoji", "Send logs when emoji is created, edited, or deleted").update(await GetCyberMod(s, 'emoji'))),
            "server": vars(LogModule("server", "Send logs when server is updated, such as thumbnail")) if log is None or log.get('server') is None else vars(LogModule("server", "Send logs when server is updated, such as thumbnail").update(await GetCyberMod(s, 'server'))),
            "voice": vars(LogModule('voice', "Send logs when members' voice chat attributes change")) if log is None or log.get('voice') is None else vars(LogModule('voice', "Send logs when members' voice chat attributes change").update(await GetCyberMod(s, 'voice')))
            }}}, upsert=True)
            # 'modules': [
            #     vars(messageContainer),
            #     vars(doorguardContainer),
            #     vars(channelContainer),
            #     vars(memberContainer),
            #     vars(roleContainer),
            #     vars(emojiContainer),
            #     vars(serverContainer),
            #     vars(voiceContainer)]
            #}}},upsert=True)
    else: #only update things that may have changed (on discord's side) if the server already exists; otherwise we're literally putting things back into the variable for no reason
        await servers.update_one({'server_id': s.id}, {"$set": { 
            'name': s.name,
            'thumbnail': str(s.icon_url),
            'channels': serverChannels,
            'roles': [{'name': role.name, 'id': role.id} for role in iter(s.roles) if not role.managed and not role.is_default()]}})
    #started2 = datetime.datetime.now()
    membDict = {}
    if serv is None: serv = await servers.find_one({'server_id': s.id})
    if serv is not None:
        spam = serv.get("antispam") #antispam object from database
        log = serv.get("cyberlog") #cyberlog object from database
        members = serv.get("members")
    for m in s.members: #Create dict 
        membDict[str(m.id)] = m.name
        membDict[m.name] = m.id
    databaseMembIDs = [m.get('id') for m in members] if members is not None else []
    serverMembIDs = [m.id for m in s.members]
    if members is None: members = []
    if serv.get('members') is None or serv is None or len(serv.get('members')) < 1: 
        membersToUpdate = []
        for member in s.members:
            membersToUpdate.append({'id': member.id, 'name': member.name, 'warnings': spam['warn'], 'quickMessages': [], 'lastMessages': []})
        await servers.update_one({'server_id': s.id}, {'$set': {'members': membersToUpdate}}, True)
    else:
        if any([m not in databaseMembIDs for m in serverMembIDs]):
            toUpdate = []
            for userID in [m for m in serverMembIDs if m not in databaseMembIDs]:
                toUpdate.append({'id': userID, 'name': membDict[str(userID)], 'warnings': spam['warn'], 'quickMessages': [], 'lastMessages': []})
            await servers.update_one({'server_id': s.id}, {"$push": {'members': { '$each': toUpdate}}}, True)
        toUpdate = []
        toRemove = []
        for member in members:
            def retrieveMember(identification):
                for m in serverMembIDs:
                    if m == identification: return s.get_member(m)
                return None
            serverMember = retrieveMember(member['id'])
            if not serverMember: toRemove.append(member)
            else:
                if serverMember.name != member['name']: toUpdate.append(serverMember)
            # if member.get('id') in serverMembIDs:
            #     try:
            #         await servers.update_one({'server_id': s.id, 'members.id': member.get('id')}, {"$set": {
            #             "members.$.id": member.get('id'),
            #             "members.$.name": membDict.get(str(member.get('id'))),
            #             "members.$.warnings": spam.get('warn') if member is None else member.get('warnings'),
            #             "members.$.quickMessages": [] if member is None or member.get('quickMessages') is None else member.get('quickMessages'),
            #             "members.$.lastMessages": [] if member is None or member.get('lastMessages') is None else member.get('lastMessages')
            #         }}, upsert=True)
            #     except: pass
            # else: await servers.update_one({'server_id': s.id}, {'$pull': {'members': {'id': member.get('id')}}})
        bulkUpdates = [pymongo.UpdateOne({'server_id': s.id, 'members.id': member.id}, {'$set': {'members.$.name': member.name}}) for member in toUpdate]
        if bulkUpdates: await servers.bulk_write(bulkUpdates)
        if toRemove: await servers.update_one({'server_id': s.id}, {'$pull': {'members': {'$in': [member['id'] for member in toRemove]}}})
        #for member in toUpdate: await servers.update_one({'server_id': s.id, 'members.id': member.id}, {"$set": {'members.$.name': member.name}}, True)
        #print(f'Verified Server {s.name}:\n Server only: {(started2 - started).seconds}s\n Members only: {(datetime.datetime.now() - started2).seconds}s\n Total: {(datetime.datetime.now() - started).seconds}s')
    return (serv.get('name'), serv.get('server_id'))

async def VerifyUsers(b: commands.Bot):
    '''Ensures every global Discord user in a bot server has one unique entry. No use for these variables at the moment; usage to come'''
    '''First: Go through all members, verifying they have entries and variables'''
    await asyncio.gather(*[VerifyUser(m, b) for m in b.users])
    await users.delete_many({'user_id': {'$nin': [m.id for m in b.users]}}) #Remove all of the user data that no longer exists
    
async def VerifyUser(m: discord.Member, b: commands.Bot):
    '''Ensures that an individual user is in the database, and checks its variables'''
    #started = datetime.datetime.now()
    current = await users.find_one({'user_id': m.id})
    if b.get_user(m.id) is None: return await users.delete_one({'user_id': m.id})
    if current: await users.update_one({'user_id': m.id}, {'$set': {'username': m.name, 'servers': [{'server_id': server.id, 'name': server.name, 'thumbnail': str(server.icon_url)} for server in b.guilds if await DashboardManageServer(server, m)]}})
    else:
        await users.update_one({"user_id": m.id}, {"$set": { #For new members, set them up. For existing members, the only things that that may have changed that we care about here are the two fields above
        "username": m.name,
        "user_id": m.id,
        'lastActive': {'timestamp': datetime.datetime.min, 'reason': 'Not tracked yet'},
        'lastOnline': datetime.datetime.min,
        'birthdayMessages': [],
        'birthday': None,
        'wishList': [],
        "servers": [{"server_id": server.id, "name": server.name, "thumbnail": str(server.icon_url)} for server in iter(b.guilds) if await DashboardManageServer(server, m)]}}, True)
    #print(f'Verified User {m.name} in {(datetime.datetime.now() - started).seconds}s')

async def GetLogChannel(s: discord.Guild, mod: str):
    '''Return the log channel associated with <mod> module'''
    return s.get_channel((await servers.find_one({"server_id": s.id})).get("cyberlog").get(mod).get("channel")) if (await servers.find_one({"server_id": s.id})).get("cyberlog").get(mod).get("channel") is not None else s.get_channel((await servers.find_one({"server_id": s.id})).get("cyberlog").get("defaultChannel"))

async def GetMainLogChannel(s: discord.Guild):
    '''Returns the log channel associated with the server (general one), if one is set'''
    return s.get_channel(await (servers.find_one({"server_id": s.id})).get("cyberlog").get("defaultChannel"))

async def GetCyberMod(s: discord.Guild, mod: str):
    '''Returns the specified module of the Cyberlog object'''
    return (await servers.find_one({"server_id": s.id})).get("cyberlog").get(mod)

async def GetReadPerms(s: discord.Guild, mod: str):
    '''Return if the bot should read the server audit log for logs'''
    return (await GetCyberMod(s, mod)).get("read")

async def GetEnabled(s: discord.Guild, mod: str):
    '''Check if this module is enabled for the current server'''
    return (await GetCyberMod(s, mod)).get("enabled") and (await servers.find_one({"server_id": s.id})).get("cyberlog").get('enabled') and ((await servers.find_one({"server_id": s.id})).get("cyberlog").get(mod).get("channel") is not None or (await servers.find_one({"server_id": s.id})).get("cyberlog").get("defaultChannel") is not None) 

async def SimpleGetEnabled(s: discord.Guild, mod: str):
    '''Check if this module is enabled for the current server (lightweight)
    REMEMBER THAT THIS DOESN'T MAKE SURE THAT THE CHANNEL IS VALID'''
    return (await servers.find_one({"server_id": s.id})).get("cyberlog").get(mod).get("enabled") and (await servers.find_one({"server_id": s.id})).get("cyberlog").get('enabled')

async def GetImageLogPerms(s: discord.Guild):
    '''Check if image logging is enabled for the current server'''
    return (await servers.find_one({"server_id": s.id})).get("cyberlog").get('image')

async def GetAntiSpamObject(s: discord.Guild):
    '''Return the Antispam database object - use 'get' to get the other objects'''
    return (await servers.find_one({"server_id": s.id})).get("antispam")

async def GetCyberlogObject(s: discord.Guild):
    '''Return the cyberlog database object'''
    return (await servers.find_one({"server_id": s.id})).get("cyberlog")

async def GetMembersList(s: discord.Guild):
    '''Return list of members DB entry objects for a server'''
    return (await servers.find_one({"server_id": s.id})).get("members")

async def PauseMod(s: discord.Guild, mod):
    '''Pauses logging for a server'''
    await servers.update_one({"server_id": s.id}, {"$set": {mod+".enabled": False}})

async def ResumeMod(s: discord.Guild, mod):
    '''Resumes logging for a server'''
    await servers.update_one({"server_id": s.id}, {"$set": {mod+".enabled": True}})

async def GetServerCollection():
    '''Return servers collection object'''
    return servers

async def GetAllServers():
    '''Return all servers...'''
    return servers.find()

async def GetAllUsers():
    '''Return all users...'''
    return users.find()

async def GetUser(u: discord.User):
    '''Returns a global user'''
    return (await users.find_one({'user_id': u.id}))

async def GetMember(m: discord.Member):
    '''Returns a member of a server'''
    return ([a for a in (await servers.find_one({"server_id": m.guild.id})).get('members') if a.get('id') == m.id][0])

async def GetProfanityFilter(s: discord.Guild):
    '''Return profanityfilter object'''
    return (await GetAntiSpamObject(s)).get("filter")

async def GetPrefix(s: discord.Guild):
    '''Return prefix associated with the server'''
    return (await servers.find_one({"server_id": s.id})).get('prefix')

async def UpdateMemberLastMessages(server: int, member: int, messages):
    '''Updates database entry for lastMessages modification
    Server: id of server the member belongs to
    Member: id of member
    Messages: list of messages to replace the old list with'''
    await servers.update_one({"server_id": server, "members.id": member}, {"$set": {"members.$.lastMessages": messages}})

async def UpdateMemberQuickMessages(server: int, member: int, messages):
    '''Updates database entry for quickMessages modification
    Server: id of server the member belongs to
    Member: id of member
    Messages: list of messages to replace the old list with'''
    await servers.update_one({"server_id": server, "members.id": member}, {"$set": {"members.$.quickMessages": messages}})

async def UpdateMemberWarnings(server: discord.Guild, member: discord.Member, warnings: int):
    '''Updates database entry for a member's warnings
    Server: Server the member belongs to
    Member: The member to update
    Warnings: Number of warnings to replace current version with'''
    await servers.update_one({"server_id": server.id, "members.id": member.id}, {"$set": {"members.$.warnings": warnings}})

async def GetChannelExclusions(s: discord.Guild):
    '''Not to be confused with DefaultChannelExclusions(). Returns server's channel exclusions
    s: discord.Guild object (server) to get the exclusions from'''
    return (await GetAntiSpamObject(s)).get("channelExclusions")

async def GetLogChannelExclusions(s: discord.Guild):
    '''Get the channel exclusions for the Cyberlog module'''
    return (await GetCyberlogObject(s)).get("channelExclusions")

async def GetRoleExclusions(s: discord.Guild):
    '''Not to be confused with DefaultRoleExclusions(). Returns server's role exclusions
    s: discord.Guild object (server) to get the exclusions from'''
    return (await GetAntiSpamObject(s)).get("roleExclusions")

async def GetLogRoleExclusions(s: discord.Guild):
    '''Get the role exclusions for the Cyberlog module'''
    return (await GetCyberlogObject(s)).get("roleExclusions")

async def GetMemberExclusions(s: discord.Guild):
    '''Not to be confused with DefaultMemberExclusions(). Returns server's member exclusions
    s: discord.Guild object (server) to get the exclusions from'''
    return (await GetAntiSpamObject(s)).get("memberExclusions")

async def GetLogMemberExclusions(s: discord.Guild):
    '''Get the member exclusions for the cyberlog module'''
    return (await GetCyberlogObject(s)).get("memberExclusions")

async def DefaultChannelExclusions(server: discord.Guild): 
    '''For now, return array of IDs of all channels with 'spam' in the name. Will be customizable later'''
    return [a.id for a in iter(server.channels) if any(word in a.name for word in ['spam', 'bot'])]

async def DefaultRoleExclusions(server: discord.Guild): 
    '''For now, return array of IDs of all roles that can manage server. Will be customizable later'''
    return [a.id for a in iter(server.roles) if a.permissions.administrator or a.permissions.manage_guild]

async def DefaultMemberExclusions(server: discord.Guild): 
    '''For now, return array of the ID of server owner. Will be customizable later'''
    return [server.owner.id]

async def ManageServer(member: discord.Member): #Check if a member can manage server, used for checking if they can edit dashboard for server
    if member.id == member.guild.owner.id: return True
    if member.id == 247412852925661185: return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.manage_guild:
            return True
    return False

async def ManageRoles(member: discord.Member):
    '''Does this member have the Manage Roles permission'''
    if member.id == member.guild.owner.id: return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.manage_roles:
            return True
    return False

async def ManageChannels(member: discord.Member):
    '''Does this member have the Manage Channels permission'''
    if member.id == member.guild.owner.id: return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.manage_channels:
            return True
    return False

async def KickMembers(member: discord.Member):
    '''Does this member have the Kick Members permission'''
    if member.id == member.guild.owner.id: return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.kick_members:
            return True
    return False

async def BanMembers(member: discord.Member):
    '''Does this member have the Ban Members permission'''
    if member.id == member.guild.owner.id: return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.ban_members:
            return True
    return False

async def CheckCyberlogExclusions(channel: discord.TextChannel, member: discord.Member):
    '''Check to see if we shouldn't log a message delete event
    True to proceed
    False to not log'''
    if channel.id in await GetLogChannelExclusions(channel.guild) or member.id in await GetLogMemberExclusions(channel.guild):
        return False
    for role in member.roles:
        if role.id in await GetLogRoleExclusions(channel.guild):
            return False
    return True

async def DashboardManageServer(server: discord.Guild, member: discord.Member):
    '''Initialize dashboard permissions; which servers a member can manage'''
    if member.id == 247412852925661185: return True
    for memb in server.members:
        if member.id == memb.id:
            return await ManageServer(memb)
    return False

async def GetSummarize(s: discord.Guild, mod):
    '''Get the summarize value'''
    return (await GetCyberlogObject(s)).get(mod).get('summarize') if (await GetCyberlogObject(s)).get('summarize') != (await GetCyberlogObject(s)).get(mod).get('summarize') else (await GetCyberlogObject(s)).get('summarize')

async def SummarizeEnabled(s: discord.Guild, mod):
    '''Is summarizing enabled for this module?'''
    return (await GetCyberlogObject(s)).get('summarize') != 0 and (await GetCyberlogObject(s)).get(mod).get('summarize') != 1

async def GeneralSummarizeEnabled(s: discord.Guild):
    '''Is summarizing enabled for this server?'''
    return (await GetCyberlogObject(s)).get('summarize') != 0

async def StringifyPermissions(p: discord.Permissions):
    '''Turn a permissions object into a partially stringified version'''
    return [a[0] for a in iter(p) if a[1]]

async def AppendSummary(s: discord.Guild, summary):
    '''Appends a Cyberlog.Summary object to a server's database entry'''
    await servers.update_one({'server_id': s.id}, {'$push': {'summaries': vars(summary) }})

async def GetSummary(s: discord.Guild, id: int):
    '''Return a summary object from a server and message ID'''
    return await servers.find_one({'server_id': s.id, 'summaries.$.id': id})

async def StringifyExtras(r: discord.Role):
    '''Turns a role into a partially stringified version for things like mentionable/displayed separately'''
    s = []
    if r.hoist: s.append('displayed separately')
    if r.mentionable: s.append('mentionable')
    return s

async def StringifyBoth(r: discord.Role):
    '''Turns a role into a combination of the above two'''
    perms = await StringifyPermissions(r.permissions)
    perms.extend(await StringifyExtras(r))
    return perms

async def ComparePerms(b: discord.Role, a: discord.Role):
    '''Bold or strikethrough differences'''
    bef = await StringifyBoth(b)
    aft = await StringifyBoth(a)
    s = []
    for perm in bef:
        if perm not in aft: s.append('~~{}~~'.format(perm))
        else: s.append(perm)
    for perm in aft:
        if perm not in bef and perm not in s: s.append('**{}**'.format(perm))
    return s

async def UnchangedPerms(b: discord.Role, a: discord.Role):
    '''Only return things that aren't changed'''
    root = await StringifyBoth(b)
    new = await StringifyBoth(a)
    returns = []
    for r in root:
        if r in new: returns.append(r)
    return returns

async def GetTimezone(s: discord.Guild):
    '''Return the timezone offset from UTC for a given server'''
    return (await servers.find_one({"server_id": s.id})).get('offset')

async def UpdateTimezone(s: discord.Guild, o):
    '''Sets the new timezone offset from UTC for a given server
    o: the new offset in hours from UTC: negative is behind, positive is ahead'''
    await servers.update_one({'server_id': s.id}, {'$set': {'offset': o}})

async def GetBirthdate(s: discord.Guild):
    '''Return the time associated with a server's Birthday Management'''
    return (await servers.find_one({'server_id': s.id})).get('birthdate')

async def GetBirthday(s: discord.Guild):
    '''Return the channel associated with a server's Birthday Management'''
    return (await servers.find_one({'server_id': s.id})).get('birthday')

async def SetBirthday(m: discord.User, d):
    '''Update a member's birthday information'''
    await users.update_one({'user_id': m.id}, {'$set': {'birthday': d}})

async def GetMemberBirthday(m: discord.User):
    '''Return a member's birthday'''
    return (await users.find_one({'user_id': m.id})).get('birthday')

async def GetBirthdayMessages(m: discord.User):
    '''Return a member's birthday messages'''
    return (await users.find_one({'user_id': m.id})).get('birthdayMessages')

async def SetBirthdayMessage(m: discord.Member, msg, auth, servers):
    '''Update a member's birthday messages (receiving)'''
    await users.update_one({'user_id': m.id}, {'$push': {'birthdayMessages': {
        'message': msg.clean_content,
        'author': auth.id,
        'authName': auth.name,
        'created': datetime.datetime.utcnow(),
        'servers': [s.id for s in servers]}}}) 

async def ResetBirthdayMessages(m: discord.Member):
    '''Resets a member's birthday messages (once their birthday has happened)'''
    await users.update_one({'user_id': m.id}, {'$set': {'birthdayMessages': []}})

async def GetAge(m: discord.Member):
    '''Return the age of a member'''
    return (await users.find_one({'user_id': m.id})).get('age')

async def SetAge(m: discord.Member, age):
    '''Set the age of a  member'''
    await users.update_one({'user_id': m.id}, {'$set': {'age': age}})

async def AppendWishlistEntry(m: discord.Member, entry):
    '''Append a wishlist entry to a member's wish list'''
    await users.update_one({'user_id': m.id}, {'$push': {'wishList': entry}}, True)

async def SetWishlist(m: discord.Member, wishlist):
    '''Sets a member's wishlist to the specified list'''
    await users.update_one({'user_id': m.id}, {'$set': {'wishList': wishlist}}, True)

async def GetWishlist(m: discord.Member):
    '''Return the wishlist of a member'''
    return (await users.find_one({'user_id': m.id})).get('wishList')

async def SetBirthdayMode(s: discord.Guild, mode):
    '''Sets auto birthday detection mode: Disabled (0), cake only (1), enabled (2)'''
    await servers.update_one({'server_id': s.id}, {'$set': {'birthdayMode': mode}})

async def GetBirthdayMode(s: discord.Guild, mode):
    '''Returns auto birthday detection mode, see above for values'''
    return (await servers.find_one({'server_id': s.id})).get('birthdayMode')

async def GetAgeKick(s: discord.Guild):
    '''Gets the ageKick of a server'''
    return (await servers.find_one({'server_id': s.id})).get('antispam').get('ageKick')

async def SetAgeKick(s: discord.Guild, ageKick):
    '''Sets the ageKick of a server'''
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.ageKick': ageKick}}, True)
    print(f'Updated ageKick for {s.name} to {ageKick} at {datetime.datetime.now():%B %d %I:%M %p}')

async def GetWhitelist(s: discord.Guild):
    '''Gets the whitelist for the ageKick of a server [list of int-IDs]'''
    return (await servers.find_one({'server_id': s.id})).get('antispam').get('ageKickWhitelist')

async def AppendWhitelistEntry(s: discord.Guild, entry):
    '''Appends to the ageKick whitelist of a server'''
    await servers.update_one({'server_id': s.id}, {'$push': {'antispam.ageKickWhitelist': entry}}, True)

async def RemoveWhitelistEntry(s: discord.Guild, entry):
    '''Removes an entry from the ageKick whitelist of a server'''
    await servers.update_one({'server_id': s.id}, {'$pull': {'antispam.ageKickWhitelist': entry}}, True)

async def ResetWhitelist(s: discord.Guild):
    '''Resets (empties) the ageKick whitelist of a server'''
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.ageKickWhitelist': []}}, True)

async def GetAgeKickDM(s: discord.Guild):
    '''Returns the custom DM message of the ageKick module for a server'''
    return (await servers.find_one({'server_id': s.id})).get('antispam').get('ageKickDM')

async def SetAgeKickDM(s: discord.Guild, message):
    '''Sets the custom DM message of the ageKick module for a server'''
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.ageKickDM': message}}, True)

async def GetAgeKickOwner(s: discord.Guild):
    '''Returns whether the ageKick configuration for the specified server can only be modified by the server owner'''
    return (await servers.find_one({'server_id': s.id})).get('antispam').get('ageKickOwner')

async def SetAgeKickOwner(s: discord.Guild, new: bool):
    '''Sets whether the ageKick configuration for the specified server can only be modified by the server owner'''
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.ageKickOwner': new}}, True)

async def AppendTimedEvent(s: discord.Guild, event):
    '''Appends a timed ban/mute/etc event to a server, these are checked periodically'''
    await servers.update_one({'server_id': s.id}, {'$push': {'antispam.timedEvents': event}}, True)

async def RemoveTimedEvent(s: discord.Guild, event):
    '''Removes a timed ban/mute/etc event from a server'''
    await servers.update_one({'server_id': s.id}, {'$pull': {'antispam.timedEvents': event}}, True)

async def AppendCustomStatusHistory(m: discord.Member, emoji, status):
    '''Appends a custom status event to a user listing of them. Member object because only they have custom status attributes, not just user objects.'''
    await users.update_one({'user_id': m.id}, {'$push': {'customStatusHistory': {'emoji': emoji, 'name': status, 'timestamp': datetime.datetime.utcnow()}}}, True)

async def AppendUsernameHistory(m: discord.User):
    '''Appends a username update to a user's listing of them'''
    await users.update_one({'user_id': m.id}, {'$push': {'usernameHistory': {'name': m.name, 'timestamp': datetime.datetime.utcnow()}}}, True)

async def AppendAvatarHistory(m: discord.User, url):
    '''Appends an avatar update to a user's listing of them. Old is the discord CDN avatar link used for comparisons, new is the permanent link from the image log channel (copy attachment)'''
    await users.update_one({'user_id': m.id}, {'$push': {'avatarHistory': {'discordURL': str(m.avatar_url), 'imageURL': url, 'timestamp': datetime.datetime.utcnow()}}}, True)

async def UnduplicateHistory(u: discord.User):
    '''Removes duplicate entries from a user's history lists'''
    userEntry = await users.find_one({'user_id': u.id})
    csh, uh, ah = [], [], []
    try:
        for c in userEntry.get('customStatusHistory'):
            if {'emoji': c.get('emoji'), 'name': c.get('name')} not in [{'emoji': i.get('emoji'), 'name': i.get('name')} for i in csh]: csh.append(c)
    except TypeError: pass
    try:
        for c in userEntry.get('usernameHistory'):
            if c.get('name') not in [i.get('name') for i in uh]: uh.append(c)
    except TypeError: pass
    try:
        for c in userEntry.get('avatarHistory'):
            if c.get('discordURL') not in [i.get('discordURL') for i in ah]: ah.append(c)
    except TypeError: pass
    for c in csh:
        await users.update_one({'user_id': u.id}, {'$pull': {'customStatusHistory': {'emoji': c.get('emoji'), 'name': c.get('name')}}})
        await users.update_one({'user_id': u.id}, {'$push': {'customStatusHistory': c}})
    for c in uh: 
        await users.update_one({'user_id': u.id}, {'$pull': {'usernameHistory': {'name': c.get('name')}}})
        await users.update_one({'user_id': u.id}, {'$push': {'usernameHistory': c}})
    for c in ah:
        await users.update_one({'user_id': u.id}, {'$pull': {'avatarHistory': {'discordURL': c.get('discordURL')}}})
        await users.update_one({'user_id': u.id}, {'$push': {'avatarHistory': c}})

async def SetLastActive(u: discord.User, timestamp, reason):
    '''Updates the last active attribute'''
    await users.update_one({'user_id': u.id}, {'$set': {'lastActive': {'timestamp': timestamp, 'reason': reason}}}, True)

async def SetLastOnline(u: discord.User, timestamp):
    '''Updates the last online attribute'''
    await users.update_one({'user_id': u.id}, {'$set': {'lastOnline': timestamp}}, True)

async def SetLogChannel(s: discord.Guild, channel):
    '''Sets whether the ageKick configuration for the specified server can only be modified by the server owner'''
    await servers.update_one({'server_id': s.id}, {'$set': {'cyberlog.defaultChannel': channel.id}}, True)

async def NameVerify(s: discord.Guild):
    '''Verifies a server by name to counter the database code error'''
    await servers.update_one({'name': s.name}, {'$set': {'server_id': s.id}}, True)

async def ZeroRepeatedJoins(s: discord.Guild):
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.repeatedJoins': [0, 0, 0]}}, True)

async def AppendMemberJoinEvent(s: discord.Guild, m: discord.Member):
    '''Appends a member join event to a server's log, uses for member join logs'''
    await servers.update_one({'server_id': s.id}, {'$push': {'cyberlog.joinLogHistory': {'id': m.id, 'timestamp': datetime.datetime.utcnow()}}})

async def GetNamezone(s: discord.Guild):
    '''Return the custom timezone name for a given server'''
    return (await servers.find_one({"server_id": s.id})).get('tzname')

async def GetServer(s: discord.Guild):
    '''Return server object'''
    return await servers.find_one({'server_id': s.id})

async def SetLastUpdate(s: discord.Guild, d: datetime.datetime, mod: None):
    '''Update the last time a server was summarized, optional module argument'''
    if mod is None: await servers.update_one({'server_id': s.id}, {'$set': {'cyberlog.lastUpdate': d}})
    else: await servers.update_one({'server_id': s.id}, {'$set': {'cyberlog.'+mod+'.lastUpdate': d}})

async def GetLastUpdate(s: discord.Guild, mod: None):
    '''Returns a datetime object representing the last time the server or a module was recapped'''
    if mod is None: return await servers.find_p({"server_id": s.id}).get("cyberlog.lastUpdate")
    else: return await GetCyberMod(s, mod).get('lastUpdate')

async def GetOldestUpdate(s: discord.Guild, mods):
    '''Returns the oldest update date from a list of provided modules. Useful for when people configure different settings for different modules'''
    return min([GetLastUpdate(s, m) for m in mods]) + datetime.timedelta(hours=await GetTimezone(s))

async def UpdateChannel(channel: discord.abc.GuildChannel):
    '''Updates the channel.updated and channel.name attributes of the given channel. .updated is used for stats on channel edit'''
    servers.update_one({'server_id': channel.guild.id, 'allChannels.id': channel.id}, {'$set': {
        'allChannels.$.updated': datetime.datetime.utcnow(),
        'allChannels.$.name': channel.name,
        'allChannels.$.oldUpdate': await GetChannelUpdate(channel)}})

async def UpdateRole(role: discord.Role):
    '''Updates the role.updated and role.name attributes of the given role. .updated is used for stats on role edit'''
    servers.update_one({'server_id': role.guild.id, 'roles.id': role.id}, {'$set': {
        'roles.$.updated': datetime.datetime.utcnow(),
        'roles.$.name': role.name,
        'roles.$.oldUpdate': await GetRoleUpdate(role)}})

async def GetChannelUpdate(channel: discord.abc.GuildChannel):
    '''Returns the channel.updated attribute, which is the last time the channel was updated'''
    return (await servers.find_one({'server_id': channel.guild.id, 'channels.$.id': channel.id})).get('updated')

async def GetOldChannelUpdate(channel: discord.abc.GuildChannel):
    '''Returns the channel.oldUpdate attribute, which is the time it was updated 2 times ago'''
    return (await servers.find_one({'server_id': channel.guild.id, 'channels.$.id': channel.id})).get('oldUpdate')

async def GetRoleUpdate(role: discord.Role):
    '''Returns the role.updated attribute, which is the last time the role was updated'''
    return (await servers.find_one({'server_id': role.guild.id, 'roles.$.id': role.id})).get('updated')

async def GetOldRoleUpdate(role: discord.Role):
    '''Returns the role.oldUpdate attribute, which is the time it was updated 2 times ago'''
    return (await servers.find_one({'server_id': role.guild.id, 'roles.$.id': role.id})).get('oldUpdate')

async def VerifyChannel(c: discord.abc.GuildChannel, new=False):
    '''Verifies a channel. Single database operation of VerifyServer'''
    if new: await servers.update_one({'server_id': c.guild.id}, {'$push': {'channels': {'name': c.name, 'id': c.id}}})
    else: await servers.update_one({"server_id": c.guild.id, 'channels.$.id': c.id}, {"$set": {"name": c.name}})

async def VerifyMember(m: discord.Member, new=False):
    '''Verifies a member. Single database operation of VerifyServer'''
    antis = await servers.find_one({"server_id": m.guild.id}).get('antispam')
    if new:
        await servers.update_one({'server_id': m.guild.id}, {'$push': { 'members': {
            'id': m.id,
            'name': m.name,
            'warnings': antis.get('warn'),
            'quickMessages': [],
            'lastMessages': []}}})
    else: await servers.update_one({"server_id": m.guild.id, "members.id": id}, {"$set": {"members.$.name": m.name}})

async def VerifyRole(r: discord.Role, new=False):
    '''Verifies a role. Single database operation of VerifyServer'''
    if new: await servers.update_one({'server_id': r.guild.id}, {'$push': {'roles': {'name': r.name, 'id': r.id}}})
    else: await servers.update_one({'server_id': r.guild.id, 'roles.$.id': r.id}, {'$set': {'name': r.name}})
 
async def CalculateGeneralChannel(g: discord.Guild, update=False):
    '''Determines the most active channel based on indexed message count
    r: Whether to return the channel. If False, just set this to the database'''
    channels = {}
    for c in g.text_channels:
        with open(f'Indexes/{g.id}/{c.id}.json') as f: channels[c] = len([v for v in json.load(f).values() if (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(v['timestamp0'])).days < 14]) #Most messages sent in last two weeks
    popular = max(channels, key = channels.get, default=0)
    if update: await servers.update_one({'server_id': g.id}, {'$set': {'generalChannel': popular.id}})
    return popular

async def CalculateAnnouncementsChannel(g: discord.Guild, update=False):
    '''Determines the announcement channel based on channel name and permissions
    r: Whether to return the channel. If False, just set this to the database'''
    try: s = sorted([c for c in g.text_channels if 'announcement' in c.name.lower() and not c.overwrites_for(g.default_role).send_messages], key=lambda x: len(x.name) - len('announcements'))[0]
    except IndexError: return 0
    if update: await servers.update_one({'server_id': g.id}, {'$set': {'announcementsChannel': s.id}})
    return s

async def CalculateModeratorChannel(g: discord.Guild, update=False):
    '''Determines the moderator channel based on channel name and permissions
    r: Whether to return the channel. If False, just set this to the database'''
    relevanceKeys = {}
    for c in g.text_channels:
        if not c.overwrites_for(g.default_role).read_messages: relevanceKeys.update({c: round(len([m for m in g.members if c.permissions_for(m).read_messages and c.permissions_for(m).send_messages]) * 100 / len([m for m in g.members if c.permissions_for(m).read_messages]))})
    for k in relevanceKeys:
        if any(word in k.name.lower() for word in ['mod', 'manager', 'staff', 'admin']): relevanceKeys[k] += 50
    result = max(relevanceKeys, key=relevanceKeys.get, default=0)
    if update: await servers.update_one({'server_id': g.id}, {'$set': {'moderatorChannel': result.id}})
    return result
    
async def CreateSupportTicket(ticket):
    '''Appends a new support ticket to the system'''
    await disguard.update_one({}, {'$push': {'tickets': ticket}}, True)

async def UpdateSupportTicket(ticketNumber, newTicket):
    '''Updates a support ticket with a new version'''
    await disguard.update_one({}, {'$set': {'tickets.$[elem]': newTicket}}, array_filters=[{'elem.number': ticketNumber}])

async def AppendTicketConversation(ticketNumber, conversationEntry):
    '''Appends a conversation entry to a support ticket'''
    await disguard.update_one({}, {'$push': {'tickets.$[elem].conversation': conversationEntry}}, array_filters=[{'elem.number': ticketNumber}])

async def FetchSupportTicket(ticketNumber):
    '''Fetches a specific support ticket, given its placement number'''
    return await disguard.find_one({'tickets': {'$elemMatch': {'number': ticketNumber}}})

async def GetSupportTickets():
    '''Returns entire support ticket collection'''
    return (await disguard.find_one({})).get('tickets')

async def SetSchedule(u: discord.User, schedule):
    '''Updates a member's school schedule'''
    await users.update_one({'user_id': u.id}, {'$set': {'schedule': schedule}}, True)

async def SetWarnings(members, warnings):
    bulkUpdates = [pymongo.UpdateOne({'server_id': members[0].guild.id, 'members.id': member.id}, {'$set': {'members.$.warnings': warnings}}) for member in members]
    await servers.bulk_write(bulkUpdates)