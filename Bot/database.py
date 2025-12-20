"""Contains code that manages the MongoDB cloud database during Disguard's operation"""

import asyncio
import datetime
import logging
import typing

import discord
import motor.motor_asyncio
import pymongo
from bson.codec_options import CodecOptions

logger = logging.getLogger('discord')

from discord.ext import commands
from pymongo import errors

import lightningdb
import secure
import utility

mongo: motor.motor_asyncio.AsyncIOMotorClient = None
db: motor.motor_asyncio.AsyncIOMotorDatabase = None
servers: motor.motor_asyncio.AsyncIOMotorCollection = None
users: motor.motor_asyncio.AsyncIOMotorCollection = None
disguard: motor.motor_asyncio.AsyncIOMotorCollection = None

lastVerifiedServer = {}
lastVerifiedUser = {}


def getDatabase():
    return db


yellow = (0xFFFF00, 0xFFFF66)
red = (0xFF0000, 0xFF6666)
green = (0x008000, 0x66FF66)
blue = (0x0000FF, 0x6666FF)
bot: commands.Bot = None

defaultAgeKickDM = """'You have been kicked from **{}** temporarily due to their antispam configuration: Your account must be {} days old for you to join the server. You can rejoin the server **{} {}**.'.format(member.guild.name,
                    ageKick, canRejoin.strftime(formatter), timezone)"""


class LogModule(object):
    """Used for consistent controlling of logging"""

    def __init__(
        self,
        name,
        description,
        embed=None,
        audit=None,
        enabled=True,
        summarize=0,
        channelID=None,
        color=None,
        library=None,
        thumbnail=None,
        author=None,
        emojiContext=None,
        hoverLinks=None,
        timestamp=None,
        botLogging=None,
        flashText=None,
        tts=None,
    ):
        self.name = name  # name of module
        self.description = description  # description of module
        self.plainText = embed  # send logs in embed form? [ENABLED BY DEFAULT, other option being plaintext]
        self.read = audit  # read audit logs to post who did the action (such as who created the channel)? [ENABLED BY DEFAULT, CUSTOMIZABLE LATER]
        self.enabled = enabled  # is this module enabled?
        self.summarize = summarize  # summarize logging (overwrite)
        self.channel = channelID  # which channel is this sent to?
        self.color = color  # custom color used for embeds
        self.advanced = None  # enable advanced mode? [LATER]
        self.library = library  # 0 = all legacy, 1 = recommended, 2 = all fluent design
        self.thumbnail = thumbnail  # 0 = off, 1 = target, 2 = moderator or none, 3 = moderator or target
        self.author = author  # 0 = off, 1 = target, 2 = moderator or none, 3 = moderator or target
        self.context = emojiContext  # 0 = no emojis, 1 = emojis and descriptions, 2 = just emojis
        self.hoverLinks = hoverLinks  # 0: data hidden, 1: data under hover links, 2: data under hover links & option to expand, 3: data visible
        self.embedTimestamp = timestamp  # 0: All off, 1: Only description, 2: Only footer, 3: All on
        self.botLogging = 0 if name == 'message' else 1 if name == 'channel' else botLogging  # To avoid spam | 0: Disabled, 1: Plaintext, 2: Embeds
        self.flashText = flashText
        self.tts = tts
        self.lastUpdate = discord.utils.utcnow()

    def update(self, entry):  # Needs to be updated before releasing customization update due to naming differences
        result = vars(self)
        if entry:
            try:
                for k, v in dict(entry).items():
                    if k == 'embed':
                        result['plainText'] = not entry['embed']
                    else:
                        if v == 'on':
                            result[k] = True
                        else:
                            result[k] = v
            except Exception:
                pass
        return result

    def convert(self, entry):  # Takes a LogModule object and returns a NewLogModule object
        template = NewLogModule(entry.get('name'), entry.get('description'))
        template.update(entry)


class NewLogModule(object):
    """
    Used for consistent controlling of logging

    One of these is kept for each individual log type, giving users insane flexibility over customization options

    1:08 AM 12/29 thought: Make a new object (or dict) for HTML form settings: enabled would be an object or dict, etc, they would all be in a list attached to each module
    """

    def __init__(self, name, description, audit=True, enabled=True, channelID=None, tts=False, customMessage=None, customEmbed=None):
        self.name = name  # name of module
        self.description = description  # description of module
        self.read = audit  # read audit logs to post who did the action (such as who created the channel)? [ENABLED BY DEFAULT]
        self.enabled = enabled  # is this module enabled?
        self.channel = channelID  # which channel is this sent to?
        self.tts = tts  # Use text to speech for logging?
        self.useDefault = True  # Use the default settings for embed/message apperance? Enabled by default
        self.customMessage = customMessage  # The message content for custom logging, if enabled
        self.customEmbed = customEmbed  # The embed for custom logging, if enabled
        self.children = []  # Children NewLogModule objects. Settings for this are applied to the children unless overwritten in the children. Children are displayed in a subcategory online.
        self.customSettings = []  # A dict of custom settings. These are formatted online as appropriate. Format is HTML form style.
        self.lastUpdate = discord.utils.utcnow()

    def update(self, entry):  # Shorten database code line - input data from database, return updated object, updated object goes into database
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


def initialize(token):
    """Configure the database based on if bot is Disguard or Disguard Beta"""
    global mongo
    global db
    global servers
    global users
    global disguard
    mongo = motor.motor_asyncio.AsyncIOMotorClient(secure.mongo())
    if token == secure.token():
        db = mongo.disguard.with_options(codec_options=CodecOptions(tz_aware=True))
    elif token == secure.beta():
        db = mongo.disguard_beta.with_options(codec_options=CodecOptions(tz_aware=True))
    servers = db.servers
    users = db.users
    disguard = db.disguard


"""Verification events"""


async def Verification(b: commands.Bot):
    """Verifies everything (all servers and users)"""
    verify_servers = VerifyServers(b, b.guilds, full=True)
    await asyncio.wait_for(verify_servers, timeout=None)
    verify_users = VerifyUsers(b, list(b.get_all_members()), full=True)
    await asyncio.wait_for(verify_users, timeout=None)
    # await VerifyServers(b, b.guilds, full=True)
    # await VerifyUsers(b, list(b.get_all_members()), full=True)
    print(f'Finished verification for {len(b.guilds)} servers and {len(list(b.get_all_members()))} users')
    logger.info(f'Finished verification for {len(b.guilds)} servers and {len(list(b.get_all_members()))} users')


async def VerifyServers(b: commands.Bot, servs: typing.List[discord.Guild], full=False):
    """Creates, updates, or deletes database entries for Disguard's servers as necessary"""
    # build set of current guild ids (small memory)
    current_guild_ids = {s.id for s in servs}

    # handle servers that exist in memory but not in DB (create)
    for server in servs:
        if not await servers.find_one({'server_id': server.id}):
            # yield_members generator kept minimal
            async def _yield_members(s):
                for m in s.members:
                    yield m

            await VerifyServer(server, b, mode='update', includeServer=True, includeMembers=_yield_members(server))

    # stream DB servers and update existing ones
    async for db_server in servers.find({'server_id': {'$in': list(current_guild_ids)}}):
        guild = b.get_guild(db_server['server_id'])
        if not guild:
            continue
        try:
            await lightningdb.post_server(db_server)
        except errors.DuplicateKeyError:
            if full:
                await lightningdb.patch_server(guild.id, db_server)
        except Exception as e:
            logger.exception('VerifyServers: lightningdb.post_server error: %s', e)

        # call VerifyServer for the live guild; pass db document to avoid re-fetching
        await VerifyServer(guild, b, serv=db_server, full=full, mode='update', includeMembers=(m for m in guild.members))

    # delete DB entries for servers the bot left
    await servers.delete_many({'server_id': {'$nin': list(current_guild_ids)}})


