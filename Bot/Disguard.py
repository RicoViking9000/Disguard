'''This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files'''

import discord
from discord.ext import commands, tasks
from discord import app_commands
import secure
import database
import lightningdb
import Antispam
import Cyberlog
import Birthdays
import Reddit
import Misc
import utility
import os
import datetime
import collections
import asyncio
import traceback
import random
import logging
import logging.handlers
import inspect
import typing
import json
import copy
import codecs
import shutil
import asyncpraw
import sys
import py7zr
from pymongo import errors as mongoErrors
import tracemalloc
import linecache

tracemalloc.start()

booted = False
loading = None
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays', 'Misc', 'Info', 'Reddit', 'Support', 'Dev', 'Help', 'Privacy']

print("Connecting...")

prefixes = {}
variables = {}
emojis = {}
NEWLINE = '\n'
qlf = '  ' #Two special characters to represent quoteLineFormat
qlfc = ' '

yellow = (0xffff00, 0xffff66)
blue = (0x0000FF, 0x6666ff)

if os.path.exists('discord.log'):
    os.remove('discord.log')

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
logging.getLogger('discord.http').setLevel(logging.INFO)
handler = logging.handlers.RotatingFileHandler(
    filename='discord.log',
    encoding='utf-8',
    maxBytes=256 * 1024 * 1024,  # 256 MiB
    backupCount=5,  # Rotate through 5 files
)
dt_fmt = '%Y-%m-%d %H:%M:%S'
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
handler.setFormatter(formatter)
logger.addHandler(handler)

async def prefix(bot: commands.Bot, message: discord.Message):
    return (await utility.prefix(message.guild)) or '.'

intents = discord.Intents.all()

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, heartbeat_timeout=1500, intents=intents, allowed_mentions = discord.AllowedMentions.none())
bot.remove_command('help')

async def main():
    lightningdb.initialize()
    database.initialize(secure.beta())
    await bot.start(secure.beta())
    # database.initialize(secure.token())
    # await bot.start(secure.token())
        
indexes = 'Indexes'

async def UpdatePresence():
    await bot.change_presence(status=presence['status'], activity=presence['activity'])

@bot.listen()
async def on_connect():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name='the server connection', type=discord.ActivityType.listening))

@bot.listen()
async def on_ready(): #Method is called whenever bot is ready after connection/reconnection. Mostly deals with database verification and creation
    '''Method called when bot connects and all the internals are ready'''
    global booted
    global presence
    global loading
    global emojis
    if not booted:
        booted=True
        print('Booting...')
        loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')
        presence['activity'] = discord.Activity(name='my boss (Syncing data...)', type=discord.ActivityType.listening)
        await UpdatePresence()
        #await bot.load_extension('Cyberlog')
        #await asyncio.sleep(2)
        for cog in cogs:
            try:
                await bot.load_extension(cog)
                print(f'Loaded cog {cog}')
            except Exception as e: 
                print(f'Cog load error: {e}')
                traceback.print_exc()
        print('Cogs loaded', bot.cogs)
        cyber: Cyberlog.Cyberlog = bot.get_cog('Cyberlog')
        emojis = cyber.emojis
        def initializeCheck(m: discord.Message): return m.author.id == bot.user.id and m.channel.id == cyber.imageLogChannel.id and m.content == 'Completed'
        print('Waiting for database callback...')
        await bot.wait_for('message', check=initializeCheck) #Wait for bot to synchronize database
        presence['activity'] = discord.Activity(name='my boss (Indexing messages...)', type=discord.ActivityType.listening)
        await UpdatePresence()
        print('Starting indexing...')
        for server in bot.guilds:
            print(f'Indexing {server.name}')
            # await asyncio.gather(*[indexMessages(server, c) for c in server.text_channels])
            # Cyberlog.indexed[server.id] = True
        presence = {'status': discord.Status.online, 'activity': discord.Activity(name=f'{len(bot.guilds)} servers', type=discord.ActivityType.watching)}
        await UpdatePresence()
        await cyber.grab_pins()
    print("Booted")
    await UpdatePresence()

