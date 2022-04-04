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

lastVerifiedServer = {}
lastVerifiedUser = {}

def getDatabase(): return db

#yellow=0xffff00
# green=0x008000
# red=0xff0000
# blue=0x0000FF
yellow = (0xffff00, 0xffff66)
red = (0xff0000, 0xff6666)
green = (0x008000, 0x66ff66)
blue = (0x0000FF, 0x6666ff)

defaultAgeKickDM = ''''You have been kicked from **{}** temporarily due to their antispam configuration: Your account must be {} days old for you to join the server. You can rejoin the server **{} {}**.'.format(member.guild.name,
                    ageKick, canRejoin.strftime(formatter), timezone)'''

class LogModule(object):
    '''Used for consistent controlling of logging'''
    def __init__(self, name, description, embed=None, audit=None, enabled=True, summarize=0, channelID=None, color=None, library=None, thumbnail=None, author=None, emojiContext=None, hoverLinks=None, timestamp = None, botLogging=None, flashText = None, tts=None):
        self.name = name #name of module
        self.description = description #description of module
        self.plainText = embed #send logs in embed form? [ENABLED BY DEFAULT, other option being plaintext]
        self.read = audit #read audit logs to post who did the action (such as who created the channel)? [ENABLED BY DEFAULT, CUSTOMIZABLE LATER]
        self.enabled = enabled #is this module enabled?
        self.summarize = summarize #summarize logging (overwrite)
        self.channel = channelID #which channel is this sent to?
        self.color = color #custom color used for embeds
        self.advanced = None #enable advanced mode? [LATER]
        self.library = library #0 = all legacy, 1 = recommended, 2 = all fluent design
        self.thumbnail = thumbnail #0 = off, 1 = target, 2 = moderator or none, 3 = moderator or target
        self.author = author #0 = off, 1 = target, 2 = moderator or none, 3 = moderator or target
        self.context = emojiContext #0 = no emojis, 1 = emojis and descriptions, 2 = just emojis
        self.hoverLinks = hoverLinks #0: data hidden, 1: data under hover links, 2: data under hover links & option to expand, 3: data visible
        self.embedTimestamp = timestamp #0: All off, 1: Only description, 2: Only footer, 3: All on
        self.botLogging = 0 if name == 'message' else 1 if name == 'channel' else botLogging #To avoid spam | 0: Disabled, 1: Plaintext, 2: Embeds
        self.flashText = flashText
        self.tts = tts
        self.lastUpdate = datetime.datetime.utcnow()

    def update(self, entry): #Needs to be updated before releasing customization update due to naming differences
        result = vars(self)
        n = datetime.datetime.now()
        if entry:
            try:
                for k, v in dict(entry).items():
                    if f'{n:%m%d%Y}' != '02282021':
                        if k == 'embed': result['plainText'] = not entry['embed']
                        else: result[k] = v
            except: pass
        return result
    def convert(self, entry): #Takes a LogModule object and returns a NewLogModule object
        template = NewLogModule(entry.get('name'), entry.get('description'))
        template.update(entry)


class NewLogModule(object):
    '''
    Used for consistent controlling of logging
    
    One of these is kept for each individual log type, giving users insane flexibility over customization options

    1:08 AM 12/29 thought: Make a new object (or dict) for HTML form settings: enabled would be an object or dict, etc, they would all be in a list attached to each module
    '''
    def __init__(self, name, description, audit=True, enabled=True, channelID=None, tts=False, customMessage=None, customEmbed=None):
        self.name = name #name of module
        self.description = description #description of module
        self.read = audit #read audit logs to post who did the action (such as who created the channel)? [ENABLED BY DEFAULT]
        self.enabled = enabled #is this module enabled?
        self.channel = channelID #which channel is this sent to?
        self.tts = tts #Use text to speech for logging?
        self.useDefault = True #Use the default settings for embed/message apperance? Enabled by default
        self.customMessage = customMessage #The message content for custom logging, if enabled
        self.customEmbed = customEmbed #The embed for custom logging, if enabled
        self.children = [] #Children NewLogModule objects. Settings for this are applied to the children unless overwritten in the children. Children are displayed in a subcategory online.
        self.customSettings = [] #A dict of custom settings. These are formatted online as appropriate. Format is HTML form style.
        self.lastUpdate = datetime.datetime.utcnow()
    def update(self, entry): #Shorten database code line - input data from database, return updated object, updated object goes into database
        self.read = entry.get('read')
        self.enabled = entry.get('enabled')
        self.channel = entry.get('channel')
        self.tts = entry.get('tts', False)
        self.useDefault = entry.get('default', True)
        self.customMessage = entry.get('customMessage')
        self.customEmbed = entry.get('customEmbed')
        self.children = entry.get('children', [])
        self.customSettings = entry.get('customSettings', [])
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


