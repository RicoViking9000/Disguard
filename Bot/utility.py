"""Contains utility functions to be used across Disguard"""

import asyncio
import datetime
import logging
import os
import re
import string
import typing

import discord
from discord.ext import commands

import lightningdb

logger = logging.getLogger('discord')

rv9k = 247412852925661185
GREEN = (0x008000, 0x66FF66)
BLUE = (0x0000FF, 0x6666FF)
RED = (0xFF0000, 0xFF6666)
ORANGE = (0xD2691E, 0xFFC966)
YELLOW = (0xFFFF00, 0xFFFF66)
INDENT = '  '
NEWLINE = '\n'
TOGGLES = {True: 'slideToggleOn', False: 'slideToggleOff'}

permissionKeys = {
    'create_instant_invite': 'Create Invite',
    'kick_members': 'Kick Members',
    'ban_members': 'Ban Members',
    'administrator': 'Administrator',
    'manage_channels': 'Manage Channels',
    'manage_guild': 'Manage Server',
    'add_reactions': 'Add Reactions',
    'view_audit_log': 'View Audit Log',
    'priority_speaker': 'Priority Speaker',
    'stream': 'Go Live',
    'read_messages': 'Read Messages',
    'send_messages': 'Send Messages',
    'send_tts_messages': 'Send TTS Messages',
    'manage_messages': 'Manage Messages',
    'embed_links': 'Embed Links',
    'attach_files': 'Attach Files',
    'read_message_history': 'Read Message History',
    'mention_everyone': 'Mention @everyone, @here, and All Roles',
    'external_emojis': 'Use External Emojis',
    'view_guild_insights': 'View Server Insights',
    'connect': 'Connect',
    'speak': 'Speak',
    'mute_members': 'Mute Members',
    'deafen_members': 'Deafen Members',
    'move_members': 'Move members',
    'use_voice_activation': 'Use Voice Activity',
    'change_nickname': 'Change Nickname',
    'manage_nicknames': 'Manage Nicknames',
    'manage_roles': 'Manage Roles',
    'manage_webhooks': 'Manage Webhooks',
    'manage_emojis': 'Manage Emojis and Stickers',
    'use_slash_commands': 'Use Slash Commands',
    'request_to_speak': 'Request to Speak in Stage Channel',
    'manage_events': 'Manage Server Events',
    'manage_threads': 'Manage Threads',
    'use_private_threads': 'Use Private Threads',
}

permissionDescriptions = {
    'create_instant_invite': '',
    'kick_members': '',
    'ban_members': '',
    'administrator': 'Members with this permission have every permission and also bypass channel specific permissions',
    'manage_channels': 'Members with this permission can create, edit, and delete channels',
    'manage_guild': "Members with this permission can change the server's name, region, icon, and other settings",
    'add_reactions': 'Members with this permission can add new reactions to a message (this permission is not needed for members to add to an existing reaction)',
    'view_audit_log': 'Members with this permission have access to view the server audit logs',
    'priority_speaker': 'Members with this permission have the ability to be more easily heard when talking. When activated, the volume of others without this permission will be automatically lowered. This power is activated using the push to talk keybind',
    'stream': 'Members with this permission can stream applications or screenshare in voice channels',
    'read_messages': '',
    'send_messages': '',
    'send_tts_messages': 'Members with this permission can send text-to-speech messages by starting a message with /tts. These messages can be heard by everyone focused on the channel who allow TTS playback in settings',
    'manage_messages': 'Members with this permission can delete messages authored by other members and can pin/unpin any message',
    'embed_links': '',
    'attach_files': '',
    'read_message_history': 'If this permission is disabled, messages in text channels will become invisible to affected members upon disconnecting from that text channel',
    'mention_everyone': 'Members with this permission can use @everyone or @here to ping all members with access to the selected channel. They can also @mention all roles, even if that role is not normally mentionable',
    'external_emojis': "Allows members to use emoji from other servers, if they're a Discord Nitro member",
    'view_guild_insights': 'View Server Insights',
    'connect': '',
    'speak': '',
    'mute_members': '',
    'deafen_members': '',
    'move_members': 'Members with this permission can move members between voice channels the member with this permission has access to',
    'use_voice_activation': 'Members must use Push-To-Talk if this permission is disabled',
    'change_nickname': 'Members with this permission can change their own nickname',
    'manage_nicknames': 'Members with this permission can set or reset nicknames of all server members',
    'manage_roles': 'Members with this permission can create new roles and edit/delete roles below their highest role granting this permission',
    'manage_webhooks': 'Members with this permission can create, edit, and delete webhooks',
    'manage_emojis': 'Members with this permission can create, edit, and delete custom emojis and stickers',
    'use_slash_commands': '',
    'request_to_speak': '',
    'manage_events': '',
    'manage_threads': '',
    'use_private_threads': '',
}