async def indexMessages(server: discord.Guild, channel: discord.TextChannel, full=False):
    if channel.id in (534439214289256478, 910598159963652126): return
    start = datetime.datetime.now()
    try: saveImages = (await utility.get_server(server))['cyberlog'].get('image') and not channel.is_nsfw()
    except AttributeError: return
    if lightningdb.database.get_collection(str(channel.id)) is None: full = True
    existing_message_counter = 0
    async for message in channel.history(limit=None, oldest_first=full):
        try: await lightningdb.post_message(message)
        except mongoErrors.DuplicateKeyError:
            if not full:
                existing_message_counter += 1
                if existing_message_counter >= 15: break
        if not message.author.bot and (discord.utils.utcnow() - message.created_at).days < 7 and saveImages:
            attachments_path = f'Attachments/{message.guild.id}/{message.channel.id}/{message.id}'
            try: os.makedirs(attachments_path)
            except FileExistsError: pass
            for attachment in message.attachments:
                if attachment.size / 1000000 < 8:
                    try: await attachment.save(f'{attachments_path}/{attachment.filename}')
                    except discord.HTTPException: pass
        if full: await asyncio.sleep(0.0015)
    print(f'Indexed {server.name}: {channel.name} in {(datetime.datetime.now() - start).seconds} seconds')

@bot.listen()
async def on_message(message: discord.Message):
    '''Calls the various functions in other cogs'''
    await bot.wait_until_ready()
    if not isinstance(message.channel, discord.TextChannel): return
    if message.author.id == bot.user.id: return
    # cyberlog: Cyberlog.Cyberlog = bot.get_cog('Cyberlog')
    # await cyberlog.on_message(message)
    # antispam: Antispam.Antispam = bot.get_cog('Antispam')
    # await antispam.on_message(message)
    if not message.content: return
    if message.author.bot: return
    reddit: Reddit.Reddit = bot.get_cog('Reddit')
    await reddit.on_message(message)
    # birthdays: Birthdays.Birthdays = bot.get_cog('Birthdays')
    # await birthdays.on_message(message)
    misc: Misc.Misc = bot.get_cog('Misc')
    await misc.on_message(message)


@bot.hybrid_command(help='Get Disguard\'s invite link')
async def invite(ctx: commands.Context):
    e = discord.Embed(title='Invite Links', description='• Invite Disguard to your server: https://discord.com/oauth2/authorize?client_id=558025201753784323&permissions=8&scope=bot\n\n• Join the Disguard discord server: https://discord.gg/xSGujjz')
    await ctx.send(embed=e)

# @bot.command()
# async def privacy(ctx):
#     await ctx.send("https://disguard.netlify.app/privacybasic")

@bot.command()
async def delete(ctx: commands.Context, message_id: str):
    '''Delete one of Disguard\'s messages from the user\'s DMs
    Parameters
    ----------
    message_id : str
        The ID of the message to delete
    '''
    try:
        message = await ctx.author.fetch_message(int(message_id))
        await message.delete()
        await ctx.message.add_reaction('✅')
    except: await ctx.message.add_reaction('❌')

@bot.hybrid_command(help='Get a link to Disguard\'s web dashboard')
async def dashboard(ctx: commands.Context):
    await ctx.send(f"https://disguard.herokuapp.com/manage/{ctx.guild.id if ctx.guild else ''}")

@bot.hybrid_command(aliases=['config', 'configuration', 'setup'], help='View Disguard\'s configuration for this server')
async def server(ctx: commands.Context):
    '''Pulls up information about the current server, configuration-wise'''
    g = ctx.guild
    config = await utility.get_server(ctx.guild)
    cyberlog = config.get('cyberlog')
    antispam = config.get('antispam')
    baseURL = f'http://disguard.herokuapp.com/manage/{ctx.guild.id}'
    green = emojis['online']
    red = emojis['dnd']
    embed=discord.Embed(title=f'Server Configuration - {g}', color=yellow[await utility.color_theme(ctx.guild)])
    embed.description=f'''**Prefix:** `{config.get("prefix")}`\n\n⚙ General Server Settings [(Edit full settings on web dashboard)]({baseURL}/server)\n> Time zone: {config.get("tzname")} ({discord.utils.utcnow() + datetime.timedelta(hours=config.get("offset")):%I:%M %p})\n> {red if config.get("birthday") == 0 else green}Birthday announcements: {"<Disabled>" if config.get("birthday") == 0 else f"Announce daily to {bot.get_channel(config.get('birthday')).mention} at {config.get('birthdate'):%I:%M %p}"}\n> {red if not config.get("jumpContext") else green}Send embed for posted jump URLs: {"Enabled" if config.get("jumpContext") else "Disabled"}'''
    embed.description+=f'''\n🔨Antispam [(Edit full settings)]({baseURL}/antispam)\n> {f"{green}Antispam: Enabled" if antispam.get("enabled") else f"{red}Antispam: Disabled"}\n> ℹMember warnings: {antispam.get("warn")}; after losing warnings: {"Nothing" if antispam.get("action") == 0 else f"Automute for {antispam.get('muteTime') // 60} minute(s)" if antispam.get("action") == 1 else "Kick" if antispam.get("action") == 2 else "Ban" if antispam.get("action") == 3 else f"Give role {g.get_role(antispam.get('customRoleID'))} for {antispam.get('muteTime') // 60} minute(s)"}'''
    embed.description+=f'''\n📜 Logging [(Edit full settings)]({baseURL}/cyberlog)\n> {f"{green}Logging: Enabled" if cyberlog.get("enabled") else f"{red}Logging: Disabled"}\n> ℹDefault log channel: {bot.get_channel(cyberlog.get("defaultChannel")).mention if bot.get_channel(cyberlog.get("defaultChannel")) else "<Not configured>" if not cyberlog.get("defaultChannel") else "<Invalid channel>"}\n'''
    await ctx.send(embed=embed)