'''Verification events'''
async def Verification(b: commands.Bot):
    '''Longest operation. Checks entire usable database *twice*, and verifies it's as it should be, creating entries as necessary'''
    await VerifyServers(b)
    await VerifyUsers(b)

async def VerifyServers(b: commands.Bot, newOnly=False, full=False):
    '''Ensures all servers have database entries; adding and removing as necessary'''
    '''First: Index all bot servers, and verify them'''
    await asyncio.gather(*[VerifyServer(s, b, newOnly, full) for s in b.guilds])

async def VerifyServer(s: discord.Guild, b: commands.Bot, newOnly=False, full=False, *, includeServer=True, includeMembers=True):
    '''Ensures that an individual server has a database entry, and checks all its variables'''
    '''First: Update operation verifies that server's variables are standard and up to date; no channels that no longer exist, for example, in the database'''
    if s.member_count > 250:
        global lastVerifiedServer
        if not lastVerifiedServer.get(s.id) or datetime.datetime.now() > lastVerifiedServer.get(s.id) + datetime.timedelta(minutes=5): #Make sure that large servers only go through this once every 5 mins
            lastVerifiedServer[s.id] = datetime.datetime.now()
        elif datetime.datetime.now() < lastVerifiedServer.get(s.id) + datetime.timedelta(minutes=5):
            return
    print('Verifying server: {} - {}'.format(s.name, s.id))
    started = datetime.datetime.now()
    serv = await servers.find_one({"server_id": s.id})
    if b.get_guild(s.id) is None: #If there's a server in the database the bot is no longer a part of, we can delete it
        await servers.delete_one({'server_id': s.id})
        return
    spam = None
    log = {}
    if serv:
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
    if (not serv or full) and includeServer:
        await servers.update_one({'server_id': s.id}, {"$set": { #add entry for new servers
        "name": s.name,
        "prefix": "." if serv is None or serv.get('prefix') is None else serv.get('prefix'),
        "thumbnail": str(s.icon_url),
        'offset': -4 if serv is None or serv.get('offset') is None else serv.get('offset'), #Distance from UTC time
        'tzname': 'EST' if serv is None or serv.get('tzname') is None else serv.get('tzname'), #Custom timezone name (EST by default)
        'jumpContext': False if serv is None or serv.get('jumpContext') is None else serv.get('jumpContext'), #Whether to provide context for posted message jump URL links
        'undoSuppression': False if not serv else serv.get('undoSuppression', False), #Whether to enable the undo functionality after a message's embed was collapsed
        'redditComplete': 0 if not serv else serv.get('redditComplete', 1), #Link to subreddits when /r/Reddit format is typed in a message. 0 = disabled, 1 = link only, 2 = link + embed
        'redditEnhance': (False, False) if not serv else serv.get('redditEnhance') if type(serv.get('redditEnhance')) is tuple else (False, False), #0: submission, 1: subreddit
        'birthday': 0 if serv is None or serv.get('birthday') is None else serv.get('birthday'), #Channel to send birthday announcements to
        'birthdate': datetime.datetime(2020, 1, 1, 12 + (-5 if serv is None or serv.get('offset') is None else serv.get('offset'))) if serv is None or serv.get('birthdate') is None else serv.get('birthdate'), #When to send bday announcements
        'birthdayMode': 0 if serv is None or serv.get('birthdayMode') is None else serv.get('birthdayMode'), #How to respond to automatic messages
        'colorTheme': 0 if not serv or not serv.get('colorTheme') else serv.get('colorTheme'), #Whether to use the new (more neon/brighter/less bold colors, value 1) or the regular more pastel yet saturated colors, value 0
        "channels": serverChannels,
        'server_id': s.id,
        "roles": [{"name": role.name, "id": role.id} for role in iter(s.roles) if not role.managed and not role.is_default()],
        'flags': {'firstBirthdayAnnouncement': False},
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
            'timedEvents': [] if serv is None or spam.get('timedEvents') is None else spam.get('timedEvents'), #Bans, mutes, etc
            'automuteRole': 0 if not spam else spam.get('automuteRole', 0)},
        "cyberlog": {
            "enabled": False if log is None or log.get('enabled') is None else log.get('enabled'),
            'ghostReactionEnabled': log.get('ghostReactionEnabled') or True,
            'disguardLogRecursion': log.get('disguardLogRecursion') or False, #Whether Disguard should clone embeds deleted in a log channel upon deletion. Enabling this makes it impossible to delete Disguard logs
            "image": False if log is None or log.get('image') is None else log.get('enabled'),
            "defaultChannel": None if log is None or log.get('defaultChannel') is None else log.get('defaultChannel'),
            'library': 1 if not log or not log.get('library') else log.get('library'), #0: all legacy, 1: recommended, 2: all new. *add an option to disable emoji, probably in the emoji display settinsg key*
            'thumbnail': 1 if not log or not log.get('thumbnail') else log.get('thumbnail'), #0: off, 1: target or none, 2: target or moderator, 3: moderator or none, 4: moderator or target
            'author': 3 if not log or not log.get('author') else log.get('author'), #0: off, 1: target or none, 2: target or moderator 3: moderator or none, 4: moderator or target
            'context': (1, 1) if not log or not log.get('context') else log.get('context'), #0 = no emojis, 1 = emojis and descriptions, 2 = just emojis. index 0 = title, index 1 = description
            'hoverLinks': 1 if not log or not log.get('hoverLinks') else log.get('hoverLinks'), #0: data hidden, 1: data under hover links, 2: data under hover links & option to expand, 3: data visible. LATER
            'embedTimestamp': 3 if not log or not log.get('embedTimestamp') else log.get('embedTimestamp'), #0: All off, 1: Just footer, 2: Just description, 3: All on
            'botLogging': log.get('botLogging') if f'{started:%m%d%Y}' != '02282021' else 2,                #0: Disabled, 1: Plaintext, 2: Embeds
            'color': ['auto', 'auto', 'auto'] if not log or not log.get('color') else log.get('color'),
            'plainText': False if not log or not log.get('plainText') else log.get('plainText'),
            'read': True if not log or not log.get('read') else log.get('read'),
            'flashText': False if not log or not log.get('flashText') else log.get('flashText'),
            'tts': False if not log or not log.get('tts') else log.get('tts'),
            'onlyVCJoinLeave': False if log is None or log.get('onlyVCJoinLeave') is None else log.get('onlyVCJoinLeave'),
            'onlyVCForceActions': True if log is None or log.get('onlyVCForceActions') is None else log.get('onlyVCForceActions'),
            'voiceChatLogRecaps': True if log is None or log.get('voiceChatLogRecaps') is None else log.get('voiceChatLogRecaps'),
            'ghostReactionTime': 10 if not log or not log.get('ghostReactionTime') else log.get('ghostReactionTime'),
            'memberGlobal': 2 if log is None or log.get('memberGlobal') is None else log.get('memberGlobal'),
            "channelExclusions": [] if log is None or log.get('channelExclusions') is None else log.get('channelExclusions'),
            'roleExclusions': [] if log is None or log.get('roleExclusions') is None else log.get('roleExclusions'),
            'memberExclusions': [] if log is None or log.get('memberExclusions') is None else log.get('memberExclusions'),
            'summarize': 0,# if log is None or log.get('summarize') is None else log.get('summarize'),
            'lastUpdate': datetime.datetime.utcnow() if serv is None or serv.get('lastUpdate') is None else serv.get('lastUpdate'),
            "message": vars(LogModule("message", "Send logs when a message is edited or deleted")) if log is None or log.get('message') is None else (LogModule("message", "Send logs when a message is edited or deleted").update(log.get('message'))),
            "doorguard": vars(LogModule("doorguard", "Send logs when a member joins or leaves server")) if log is None or log.get('doorguard') is None else (LogModule("doorguard", "Send logs when a member joins or leaves server").update(log.get('doorguard'))),
            "channel": vars(LogModule("channel", "Send logs when channel is created, edited, or deleted")) if log is None or log.get('channel') is None else (LogModule("channel", "Send logs when channel is created, edited, or deleted").update(log.get('channel'))),
            "member": vars(LogModule("member", "Send logs when member changes username or nickname, has roles added or removed, changes avatar, or changes discriminator")) if log is None or log.get('member') is None else (LogModule("member", "Send logs when member changes username or nickname, has roles added or removed, changes avatar, or changes discriminator").update(log.get('member'))),
            "role": vars(LogModule("role", "Send logs when a role is created, edited, or deleted")) if log is None or log.get('role') is None else (LogModule("role", "Send logs when a role is created, edited, or deleted").update(log.get('role'))),
            "emoji": vars(LogModule("emoji", "Send logs when emoji is created, edited, or deleted")) if log is None or log.get('emoji') is None else (LogModule("emoji", "Send logs when emoji is created, edited, or deleted").update(log.get('emoji'))),
            "server": vars(LogModule("server", "Send logs when server is updated, such as thumbnail")) if log is None or log.get('server') is None else (LogModule("server", "Send logs when server is updated, such as thumbnail").update(log.get('server'))),
            "voice": vars(LogModule('voice', "Send logs when members' voice chat attributes change")) if log is None or log.get('voice') is None else (LogModule('voice', "Send logs when members' voice chat attributes change").update(log.get('voice'))),
            "misc": vars(LogModule('misc', "Logging for various bonus features that don't fit into an above category (currently only ghost reaction logging)")) if log is None or log.get('misc') is None else (LogModule('misc', "Logging for various bonus features that don't fit into an above category").update(log.get('misc')))
        }}}, upsert=True)
    elif includeServer: #only update things that may have changed (on discord's side) if the server already exists; otherwise we're literally putting things back into the variable for no reason
        base = {} #Empty dict, to be added to when things need to be updated
        roleGen = [{'name': role.name, 'id': role.id} for role in iter(s.roles) if not role.managed and not role.is_default()]
        if s.name != serv['name']: base.update({'name': s.name})
        if str(s.icon_url) != serv['thumbnail']: base.update({'thumbnail': str(s.icon_url)})
        if serverChannels != serv['channels']: base.update({'channels': serverChannels})
        if roleGen != serv['roles']: base.update({'roles': roleGen})
        await servers.update_one({'server_id': s.id}, {"$set": base})
    if includeMembers:
        started2 = datetime.datetime.now()
        membDict = {}
        if not serv: serv = await servers.find_one({'server_id': s.id})
        if serv:
            spam = serv.get("antispam") #antispam object from database
            log = serv.get("cyberlog") #cyberlog object from database
            members = serv.get("members") or []
        else: return
        serverMembIDs = set()
        membersToUpdate = []
        for m in s.members: #Create dict 
            membDict[str(m.id)] = m.name
            #membDict[m.name] = m.id
            serverMembIDs.add(m.id)
            if len(members) < 1: membersToUpdate.append({'id': m.id, 'name': m.name, 'warnings': spam['warn']})
        if len(members) < 1: 
            await servers.update_one({'server_id': s.id}, {'$set': {'members': membersToUpdate}}, True)
        else: #Need to update existing members
            fullMembDict = {}
            for m in members: fullMembDict[m['id']] = m
            databaseMembIDs = set(m.get('id') for m in members)
            toInsert = []
            for m in serverMembIDs:
                if m not in databaseMembIDs:
                    #toInsert.append({'id': m, 'name': membDict[str(m)], 'warnings': spam['warn'], 'quickMessages': [], 'lastMessages': []}) #Add members that aren't in the database yet
                    fullMembDict[m] = {'id': m, 'name': membDict[str(m)], 'warnings': spam['warn']}
            #await servers.update_one({'server_id': s.id}, {"$push": {'members': {'$each': toInsert}}}, True)
            bulkUpdates = []
            bulkRemovals = []
            for member in members:
                serverMember = s.get_member(member['id'])
                if not serverMember:
                    #bulkRemovals.append(pymongo.UpdateOne({'server_id': s.id}, {'$pull': {'members': {'id': member['id']}}}))
                    fullMembDict.pop(member['id'])
                else:
                    #if serverMember.name != member['name']: bulkUpdates.append(pymongo.UpdateOne({'server_id': s.id, 'members.id': serverMember.id}, {'$set': {'members.$.name': serverMember.name}}))
                    if serverMember.name != member['name']: fullMembDict[member['id']].update({'name': serverMember.name})
            #if bulkUpdates or bulkRemovals: await servers.bulk_write(bulkUpdates + bulkRemovals, ordered=False)
            await servers.update_one({'server_id': s.id}, {'$set': {'members': list(fullMembDict.values())}})
    print(f'Verified Server {s.name}:\n Server only: {(started2 - started).seconds if includeServer else "N/A"}s\n Members only: {(datetime.datetime.now() - started2).seconds if includeMembers else "N/A"}s\n Total: {(datetime.datetime.now() - started).seconds}s')
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
    global lastVerifiedUser
    if not lastVerifiedUser.get(m.id) or datetime.datetime.now() > lastVerifiedUser.get(m.id) + datetime.timedelta(minutes=10):
        lastVerifiedUser[m.id] = datetime.datetime.now()
    elif datetime.datetime.now() < lastVerifiedUser.get(m.id) + datetime.timedelta(minutes=10):
        return
    if current and current.get('privacy'): 
        flags = current.get('flags', {})
        if flags.get('birthdayDataPurgeAnnouncement', -1) == -1: flags.update({'birthdayDataPurgeAnnouncement': False})
        #str(m.avatar_url_as(static_format='png', size=2048))
        #str(server.icon_url)
        await users.update_one({'user_id': m.id}, {'$set': {'username': m.name, 'avatar': str(m.avatar_url_as(static_format='png', size=2048)), 'flags': flags, 'servers': [{'server_id': server.id, 'name': server.name, 'thumbnail': str(server.icon_url)} for server in b.guilds if await DashboardManageServer(server, m)]}})
    else:
        await users.update_one({"user_id": m.id}, {"$set": { #For new members, set them up. For existing members, the only things that that may have changed that we care about here are the two fields above
        "username": m.name,
        #'discriminator': m.discriminator,
        "user_id": m.id,
        'avatar': str(m.avatar_url_as(static_format='png', size=2048)),
        'lastActive': {'timestamp': datetime.datetime.min, 'reason': 'Not tracked yet'},
        'lastOnline': datetime.datetime.min,
        'birthdayMessages': [],
        'wishlist': [],
        "servers": [{"server_id": server.id, "name": server.name, "thumbnail": str(server.icon_url)} for server in iter(b.guilds) if await DashboardManageServer(server, m)],
        # 'profile': {
        #     
        #     'bio': None,
        #     'tzoffset': -4,
        #     'tzname': 'EDT',
        #     'favColor': 0x000000,
        #     'colorTheme': 1, #0: Original, 1: New
        #     'name': '',
        # },
        'privacy': {
            'default': (1, 1), #Index 0 - 0: Disable features, 1: Enable features || Index 1 - 0: Hidden to others, 1: Visible to everyone, Array: List of user IDs allowed to view the profile
            'birthdayModule': (2, 2), #Index 0 - 0: Disable, 1: Enable, 2: Default || Index 1 - 0: Hidden, 1: Everyone, 2: Default, Array: Certain users || Applies to the next fields unless otherwise specified
            'age': (2, 2),
            'birthdayDay': (2, 2),
            'wishlist': (2, 2),
            'birthdayMessages': (2, 2), #Array of certain users is not applicable to this setting - this means when things are announced publicly in a server
            'attributeHistory': (2, 2),
            'customStatusHistory': (2, 2),
            'usernameHistory': (2, 2),
            'avatarHistory': (2, 2),
            'lastOnline': (2, 2),
            'lastActive': (2, 2),
            'profile': (2, 2),
            'bio': (2, 2),
            'timezone': (2, 2),
            'favColor': (2, 2),
            'colorTheme': (2, 2),
            'name': (2, 0)
        },
        'flags': {
            'birthdayDataPurgeAnnouncement': False,
            'usedFirstCommand': False,
            'announcedPrivacySettings': False,
        }
        }}, True)
    #print(f'Verified User {m.name} in {(datetime.datetime.now() - started).seconds}s')

