'''This file creates, verifies, and manages database entries as necessary during Disguard's operation
   This file also houses various useful methods that can be used across multiple files'''
import pymongo
import dns
import secure
import discord
import profanityfilter
import datetime
from discord.ext import commands

mongo = pymongo.MongoClient(secure.mongo()) #Database connection URL stored in another file for security reasons
db = None
servers = None
users = None

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
    print('Verifying server: {} - {}'.format(s.name, s.id))
    serv = servers.find_one({"server_id": s.id})
    if b.get_guild(s.id) is None: 
        servers.delete_one({'server_id': s.id})
        return
    spam = None
    log = None
    members = None
    if serv is not None:
        spam = serv.get("antispam") #antispam object from database
        log = serv.get("cyberlog") #cyberlog object from database
        members = serv.get("members")
    membIDs = [memb.id for memb in s.members]
    servers.update_one({"server_id": s.id}, {"$set": { #update database
    "name": s.name,
    "prefix": "." if serv is None or serv.get('prefix') is None else serv.get('prefix'),
    "thumbnail": str(s.icon_url),
    'offset': -4 if serv is None or serv.get('offset') is None else serv.get('offset'), #Distance from UTC time
    'tzname': 'EST' if serv is None or serv.get('tzname') is None else serv.get('tzname'), #Custom timezone name (EST by default)
    "channels": [{"name": channel.name, "id": channel.id} for channel in iter(s.channels) if type(channel) is discord.TextChannel],
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
        "channelExclusions": [] if log is None or log.get('channelExclusions') is None else log.get('channelExclusions'),
        'roleExclusions': [] if log is None or log.get('roleExclusions') is None else log.get('roleExclusions'),
        'memberExclusions': [] if log is None or log.get('memberExclusions') is None else log.get('memberExclusions'),
        'summarize': 0,# if log is None or log.get('summarize') is None else log.get('summarize'),
        'lastUpdate': datetime.datetime.utcnow() if serv is None or serv.get('lastUpdate') is None else serv.get('lastUpdate'),
        "message": vars(LogModule("message", "Send logs when a message is edited or deleted")) if log is None or log.get('message') is None else vars(LogModule("message", "Send logs when a message is edited or deleted").update(GetCyberMod(s, 'message'))),
        "doorguard": vars(LogModule("doorguard", "Send logs when a member joins or leaves server")) if log is None or log.get('doorguard') is None else vars(LogModule("doorguard", "Send logs when a member joins or leaves server").update(GetCyberMod(s, 'doorguard'))),
        "channel": vars(LogModule("channel", "Send logs when channel is created, edited, or deleted")) if log is None or log.get('channel') is None else vars(LogModule("channel", "Send logs when channel is created, edited, or deleted").update(GetCyberMod(s, 'channel'))),
        "member": vars(LogModule("member", "Send logs when member changes username or nickname, has roles added or removed, changes avatar, or changes discriminator")) if log is None or log.get('member') is None else vars(LogModule("member", "Send logs when member changes username or nickname, has roles added or removed, changes avatar, or changes discriminator").update(GetCyberMod(s, 'member'))),
        "role": vars(LogModule("role", "Send logs when a role is created, edited, or deleted")) if log is None or log.get('role') is None else vars(LogModule("role", "Send logs when a role is created, edited, or deleted").update(GetCyberMod(s, 'role'))),
        "emoji": vars(LogModule("emoji", "Send logs when emoji is created, edited, or deleted")) if log is None or log.get('emoji') is None else vars(LogModule("emoji", "Send logs when emoji is created, edited, or deleted").update(GetCyberMod(s, 'emoji'))),
        "server": vars(LogModule("server", "Send logs when server is updated, such as thumbnail")) if log is None or log.get('server') is None else vars(LogModule("server", "Send logs when server is updated, such as thumbnail").update(GetCyberMod(s, 'server'))),
        "voice": vars(LogModule('voice', "Send logs when members' voice chat attributes change")) if log is None or log.get('voice') is None else vars(LogModule('voice', "Send logs when members' voice chat attributes change").update(GetCyberMod(s, 'voice')))}}},upsert=True)
    membDict = {}
    serv = servers.find_one({"server_id": s.id})
    if serv is not None:
        spam = serv.get("antispam") #antispam object from database
        log = serv.get("cyberlog") #cyberlog object from database
        members = serv.get("members")
    for m in s.members: #Create dict 
        membDict[str(m.id)] = m.name
        membDict[m.name] = m.id
    for id in membIDs:
        member=None
        if members is not None:
            for m in members:
                if m.get('id') == id:
                    member=m
                    break
        try:
            servers.update_one({"server_id": s.id, "members.id": id}, {"$set": {
                "members.$.id": id,
                "members.$.name": membDict.get(str(id)),
                "members.$.warnings": spam.get('warn') if member is None else member.get('warnings'),
                "members.$.quickMessages": [] if member is None or member.get('quickMessages') is None else member.get('quickMessages'),
                "members.$.lastMessages": [] if member is None or member.get('lastMessages') is None else member.get('lastMessages')
            }}, True)
        except: #new member joined since last database refresh
            servers.update_one({'server_id': s.id}, {'$push': { 'members': {
                'id': id,
                'name': membDict.get(str(id)),
                'warnings': spam.get('warn'),
                'quickMessages': [],
                'lastMessages': []}}})

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
    return s.get_channel(servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("channel")) if servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("channel") is not None else s.get_channel(servers.find_one({"server_id": s.id}).get("cyberlog").get("defaultChannel"))