@bot.hybrid_command(help='Check Disguard\'s response time')
async def ping(ctx):
    await ctx.send(f'Pong! Websocket latency: {round(bot.latency * 1000)}ms')

@bot.command(name='synctree')
@commands.is_owner()
async def sync_tree(ctx: commands.Context):
    await bot.tree.sync()
    await bot.tree.sync(guild=discord.Object(utility.DISGUARD_SERVER_ID))
    await ctx.send('Synced tree')

@bot.hybrid_command(help='Retrieve the data Disguard stores about you')
async def data(ctx: commands.Context):
    def accept(r: discord.Reaction, u: discord.User): return str(r) in ['🇦', '🇧'] and u.id == ctx.author.id and r.message.id == requestMessage.id
    requestMessage = await ctx.send(f'Data retrieval command: I will gather all of the data I store about you and DM it to you as an archive file\nTo continue, please choose a file format\n{qlf}A - .zip\n{qlf}B - .7z')
    for reac in ['🇦', '🇧']: await requestMessage.add_reaction(reac)
    result = await bot.wait_for('reaction_add', check=accept)
    if str(result[0]) == '🇦': ext = 'zip'
    else: ext = '7z'
    if not ctx.author.dm_channel: await ctx.author.create_dm()
    ctx.channel = ctx.author.dm_channel
    statusMessage = await ctx.send(f'•You will be sent a .{ext} file containing all relevant data involving you for each server, with directories containing relevant data from that server stored as .json files\n•If you have Administrator permissions in a server, one of the .json files will be the entire database entry for your server\n•You will also receive a .json containing your global user data (independent of server-specific data)\n\n{loading}Processing data...')
    if not ctx.guild: await requestMessage.delete()
    else: await requestMessage.edit(content=None, embed=discord.Embed(description=f'[Click to jump to the DM I just sent you]({statusMessage.jump_url})'))
    def convertToFilename(string):
        export = ''
        illegalCharList = [c for c in '#%&\{\}\\<>*?/$!\'":@+`|=']
        for char in string:
            if char not in illegalCharList: 
                if char != ' ': export += char
                else: export += '-'
        return export
    basePath = f'Attachments/Temp/{ctx.message.id}'
    os.makedirs(basePath)
    userData = (await database.GetUser(ctx.author))
    if userData:
        userData.pop('_id')
        dataToWrite = json.dumps(userData, indent=4, default=serializeJson)
        attachmentCount = 0
        with open(f'{basePath}/{f"{convertToFilename(str(ctx.author))} - UserData"}.json', 'w+') as f:
            f.write(dataToWrite)
    for server in [g for g in bot.guilds if ctx.author in g.members]:
        member = [m for m in server.members if m.id == ctx.author.id][0]
        serverPath = f'{basePath}/{convertToFilename(server.name)}'
        os.makedirs(f'{serverPath}/MessageAttachments')
        if any(role.permissions.administrator for role in member.roles) or server.owner.id == member.id:
            try: os.makedirs(serverPath)
            except FileExistsError: pass
            serverData = (await database.GetServer(server))
            if serverData:
                serverData.pop('_id')
                dataToWrite = json.dumps(serverData, indent=4, default=serializeJson)
                with open(f'{serverPath}/ServerDatabaseEntry.json', 'w+') as f:
                    f.write(dataToWrite)
        dataToWrite = json.dumps(await lightningdb.get_member(server.id, member.id), indent=4, default=serializeJson)
        with open(f'{serverPath}/Server-MemberInfo.json', 'w+') as f:
            f.write(dataToWrite)
        for channel in server.text_channels:
            indexData = await lightningdb.get_messages_by_author(member.id, [channel.id])
            if not indexData: continue
            memberIndexData = {}
            for k, v in indexData[0].items():
                try: os.makedirs(f'{serverPath}/MessageIndexes')
                except FileExistsError: pass
                memberIndexData.update({k: v})
                try:
                    aPath = f'Attachments/{server.id}/{channel.id}/{k}'
                    attachmentCount += len(os.listdir(aPath))
                except FileNotFoundError: pass
            if len(memberIndexData) > 0:
                with open(f'{serverPath}/MessageIndexes/{convertToFilename(channel.name)}.json', 'w+') as f:
                    f.write(json.dumps(memberIndexData, indent=4))
        with codecs.open(f'{serverPath}/MessageAttachments/README.TXT', 'w+', 'utf-8-sig') as f: 
            f.write(f"I also have {attachmentCount} file attachments on file that you've uploaded, but I can't attach them due to the 8MB file size limit. If you would like to receive these files, contact my developer (RicoViking9000#2395) in one of the following ways:\n{qlf}•Use the `invite` command to join my support server\n{qlf}•Use the `ticket` command to get in direct contact with my developer through the Ticket System\n{qlf}•If you share a server with my developer, you may DM him - but he won\'t accept random friend requests from users sharing no servers with him'")
    readMe = f'Directory Format\n\nDisguardUserDataRequest_[Timestamp]\n|-- 📄UserData.json --> Contains the database entry for your global data, not specific to a server\n|-- 📁[Server name] --> Contains the data for this server'
    readMe += f'\n|-- |-- 📄ServerDatabaseEntry.json --> If you are an administrator of this server, this will contain the database entry for this server\n|-- |-- 📄Server-MemberInfo.json --> Contains your server-indepedent data entry for this server'
    readMe += f'\n|-- |-- 📁MessageIndexes --> Folder containing message indexes authored by you for this server\n|-- |-- |-- 📄[channel name].json --> File containing message indexes authored by you for this channel'
    readMe += f'\n|-- |-- 📁MessageAttachments --> Folder containing a ReadMe file explaining how to obtain message attachment data'
    readMe += '\n\nThis readME is also saved just inside of the zipped folder. If you do not have a code editor to open .json files and make them look nice, web browsers can open them (drag into new tab area or use ctrl + o in your web browser), along with Notepad or Notepad++ (or any text editor)\n\nA guide on how to interpret the data fields will be available soon on my website. In the meantime, if you have a question about any of the data, contact my developer through the `ticket` command or ask in my support server (`invite` command)'
    with codecs.open(f'{basePath}/README.txt', 'w+', 'utf-8-sig') as f: 
        f.write(readMe)
    fileName = f'Attachments/Temp/DisguardUserDataRequest_{(discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(ctx.guild) if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
    await statusMessage.edit(content=statusMessage.content[:statusMessage.content.find(str(loading))] + f'{loading}Zipping data...')
    shutil.register_archive_format('7zip', py7zr.pack_7zarchive, description='7zip archive')
    shutil.make_archive(fileName, '7zip' if ext == '7z' else 'zip', basePath)
    fl = discord.File(f'{fileName}.{ext}')
    await statusMessage.delete()
    await ctx.send(content=f'```{readMe}```', file=fl)

@commands.is_owner()
@bot.command()
async def nameVerify(ctx):
    await database.NameVerify(ctx.guild)
    await ctx.send('Successful')

# @bot.event
# async def on_error(event, *args, **kwargs):
#     logging.error(exc_info=True)
#     traceback.print_exc()

@bot.hybrid_command(help='You know the rules, and so do I')
async def rickroll(ctx: commands.Context):
    await ctx.send('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

@bot.command()
@commands.is_owner()
async def test(ctx: commands.Context):
    await ctx.interaction.response.defer()
    for server in bot.guilds:
        await database.convert_reddit_feeds(server)
    await ctx.send('Done converting')

def serializeJson(o):
    if type(o) is datetime.datetime: return o.isoformat()

asyncio.run(main())