async def DeleteServer(s, bot):
    if not bot.get_guild(s):
        await servers.delete_one({'server_id': s})

async def DeleteUser(u, bot):
    if not bot.get_user(u):
        await users.delete_one({'user_id': u})

async def GetLogChannel(s: discord.Guild, mod: str):
    '''Return the log channel associated with <mod> module'''
    return s.get_channel((await servers.find_one({"server_id": s.id})).get("cyberlog").get('modules')[await getModElement(s, mod)].get("channel")) if (await servers.find_one({"server_id": s.id})).get("cyberlog")[await getModElement(s, mod)].get("channel") is not None else s.get_channel((await servers.find_one({"server_id": s.id})).get("cyberlog").get("defaultChannel"))

async def SetSubLogChannel(s: discord.Guild, mod: str, channel: int):
    '''Sets the log channel associated with <mod> module. Not configured for beta data management revision.'''
    await servers.update_one({'server_id': s.id}, {'$set': {f'cyberlog.{mod}.channel': channel}})

async def GetMainLogChannel(s: discord.Guild):
    '''Returns the log channel associated with the server (general one), if one is set'''
    return s.get_channel(await (servers.find_one({"server_id": s.id})).get("cyberlog").get("defaultChannel"))

async def GetCyberMod(s: discord.Guild, mod: str):
    '''Returns the specified module of the Cyberlog object'''
    #return (await servers.find_one({"server_id": s.id})).get("cyberlog").get('modules')[await getModElement(s, mod)]
    return (await servers.find_one({"server_id": s.id})).get("cyberlog").get(mod)