async def VerifyServer(
    s: discord.Guild,
    b: commands.Bot,
    serv: dict | None = None,
    full: bool = False,
    new: bool = False,
    *,
    mode: str = 'update',
    includeServer: bool = True,
    includeMembers: typing.Iterable[discord.Member] | None = None,
    parallel: bool = True,
):
    """Ensures that a server has a database entry, and checks/updates all its variables & members
    newOnly: if True, only create new servers
    full: if True, go over all variables even for existing servers
    mode: update = update serially in this method, return = return update operations to be performed in bulk from an external method
    includeServer: if True, update server variables if applicable
    includeMembers: update the members whose IDs are specified, if any
    """
    print(f'Verifying server: {s.name} - {s.id}')
    logger.info(f'Verifying server: {s.name} - {s.id}')
    started = datetime.datetime.now()
    global bot
    bot = b

    if serv is None and not new:
        serv = await servers.find_one({'server_id': s.id}) or {}
    serv = serv or {}

    spam = serv.get('antispam', {})
    log = serv.get('cyberlog', {})

    # build channels list
    serverChannels: list[dict] = []
    categoriesAdded: list[int] = []
    for category, channels in s.by_category():
        cid = category.id if category else 0
        if cid not in categoriesAdded:
            serverChannels.append({'name': f'-----{category.name if category else "NO CATEGORY"}-----', 'id': cid})
            categoriesAdded.append(cid)
        serverChannels += [{'name': channel.name, 'id': channel.id} for channel in channels if isinstance(channel, discord.TextChannel)]

    update_ops: list[pymongo.UpdateOne] = []

    # If server missing (new) or full requested, build full $set with all original field names so upsert creates full entry
    if (not serv or full) and includeServer:
        full_set = {
            'name': s.name,
            'prefix': serv.get('prefix', '.'),
            'thumbnail': s.icon.with_static_format('png').with_size(512).url if s.icon else '',
            'offset': serv.get('offset', utility.daylightSavings() * -1),
            'tzname': serv.get('tzname', 'EST'),
            'jumpContext': serv.get('jumpContext', False),
            'undoSuppression': serv.get('undoSuppression', False),
            'redditComplete': serv.get('redditComplete', 0),
            'redditEnhance': (False, False)
            if serv.get('redditEnhance') == 0
            else (True, False)
            if serv.get('redditEnhance') == 1
            else (False, True)
            if serv.get('redditEnhance') == 2
            else (True, True)
            if serv.get('redditEnhance') == 3
            else serv.get('redditEnhance', (True, True)),
            'birthdayChannel': serv.get('birthdayChannel') or serv.get('birthday', 0),
            'birthdate': serv.get('birthdate', datetime.datetime(started.year, 1, 1, 12 - utility.daylightSavings())),
            'birthdayMode': serv.get('birthdayMode', 1),
            'colorTheme': serv.get('colorTheme', 0),
            'channels': serverChannels,
            'server_id': s.id,
            'roles': [{'name': role.name, 'id': role.id} for role in iter(s.roles) if not role.managed and not role.is_default()],
            'flags': {},
            'announcementsChannel': serv.get('announcementsChannel', (0, False)),
            'moderatorChannel': serv.get('moderatorChannel', (0, False)),
            'generalChannel': serv.get('generalChannel', (0, False)),
            'antispam': {
                'enabled': spam.get('enabled', False),
                'whisper': spam.get('whisper', False),
                'log': spam.get('log', 0),
                'warn': spam.get('warn', 3),
                'delete': 1 if spam.get('delete') is False else 3 if spam.get('delete') is True else spam.get('delete', 3),
                'muteTime': spam.get('muteTime', 300),
                'action': spam.get('action', 1),
                'customRoleID': spam.get('customRoleID', None),
                'congruent': spam.get('congruent', [4, 7, 300]),
                'emoji': spam.get('emoji', 0),
                'mentions': spam.get('mentions', 3),
                'selfbot': spam.get('selfbot', True),
                'caps': spam.get('caps', 0),
                'links': spam.get('links', False),
                'attachments': spam.get('attachments', [False] * 9),
                'invites': spam.get('invites', False),
                'everyoneTags': spam.get('everyoneTags', 2),
                'hereTags': spam.get('hereTags', 2),
                'roleTags': spam.get('roleTags', 3),
                'quickMessages': spam.get('quickMessages', [5, 10]),
                'consecutiveMessages': spam.get('consecutiveMessages', [10, 120]),
                'repeatedJoins': spam.get('repeatedJoins', [0, 300, 86400]),
                'ignoreRoled': spam.get('ignoreRoled', False),
                'exclusionMode': spam.get('exclusionMode', 1),
                'channelExclusions': spam.get('channelExclusions', await DefaultChannelExclusions(s)),
                'roleExclusions': spam.get('roleExclusions', await DefaultRoleExclusions(s)),
                'memberExclusions': spam.get('memberExclusions', await DefaultMemberExclusions(s)),
                'profanityEnabled': spam.get('profanityEnabled', False),
                'profanityTolerance': spam.get('profanityTolerance', 0),
                'filter': spam.get('filter', []),
                'ageKick': spam.get('ageKick', None),
                'ageKickDM': spam.get('ageKickDM', defaultAgeKickDM),
                'ageKickWhitelist': spam.get('ageKickWhitelist', []),
                'warmup': spam.get('warmup', 0),
                'timedEvents': spam.get('timedEvents', []),
                'automuteRole': spam.get('automuteRole', 0),
            },
            'cyberlog': {
                'enabled': log.get('enabled', False),
                'ghostReactionEnabled': log.get('ghostReactionEnabled', True),
                'disguardLogRecursion': log.get('disguardLogRecursion', False),
                'indexing': log.get('indexing', log.get('enabled', True)),
                'image': log.get('image', False),
                'sendIndexFile': log.get('sendIndexFile', True),
                'storageCap': log.get('storageCap', 20),
                'messageLogsBotAuthor': log.get('messageLogsBotAuthor', 0),
                'defaultChannel': log.get('defaultChannel', None),
                'library': log.get('library', 1),
                'thumbnail': log.get('thumbnail', 1),
                'author': log.get('author', 3),
                'context': log.get('context', (1, 1)),
                'hoverLinks': log.get('hoverLinks', 1),
                'embedTimestamp': log.get('embedTimestamp', 2),
                'botLogging': 0 if log.get('botLogging') is None else log.get('botLogging', 0),
                'color': log.get('color', ('auto', 'auto', 'auto')),
                'plainText': log.get('plainText', False),
                'read': log.get('read', True),
                'flashText': log.get('flashText'),
                'tts': log.get('tts'),
                'onlyVCJoinLeave': log.get('onlyVCJoinLeave', False),
                'onlyVCForceActions': log.get('onlyVCForceActions', True),
                'voiceChatLogRecaps': log.get('voiceChatLogRecaps', True),
                'ghostReactionTime': log.get('ghostReactionTime', 10),
                'memberGlobal': log.get('memberGlobal', 2),
                'channelExclusions': log.get('channelExclusions', []),
                'roleExclusions': log.get('roleExclusions', []),
                'memberExclusions': log.get('memberExclusions', []),
                'lastUpdate': serv.get('lastUpdate', discord.utils.utcnow()),
                'message': LogModule('message', 'Send logs when a message is edited or deleted').update(log.get('message', {})),
                'doorguard': LogModule('doorguard', 'Send logs when a member joins or leaves server').update(log.get('doorguard', {})),
                'channel': LogModule('channel', 'Send logs when channel is created, edited, or deleted').update(log.get('channel', {})),
                'member': LogModule(
                    'member',
                    'Send logs when member changes username or nickname, has roles added or removed, changes avatar, or changes discriminator',
                ).update(log.get('member', {})),
                'role': LogModule('role', 'Send logs when a role is created, edited, or deleted').update(log.get('role', {})),
                'emoji': LogModule('emoji', 'Send logs when emoji is created, edited, or deleted').update(log.get('emoji', {})),
                'server': LogModule('server', 'Send logs when server is updated, such as thumbnai').update(log.get('server', {})),
                'voice': LogModule('voice', "Send logs when members' voice chat attributes change").update(log.get('voice', {})),
                'misc': LogModule('misc', "Logging for various bonus features that don't fit into an above category").update(log.get('misc', {})),
            },
        }
        # perform actual write or prepare UpdateOne
        if mode == 'update':
            await servers.update_one({'server_id': s.id}, {'$set': full_set}, upsert=True)
        else:
            update_ops.append(pymongo.UpdateOne({'server_id': s.id}, {'$set': full_set}, upsert=True))

    elif includeServer:
        # existing server: only set fields that changed
        base: dict = {}
        roleGen = [{'name': role.name, 'id': role.id} for role in iter(s.roles) if not role.managed and not role.is_default()]
        if serv.get('name') != s.name:
            base['name'] = s.name
        thumbnail = s.icon.with_static_format('png').with_size(512).url if s.icon else ''
        if serv.get('thumbnail') != thumbnail:
            base['thumbnail'] = thumbnail
        if serverChannels != serv.get('channels'):
            base['channels'] = serverChannels
        if roleGen != serv.get('roles'):
            base['roles'] = roleGen
        if base:
            if mode == 'update':
                await servers.update_one({'server_id': s.id}, {'$set': base})
            else:
                update_ops.append(pymongo.UpdateOne({'server_id': s.id}, {'$set': base}))

    # handle members
    started2 = datetime.datetime.now()
    if includeMembers:
        results = await VerifyMembers(s, includeMembers, serv, mode=mode, parallel=parallel)
        if mode == 'return' and results:
            # VerifyMembers returns UpdateOne list when mode=='return'
            update_ops += results
    started3 = datetime.datetime.now()

    # If mode == 'update', nothing else to do (we already wrote changes)
    # If mode == 'return', return collected UpdateOne operations
    print(
        f'Verified Server {s.name}:\n Preparation: {(started2 - started).seconds}s\n Member updates: {(started3 - started2).seconds}s\n Database write: {(datetime.datetime.now() - started3).seconds}s\n Total: {(datetime.datetime.now() - started).seconds}s'
    )
    logger.info(
        f'Verified Server {s.name}:\n Preparation: {(started2 - started).seconds}s\n Member updates: {(started3 - started2).seconds}s\n Database write: {(datetime.datetime.now() - started3).seconds}s\n Total: {(datetime.datetime.now() - started).seconds}s'
    )

    if mode == 'return':
        return update_ops