def GetMainLogChannel(s: discord.Guild):
    '''Returns the log channel associated with the server (general one), if one is set'''
    return s.get_channel(servers.find_one({"server_id": s.id}).get("cyberlog").get("defaultChannel"))

def GetCyberMod(s: discord.Guild, mod: str):
    '''Returns the specified module of the Cyberlog object'''
    return servers.find_one({"server_id": s.id}).get("cyberlog").get(mod)

def GetReadPerms(s: discord.Guild, mod: str):
    '''Return if the bot should read the server audit log for logs'''
    return GetCyberMod(s, mod).get("read")

def GetEnabled(s: discord.Guild, mod: str):
    '''Check if this module is enabled for the current server'''
    return GetCyberMod(s, mod).get("enabled") and servers.find_one({"server_id": s.id}).get("cyberlog").get('enabled') and (servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("channel") is not None or servers.find_one({"server_id": s.id}).get("cyberlog").get("defaultChannel") is not None) 

def SimpleGetEnabled(s: discord.Guild, mod: str):
    '''Check if this module is enabled for the current server (lightweight)
    REMEMBER THAT THIS DOESN'T MAKE SURE THAT THE CHANNEL IS VALID'''
    return servers.find_one({"server_id": s.id}).get("cyberlog").get(mod).get("enabled") and servers.find_one({"server_id": s.id}).get("cyberlog").get('enabled')

def GetImageLogPerms(s: discord.Guild):
    '''Check if image logging is enabled for the current server'''
    return servers.find_one({"server_id": s.id}).get("cyberlog").get('image')

def GetAntiSpamObject(s: discord.Guild):
    '''Return the Antispam database object - use 'get' to get the other objects'''
    return servers.find_one({"server_id": s.id}).get("antispam")

def GetCyberlogObject(s: discord.Guild):
    '''Return the cyberlog database object'''
    return servers.find_one({"server_id": s.id}).get("cyberlog")

def GetMembersList(s: discord.Guild):
    '''Return list of members DB entry objects for a server'''
    return servers.find_one({"server_id": s.id}).get("members")

def PauseMod(s: discord.Guild, mod):
    '''Pauses logging for a server'''
    servers.update_one({"server_id": s.id}, {"$set": {mod+".enabled": False}})

def ResumeMod(s: discord.Guild, mod):
    '''Resumes logging for a server'''
    servers.update_one({"server_id": s.id}, {"$set": {mod+".enabled": True}})

def GetServerCollection():
    '''Return servers collection object'''
    return servers

def GetAllServers():
    '''Return all servers...'''
    return servers.find()

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