async def GetReadPerms(s: discord.Guild, mod: str):
    '''Return if the bot should read the server audit log for logs'''
    return (await GetCyberMod(s, mod)).get("read")

async def GetEnabled(s: discord.Guild, mod: str):
    '''Check if this module is enabled for the current server'''
    #return (await GetCyberMod(s, mod)).get("enabled") and (await servers.find_one({"server_id": s.id})).get("cyberlog").get('enabled') and ((await servers.find_one({"server_id": s.id})).get("cyberlog")[await getModElement(s, mod)].get("channel") is not None or (await servers.find_one({"server_id": s.id})).get("cyberlog").get("defaultChannel") is not None) 
    return (await GetCyberMod(s, mod)).get("enabled") and (await servers.find_one({"server_id": s.id})).get("cyberlog").get('enabled') and ((await servers.find_one({"server_id": s.id})).get("cyberlog").get(mod).get("channel") is not None or (await servers.find_one({"server_id": s.id})).get("cyberlog").get("defaultChannel") is not None) 

async def SimpleGetEnabled(s: discord.Guild, mod: str):
    '''Check if this module is enabled for the current server (lightweight)
    REMEMBER THAT THIS DOESN'T MAKE SURE THAT THE CHANNEL IS VALID'''
    #return (await servers.find_one({"server_id": s.id})).get("cyberlog").get('modules')[await getModElement(s, mod)].get("enabled") and (await servers.find_one({"server_id": s.id})).get("cyberlog").get('enabled')
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