CHANNEL_KEYS = {
    'category': 'Category',
    'private': 'Private',
    'group': 'Group',
    'news': 'News',
    'stage_voice': 'Stage',
    'public_thread': 'Thread',
    'private_thread': 'Private thread',
    'news_thread': 'News thread',
    'text': 'Text',
    'voice': 'Voice',
    'forum': 'Forum',
    'media': 'Media',
}

DISGUARD_SERVER_ID = 560457796206985216
DISGUARD_ID = 558025201753784323


def rickroll():
    return 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'


def ManageServer(member: discord.Member):
    return CheckPermissions(member, discord.Permissions(manage_guild=True), True)


def CheckPermissions(member: discord.Member, permissions: discord.Permissions, includeDev=False):
    """Compares a given permissions with the server permissions of the given member"""
    return member.id in (member.guild.owner_id, 247412852925661185 if includeDev else 0) or member.guild_permissions.is_superset(permissions)


async def ManageRoles(member: discord.Member):
    """Does this member have the Manage Roles permission"""
    if member.id == member.guild.owner.id:
        return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.manage_roles:
            return True
    return False


async def ManageChannels(member: discord.Member):
    """Does this member have the Manage Channels permission"""
    if member.id == member.guild.owner.id:
        return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.manage_channels:
            return True
    return False


async def KickMembers(member: discord.Member):
    """Does this member have the Kick Members permission"""
    if member.id == member.guild.owner.id:
        return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.kick_members:
            return True
    return False


async def BanMembers(member: discord.Member):
    """Does this member have the Ban Members permission"""
    if member.id == member.guild.owner.id:
        return True
    for a in member.roles:
        if a.permissions.administrator or a.permissions.ban_members:
            return True
    return False


def rawStringifyPermissions(p: discord.Permissions):
    """Turn a permissions object into a raw stringified version"""
    return [a[0] for a in iter(p) if a[1]]


def stringifyPermissions(p: discord.Permissions):
    """Turn a permissions object into a stringified version using the official Discord UI descriptions"""
    return [permissionKeys.get(a[0], a[0]) for a in iter(p) if a[1]]


def outputPermissions(p: discord.Permissions):
    """Converts stringifyPermissions(p) to a comma-separated string"""
    return ', '.join(stringifyPermissions(p))


def getPermission(p: str):
    """Given a String in the form of a raw permission string value (aka the keys in <permissionKeys>), return its Discord-UI friendly form if possible"""
    return permissionKeys.get(p, p)


def pretty_permissions(p: discord.Permissions):
    """Converts a permissions object into a string by replacing underscores with spaces and capitalizing the first letter of each word"""
    return ', '.join([a[0].replace('_', ' ').title() for a in iter(p) if a[1]])


def pretty_permission(p: str):
    """Converts a permission string into a string by replacing underscores with spaces and capitalizing the first letter of each word"""
    return p.replace('_', ' ').title()


def ParseDuration(string: str) -> typing.Tuple[int, int, str]:
    """Parses a string into a duration in seconds, the integer value, and the unit of time"""
    units = {'s': 'second', 'm': 'minute', 'h': 'hour', 'd': 'day', 'w': 'week', 'mo': 'month', 'y': 'year'}
    search = re.search(r'\D', string)
    if not search:
        return 0, 0, ''
    int_arg = string[: search.start()]
    unit_arg = search.group().lower()
    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800, 'mo': 2628000, 'y': 31536000}
    duration = int(int_arg) * multipliers[unit_arg]
    return duration, int_arg, units[unit_arg] + ('s' if int_arg != 1 else '')


