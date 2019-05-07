'''This file creates, verifies, and manages database entries as necessary during Disguard's operation'''
import pymongo
import dns
import secure
import discord
import profanityfilter
from discord.ext import commands

mongo = pymongo.MongoClient(secure.mongo()) #Database connection URL stored in another file for security reasons
db = None
servers = None
users = None

class LogModule(object):
    '''Used for consistent controlling of logging'''
    def __init__(self, name, description, embed=True, audit=True, enabled=True, channelID=None, embedColor=None, advanced=False):
        self.name = name #name of module
        self.description = description #description of module
        self.embed = embed #send logs in embed form? [ENABLED BY DEFAULT, CUSTOMIZABLE LATER]
        self.read = audit #read audit logs to post who did the action (such as who created the channel)? [ENABLED BY DEFAULT, CUSTOMIZABLE LATER]
        self.enabled = enabled #is this module enabled?
        self.channel = channelID #which channel is this sent to?
        self.color = embedColor #custom color used for embed [LATER]
        self.advanced = advanced #enable advanced mode? [LATER]

def Initialize(token):
    '''Configure the database based on if bot is Disguard or Disguard Beta'''
    global db
    global servers
    global users
    if token == secure.token():
        db = mongo.disguard
    elif token == secure.beta():
        db = mongo.disguard_beta
    servers = db.servers
    users = db.users
    

'''Checking events'''
def Verification(b: commands.Bot):
    '''Longest operation. Checks entire usable database *twice*, and verifies it's as it should be, creating entries as necessary'''
    VerifyServers(b)
    VerifyServers(b)
    VerifyUsers(b)
    VerifyUsers(b)

def VerifyServers(b: commands.Bot):
    '''Ensures all servers have database entries; adding and removing as necessary'''
    '''First: Index all bot servers, and verify them'''
    for s in b.guilds:
        VerifyServer(s, b)
    for result in servers.find(): #Delete servers that disguard is no longer a part of
        if b.get_guild(result.get("server_id")) is None:
            servers.delete_one({"server_id": result.get("server_id")})
    '''Second: Index database entries to check for extraneous entries'''

