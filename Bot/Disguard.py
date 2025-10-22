"""This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files"""

import asyncio
import logging
import logging.handlers
import os
import traceback
import tracemalloc

import discord
from discord.ext import commands

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


@bot.listen()
async def on_message(message: discord.Message):
    """Calls the various functions in other cogs"""
    if not bot.is_ready():
        return
    if not isinstance(message.channel, discord.TextChannel):
        return
    if message.author.id == bot.user.id:
        return

    # cheap early exits before heavier work
    if not message.content:
        return
    if message.author.bot:
        return

    data = await utility.get_server(message.guild)

    # gather other handlers concurrently to reduce latency
    indexing: Indexing.Indexing = bot.get_cog('Indexing')
    cyberlog: Cyberlog.Cyberlog = bot.get_cog('Cyberlog')
    reddit: Reddit.Reddit = bot.get_cog('Reddit')
    birthdays: Birthdays.Birthdays = bot.get_cog('birthdays')
    misc: Misc.Misc = bot.get_cog('Misc')

    tasks = []
    if indexing:
        tasks.append(asyncio.create_task(indexing.on_message(message, data)))
    if cyberlog:
        tasks.append(asyncio.create_task(cyberlog.on_message(message, data)))
    if reddit:
        tasks.append(asyncio.create_task(reddit.on_message(message, data)))
    if birthdays:
        tasks.append(asyncio.create_task(birthdays.on_message(message, data)))
    if misc:
        tasks.append(asyncio.create_task(misc.on_message(message, data)))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                logger.error(f'Error in on_message handler task: {res}')
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