def suffix(count: int):
    sfx = 'th'
    if count % 100 in [11, 12, 13]:
        sfx = 'th'
    elif count % 10 == 1:
        sfx = 'st'
    elif count % 10 == 2:
        sfx = 'nd'
    elif count % 10 == 3:
        sfx = 'rd'
    return sfx


def hexToColor(string):
    """Convert a hex code (including if it's a string) to a discord color"""
    string = str(string).replace('#', '')  # In case it isn't already
    if len(string) != 6:
        return discord.Color.default()  # Invalid value
    try:
        r, g, b = int(string[:2], 16), int(string[2:4], 16), int(string[4:], 16)
        return discord.Color.from_rgb(r, g, b)
    except:
        return discord.Color.default()


def basicURL(url):
    """Return the URL only containing site domain"""
    return url[url.find('//') + 2 : url.find('/', url.find('//') + 2)]


def multiLineQuote(s):
    """Converts a string containing newlines in it to a block quote"""
    if '\n' in s:
        return '\n'.join([f'> {line}' for line in s.split('\n')])
    else:
        return '\n'.join([line for line in s.split('\n')])


def clockEmoji(timestamp):
    """Returns clock emoji in proper hand position, based on timestamp"""
    return f':clock{int(timestamp.strftime("%I"))}{"30" if int(f"{timestamp:%M}") in range(15, 46) else ""}:'  # Converting to int in the first part removes padded zeros, and actually converts for range comparison in the second part


def absTime(x, y, distance):
    """Checks to ensure x and y (date objects (date, datetime, or time)) are within `distance` (timedelta) of each other"""
    return abs(x - y) < distance


def daylightSavings():
    """Returns True if the USA is in daylight savings time"""
    return 4 if datetime.datetime.now() < datetime.datetime(2023, 11, 5, 2) else 5


def embedToPlaintext(e: discord.Embed):
    """Returns a string composed of fields/values in the embed. Cleans up the content too."""
    result = ''
    for f in e.fields:
        result += f'\n{f.name}: {multiLineQuote(f.value) if len(f.value) < 300 else "<Truncated>"}'
    # This somewhat intensive loop has to go character by character to clean up emojis and the like
    parsed = ''
    append = True  # Whether to add characters into the parsed result (used for custom emojis, since those have angle brackets)
    for char in result:
        if char == '<':
            append = False  # Pause appending for content inside of angle brackets
        if char == '>':
            append = True  # Resume appending for content outside of angle brackets
        if char in string.printable and append:
            parsed += char
    return discord.utils.escape_mentions(parsed).replace('**', '').replace('*', '').replace('__', '')[:2000]


def contentParser(message: discord.Message):
    return (
        '<Hidden due to channel being NSFW>'
        if message.channel.is_nsfw() and not message.channel.is_nsfw()
        else message.content
        if message.content
        else f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f': {message.attachments[0].filename}'}>"
        if len(message.attachments) > 0
        else f'<{len(message.embeds)} embed>'
        if len(message.embeds) > 0
        else '<No content>'
    )


def empty(value):
    """Compares an embed field to its delegated empty value (in d.py 2.0, changed from Embed.Empty to None"""
    return value is None