def VerifyServer(s: discord.Guild, b: commands.Bot):
    '''Ensures that an individual server has a database entry, and checks all its variables'''
    '''First: Update operation verifies that server's variables are standard and up to date; no channels that no longer exist, for example, in the database'''
    serv = servers.find_one({"server_id": s.id})
    spam = None
    log = None
    if serv is not None:
        spam = serv.get("antispam") #antispam object from database
        log = serv.get("cyberlog") #cyberlog object from database
        members = serv.get("members")
    servers.update_one({"server_id": s.id}, {"$set": { #update database
    "name": s.name,
    "prefix": "." if serv is None or serv.get('prefix') is None else serv.get('prefix'),
    "thumbnail": str(s.icon_url),
    "channels": [{"name": channel.name, "id": channel.id} for channel in iter(s.channels) if type(channel) is discord.TextChannel],
    "roles": [{"name": role.name, "id": role.id} for role in iter(s.roles) if role.name != "@everyone"],
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
        "invites": True if serv is None or spam.get('invites') is None else spam.get('invites'), #Discord.gg invites allowed?
        "everyoneTags": 2 if serv is None or spam.get('everyoneTags') is None else spam.get('everyoneTags'), #Max number of @everyone, if it doesn't actually tag; 0=anything tolerated
        "hereTags": 2 if serv is None or spam.get('hereTags') is None else spam.get('hereTags'), #Max number of @here, if it doesn't actually tag; 0=anything tolerated
        "roleTags": 3 if serv is None or spam.get('roleTags') is None else spam.get('roleTags'), #Max number of <role> mentions tolerated (0 = anything tolerated)
        "quickMessages": [5, 10] if serv is None or spam.get('quickMessages') is None else spam.get('quickMessages'), #If [0] messages sent in [1] seconds, flag message ([0]=0: disabled)
        "ignoreRoled": False if serv is None or spam.get('ignoreRoled') is None else spam.get('ignoreRoled'), #Ignore people with a role?
        "exclusionMode": 1 if serv is None or spam.get('exclusionMode') is None else spam.get('exclusionMode'), #Blacklist (0) or Whitelist(1) the channel exclusions
        "channelExclusions": DefaultChannelExclusions(s) if serv is None or spam.get('channelExclusions') is None else spam.get('channelExclusions'), #Don't filter messages in channels in this list
        "roleExclusions": DefaultRoleExclusions(s) if serv is None or spam.get('roleExclusions') is None else spam.get('roleExclusions'), #Don't filter messages sent by members with a role in this list
        "memberExclusions": DefaultMemberExclusions(s) if serv is None or spam.get('memberExclusions') is None else spam.get('memberExclusions'), #Don't filter messages sent by a member in this list
        "profanityEnabled": False if serv is None or spam.get("profanityEnabled") is None else spam.get('profanityEnabled'), #Is the profanity filter enabled
        "profanityTolerance": 0.25 if serv is None or spam.get('profanityTolerance') is None else spam.get('profanityTolerance'), #% of message to be profanity to be flagged
        "filter": [] if serv is None or spam.get("filter") is None else spam.get("filter")}, #Profanity filter list
    "cyberlog": {
        "enabled": False if log is None or log.get('enabled') is None else log.get('enabled'),
        "image": False if log is None or log.get('image') is None else log.get('enabled'),
        "defaultChannel": None if log is None or log.get('defaultChannel') is None else log.get('defaultChannel'),
        "message": vars(LogModule("message", "Send logs when a message is edited or deleted")) if log is None or log.get('message') is None else log.get('message'),
        "doorguard": vars(LogModule("doorguard", "Send logs when a member joins or leaves server")) if log is None or log.get('message') is None else log.get('doorguard'),
        "channel": vars(LogModule("channel", "Send logs when channel is created, edited, or deleted")) if log is None or log.get('channel') is None else log.get('channel'),
        "member": vars(LogModule("member", "Send logs when member changes username or nickname, has roles added or removed, changes avatar, or changes discriminator")) if log is None or log.get('member') is None else log.get('member'),
        "role": vars(LogModule("role", "Send logs when a role is created, edited, or deleted")) if log is None or log.get('role') is None else log.get('role'),
        "emoji": vars(LogModule("emoji", "Send logs when emoji is created, edited, or deleted")) if log is None or log.get('emoji') is None else log.get('emoji'),
        "server": vars(LogModule("server", "Send logs when server is updated, such as thumbnail")) if log is None or log.get('server') is None else log.get('server'),
        "voice": vars(LogModule('voice', "Send logs when members' voice chat attributes change")) if log is None or log.get('voice') is None else log.get('voice')},
    "members": [{
        "name": member.name, 
        "id": member.id, 
        "warnings": 3 if spam is None else spam.get('warn'), 
        "quickMessages": [], 
        "lastMessages": []
            } for member in iter(s.members)] if log is None or members is None else [{
        "name": member.name, 
        "id": member.id, 
        "warnings": spam.get('warn') if len([a for a in iter(servers.find_one({"server_id": s.id}).get("members")) if a.get("id") == member.id]) < 1 else [memb.get("warnings") for memb in iter(servers.find_one({"server_id": s.id}).get("members")) if memb.get("id") == member.id][0], 
        "quickMessages": [] if len([a for a in iter(servers.find_one({"server_id": s.id}).get("members")) if a.get("id") == member.id]) < 1 else [memb.get("quickMessages") for memb in iter(servers.find_one({"server_id": s.id}).get("members")) if memb.get("id") == member.id][0],
        "lastMessages": [] if len([a for a in iter(servers.find_one({"server_id": s.id}).get("members")) if a.get("id") == member.id]) < 1 else [memb.get("lastMessages") for memb in iter(servers.find_one({"server_id": s.id}).get("members")) if memb.get("id") == member.id][0]
            } for member in iter(s.members)]
             }}, True)

def VerifyUsers(b: commands.Bot):
    '''Ensures every global Discord user in a bot server has one unique entry. No use for these variables at the moment; usage to come'''
    '''First: Go through all members, verifying they have entries and variables'''
    for user in b.get_all_members():
        VerifyUser(user, b)
    for result in users.find(): #Delete users that aren't in any disguard servers
        if b.get_user(result.get("user_id")) is None:
            users.delete_one({"user_id": result.get("user_id")})
    
    
def VerifyUser(m: discord.Member, b: commands.Bot):
    '''Ensures that an individual user is in the database, and checks its variables'''
    users.update_one({"user_id": m.id}, {"$set": { #update database
    "username": m.name,
    "user_id": m.id,
    "servers": [{"server_id": server.id, "name": server.name, "thumbnail": str(server.icon_url)} for server in iter(b.guilds) if DashboardManageServer(server, m)]}}, True)