def GetLogChannelExclusions(s: discord.Guild):
    '''Get the channel exclusions for the Cyberlog module'''
    return GetCyberlogObject(s).get("channelExclusions")

def GetRoleExclusions(s: discord.Guild):
    '''Not to be confused with DefaultRoleExclusions(). Returns server's role exclusions
    s: discord.Guild object (server) to get the exclusions from'''
    return GetAntiSpamObject(s).get("roleExclusions")

def GetLogRoleExclusions(s: discord.Guild):
    '''Get the role exclusions for the Cyberlog module'''
    return GetCyberlogObject(s).get("roleExclusions")

def GetMemberExclusions(s: discord.Guild):
    '''Not to be confused with DefaultMemberExclusions(). Returns server's member exclusions
    s: discord.Guild object (server) to get the exclusions from'''
    return GetAntiSpamObject(s).get("memberExclusions")

def GetLogMemberExclusions(s: discord.Guild):
    '''Get the member exclusions for the cyberlog module'''
    return GetCyberlogObject(s).get("memberExclusions")

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

def ManageRoles(member: discord.Member):
    '''Does this member have the Manage Roles permission'''
    for a in member.roles:
        if a.permissions.administrator or a.permissions.manage_roles:
            return True
    return False

def KickMembers(member: discord.Member):
    '''Does this member have the Kick Members permission'''
    for a in member.roles:
        if a.permissions.administrator or a.permissions.kick_members:
            return True
    return False

def BanMembers(member: discord.Member):
    '''Does this member have the Ban Members permission'''
    for a in member.roles:
        if a.permissions.administrator or a.permissions.ban_members:
            return True
    return False

def CheckCyberlogExclusions(channel: discord.TextChannel, member: discord.Member):
    '''Check to see if we shouldn't log a message delete event
    True to proceed
    False to not log'''
    if channel.id in GetLogChannelExclusions(channel.guild) or member.id in GetLogMemberExclusions(channel.guild):
        return False
    for role in member.roles:
        if role.id in GetLogRoleExclusions(channel.guild):
            return False
    return True

def DashboardManageServer(server: discord.Guild, member: discord.Member):
    '''Initialize dashboard permissions; which servers a member can manage'''
    for memb in server.members:
        if member.id == memb.id:
            return ManageServer(memb) or member.id == server.owner.id
    return False

def GetSummarize(s: discord.Guild, mod):
    '''Get the summarize value'''
    return GetCyberlogObject(s).get(mod).get('summarize') if GetCyberlogObject(s).get('summarize') != GetCyberlogObject(s).get(mod).get('summarize') else GetCyberlogObject(s).get('summarize')

def SummarizeEnabled(s: discord.Guild, mod):
    '''Is summarizing enabled for this module?'''
    return GetCyberlogObject(s).get('summarize') != 0 and GetCyberlogObject(s).get(mod).get('summarize') != 1

def GeneralSummarizeEnabled(s: discord.Guild):
    '''Is summarizing enabled for this server?'''
    return GetCyberlogObject(s).get('summarize') != 0

def StringifyPermissions(p: discord.Permissions):
    '''Turn a permissions object into a partially stringified version'''
    return [a[0] for a in iter(p) if a[1]]

def AppendSummary(s: discord.Guild, summary):
    '''Appends a Cyberlog.Summary object to a server's database entry'''
    servers.update_one({'server_id': s.id}, {'$push': {'summaries': vars(summary) }})

def GetSummary(s: discord.Guild, id: int):
    '''Return a summary object from a server and message ID'''
    return [a for a in servers.find_one({"server_id": s.id}).get('summaries') if a.get('id') == id][0]

def StringifyExtras(r: discord.Role):
    '''Turns a role into a partially stringified version for things like mentionable/displayed separately'''
    s = []
    if r.hoist: s.append('displayed separately')
    if r.mentionable: s.append('mentionable')
    return s

def StringifyBoth(r: discord.Role):
    '''Turns a role into a combination of the above two'''
    perms = StringifyPermissions(r.permissions)
    perms.extend(StringifyExtras(r))
    return perms