def channelEmoji(self, c: typing.Union[discord.DMChannel, discord.abc.GuildChannel]):
    """Returns an emoji corresponding to the type of channel"""
    # Emojis need to be updated
    match c.type:
        case discord.ChannelType.category:
            return self.emojis['folder']
        case discord.ChannelType.private:
            return self.emojis['member']
        case discord.ChannelType.group:
            return self.emojis['members']
        case discord.ChannelType.news:
            if c.threads:
                return self.emojis['announcementsThreads']
            return self.emojis['announcementsChannel']
        case discord.ChannelType.stage_voice:
            if not c.overwrites_for(c.guild.default_role).read_messages:
                return self.emojis['privateStage']
            return self.emojis['stageChannel']
        case discord.ChannelType.public_thread:
            return self.emojis['threadChannel']
        case discord.ChannelType.private_thread:
            return self.emojis['privateThreadChannel']
        case discord.ChannelType.news_thread:
            return self.emojis['textThreads']
        case discord.ChannelType.forum:
            if not c.overwrites_for(c.guild.default_role).read_messages:
                return self.emojis['privateForum']
            return self.emojis['forumChannel']
        case discord.ChannelType.text:
            private = c.overwrites_for(c.guild.default_role).read_messages is False
            if c.threads and not private:
                return self.emojis['textThreads']
            if c.is_nsfw():
                return self.emojis['nsfwChannel']
            elif c.guild.rules_channel and c.id == c.guild.rules_channel.id:
                return self.emojis['rulesChannel']
            elif private:
                if c.threads:
                    return self.emojis['privateTextThreads']
                return self.emojis['privateTextChannel']
            else:
                return self.emojis['textChannel']
        case discord.ChannelType.voice:
            private = c.overwrites_for(c.guild.default_role).read_messages is False
            if private:
                return self.emojis['privateVoiceChannel']
            elif c.is_nsfw():
                return self.emojis['nsfwVoice']
            else:
                return self.emojis['voiceChannel']
        case _:
            return '❔'


def channelIsHidden(self, c: discord.abc.GuildChannel, member: discord.Member):
    """Returns a boolean representing whether a channel is visible to the given member"""
    return not c.permissions_for(member).read_messages