def GetLogChannel(s: discord.Guild, mod: str):
    '''Return the log channel associated with <mod> module'''
    return s.get_channel(servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("channel")) if servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("channel") is not None else servers.find_one({"server_id": s.id}).get("cyberlog").get("defaultChannel")

def GetReadPerms(s: discord.Guild, mod: str):
    '''Return if the bot should read the server audit log for logs'''
    return servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("read")

def GetEnabled(s: discord.Guild, mod: str):
    '''Check if this module is enabled for the current server'''
    return servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("enabled") and servers.find_one({"server_id": s.id}).get("cyberlog").get('enabled') and servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("channel")

def GetImageLogPerms(s: discord.Guild):
    '''Check if image logging is enabled for the current server'''
    return servers.find_one({"server_id": s.id}).get("cyberlog").get('image')

def GetAntiSpamObject(s: discord.Guild):
    '''Return the Antispam database object - use 'get' to get the other objects'''
    return servers.find_one({"server_id": s.id}).get("antispam")

def GetMembersList(s: discord.Guild):
    '''Return list of members DB entry objects for a server'''
    return servers.find_one({"server_id": s.id}).get("members")

def GetServerCollection():
    '''Return servers collection object'''
    return servers

def GetProfanityFilter(s: discord.Guild):
    '''Return profanityfilter object'''
    return GetAntiSpamObject(s).get("filter")

def GetPrefix(s: discord.Guild):
    '''Return prefix associated with the server'''
    return servers.find_one({"server_id": s.id}).get('prefix')

def UpdateMemberLastMessages(server: int, member: int, messages):
    '''Updates database entry for lastMessages modification
    Server: id of server the member belongs to
    Member: id of member
    Messages: list of messages to replace the old list with'''
    servers.update_one({"server_id": server, "members.id": member}, {"$set": {"members.$.lastMessages": messages}})

def UpdateMemberQuickMessages(server: int, member: int, messages):
    '''Updates database entry for quickMessages modification
    Server: id of server the member belongs to
    Member: id of member
    Messages: list of messages to replace the old list with'''
    servers.update_one({"server_id": server, "members.id": member}, {"$set": {"members.$.quickMessages": messages}})

def UpdateMemberWarnings(server: discord.Guild, member: discord.Member, warnings: int):
    '''Updates database entry for a member's warnings
    Server: Server the member belongs to
    Member: The member to update
    Warnings: Number of warnings to replace current version with'''
    servers.update_one({"server_id": server.id, "members.id": member.id}, {"$set": {"members.$.warnings": warnings}})

def GetChannelExclusions(s: discord.Guild):
    '''Not to be confused with DefaultChannelExclusions(). Returns server's channel exclusions
    s: discord.Guild object (server) to get the exclusions from'''
    return GetAntiSpamObject(s).get("channelExclusions")

def GetRoleExclusions(s: discord.Guild):
    '''Not to be confused with DefaultRoleExclusions(). Returns server's role exclusions
    s: discord.Guild object (server) to get the exclusions from'''
    return GetAntiSpamObject(s).get("roleExclusions")

def GetMemberExclusions(s: discord.Guild):
    '''Not to be confused with DefaultMemberExclusions(). Returns server's member exclusions
    s: discord.Guild object (server) to get the exclusions from'''
    return GetAntiSpamObject(s).get("memberExclusions")

def DefaultChannelExclusions(server: discord.Guild): 
    '''For now, return array of IDs of all channels with 'spam' in the name. Will be customizable later'''
    return [a.id for a in iter(server.channels) if "spam" in a.name]

def DefaultRoleExclusions(server: discord.Guild): 
    '''For now, return array of IDs of all roles that can manage server. Will be customizable later'''
    return [a.id for a in iter(server.roles) if a.permissions.administrator or a.permissions.manage_guild]

def DefaultMemberExclusions(server: discord.Guild): 
    '''For now, return array of the ID of server owner. Will be customizable later'''
    return [server.owner.id]

def ManageServer(member: discord.Member): #Check if a member can manage server, used for checking if they can edit dashboard for server
    for a in member.roles:
        if a.permissions.administrator or a.permissions.manage_guild:
            return True
    return False

def DashboardManageServer(server: discord.Guild, member: discord.Member):
    '''Initialize dashboard permissions; which servers a member can manage'''
    for memb in server.members:
        if member.id == memb.id:
            return ManageServer(memb)
    return False

    


        