async def VerifyMembers(
    s: discord.Guild, members: typing.Iterable[discord.Member], serv=None, *, mode='update', parallel=True, chunk_size: int = 1000
):
    """Verifies multiple server members

    This version avoids building a massive in-memory dict by writing members
    to the DB in batches using bulk_write.
    """
    if not serv:
        serv = (await servers.find_one({'server_id': s.id})) or {}
    antispam = serv.get('antispam', {})
    warnings_default = antispam.get('warn', 3)

    db_memb = serv.get('members', {})
    # convert legacy list format to dict without deepcopy (only if needed)
    if isinstance(db_memb, list):
        db_memb = {str(m['id']): {'name': m.get('name'), 'warnings': m.get('warnings', warnings_default)} for m in db_memb}

    ops: list[pymongo.UpdateOne] = []
    results_ops: list[pymongo.UpdateOne] | None = [] if mode == 'return' else None

    count = 0
    for member in members:
        member_id = str(member.id)
        warnings_val = db_memb.get(member_id, {}).get('warnings', warnings_default)
        member_doc = {'name': member.name, 'warnings': warnings_val}
        op = pymongo.UpdateOne({'server_id': s.id}, {'$set': {f'members.{member_id}': member_doc}})
        if mode == 'return':
            results_ops.append(op)
        else:
            ops.append(op)
            count += 1
            if count >= chunk_size:
                await servers.bulk_write(ops, ordered=not parallel)
                ops.clear()
                count = 0

    # flush remaining ops
    if mode != 'return' and ops:
        await servers.bulk_write(ops, ordered=not parallel)

    if mode == 'return':
        return results_ops


async def VerifyUsers(b: commands.Bot, usrs: typing.List[discord.User], full=False, *, chunk_size: int = 500):
    """Ensures every global Discord user in a bot server has one unique entry, and ensures everyone's attributes are up to date.

    Processes users in chunks to reduce peak memory usage.
    """
    print(f'Verifying {len(usrs)} users...')
    logger.info(f'Verifying {len(usrs)} users...')
    start_time = datetime.datetime.now()

    # iterate in chunks so we don't build huge dicts or load massive DB query results
    update_ops: list[pymongo.UpdateOne] = []
    updated_users = set()

    # helper to flush ops to DB in chunks
    async def _flush_ops(ops: list[pymongo.UpdateOne]):
        if not ops:
            return
        await users.bulk_write(ops, ordered=False)
        ops.clear()

    # process in batches
    for i in range(0, len(usrs), chunk_size):
        batch = usrs[i : i + chunk_size]
        batch_ids = [u.id for u in batch]
        # fetch only the DB users that correspond to this batch
        db_batch = await users.find({'user_id': {'$in': batch_ids}}).to_list(None)
        db_user_map = {d['user_id']: d for d in db_batch}

        # add new users in this batch
        for u in batch:
            if u.id not in db_user_map:
                # re-use VerifyUser in 'return' mode to collect ops (hopefully small per user)
                ops = await VerifyUser(u, b, mode='return', new=True)
                if ops:
                    update_ops.extend(ops)
                updated_users.add(u.id)
                # flush periodically to keep memory down
                if len(update_ops) >= 1000:
                    await _flush_ops(update_ops)

        # update existing users in this batch
        for db_user in db_batch:
            uid = db_user['user_id']
            if uid in updated_users:
                continue
            u = next((x for x in batch if x.id == uid), None)
            if u is None:
                continue
            try:
                await lightningdb.post_user(db_user)
            except errors.DuplicateKeyError:
                if full:
                    await lightningdb.patch_user(u.id, db_user)
            except (AttributeError, KeyError, TypeError):
                pass
            ops = await VerifyUser(u, b, db_user, full, True, mode='return')
            if ops:
                update_ops.extend(ops)
            updated_users.add(uid)
            if len(update_ops) >= 1000:
                await _flush_ops(update_ops)

    # final flush of any remaining ops
    await _flush_ops(update_ops)

    # Delete users not in the bot's mutual servers.
    # If the total user list is huge and cannot be passed directly to $nin,
    # consider an alternative approach (mark-and-sweep or temporary collection).
    all_ids = [u.id for u in usrs]
    if all_ids:
        await users.delete_many({'user_id': {'$nin': all_ids}})

    print(f'Verified {len(updated_users)} users')
    logger.info(f'Verified {len(updated_users)} users in {(datetime.datetime.now() - start_time)} delta')