def elapsedDuration(timeSpan: datetime.timedelta, joinString=True, fullUnits=True, *, onlyTimes=False):
    """Returns a list of string representing elapsed time, given a dateTime. joinString determines return type"""
    units = ['second', 'minute', 'hour', 'day']
    hours, minutes, seconds = (
        timeSpan.seconds // 3600,
        (timeSpan.seconds // 60) % 60,
        timeSpan.seconds - (timeSpan.seconds // 3600) * 3600 - ((timeSpan.seconds // 60) % 60) * 60,
    )
    timeList = [seconds, minutes, hours, timeSpan.days]
    if onlyTimes:
        return list(reversed(timeList))
    display = []
    for i, v in reversed(tuple(enumerate(timeList))):  # v stands for value
        if v != 0:
            display.append(f'{v} {units[i] if fullUnits else units[i][0]}{"s" if v != 1 and fullUnits else ""}')
    if len(display) == 0:
        display = ['0 seconds']
    if joinString:
        return f"{', '.join(display[:-1])} and {display[-1]}" if len(display) > 1 else display[0]
    else:
        return display  # This is a list that will be joined as appropriate at my discretion in the parent method, if I don't want to use the default joiner above


def DisguardShortTimestamp(t):
    """Given a datetime module object, returns a Discord-UI based timestamp with <HH:MM> format"""
    try:
        r = round(t.timestamp())
    except:
        r = 0
    return f'<t:{r}:t>'


def DisguardShortmonthTimestamp(t):
    """Given a datetime module object, returns a Discord-UI based timestamp with <MM/DD/YYYY> <HH:MM:SS AM/PM> format"""
    try:
        r = round(t.timestamp())
    except:
        r = 0
    return f'<t:{r}:d> <t:{r}:T>'


def DisguardIntermediateTimestamp(t):
    """Given a datetime module object, returns a Discord-UI based timestamp with <MMMM DD, YYYY HH:MM AM/PM> format"""
    try:
        r = round(t.timestamp())
    except:
        r = 0
    return f'<t:{r}:f>'


def DisguardLongTimestamp(t):
    """Given a datetime module object, returns a Discord-UI based timestamp with <MMMM DD, YYYY> <HH:MM:SS AM/PM> format"""
    try:
        r = round(t.timestamp())
    except:
        r = 0
    return f'<t:{r}:D> <t:{r}:T>'


def DisguardRelativeTimestamp(t):
    """Given a datetime module object, returns a Discord-UI based timestamp with relative <In x days> format"""
    try:
        r = round(t.timestamp())
    except:
        r = 0
    return f'<t:{r}:R>'


def DisguardStandardTimestamp(t: datetime.datetime):
    return f'{t:%B %d, %Y • %I:%M:%S %p}'


def FindMember(g: discord.Guild, arg):
    def check(m):
        return any([arg.lower() == m.nick, arg.lower() in m.name.lower(), arg in m.discriminator, arg in str(m.id)])

    return discord.utils.find(check, g.members)


def FindServers(guilds: list[discord.Guild], arg: str):
    """Used for smart info command. Finds anything matching the filter"""
    arg = arg.lower()

    def check(s: discord.Guild):
        if arg in s.name.lower():
            return compareMatch(arg, s.name)
        if arg in str(s.id):
            return compareMatch(arg, str(s.id))
        return None

    return [(server, check(server)) for server in guilds if check(server) is not None]


def FindMembers(g: discord.Guild, arg):
    """Used for smart info command. Finds anything matching the filter"""
    arg = arg.lower()

    def check(m):
        if m.nick is not None and m.nick.lower() == arg:
            return compareMatch(arg, m.nick)
        if arg in m.name.lower():
            return compareMatch(arg, m.name)
        if arg in m.display_name.lower():
            return compareMatch(arg, m.display_name)
        if arg in m.discriminator:
            return compareMatch(arg, m.discriminator)
        if arg in str(m.id):
            return compareMatch(arg, str(m.id))
        return None

    return [(mem, check(mem)) for mem in g.members if check(mem) is not None]


def FindRoles(g: discord.Guild, arg):
    arg = arg.lower()

    def check(r):
        if arg in r.name.lower():
            return compareMatch(arg, r.name)
        if arg in str(r.id):
            return compareMatch(arg, str(r.id))
        return None

    return [(rol, check(rol)) for rol in g.roles if check(rol) is not None]


def FindChannels(g: discord.Guild, arg):
    arg = arg.lower()

    def check(c):
        if arg in c.name.lower():
            return compareMatch(arg, c.name)
        if arg in str(c.id):
            return compareMatch(arg, str(c.id))
        return None

    return [(cha, check(cha)) for cha in g.channels if check(cha) is not None]


def FindEmojis(g: discord.Guild, arg):
    arg = arg.lower()

    def check(e):
        if arg in e.name.lower():
            return compareMatch(arg, e.name)
        if arg in str(e.id):
            return compareMatch(arg, str(e.id))
        return None

    return [(emo, check(emo)) for emo in g.emojis if check(emo) is not None]


"""Split between initial findings and later findings - optimizations"""


async def FindMoreMembers(members: list[discord.User], arg) -> list[dict[str, typing.Any]]:
    arg = arg.lower()

    def check(m):
        if type(m) is discord.Member and m.nick is not None and m.nick.lower() == arg.lower():
            return "Nickname is '{}'".format(m.nick.replace(arg, '**{}**'.format(arg))), compareMatch(arg, m.nick)
        if arg in m.name.lower():
            return "Username is '{}'".format(m.name).replace(arg, '**{}**'.format(arg)), compareMatch(arg, m.name)
        if arg in m.display_name.lower():
            return "Display name is '{}'".format(m.display_name).replace(arg, '**{}**'.format(arg)), compareMatch(arg, m.display_name)
        if arg in m.discriminator:
            return "Discriminator is '{}'".format(m.discriminator).replace(arg, '**{}**'.format(arg)), compareMatch(arg, m.discriminator)
        if arg in str(m.id):
            return "ID matches: '{}'".format(m.id).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(m.id))
        if arg in '<@!{}>'.format(m.id):
            return 'Mentioned', 100
        if type(m) is discord.Member and len(m.activities) > 0:
            if any(arg in a.name.lower() for a in m.activities if a.name is not None):
                return "Playing '{}'".format([a.name for a in m.activities if a.name is not None and arg in a.name.lower()][0]).replace(
                    arg, '**{}**'.format(arg)
                ), compareMatch(arg, [a.name for a in m.activities if arg in a.name.lower()][0])
            if any(a.type is discord.ActivityType.listening for a in m.activities):
                for a in m.activities:
                    try:
                        if a.type is discord.ActivityType.listening:
                            if arg in a.title.lower():
                                return 'Listening to {} by {}'.format(a.title.replace(arg, '**{}**'.format(arg)), ', '.join(a.artists)), compareMatch(
                                    arg, a.title
                                )
                            elif any([arg in s.lower() for s in a.artists]):
                                return 'Listening to {} by {}'.format(a.title, ', '.join(a.artists).replace(arg, '**{}**'.format(arg))), compareMatch(
                                    arg, [s for s in a.artists if arg in s.lower()][0]
                                )
                    except:
                        pass
        if type(m) is discord.Member and arg in m.joined_at.strftime('%A %B %d %Y %B %Y').lower():
            return 'Server join date appears to match your search', compareMatch(arg, m.created_at.strftime('%A%B%d%Y%B%Y'))
        if arg in m.created_at.strftime('%A %B %d %Y %B %Y').lower():
            return 'Account creation date appears to match your search', compareMatch(arg, m.created_at.strftime('%A%B%d%Y%B%Y'))
        if type(m) is discord.Member and arg in str(m.status):
            return "Member is '{}'".format(str(m.status).replace(arg, '**{}**'.format(arg))), compareMatch(arg, str(m.status))
        if type(m) is discord.Member and any(s in arg for s in ['mobile', 'phone']) and m.is_on_mobile():
            return 'Is on mobile app'.replace(arg, '**{}**'.format(arg)), compareMatch(arg, 'mobile')
        if type(m) is discord.Member and (any(arg in r.name.lower() for r in m.roles) or any(arg in str(r.id) for r in m.roles)):
            return 'Has role matching **{}**'.format(arg), compareMatch(
                arg, [r.name for r in m.roles if arg in r.name.lower() or arg in str(r.id)][0]
            )
        if type(m) is discord.Member and any([arg in [p[0] for p in iter(m.guild_permissions) if p[1]]]):
            return "Has permissions: '{}'".format(
                [p[0] for p in iter(m.guild_permissions) if p[1] and arg in p[0]][0].replace(arg, '**{}**'.format(arg))
            ), compareMatch(arg, [p[0] for p in iter(m.guild_permissions) if p[1] and arg in p[0]][0])
        if 'bot' in arg and m.bot:
            return 'Bot account', compareMatch(arg, 'bot')
        if type(m) is not discord.Member:
            return None
        if m.voice is None:
            return None  # Saves multiple checks later on since it's all voice attribute matching
        if any(s in arg for s in ['voice', 'audio', 'talk']):
            return 'In voice chat', compareMatch(arg, 'voice')
        if 'mute' in arg and (m.voice.mute or m.voice.self_mute):
            return 'Muted', compareMatch(arg, 'mute')
        if 'deaf' in arg and (m.voice.deaf or m.voice.self_deaf):
            return 'Deafened', compareMatch(arg, 'deaf')
        if arg in m.voice.channel.name.lower():
            return 'Current voice channel matches **{}**'.format(arg), compareMatch(arg, m.voice.channel.name)
        return None

    return [{'member': m, 'check': check(m)} for m in members if check(m) is not None]  # list of dicts


async def FindMoreRoles(g: discord.Guild, arg):
    arg = arg.lower()

    def check(r):
        if arg in r.name.lower():
            return "Role name is '{}'".format(r.name.replace(arg, '**{}**'.format(arg))), compareMatch(arg, r.name)
        if arg in str(r.id):
            return "Role ID is '{}'".format(r.id).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(r.id))
        if any([arg in [p[0] for p in iter(r.permissions) if p[1]]]):
            return "Role has permissions: '{}'".format(
                [p[0] for p in iter(r.permissions) if p[1] and arg in p[0]][0].replace(arg, '**{}**'.format(arg))
            ), compareMatch(arg, [p[0] for p in iter(r.permissions) if p[1] and arg in p[0]][0])
        if any(['hoist' in arg, all(s in arg for s in ['display', 'separate'])]) and r.hoist:
            return 'Role is displayed separately', compareMatch(arg, 'separate')
        if 'managed' in arg and r.managed:
            return 'Role is externally managed', compareMatch(arg, 'managed')
        if 'mentionable' in arg and r.mentionable:
            return 'Role is mentionable', compareMatch(arg, 'mentionable')
        if arg in r.created_at.strftime('%A %B %d %Y %B %Y').lower():
            return 'Role creation date appears to match your search', compareMatch(arg, r.created_at.strftime('%A%B%d%Y%B%Y'))
        return None

    return [{'role': r, 'check': check(r)} for r in g.roles if check(r) is not None]  # List of dicts