async def GetUserCollection():
    '''Returns the users collection object'''
    return users

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
    return await ManageServer(member)

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
    await users.update_one({'user_id': m.id}, {'$push': {'wishlist': entry}}, True)

async def SetWishlist(m: discord.Member, wishlist):
    '''Sets a member's wishlist to the specified list'''
    await users.update_one({'user_id': m.id}, {'$set': {'wishlist': wishlist}}, True)

async def GetWishlist(m: discord.Member):
    '''Return the wishlist of a member'''
    return (await users.find_one({'user_id': m.id})).get('wishlist')

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
    await users.update_one({'user_id': m.id}, {'$push': {'customStatusHistory': {'emoji': emoji, 'name': status, 'timestamp': datetime.datetime.utcnow()}}})

async def SetCustomStatusHistory(m: discord.Member, entries):
    '''Overwrites the member's custom status history list'''
    await users.update_one({'user_id': m.id}, {'$set': {'customStatusHistory': entries}})

async def AppendUsernameHistory(m: discord.User):
    '''Appends a username update to a user's listing of them'''
    await users.update_one({'user_id': m.id}, {'$push': {'usernameHistory': {'name': m.name, 'timestamp': datetime.datetime.utcnow()}}})

async def SetUsernameHistory(m: discord.User, entries):
    '''Overwrites the user's username history list'''
    await users.update_one({'user_id': m.id}, {'$set': {'usernameHistory': entries}})