async def VerifyUser(u: discord.User, b: commands.Bot, current={}, full=False, new=False, *, mode='update', parallel=True):
    """Ensures that an individual user is in the database, and checks their variables"""
    # started = datetime.datetime.now()
    if not new and not current:
        current = await users.find_one({'user_id': u.id}) or {}
    # if b.get_user(m.id) is None: return await users.delete_one({'user_id': m.id})
    updateOperations: list[pymongo.UpdateOne] = []
    if full or not current:
        update_document = {
            'user_id': u.id,
            'lastActive': current.get('lastActive', {'timestamp': datetime.datetime.min, 'reason': 'Not tracked yet'}),
            'lastOnline': current.get('lastOnline', datetime.datetime.min),
            'birthdayMessages': current.get('birthdayMessages', []),
            'wishlist': current.get('wishlist', []),
            'servers': [
                {
                    'server_id': server.id,
                    'name': server.name,
                    'thumbnail': server.icon.with_static_format('png').with_size(512).url if server.icon else '',
                }
                for server in u.mutual_guilds
                if utility.ManageServer(server.get_member(u.id))
            ]
            if u.id != b.user.id
            else [],  # d.py V2.0
            'privacy': {
                'default': current.get('privacy', {}).get(
                    'default', (1, 1)
                ),  # Index 0 - 0: Disable features, 1: Enable features || Index 1 - 0: Hidden to others, 1: Visible to everyone, Array: List of user IDs allowed to view the profile
                'birthdayModule': current.get('privacy', {}).get(
                    'birthdayModule', (2, 2)
                ),  # Index 0 - 0: Disable, 1: Enable, 2: Default || Index 1 - 0: Hidden, 1: Everyone, 2: Default, Array: Certain users || Applies to the next fields unless otherwise specified
                'age': current.get('privacy', {}).get('age', (2, 2)),
                'birthdayDay': current.get('privacy', {}).get('birthdayDay', (2, 2)),
                'wishlist': current.get('privacy', {}).get('wishlist', (2, 2)),
                'birthdayMessages': current.get('privacy', {}).get(
                    'birthdayMessages', (2, 2)
                ),  # Array of certain users is not applicable to this setting - this means when things are announced publicly in a server
                'attributeHistory': current.get('privacy', {}).get('attributeHistory', (2, 2)),
                'statusHistory': current.get('privacy', {}).get('statusHistory', current.get('privacy', {}).get('customStatusHistory', (0, 2))),
                'usernameHistory': current.get('privacy', {}).get('usernameHistory', (0, 2)),
                'displaynameHistory': current.get('privacy', {}).get('displaynameHistory', (0, 2)),
                'avatarHistory': current.get('privacy', {}).get('avatarHistory', (0, 2)),
                'lastOnline': current.get('privacy', {}).get('lastOnline', (2, 2)),
                'lastActive': current.get('privacy', {}).get('lastActive', (2, 2)),
                'profile': current.get('privacy', {}).get('profile', (2, 2)),
            },
            'flags': {
                'usedFirstCommand': current.get('flags', {}).get('usedFirstCommand', False),
            },
        }
        updateOperations.append(
            pymongo.UpdateOne(
                {'user_id': u.id},
                {'$set': update_document},
                True,
            )
        )
        await lightningdb.patch_user(u.id, update_document)
    else:
        base = {}
        serverGen = [
            {'server_id': server.id, 'name': server.name, 'thumbnail': str(server.icon.with_static_format('png').url)}
            for server in u.mutual_guilds
            if utility.ManageServer(server.get_member(u.id))
        ]  # d.py V2.0
        if serverGen != current['servers']:
            base.update({'servers': serverGen})
        if base:
            updateOperations.append(pymongo.UpdateOne({'user_id': u.id}, {'$set': base}))
    if mode == 'update' and updateOperations:
        await users.bulk_write(updateOperations, ordered=not parallel)
    elif mode == 'return':
        return updateOperations
    # print(f'Verified User {m.name} in {(datetime.datetime.now() - started).seconds}s')


async def DeleteServer(s: int, bot: commands.Bot):
    if not bot.get_guild(s):
        await servers.delete_one({'server_id': s})


async def DeleteUser(u: int, bot: commands.Bot):
    if not bot.get_user(u):
        await users.delete_one({'user_id': u})


async def edit_server_data(s: discord.Guild, parameter: str, data: any):
    """Edits top-level server data"""
    await servers.update_one({'server_id': s.id}, {'$set': {parameter: data}})


async def GetLogChannel(s: discord.Guild, mod: str):
    """Return the log channel associated with <mod> module"""
    return (
        s.get_channel((await servers.find_one({'server_id': s.id})).get('cyberlog').get('modules')[await getModElement(s, mod)].get('channel'))
        if (await servers.find_one({'server_id': s.id})).get('cyberlog')[await getModElement(s, mod)].get('channel') is not None
        else s.get_channel((await servers.find_one({'server_id': s.id})).get('cyberlog').get('defaultChannel'))
    )


async def SetSubLogChannel(s: discord.Guild, mod: str, value: any):
    """Sets the log channel associated with <mod> module. Not configured for beta data management revision."""
    await servers.update_one({'server_id': s.id}, {'$set': {f'cyberlog.{mod}.channel': value}})


async def GetMainLogChannel(s: discord.Guild):
    """Returns the log channel associated with the server (general one), if one is set"""
    return s.get_channel(await (servers.find_one({'server_id': s.id})).get('cyberlog').get('defaultChannel'))


async def GetCyberMod(s: discord.Guild, mod: str):
    """Returns the specified module of the Cyberlog object"""
    # return (await servers.find_one({"server_id": s.id})).get("cyberlog").get('modules')[await getModElement(s, mod)]
    return (await servers.find_one({'server_id': s.id})).get('cyberlog').get(mod)


async def GetReadPerms(s: discord.Guild, mod: str):
    """Return if the bot should read the server audit log for logs"""
    return (await GetCyberMod(s, mod)).get('read')


async def GetEnabled(s: discord.Guild, mod: str):
    """Check if this module is enabled for the current server"""
    # return (await GetCyberMod(s, mod)).get("enabled") and (await servers.find_one({"server_id": s.id})).get("cyberlog").get('enabled') and ((await servers.find_one({"server_id": s.id})).get("cyberlog")[await getModElement(s, mod)].get("channel") is not None or (await servers.find_one({"server_id": s.id})).get("cyberlog").get("defaultChannel") is not None)
    return (
        (await GetCyberMod(s, mod)).get('enabled')
        and (await servers.find_one({'server_id': s.id})).get('cyberlog').get('enabled')
        and (
            (await servers.find_one({'server_id': s.id})).get('cyberlog').get(mod).get('channel') is not None
            or (await servers.find_one({'server_id': s.id})).get('cyberlog').get('defaultChannel') is not None
        )
    )


async def SimpleGetEnabled(s: discord.Guild, mod: str):
    """Check if this module is enabled for the current server (lightweight)
    REMEMBER THAT THIS DOESN'T MAKE SURE THAT THE CHANNEL IS VALID"""
    # return (await servers.find_one({"server_id": s.id})).get("cyberlog").get('modules')[await getModElement(s, mod)].get("enabled") and (await servers.find_one({"server_id": s.id})).get("cyberlog").get('enabled')
    return (await servers.find_one({'server_id': s.id})).get('cyberlog').get(mod).get('enabled') and (
        await servers.find_one({'server_id': s.id})
    ).get('cyberlog').get('enabled')


# async def GetImageLogPerms(s: discord.Guild):
#     '''Check if image logging is enabled for the current server'''
#     return (await servers.find_one({'server_id': s.id})).get('cyberlog').get('image')


async def GetAntiSpamObject(s: discord.Guild):
    """Return the Antispam database object - use 'get' to get the other objects"""
    return (await servers.find_one({'server_id': s.id})).get('antispam')


async def GetCyberlogObject(s: discord.Guild):
    """Return the cyberlog database object"""
    return (await servers.find_one({'server_id': s.id})).get('cyberlog')


async def GetMembersList(s: discord.Guild) -> typing.Dict[int, dict]:
    """Return dict of members DB entry objects for a server"""
    return (await servers.find_one({'server_id': s.id})).get('members')


async def PauseMod(s: discord.Guild, mod):
    """Pauses logging for a server"""
    await servers.update_one({'server_id': s.id}, {'$set': {mod + '.enabled': False}})


async def ResumeMod(s: discord.Guild, mod):
    """Resumes logging for a server"""
    await servers.update_one({'server_id': s.id}, {'$set': {mod + '.enabled': True}})


async def GetServerCollection():
    """Return servers collection object"""
    return servers


async def GetAllServers():
    """Return all servers..."""
    return servers.find()


async def GetAllUsers():
    """Return all users..."""
    return users.find()


async def GetUser(u: discord.User):
    """Returns a global user"""
    return await users.find_one({'user_id': u.id})


async def GetUserCollection():
    """Returns the users collection object"""
    return users


async def UpdateMemberWarnings(server: discord.Guild, member: discord.Member, warnings: int):
    """Updates database entry for a member's warnings
    Server: Server the member belongs to
    Member: The member to update
    Warnings: Number of warnings to replace current version with"""
    await servers.update_one({'server_id': server.id}, {'$set': {f'members.{member.id}.warnings': warnings}})