async def FindMoreChannels(g: discord.Guild, arg):
    arg = arg.lower()

    def check(c):
        if arg in c.name.lower():
            return "Name is '{}'".format(c.name.replace(arg, '**{}**'.format(arg))), compareMatch(arg, c.name)
        if arg in str(c.id):
            return "ID is '{}'".format(c.id).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(c.id))
        if arg in c.created_at.strftime('%A %B %d %Y %B %Y').lower():
            return 'Creation date appears to match your search', compareMatch(arg, c.created_at.strftime('%A%B%d%Y%B%Y'))
        if type(c) is discord.TextChannel and c.topic is not None and arg in c.topic:
            return 'Topic contains **{}**'.format(arg), compareMatch(arg, c.topic)
        if type(c) is discord.TextChannel and c.slowmode_delay > 0 and arg in str(c.slowmode_delay):
            return 'Slowmode is {}s'.format(c.slowmode_delay), compareMatch(arg, c.slowmode_delay)
        if type(c) is discord.TextChannel and c.is_news() and 'news' in arg:
            return 'News channel', compareMatch(arg, 'news')
        if type(c) is discord.VoiceChannel and arg in str(c.bitrate / 1000):
            return 'Bitrate: {}'.format(round(c.bitrate / 1000)).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(round(c.bitrate / 1000)))
        if type(c) is discord.VoiceChannel and c.user_limit > 0 and arg in str(c.user_limit):
            return 'User limit is {}'.format(c.user_limit).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(c.user_limit))
        if type(c) is not discord.VoiceChannel and c.is_nsfw() and 'nsfw' in arg:
            return 'NSFW', compareMatch(arg, 'nsfw')
        return None

    return [{'channel': c, 'check': check(c)} for c in g.channels if check(c) is not None]