async def AppendAvatarHistory(m: discord.User, url):
    '''Appends an avatar update to a user's listing of them. Old is the discord CDN avatar link used for comparisons, new is the permanent link from the image log channel (copy attachment)'''
    await users.update_one({'user_id': m.id}, {'$push': {'avatarHistory': {'discordURL': str(m.avatar_url), 'imageURL': url, 'timestamp': datetime.datetime.utcnow()}}})

async def SetAvatarHistory(m: discord.User, entries):
    '''Overwrites the user's avatar history list'''
    await users.update_one({'user_id': m.id}, {'$set': {'avatarHistory': entries}})

async def UnduplicateHistory(u: discord.User):
    '''Removes duplicate entries from a user's history lists'''
    userEntry = await users.find_one({'user_id': u.id})
    csh, uh, ah = [], [], []
    try:
        for c in userEntry.get('customStatusHistory'):
            if len(csh) > 0 and {'emoji': c.get('emoji'), 'name': c.get('name')} != {'emoji': csh[-1].get('emoji'), 'name': csh[-1].get('name')}: csh.append(c)
            elif len(csh) == 0: csh.append(c)
    except TypeError: pass
    try:
        for c in userEntry.get('usernameHistory'):
            if c.get('name') not in [i.get('name') for i in uh]: uh.append(c)
    except TypeError: pass
    try:
        for c in userEntry.get('avatarHistory'):
            if c.get('discordURL') not in [i.get('discordURL') for i in ah]: ah.append(c)
    except TypeError: pass
    customStatusPulls = []
    for c in csh:
        def inRange(time, comp): return comp >= time - datetime.timedelta(minutes=30) and comp <= time + datetime.timedelta(minutes=30)
        for e in userEntry['customStatusHistory']:
            if inRange(e['timestamp'], c['timestamp']): customStatusPulls.append(pymongo.UpdateOne({'user_id': u.id}, {'$pull': {'customStatusHistory': e}}))
    if customStatusPulls: await users.bulk_write(customStatusPulls)
    for c in csh: await users.update_one({'user_id': u.id}, {'$push': {'customStatusHistory': c}})
    for c in uh: 
        await users.update_one({'user_id': u.id}, {'$pull': {'usernameHistory': {'name': c.get('name')}}})
        await users.update_one({'user_id': u.id}, {'$push': {'usernameHistory': c}})
    for c in ah:
        await users.update_one({'user_id': u.id}, {'$pull': {'avatarHistory': {'discordURL': c.get('discordURL')}}})
        await users.update_one({'user_id': u.id}, {'$push': {'avatarHistory': c}})