async def GetChannelExclusions(s: discord.Guild):
    """Not to be confused with DefaultChannelExclusions(). Returns server's channel exclusions
    s: discord.Guild object (server) to get the exclusions from"""
    return (await GetAntiSpamObject(s)).get('channelExclusions')


async def GetLogChannelExclusions(s: discord.Guild):
    """Get the channel exclusions for the Cyberlog module"""
    return (await GetCyberlogObject(s)).get('channelExclusions')


async def GetRoleExclusions(s: discord.Guild):
    """Not to be confused with DefaultRoleExclusions(). Returns server's role exclusions
    s: discord.Guild object (server) to get the exclusions from"""
    return (await GetAntiSpamObject(s)).get('roleExclusions')


async def GetLogRoleExclusions(s: discord.Guild):
    """Get the role exclusions for the Cyberlog module"""
    return (await GetCyberlogObject(s)).get('roleExclusions')


async def GetMemberExclusions(s: discord.Guild):
    """Not to be confused with DefaultMemberExclusions(). Returns server's member exclusions
    s: discord.Guild object (server) to get the exclusions from"""
    return (await GetAntiSpamObject(s)).get('memberExclusions')


async def GetLogMemberExclusions(s: discord.Guild):
    """Get the member exclusions for the cyberlog module"""
    return (await GetCyberlogObject(s)).get('memberExclusions')


async def DefaultChannelExclusions(server: discord.Guild):
    """For now, return array of IDs of all channels with 'spam' in the name. Will be customizable later"""
    return [a.id for a in server.channels if any(word in a.name for word in ['spam', 'bot'])]


async def DefaultRoleExclusions(server: discord.Guild):
    """For now, return array of IDs of all roles that can manage server. Will be customizable later"""
    return [a.id for a in server.roles if a.permissions.administrator or a.permissions.manage_guild]


async def DefaultMemberExclusions(server: discord.Guild):
    """For now, return array of the ID of server owner. Will be customizable later"""
    return [server.owner.id]


async def CheckCyberlogExclusions(channel: discord.TextChannel, member: discord.Member):
    """Check to see if we shouldn't log a message delete event
    True to proceed
    False to not log"""
    if channel.id in await GetLogChannelExclusions(channel.guild) or member.id in await GetLogMemberExclusions(channel.guild):
        return False
    for role in member.roles:
        if role.id in await GetLogRoleExclusions(channel.guild):
            return False
    return True


async def getModElement(s: discord.Guild, mod):
    """Return the placement of the desired log module"""
    return (
        (await GetCyberlogObject(s)).get('modules').index([x for x in (await GetCyberlogObject(s)).get('modules') if x.get('name').lower() == mod][0])
    )


# async def GetSummarize(s: discord.Guild, mod):
#     '''Get the summarize value'''
#     return (await GetCyberlogObject(s)).get('modules')[await getModElement(s, mod)].get('summarize') if (await GetCyberlogObject(s)).get('summarize') != (await GetCyberlogObject(s)).get('modules')[await getModElement(s, mod)].get('summarize') else (await GetCyberlogObject(s)).get('summarize')

# async def SummarizeEnabled(s: discord.Guild, mod):
#     '''Is summarizing enabled for this module?'''
#     return (await GetCyberlogObject(s)).get('summarize') != 0 and (await GetCyberlogObject(s)).get('modules')[await getModElement(s, mod)].get('summarize') != 1

# async def GeneralSummarizeEnabled(s: discord.Guild):
#     '''Is summarizing enabled for this server?'''
#     return (await GetCyberlogObject(s)).get('summarize') != 0

# async def StringifyPermissions(p: discord.Permissions):
#     '''Turn a permissions object into a partially stringified version'''
#     return [a[0] for a in iter(p) if a[1]]

# async def AppendSummary(s: discord.Guild, summary):
#     '''Appends a Cyberlog.Summary object to a server's database entry'''
#     await servers.update_one({'server_id': s.id}, {'$push': {'summaries': vars(summary) }})

# async def GetSummary(s: discord.Guild, id: int):
#     '''Return a summary object from a server and message ID'''
#     return await servers.find_one({'server_id': s.id, 'summaries.$.id': id})

# async def StringifyExtras(r: discord.Role):
#     '''Turns a role into a partially stringified version for things like mentionable/displayed separately'''
#     s = []
#     if r.hoist: s.append('displayed separately')
#     if r.mentionable: s.append('mentionable')
#     return s

# async def StringifyBoth(r: discord.Role):
#     '''Turns a role into a combination of the above two'''
#     perms = await StringifyPermissions(r.permissions)
#     perms.extend(await StringifyExtras(r))
#     return perms

# async def ComparePerms(b: discord.Role, a: discord.Role):
#     '''Bold or strikethrough differences'''
#     bef = await StringifyBoth(b)
#     aft = await StringifyBoth(a)
#     s = []
#     for perm in bef:
#         if perm not in aft: s.append('~~{}~~'.format(perm))
#         else: s.append(perm)
#     for perm in aft:
#         if perm not in bef and perm not in s: s.append('**{}**'.format(perm))
#     return s

# async def UnchangedPerms(b: discord.Role, a: discord.Role):
#     '''Only return things that aren't changed'''
#     root = await StringifyBoth(b)
#     new = await StringifyBoth(a)
#     returns = []
#     for r in root:
#         if r in new: returns.append(r)
#     return returns


async def GetTimezone(s: discord.Guild):
    """Return the timezone offset from UTC for a given server"""
    return (await servers.find_one({'server_id': s.id})).get('offset')


async def UpdateTimezone(s: discord.Guild, o):
    """Sets the new timezone offset from UTC for a given server
    o: the new offset in hours from UTC: negative is behind, positive is ahead"""
    await servers.update_one({'server_id': s.id}, {'$set': {'offset': o}})


async def GetBirthdate(s: discord.Guild):
    """Return the time associated with a server's Birthday Management"""
    return (await servers.find_one({'server_id': s.id})).get('birthdate')


async def GetBirthday(s: discord.Guild):
    """Return the channel associated with a server's Birthday Management"""
    return (await servers.find_one({'server_id': s.id})).get('birthday')


async def SetBirthday(m: discord.User, d):
    """Update a member's birthday information"""
    await users.update_one({'user_id': m.id}, {'$set': {'birthday': d}})


async def GetMemberBirthday(m: discord.User):
    """Return a member's birthday"""
    return (await users.find_one({'user_id': m.id})).get('birthday')


async def GetBirthdayMessages(m: discord.User):
    """Return a member's birthday messages"""
    return (await users.find_one({'user_id': m.id})).get('birthdayMessages')


async def SetBirthdayMessage(m: discord.Member, msg, auth, servers):
    """Update a member's birthday messages (receiving)"""
    await users.update_one(
        {'user_id': m.id},
        {
            '$push': {
                'birthdayMessages': {
                    'message': msg.clean_content,
                    'author': auth.id,
                    'authName': auth.display_name,
                    'created': discord.utils.utcnow(),
                    'servers': [s.id for s in servers],
                }
            }
        },
    )


async def ResetBirthdayMessages(u: discord.User):
    """Resets a member's birthday messages (once their birthday has happened)"""
    await users.update_one({'user_id': u.id}, {'$set': {'birthdayMessages': []}})


async def GetAge(m: discord.Member):
    """Return the age of a member"""
    return (await users.find_one({'user_id': m.id})).get('age')


async def SetAge(m: discord.Member, age):
    """Set the age of a  member"""
    await users.update_one({'user_id': m.id}, {'$set': {'age': age}})


async def AppendWishlistEntry(m: discord.Member, entry):
    """Append a wishlist entry to a member's wish list"""
    await users.update_one({'user_id': m.id}, {'$push': {'wishlist': entry}}, True)


async def SetWishlist(m: discord.Member, wishlist):
    """Sets a member's wishlist to the specified list"""
    await users.update_one({'user_id': m.id}, {'$set': {'wishlist': wishlist}}, True)