async def FindMoreInvites(g: discord.Guild, arg):
    arg = arg.lower()

    def check(i):
        if arg in i.code.lower():
            return i.code.replace(arg, '**{}**'.format(arg)), compareMatch(arg, i.code)
        if arg in i.created_at.strftime('%A %B %d %Y %B %Y').lower():
            return 'Creation date appears to match your search', compareMatch(arg, i.created_at.strftime('%A%B%d%Y%B%Y'))
        if i.temporary and 'temp' in arg:
            return 'Invite is temporary'
        if arg in str(i.uses):
            return 'Used {} times'.format(i.uses), compareMatch(arg, str(i.uses))
        if arg in str(i.max_uses):
            return 'Can be used {} times'.format(i.max_uses), compareMatch(arg, str(i.uses))
        if arg in i.inviter.name or arg in str(i.inviter.id):
            return 'Created by {}'.format(i.inviter.name).replace(arg, '**{}**'.format(arg)), compareMatch(arg, i.inviter.name)
        if arg in i.channel.name or arg in str(i.channel.id):
            return 'Goes to {}'.format(i.channel.name).replace(arg, '**{}**'.format(arg)), compareMatch(arg, i.channel.name)
        return None

    try:
        return [{'invite': i, 'check': check(i)} for i in (await g.invites()) if check(i) is not None]
    except:
        return []


async def FindMoreEmojis(g: discord.Guild, arg):
    arg = arg.lower()

    def check(e):
        if arg in e.name.lower():
            return 'Emoji name is {}'.format(e.name.replace(arg, '**{}**'.format(arg))), compareMatch(arg, e.name)
        if arg == str(e):
            return 'Emoji typed in search query', 100
        if arg in str(e.id):
            return "ID is '{}'".format(e.id).replace(arg, '**{}**'.format(arg)), compareMatch(arg, str(e.id))
        if 'animated' in arg and e.animated:
            return 'Emoji is animated', compareMatch(arg, 'animated')
        if 'managed' in arg and e.managed:
            return 'Emoji is externally managed', compareMatch(arg, 'managed')
        if arg in e.created_at.strftime('%A %B %d %Y %B %Y').lower():
            return 'Role creation date appears to match your search', compareMatch(arg, e.created_at.strftime('%A%B%d%Y%B%Y'))
        return None

    return [{'emoji': e, 'check': check(e)} for e in g.emojis if check(e) is not None]