async def ClearMemberMessages(s: discord.Guild):
    '''Empties the lastMessage and quickMessage lists belonging to members of the specified server'''
    bulkUpdates = [pymongo.UpdateOne({'server_id': s.id, 'members.id': m.id}, {'$set': {'members.$.lastMessages': [], 'members.$.quickMessages': []}}) for m in s.members]
    if bulkUpdates: await servers.bulk_write(bulkUpdates)

async def SetLastActive(u: discord.User, timestamp, reason):
    '''Updates the last active attribute'''
    await users.update_one({'user_id': u.id}, {'$set': {'lastActive': {'timestamp': timestamp, 'reason': reason}}})

async def SetLastOnline(u: discord.User, timestamp):
    '''Updates the last online attribute'''
    await users.update_one({'user_id': u.id}, {'$set': {'lastOnline': timestamp}})

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
 
async def CalculateGeneralChannel(g: discord.Guild, bot, update=False):
    '''Determines the most active channel based on indexed message count
    r: Whether to return the channel. If False, just set this to the database'''
    currentGeneralChannel = bot.lightningLogging[g.id].get('generalChannel', ())
    if not currentGeneralChannel or type(currentGeneralChannel) != list or False in currentGeneralChannel:
        channels = {}
        for c in g.text_channels:
            with open(f'Indexes/{g.id}/{c.id}.json') as f: channels[c] = len([v for v in json.load(f).values() if (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(v['timestamp0'])).days < 14]) #Most messages sent in last two weeks
        popular = max(channels, key = channels.get, default=0)
        if update: await servers.update_one({'server_id': g.id}, {'$set': {'generalChannel': (popular.id, False)}})
    else: popular = bot.get_channel(currentGeneralChannel[0])
    return popular

async def CalculateAnnouncementsChannel(g: discord.Guild, bot, update=False):
    '''Determines the announcement channel based on channel name and permissions
    r: Whether to return the channel. If False, just set this to the database'''
    currentAnnouncementsChannel = bot.lightningLogging[g.id].get('announcementsChannel', ())
    if not currentAnnouncementsChannel or type(currentAnnouncementsChannel) != list or False in currentAnnouncementsChannel:
        try: s = sorted([c for c in g.text_channels if 'announcement' in c.name.lower() and not c.overwrites_for(g.default_role).send_messages], key=lambda x: len(x.name) - len('announcements'))[0]
        except IndexError: return 0
        if update: await servers.update_one({'server_id': g.id}, {'$set': {'announcementsChannel': (s.id, False)}})
    else: s = bot.get_channel(currentAnnouncementsChannel[0])
    return s