def ComparePerms(b: discord.Role, a: discord.Role):
    '''Bold or strikethrough differences'''
    bef = StringifyBoth(b)
    aft = StringifyBoth(a)
    s = []
    for perm in bef:
        if perm not in aft: s.append('~~{}~~'.format(perm))
        else: s.append(perm)
    for perm in aft:
        if perm not in bef and perm not in s: s.append('**{}**'.format(perm))
    return s

def UnchangedPerms(b: discord.Role, a: discord.Role):
    '''Only return things that aren't changed'''
    root = StringifyBoth(b)
    new = StringifyBoth(a)
    returns = []
    for r in root:
        if r in new: returns.append(r)
    return returns

def GetTimezone(s: discord.Guild):
    '''Return the timezone offset from UTC for a given server'''
    return servers.find_one({"server_id": s.id}).get('offset')

def GetNamezone(s: discord.Guild):
    '''Return the custom timezone name for a given server'''
    return servers.find_one({"server_id": s.id}).get('tzname')

def GetServer(s: discord.Guild):
    '''Return server object'''
    return servers.find_one({'server_id': s.id})

def SetLastUpdate(s: discord.Guild, d: datetime.datetime, mod: None):
    '''Update the last time a server was summarized, optional module argument'''
    if mod is None: servers.update_one({'server_id': s.id}, {'$set': {'cyberlog.lastUpdate': d}})
    else: servers.update_one({'server_id': s.id}, {'$set': {'cyberlog.'+mod+'.lastUpdate': d}})

def GetLastUpdate(s: discord.Guild, mod: None):
    '''Returns a datetime object representing the last time the server or a module was recapped'''
    if mod is None: return servers.find_one({"server_id": s.id}).get("cyberlog.lastUpdate")
    else: return GetCyberMod(s, mod).get('lastUpdate')

def GetOldestUpdate(s: discord.Guild, mods):
    '''Returns the oldest update date from a list of provided modules. Useful for when people configure different settings for different modules'''
    return min([GetLastUpdate(s, m) for m in mods]) + datetime.timedelta(hours=GetTimezone(s))

def UpdateChannel(channel: discord.abc.GuildChannel):
    '''Updates the channel.updated and channel.name attributes of the given channel. .updated is used for stats on channel edit'''
    servers.update_one({'server_id': channel.guild.id, 'allChannels.id': channel.id}, {'$set': {
        'allChannels.$.updated': datetime.datetime.utcnow(),
        'allChannels.$.name': channel.name,
        'allChannels.$.oldUpdate': GetChannelUpdate(channel)}})

def UpdateRole(role: discord.Role):
    '''Updates the role.updated and role.name attributes of the given role. .updated is used for stats on role edit'''
    servers.update_one({'server_id': role.guild.id, 'roles.id': role.id}, {'$set': {
        'roles.$.updated': datetime.datetime.utcnow(),
        'roles.$.name': role.name,
        'roles.$.oldUpdate': GetRoleUpdate(role)}})

def GetChannelUpdate(channel: discord.abc.GuildChannel):
    '''Returns the channel.updated attribute, which is the last time the channel was updated'''
    return [a.get('updated') for a in servers.find_one({'server_id': channel.guild.id}).get('allChannels') if a.get('id') == channel.id][0]

def GetOldChannelUpdate(channel: discord.abc.GuildChannel):
    '''Returns the channel.oldUpdate attribute, which is the time it was updated 2 times ago'''
    return [a.get('oldUpdate') for a in servers.find_one({'server_id': channel.guild.id}).get('allChannels') if a.get('id') == channel.id][0]

def GetRoleUpdate(role: discord.Role):
    '''Returns the role.updated attribute, which is the last time the role was updated'''
    return [a.get('updated') for a in servers.find_one({'server_id': role.guild.id}).get('roles') if a.get('id') == role.id][0]

def GetOldRoleUpdate(role: discord.Role):
    '''Returns the role.oldUpdate attribute, which is the time it was updated 2 times ago'''
    return [a.get('oldUpdate') for a in servers.find_one({'server_id': role.guild.id}).get('roles') if a.get('id') == role.id][0] 