async def GetWishlist(m: discord.Member):
    """Return the wishlist of a member"""
    return (await users.find_one({'user_id': m.id})).get('wishlist')


async def SetBirthdayMode(s: discord.Guild, mode):
    """Sets auto birthday detection mode: Disabled (0), cake only (1), enabled (2)"""
    await servers.update_one({'server_id': s.id}, {'$set': {'birthdayMode': mode}})


async def GetBirthdayMode(s: discord.Guild, mode):
    """Returns auto birthday detection mode, see above for values"""
    return (await servers.find_one({'server_id': s.id})).get('birthdayMode')


async def GetAgeKick(s: discord.Guild):
    """Gets the ageKick of a server"""
    return (await servers.find_one({'server_id': s.id})).get('antispam').get('ageKick')


async def SetAgeKick(s: discord.Guild, ageKick):
    """Sets the ageKick of a server (in seconds)"""
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.ageKick': ageKick}}, True)
    print(f'Updated ageKick for {s.name} to {ageKick} at {datetime.datetime.now():%B %d %I:%M %p}')


async def GetWhitelist(s: discord.Guild):
    """Gets the whitelist for the ageKick of a server [list of int-IDs]"""
    return (await servers.find_one({'server_id': s.id})).get('antispam').get('ageKickWhitelist')


async def AppendWhitelistEntry(s: discord.Guild, entry):
    """Appends to the ageKick whitelist of a server"""
    await servers.update_one({'server_id': s.id}, {'$push': {'antispam.ageKickWhitelist': entry}}, True)


async def RemoveWhitelistEntry(s: discord.Guild, entry):
    """Removes an entry from the ageKick whitelist of a server"""
    await servers.update_one({'server_id': s.id}, {'$pull': {'antispam.ageKickWhitelist': entry}}, True)


async def ResetWhitelist(s: discord.Guild):
    """Resets (empties) the ageKick whitelist of a server"""
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.ageKickWhitelist': []}}, True)


async def GetAgeKickDM(s: discord.Guild):
    """Returns the custom DM message of the ageKick module for a server"""
    return (await servers.find_one({'server_id': s.id})).get('antispam').get('ageKickDM')


async def SetAgeKickDM(s: discord.Guild, message):
    """Sets the custom DM message of the ageKick module for a server"""
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.ageKickDM': message}}, True)


async def GetAgeKickOwner(s: discord.Guild):
    """Returns whether the ageKick configuration for the specified server can only be modified by the server owner"""
    return (await servers.find_one({'server_id': s.id})).get('antispam').get('ageKickOwner')


async def SetAgeKickOwner(s: discord.Guild, new: bool):
    """Sets whether the ageKick configuration for the specified server can only be modified by the server owner"""
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.ageKickOwner': new}}, True)


async def AppendTimedEvent(s: discord.Guild, event):
    """Appends a timed ban/mute/etc event to a server, these are checked periodically"""
    await servers.update_one({'server_id': s.id}, {'$push': {'antispam.timedEvents': event}}, True)


async def RemoveTimedEvent(s: discord.Guild, event):
    """Removes a timed ban/mute/etc event from a server"""
    await servers.update_one({'server_id': s.id}, {'$pull': {'antispam.timedEvents': event}}, True)


async def AppendCustomStatusHistory(m: discord.Member, emoji, status):
    """Appends a custom status event to a user listing of them. Member object because only they have custom status attributes, not just user objects."""
    if bot.useAttributeQueue:
        bot.attributeHistoryQueue[m.id].update({'statusHistory': {'emoji': emoji, 'name': status, 'timestamp': discord.utils.utcnow()}})
    else:
        await users.update_one({'user_id': m.id}, {'$push': {'statusHistory': {'emoji': emoji, 'name': status, 'timestamp': discord.utils.utcnow()}}})


async def SetCustomStatusHistory(m: discord.Member, entries):
    """Overwrites the member's custom status history list"""
    await users.update_one({'user_id': m.id}, {'$set': {'statusHistory': entries}})


async def AppendUsernameHistory(m: discord.User):
    """Appends a username update to a user's listing of them"""
    if bot.useAttributeQueue:
        bot.attributeHistoryQueue[m.id].update({'usernameHistory': {'name': m.name, 'timestamp': discord.utils.utcnow()}})
    else:
        await users.update_one({'user_id': m.id}, {'$push': {'usernameHistory': {'name': m.name, 'timestamp': discord.utils.utcnow()}}})


async def SetUsernameHistory(m: discord.User, entries):
    """Overwrites the user's username history list"""
    await users.update_one({'user_id': m.id}, {'$set': {'usernameHistory': entries}})


async def AppendDisplaynameHistory(u: discord.User):
    """Appends a display name update to a user's listing of them"""
    if bot.useAttributeQueue:
        bot.attributeHistoryQueue[u.id].update({'displaynameHistory': {'name': u.display_name, 'timestamp': discord.utils.utcnow()}})
    else:
        await users.update_one({'user_id': u.id}, {'$push': {'displaynameHistory': {'name': u.display_name, 'timestamp': discord.utils.utcnow()}}})


async def SetDisplaynameHistory(u: discord.User, entries):
    """Overwrites the user's display name history list"""
    await users.update_one({'user_id': u.id}, {'$set': {'displaynameHistory': entries}})


async def AppendAvatarHistory(m: discord.User, url):
    """Appends an avatar update to a user's listing of them. Old is the discord CDN avatar link used for comparisons, new is the permanent link from the image log channel (copy attachment)"""
    if bot.useAttributeQueue:
        bot.attributeHistoryQueue[m.id].update(
            {'avatarHistory': {'discordURL': m.display_avatar.url, 'imageURL': url, 'timestamp': discord.utils.utcnow()}}
        )
    else:
        await users.update_one(
            {'user_id': m.id},
            {'$push': {'avatarHistory': {'discordURL': m.display_avatar.url, 'imageURL': url, 'timestamp': discord.utils.utcnow()}}},
        )


async def SetAvatarHistory(m: discord.User, entries):
    """Overwrites the user's avatar history list"""
    await users.update_one({'user_id': m.id}, {'$set': {'avatarHistory': entries}})


async def BulkUpdateHistory(entries: dict):
    """New in v1.0. Given a dict of dicts, perform bulk updates for the users' attribute history"""
    # For the queue, pass the bot to the methods above. If we need to use the queue, we'll add stuff to the queue, and whatever method opened the queue will pass the queue here afterwards
    updateOperations = []
    for k, v in entries.items():
        updateOperations.append(pymongo.UpdateOne({'user_id': k}, {'$push': {kk: vv for kk, vv in v.items()}}))
    if updateOperations:
        await users.bulk_write(updateOperations, ordered=False)


async def UnduplicateUsers(usrs, interaction: discord.Interaction = None):
    """Removes duplicate entries from the given users' history lists, making use of bulk operations"""
    if interaction:
        await interaction.response.send_message(f'Unduplicating {len(usrs)} users')
    gathered = await (users.find({'user_id': {'$in': [u.id for u in usrs]}})).to_list(None)
    gatheredDict = {u['user_id']: u for u in gathered}
    chunkSize = 1000
    counter = 0
    fullCounter = 0
    updateOperations = []
    for u in gathered:
        counter += 1
        fullCounter += 1
        updateOperations += await UnduplicateHistory(u, gatheredDict.get(u.id), mode='return')
        if counter >= chunkSize:
            await users.bulk_write(updateOperations, ordered=False)
            counter = 0
            updateOperations = []
            if interaction:
                await interaction.response.edit_message(content=f'Unduplicating {fullCounter}/{len(usrs)} users')
    await users.bulk_write(updateOperations, ordered=False)
    if interaction:
        await interaction.response.edit_message(content=f'Successfully unduplicated {len(usrs)} users')


