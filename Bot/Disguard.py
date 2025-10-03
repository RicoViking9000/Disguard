"""This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files"""

import asyncio
import datetime
import logging
import logging.handlers
import os
import traceback
import tracemalloc

import discord
from discord.ext import commands
from pymongo import errors as mongoErrors

import Birthdays
import Cyberlog
import database
import Indexing
import lightningdb
import Misc
import Reddit
import secure
import utility

tracemalloc.start()

booted = False
loading = None
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays', 'Misc', 'Info', 'Reddit', 'Support', 'Dev', 'Help', 'Privacy', 'Indexing', 'Backblaze']

print('Connecting...')

prefixes = {}
variables = {}
emojis = {}
NEWLINE = '\n'
qlf = '  '  # Two special characters to represent quoteLineFormat
qlfc = ' '

yellow = (0xFFFF00, 0xFFFF66)
blue = (0x0000FF, 0x6666FF)

if os.path.exists('discord.log'):
    os.remove('discord.log')

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
logging.getLogger('discord.http').setLevel(logging.INFO)
handler = logging.handlers.RotatingFileHandler(
    filename='discord.log',
    encoding='utf-8',
    maxBytes=8 * 1024 * 1024,  # 8 MiB
    backupCount=15,  # Rotate through 15 files
)
dt_fmt = '%Y-%m-%d %H:%M:%S'
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
handler.setFormatter(formatter)
logger.addHandler(handler)


async def prefix(bot: commands.Bot, message: discord.Message):
    return (await utility.prefix(message.guild)) or '.'


intents = discord.Intents.all()
intents.presences = False
intents.typing = False

bot = commands.Bot(
    command_prefix=prefix, case_insensitive=True, heartbeat_timeout=1500, intents=intents, allowed_mentions=discord.AllowedMentions.none()
)
bot.remove_command('help')
bot.initialized = False


async def main():
    lightningdb.initialize()
    # database.initialize(secure.beta())
    # await bot.start(secure.beta())
    database.initialize(secure.token())
    await bot.start(secure.token())


indexes = 'Indexes'


@bot.listen()
async def on_connect():
    await utility.update_bot_presence(bot, discord.Status.idle, discord.CustomActivity(name='Booting Disguard...'))


@bot.listen()
async def on_ready():  # Method is called whenever bot is ready after connection/reconnection. Mostly deals with database verification and creation
    """Method called when bot connects and all the internals are ready"""
    global booted
    global presence
    global loading
    global emojis
    if not booted:
        booted = True
        print('Booting...')
        loading = discord.utils.get(bot.get_guild(560457796206985216).emojis, name='loading')
        await utility.update_bot_presence(bot, activity=discord.CustomActivity(name='Synchronizing database'))
        # await bot.load_extension('Cyberlog')
        # await asyncio.sleep(2)
        for cog in cogs:
            try:
                await bot.load_extension(cog)
            except Exception as e:
                print(f'Cog load error: {e}')
                traceback.print_exc()
        print('Cogs loaded', bot.cogs)
        cyber: Cyberlog.Cyberlog = bot.get_cog('Cyberlog')
        emojis = cyber.emojis

        async def initialize_check():
            while not bot.initialized:
                await asyncio.sleep(1)

        print('Waiting for database callback...')
        await asyncio.wait_for(initialize_check(), timeout=None)
        await utility.update_bot_presence(bot, activity=discord.CustomActivity(name='Retrieving data'))
        print('Grabbing pins...')
        await cyber.grab_pins()
    print('Booted')
    presence = {'status': discord.Status.online, 'activity': discord.Activity(name=f'{len(bot.guilds)} servers', type=discord.ActivityType.watching)}
    if not bot.activity:
        await utility.update_bot_presence(bot, discord.Status.online, discord.CustomActivity(name=f'Guarding {len(bot.guilds)} servers'))