async def CalculateModeratorChannel(g: discord.Guild, bot, update=False, *, logChannelID=0):
    '''Determines the moderator channel based on channel name and permissions
    r: Whether to return the channel. If False, just set this to the database'''
    currentModeratorChannel = bot.lightningLogging[g.id].get('moderatorChannel', ())
    if not currentModeratorChannel or type(currentModeratorChannel) != list or False in currentModeratorChannel:
        relevanceKeys = {}
        for c in g.text_channels:
            if not c.overwrites_for(g.default_role).read_messages and c.id != logChannelID: relevanceKeys.update({c: round(len([m for m in g.members if c.permissions_for(m).read_messages and c.permissions_for(m).send_messages]) * 100 / len([m for m in g.members if c.permissions_for(m).read_messages]))})
        for k in relevanceKeys:
            if any(word in k.name.lower() for word in ['mod', 'manager', 'staff', 'admin']): relevanceKeys[k] += 50
            if any(word in k.name.lower() for word in ['chat', 'discussion', 'talk']): relevanceKeys[k] += 10
            if 'announce' in k.name.lower(): relevanceKeys[k] = 1
        result = max(relevanceKeys, key=relevanceKeys.get, default=0)
        if update: await servers.update_one({'server_id': g.id}, {'$set': {'moderatorChannel': (result.id, False)}})
    else: result = bot.get_channel(currentModeratorChannel[0])
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

async def SetHSDaysOff(days):
    '''Updates the listing under the RicoViking9000 user entry for the custom schedule command for my friends at the high school I went to'''
    await users.update_one({'user_id': 247412852925661185}, {'$set': {'highSchoolDaysOffSpring2021': days}})

async def SetHSEventDays(days):
    '''Updates the listing under the RicoViking9000 user entry for the custom schedule command for my friends at the high school I went to'''    
    await users.update_one({'user_id': 247412852925661185}, {'$set': {'highSchoolEventDaysSpring2021': days}})

async def SetWarnings(members, warnings):
    bulkUpdates = [pymongo.UpdateOne({'server_id': members[0].guild.id, 'members.id': member.id}, {'$set': {'members.$.warnings': warnings}}) for member in members]
    await servers.bulk_write(bulkUpdates)

async def SetMuteRole(s: discord.Guild, r: discord.Role):
    '''Sets the automute role for a server'''
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.automuteRole': r.id}})

async def SetMuteCache(s: discord.Guild, members, rlist):
    '''Stores a list of roles to a member's database cache to be used to unmute in the future'''
    updates = [pymongo.UpdateOne({'server_id': s.id, 'members.id': m.id}, {'$set': {'members.$.roleCache': [r.id for r in rlist[m.id]] if type(rlist) is dict else []}}) for m in members]
    await servers.bulk_write(updates)

async def SetPermissionsCache(s: discord.Guild, members, plist):
    '''Stores a list of permission overwrites to a member's database cache to be used to unmute in the future'''
    updates = [pymongo.UpdateOne({'server_id': s.id, 'members.id': m.id}, {'$set': {'members.$.permissionsCache': plist[str(m.id)] if type(plist) is not list else {}}}) for m in members]
    await servers.bulk_write(updates)

async def AdjustDST(s: discord.Guild):
    server = await GetServer(s)
    offset = server['offset']
    tzname = server['tzname']
    if offset in [-5, -6, -7, -8]: #SPRING FORWARD
        if not (offset == -4 and tzname == 'EST'): 
            await servers.update_one({'server_id': s.id}, {'$inc': {'offset': 1}})
            return True
    return False

async def GetBirthdayList():
    '''Returns the global birthday dictionary'''
    return (await disguard.find_one({})).get('birthdays')

async def UpdateBirthdayList(u: discord.User, d: datetime.datetime):
    '''Adds a member's birthday to the global dictionary'''
    birthdayList = await GetBirthdayList()
    if not birthdayList: birthdayList = {}
    try: birthdayList[d.strftime('%m/%d/%Y')].append({u.id: d})
    except KeyError: birthdayList[d.strftime('%m/%d/%Y')] = [{u.id: d}]
    await disguard.update_one({}, {'$set': {'birthdays': birthdayList}}, True)