async def UnduplicateHistory(u: discord.User, userEntry=None, *, mode='update'):
    """Removes duplicate entries from a user's history lists"""
    # v1.0: Changed behavior to build list locally instead of spam MongoDB operations repeatedly. The new algorithm also reduces data loss and improves speed.
    if not userEntry:
        userEntry = await users.find_one({'user_id': u.id})
    csh, uh, ah = [], [], []
    cache = None
    try:
        for entry in userEntry.get('statusHistory'):
            current = {'emoji': entry.get('emoji'), 'name': entry.get('name')}
            if cache != current:
                cache = current
                csh.append(entry)
    except TypeError:
        pass
    try:
        for entry in userEntry.get('usernameHistory'):
            if cache != entry.get('name'):
                cache = entry.get('name')
                uh.append(entry)
    except TypeError:
        pass
    try:
        for entry in userEntry.get('avatarHistory'):
            if cache != entry.get('discordURL'):
                cache = entry.get('discordURL')
                ah.append(entry)
    except TypeError:
        pass
    if mode == 'update':
        await users.update_one({'user_id': u.id}, {'$set': {'customStatusHistry': csh, 'usernameHistory': uh, 'avatarHistory': ah}})
    elif mode == 'return':
        return pymongo.UpdateOne({'user_id': u.id}, {'$set': {'customStatusHistry': csh, 'usernameHistory': uh, 'avatarHistory': ah}})


async def SetLastActive(u: typing.List[discord.User], timestamp, reason):
    """Updates the last active attribute"""
    await users.update_many({'user_id': {'$in': [user.id for user in u]}}, {'$set': {'lastActive': {'timestamp': timestamp, 'reason': reason}}})


async def SetLastOnline(u: typing.List[discord.User], timestamp):
    """Updates the last online attribute"""
    await users.update_many({'user_id': {'$in': [user.id for user in u]}}, {'$set': {'lastOnline': timestamp}})


async def SetLogChannel(s: discord.Guild, value: any):
    """Setsa server's default log channel"""
    await servers.update_one({'server_id': s.id}, {'$set': {'cyberlog.defaultChannel': value}}, True)


# async def NameVerify(s: discord.Guild):
#     '''Verifies a server by name to counter the database code error'''
#     await servers.update_one({'name': s.name}, {'$set': {'server_id': s.id}}, True)


async def ZeroRepeatedJoins(s: discord.Guild):
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.repeatedJoins': [0, 0, 0]}}, True)


async def AppendMemberJoinEvent(s: discord.Guild, m: discord.Member):
    """Appends a member join event to a server's log, uses for member join logs"""
    # Was this one of the many features I want to do but can't implement in full for the time being?
    await servers.update_one({'server_id': s.id}, {'$push': {'cyberlog.joinLogHistory': {'id': m.id, 'timestamp': discord.utils.utcnow()}}})


# async def GetNamezone(s: discord.Guild):
#     '''Return the custom timezone name for a given server'''
#     return (await servers.find_one({"server_id": s.id})).get('tzname')


async def GetServer(s: discord.Guild):
    """Return server object"""
    return await servers.find_one({'server_id': s.id})


async def SetLastUpdate(s: discord.Guild, d: datetime.datetime, mod: None):
    """Update the last time a server was summarized, optional module argument"""
    if mod is None:
        await servers.update_one({'server_id': s.id}, {'$set': {'cyberlog.lastUpdate': d}})
    else:
        await servers.update_one({'server_id': s.id}, {'$set': {'cyberlog.' + mod + '.lastUpdate': d}})


# async def GetLastUpdate(s: discord.Guild, mod: None):
#     '''Returns a datetime object representing the last time the server or a module was recapped'''
#     if mod is None: return await servers.find_p({"server_id": s.id}).get("cyberlog.lastUpdate")
#     else: return await GetCyberMod(s, mod).get('lastUpdate')

# async def GetOldestUpdate(s: discord.Guild, mods):
#     '''Returns the oldest update date from a list of provided modules. Useful for when people configure different settings for different modules'''
#     return min([GetLastUpdate(s, m) for m in mods]) + datetime.timedelta(hours=await GetTimezone(s))

# async def UpdateChannel(channel: discord.abc.GuildChannel):
#     '''Updates the channel.updated and channel.name attributes of the given channel. .updated is used for stats on channel edit'''
#     servers.update_one({'server_id': channel.guild.id, 'allChannels.id': channel.id}, {'$set': {
#         'allChannels.$.updated': discord.utils.utcnow(),
#         'allChannels.$.name': channel.name,
#         'allChannels.$.oldUpdate': await GetChannelUpdate(channel)}})

# async def UpdateRole(role: discord.Role):
#     '''Updates the role.updated and role.name attributes of the given role. .updated is used for stats on role edit'''
#     servers.update_one({'server_id': role.guild.id, 'roles.id': role.id}, {'$set': {
#         'roles.$.updated': discord.utils.utcnow(),
#         'roles.$.name': role.name,
#         'roles.$.oldUpdate': await GetRoleUpdate(role)}})

# async def GetChannelUpdate(channel: discord.abc.GuildChannel):
#     '''Returns the channel.updated attribute, which is the last time the channel was updated'''
#     return (await servers.find_one({'server_id': channel.guild.id, 'channels.$.id': channel.id})).get('updated')

# async def GetOldChannelUpdate(channel: discord.abc.GuildChannel):
#     '''Returns the channel.oldUpdate attribute, which is the time it was updated 2 times ago'''
#     return (await servers.find_one({'server_id': channel.guild.id, 'channels.$.id': channel.id})).get('oldUpdate')

# async def GetRoleUpdate(role: discord.Role):
#     '''Returns the role.updated attribute, which is the last time the role was updated'''
#     return (await servers.find_one({'server_id': role.guild.id, 'roles.$.id': role.id})).get('updated')

# async def GetOldRoleUpdate(role: discord.Role):
#     '''Returns the role.oldUpdate attribute, which is the time it was updated 2 times ago'''
#     return (await servers.find_one({'server_id': role.guild.id, 'roles.$.id': role.id})).get('oldUpdate')


async def VerifyChannel(c: discord.abc.GuildChannel, new=False):
    """Verifies a channel. Single database operation of VerifyServer"""
    if new:
        await servers.update_one({'server_id': c.guild.id}, {'$push': {'channels': {'name': c.name, 'id': c.id}}})
    else:
        await servers.update_one({'server_id': c.guild.id, 'channels.$.id': c.id}, {'$set': {'name': c.name}})


async def VerifyMember(m: discord.Member, new=False, warnings=None):
    """Verifies a member. Single database operation of VerifyServer"""
    server = await servers.find_one({'server_id': m.guild.id})
    warnings - server.get('antispam', {}).get('warn', 3)
    await servers.update_one({'server_id': m.guild.id}, {'$set': {f'members.{m.id}': {'id': m.id, 'name': m.name, 'warnings': warnings}}})


async def VerifyRole(r: discord.Role, new=False):
    """Verifies a role. Single database operation of VerifyServer"""
    if new:
        await servers.update_one({'server_id': r.guild.id}, {'$push': {'roles': {'name': r.name, 'id': r.id}}})
    else:
        await servers.update_one({'server_id': r.guild.id, 'roles.$.id': r.id}, {'$set': {'name': r.name}})


async def CalculateGeneralChannel(g: discord.Guild, bot, update=False):
    """Determines the most active channel based on indexed message count
    r: Whether to return the channel. If False, just set this to the database"""
    try:
        currentGeneralChannel = (await utility.get_server(g)).get('generalChannel', ())
    except KeyError:
        currentGeneralChannel = await GetServer(g).get('generalChannel', ())
    if not currentGeneralChannel or type(currentGeneralChannel) is not list or False in currentGeneralChannel:
        channels: typing.Dict[int, int] = {}
        for c in g.text_channels:
            channels[c.id] = len(
                await lightningdb.get_messages_by_timestamp(after=discord.utils.utcnow() - datetime.timedelta(days=14), channel_ids=[c.id])
            )
        popular = max(channels, key=channels.get, default=0)
        if update and channels:
            await servers.update_one({'server_id': g.id}, {'$set': {'generalChannel': (popular, False)}})
    else:
        popular = bot.get_channel(currentGeneralChannel[0])
    return popular