async def indexMessages(server: discord.Guild, channel: discord.TextChannel, full=False):
    if channel.id in (534439214289256478, 910598159963652126):
        return
    start = datetime.datetime.now()
    try:
        saveImages = (await utility.get_server(server))['cyberlog'].get('image') and not channel.is_nsfw()
    except AttributeError:
        return
    if lightningdb.database.get_collection(str(channel.id)) is None:
        full = True
    existing_message_counter = 0
    async for message in channel.history(limit=None, oldest_first=full):
        try:
            await lightningdb.post_message_2024(message)
        except mongoErrors.DuplicateKeyError:
            if not full:
                existing_message_counter += 1
                if existing_message_counter >= 15:
                    break
        if not message.author.bot and (discord.utils.utcnow() - message.created_at).days < 7 and saveImages:
            attachments_path = f'Attachments/{message.guild.id}/{message.channel.id}/{message.id}'
            try:
                os.makedirs(attachments_path)
            except FileExistsError:
                pass
            for attachment in message.attachments:
                if attachment.size / 1000000 < 8:
                    try:
                        await attachment.save(f'{attachments_path}/{attachment.filename}')
                    except discord.HTTPException:
                        pass
        if full:
            await asyncio.sleep(0.0015)
    print(f'Indexed {server.name}: {channel.name} in {(datetime.datetime.now() - start).seconds} seconds')


@bot.listen()
async def on_message(message: discord.Message):
    """Calls the various functions in other cogs"""
    await bot.wait_until_ready()
    if not isinstance(message.channel, discord.TextChannel):
        return
    if message.author.id == bot.user.id:
        return
    # cyberlog: Cyberlog.Cyberlog = bot.get_cog('Cyberlog')
    # await cyberlog.on_message(message)

    # indexing: Indexing.Indexing = bot.get_cog('Indexing')
    # await indexing.on_message(message)

    # antispam: Antispam.Antispam = bot.get_cog('Antispam')
    # await antispam.on_message(message)
    indexing: Indexing.Indexing = bot.get_cog('Indexing')
    try:
        await indexing.on_message(message)
    except Exception as e:
        logger.error(f'Error in Indexing on_message: {e}')
        traceback.print_exc()
    if not message.content:
        return
    if message.author.bot:
        return
    reddit: Reddit.Reddit = bot.get_cog('Reddit')
    try:
        await reddit.on_message(message)
    except Exception as e:
        logger.error(f'Error in Reddit on_message: {e}')
        traceback.print_exc()
    birthdays: Birthdays.Birthdays = bot.get_cog('birthdays')
    try:
        await birthdays.on_message(message)
    except Exception as e:
        logger.error(f'Error in Birthdays on_message: {e}')
        traceback.print_exc()
    misc: Misc.Misc = bot.get_cog('Misc')
    try:
        await misc.on_message(message)
    except Exception as e:
        logger.error(f'Error in Misc on_message: {e}')
        traceback.print_exc()


@bot.hybrid_command(help="Get Disguard's invite link")
async def invite(ctx: commands.Context):
    e = discord.Embed(
        title='Invite Links',
        description='• Invite Disguard to your server: https://discord.com/oauth2/authorize?client_id=558025201753784323&permissions=8&scope=bot\n\n• Join the Disguard discord server: https://discord.gg/xSGujjz',
    )
    await ctx.send(embed=e)


@bot.hybrid_command(help="Get a link to Disguard's web dashboard")
async def dashboard(ctx: commands.Context):
    await ctx.send(f"https://disguard.herokuapp.com/manage/{ctx.guild.id if ctx.guild else ''}")


@bot.hybrid_command(help="Check Disguard's response time")
async def ping(ctx):
    await ctx.send(f'Pong! Websocket latency: {round(bot.latency * 1000)}ms')


@bot.command(name='synctree')
@commands.is_owner()
async def sync_tree(ctx: commands.Context):
    await bot.tree.sync()
    await bot.tree.sync(guild=discord.Object(utility.DISGUARD_SERVER_ID))
    await ctx.send('Synced tree')


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
    message = await ctx.send('Evaluating this message type...')
    await message.edit(content=f'Type: {message.type.name}')


asyncio.run(main())