def compareMatch(arg, search):
    """Return number between 0 and 100, based on how close the search term is to the result in length"""
    return round(len(arg) / len(search) * 100)


async def name_zone(s: discord.Guild):
    return (await get_server(s)).get('tzname', 'EST')


async def time_zone(s: discord.Guild):
    return (await get_server(s)).get('offset', -4)


async def prefix(s: discord.Guild):
    return (await get_server(s)).get('prefix', '.')


async def color_theme(s):
    return (await get_server(s)).get('colorTheme', 0)


async def get_server(s: discord.Guild, return_value={}):
    return await lightningdb.get_server(s.id, return_value)


async def get_user(u: discord.User):
    return await lightningdb.get_user(u.id)


async def getServerMember(m: discord.Member):
    """Gets the member data given a member object"""
    return (await get_server(m.guild))['members'].get(str(m.id))


def paginate(iterable: list, per_page=10):
    """Splits a list into pages of a given size"""
    for i in range(0, len(iterable), per_page):
        yield iterable[i : i + per_page]


def first_letter_upper(s: str):
    """Capitalizes the first letter of a string"""
    return s[0].upper() + s[1:]


def serialize_json(o):
    if type(o) is datetime.datetime:
        return o.isoformat()


def sanitize_filename(string: str):
    illegal_char_list = '#%&\{\}\\<>*?/$!\'":@+`|='
    export = ''.join(char if char not in illegal_char_list else '-' for char in string.replace(' ', '_') if char != ' ')
    return export


def date_to_filename(date: datetime.datetime):
    return date.strftime('%m%d%Y%H%M%S%f')


def large_server(server: discord.Guild):
    return server.member_count > 150


async def update_bot_presence(bot: commands.Bot, status: discord.Status = None, activity: discord.BaseActivity = None):
    """Updates the bot's presence based on the given dictionary"""
    current_presence = {'status': bot.status, 'activity': bot.activity}
    new_presence = {'status': status or bot.status, 'activity': activity or bot.activity}
    if current_presence != new_presence:
        await bot.change_presence(**new_presence)


async def await_task(task):
    try:
        return await task
    except asyncio.CancelledError:
        pass


async def run_task(task: asyncio.Task, queue: set, name: str = '', cancel_after: int = 1800):
    task = asyncio.create_task(task, name=name)
    queue.add(task)
    task.add_done_callback(queue.discard)
    while not task.done() and not task.cancelled() and cancel_after > 0:
        await asyncio.sleep(1)
        cancel_after -= 1
    if not task.done():
        task.cancel()
        logger.info(f'Cancelled task {name} after {cancel_after} seconds')


def get_dir_size(path='.'):
    """
    Calculate the total size of all files in a directory, including subdirectories.

    Parameters:
        path (str): The directory path to calculate the size for. Defaults to the current directory.

    Returns:
        int: The total size of all files in the directory in bytes.
    """
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file() and not entry.is_symlink():
                        total += entry.stat().st_size
                    elif entry.is_dir():
                        total += get_dir_size(entry.path)
                except (PermissionError, FileNotFoundError):
                    continue
    except (PermissionError, FileNotFoundError):
        pass
    return total


def sort_files_by_oldest(directory):
    # Get all files in the directory
    files = [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

    # Sort files by modification time (oldest first)
    files.sort(key=lambda x: os.path.getmtime(x))

    return files


def sort_folders_by_oldest(directory):
    # Get all folders in the directory
    folders = [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isdir(os.path.join(directory, f))]

    # Sort folders by creation time (oldest first)
    folders.sort(key=lambda x: os.path.getctime(x))

    return folders


class BasicView(discord.ui.View):
    """For when you just need somewhere to stick some components"""

    def __init__(self, timeout=300):
        super().__init__(timeout=timeout)