async def CalculateAnnouncementsChannel(g: discord.Guild, bot, update=False):
    """Determines the announcement channel based on channel name and permissions
    r: Whether to return the channel. If False, just set this to the database"""
    try:
        currentAnnouncementsChannel = (await utility.get_server(g)).get('announcementsChannel', ())
    except KeyError:
        currentAnnouncementsChannel = await GetServer(g).get('announcementsChannel', ())
    if not currentAnnouncementsChannel or type(currentAnnouncementsChannel) is not list or False in currentAnnouncementsChannel:
        try:
            s = sorted(
                [c for c in g.text_channels if 'announcement' in c.name.lower() and not c.overwrites_for(g.default_role).send_messages],
                key=lambda x: len(x.name) - len('announcement'),
            )[0]
        except IndexError:
            return 0
        if update:
            await servers.update_one({'server_id': g.id}, {'$set': {'announcementsChannel': (s.id, False)}})
    else:
        s = bot.get_channel(currentAnnouncementsChannel[0])
    return s


async def CalculateModeratorChannel(g: discord.Guild, bot: commands.Bot, update=False, *, logChannelID=0):
    """Determines the moderator channel based on channel name and permissions
    r: Whether to return the channel. If False, just set this to the database"""
    try:
        currentModeratorChannel = (await utility.get_server(g)).get('moderatorChannel', ())
    except KeyError:
        currentModeratorChannel = await GetServer(g).get('moderatorChannel', ())
    if not currentModeratorChannel or type(currentModeratorChannel) is not list or False in currentModeratorChannel:
        relevanceKeys: typing.Dict[discord.TextChannel, int] = {}
        for c in g.text_channels:
            if not c.overwrites_for(g.default_role).read_messages and c.id != logChannelID:
                relevanceKeys.update(
                    {
                        c: round(
                            len([m for m in g.members if c.permissions_for(m).read_messages and c.permissions_for(m).send_messages])
                            * 100
                            / len([m for m in g.members if c.permissions_for(m).read_messages])
                        )
                    }
                )
        for k in relevanceKeys.keys():
            if any(word in k.name.lower() for word in ['mod', 'manager', 'staff', 'admin']):
                relevanceKeys[k] += 50
            if any(word in k.name.lower() for word in ['chat', 'discussion', 'talk']):
                relevanceKeys[k] += 10
            if 'announce' in k.name.lower():
                relevanceKeys[k] = 1
        result: discord.TextChannel = max(relevanceKeys, key=relevanceKeys.get, default=0)
        if update:
            await servers.update_one({'server_id': g.id}, {'$set': {'moderatorChannel': (result.id, False)}})
    else:
        result = bot.get_channel(currentModeratorChannel[0])
    return result


async def CreateSupportTicket(ticket):
    """Appends a new support ticket to the system"""
    await disguard.update_one({}, {'$push': {'tickets': ticket}}, True)


async def UpdateSupportTicket(ticketNumber, newTicket):
    """Updates a support ticket with a new version"""
    await disguard.update_one({}, {'$set': {'tickets.$[elem]': newTicket}}, array_filters=[{'elem.number': ticketNumber}])


async def AppendTicketConversation(ticketNumber, conversationEntry):
    """Appends a conversation entry to a support ticket"""
    await disguard.update_one({}, {'$push': {'tickets.$[elem].conversation': conversationEntry}}, array_filters=[{'elem.number': ticketNumber}])


async def FetchSupportTicket(ticketNumber):
    """Fetches a specific support ticket, given its placement number"""
    return await disguard.find_one({'tickets': {'$elemMatch': {'number': ticketNumber}}})


async def GetSupportTickets():
    """Returns entire support ticket collection"""
    return (await disguard.find_one({})).get('tickets')


async def SetWarnings(members: typing.List[discord.Member], warnings: int):
    bulkUpdates = [pymongo.UpdateOne({'server_id': members[0].guild.id}, {'$set': {f'members.{member.id}.warnings': warnings}}) for member in members]
    await servers.bulk_write(bulkUpdates)


async def SetMuteRole(s: discord.Guild, r: discord.Role):
    """Sets the automute role for a server"""
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.automuteRole': r.id}})


async def SetMuteCache(s: discord.Guild, members: typing.List[discord.Member], rlist: typing.Dict[int, typing.List[discord.Role]]):
    """Stores a list of roles to a member's database cache to be used to unmute in the future"""
    updates = [
        pymongo.UpdateOne(
            {'server_id': s.id}, {'$set': {f'members.{member.id}.roleCache': [r.id for r in rlist[member.id]] if type(rlist) is dict else []}}
        )
        for member in members
    ]
    await servers.bulk_write(updates)


async def SetPermissionsCache(s: discord.Guild, members: typing.List[discord.Member], plist: typing.Dict[str, typing.Dict[any, any]]):
    """Stores a list of permission overwrites to a member's database cache to be used to unmute in the future"""
    updates = [
        pymongo.UpdateOne(
            {'server_id': s.id}, {'$set': {f'members.{member.id}.permissionsCache': plist[str(member.id)] if type(plist) is not list else {}}}
        )
        for member in members
    ]
    await servers.bulk_write(updates)


async def AdjustDST(s: discord.Guild):
    server = await GetServer(s)
    offset = server['offset']
    tzname = server['tzname']
    if offset in [-5, -6, -7, -8]:  # SPRING FORWARD
        if not (offset == -4 and tzname == 'EST'):
            await servers.update_one({'server_id': s.id}, {'$inc': {'offset': 1}})
            return True
    return False


async def GetBirthdayList():
    """Returns the global birthday dictionary"""
    return (await disguard.find_one({})).get('birthdays', {})


async def UpdateBirthdayList(u: discord.User, d: datetime.datetime):
    """Adds a member's birthday to the global dictionary"""
    birthdayList = await GetBirthdayList()
    if not birthdayList:
        birthdayList = {}
    try:
        birthdayList[d.strftime('%m/%d/%Y')].append({u.id: d})
    except KeyError:
        birthdayList[d.strftime('%m/%d/%Y')] = [{u.id: d}]
    await disguard.update_one({}, {'$set': {'birthdays': birthdayList}}, True)


async def SetBirthdayList(input: dict):
    """Sets the global birthday directory to the passed dictionary"""
    await disguard.update_one({}, {'$set': {'birthdays': await GetBirthdayList()}}, True)


async def SetWarmup(s: discord.Guild, warmup: int):
    """Sets a server's warmup value"""
    await servers.update_one({'server_id': s.id}, {'$set': {'antispam.warmup': warmup}})


async def create_reddit_feed(s: discord.Guild, feed: dict):
    """Creates a new reddit feed"""
    await servers.update_one({'server_id': s.id}, {'$set': {f'redditFeeds.{feed["subreddit"]}': feed}})


async def delete_reddit_feed(s: discord.Guild, feed_name: str):
    """Deletes a reddit feed"""
    await servers.update_one({'server_id': s.id}, {'$unset': {f'redditFeeds.{feed_name}': ''}})


async def convert_reddit_feeds(s: discord.Guild):
    """Converts the reddit feed data from list to dict"""
    feeds = (await servers.find_one({'server_id': s.id})).get('redditFeeds', [])
    if type(feeds) is list:
        newFeeds = {}
        for feed in feeds:
            newFeeds[feed['subreddit']] = feed
        await servers.update_one({'server_id': s.id}, {'$set': {'redditFeeds': newFeeds}})
        await lightningdb.patch_server(s, {'redditFeeds': newFeeds})


async def convert_status_history():
    """Renames the customStatusHistory key to statusHistory"""
    await users.update_many({}, {'$rename': {'customStatusHistory': 'statusHistory'}})


async def patch_privacy(u: discord.User, module: str, enabled: int = 2, visibility: int = 2):
    """Updates a user's privacy settings"""
    await users.update_one({'user_id': u.id}, {'$set': {f'privacy.{module}': (enabled, visibility)}})
