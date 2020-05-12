'''This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files'''

import discord
from discord.ext import commands, tasks
import secure
import database
import Antispam
import Cyberlog
import os
import datetime
import collections
import asyncio
import traceback
import random
import logging
import inspect
import typing


booted = False
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays']
print("Booting...")
prefixes = {}
variables = {}

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

def prefix(bot, message):
    p = prefixes.get(message.guild.id)
    return p if p is not None else '.'

bot = commands.Bot(command_prefix=prefix, case_insensitive=True, heartbeat_timeout=300)
bot.remove_command('help')

indexes = 'Indexes'
oPath = 'G:/My Drive/Other'
urMom = 'G:/My Drive/Other/ur mom'
campMax = 'G:/My Drive/Other/M A X'

@tasks.loop(minutes=1)
async def updatePrefixes():
    for server in bot.guilds: prefixes[server.id] = await database.GetPrefix(server)

# @tasks.loop(minutes=1)
# async def anniversaryDayKickoff():
#     if datetime.datetime.now().strftime('%m %d %y %H:%M') == '03 18 20 10:55':
#         embed=discord.Embed(title=datetime.datetime.now().strftime('%B %d, %Y %H:%M %p'),description=secure.anniversary(),color=0xffff00, timestamp=datetime.datetime.utcnow())
#         embed.set_image(url=secure.embedImage())
#         await bot.get_user(596381991151337482).send(content=secure.anniversaryMessage(), embed=embed)
#         anniversaryDayKickoff.cancel()

# @tasks.loop(minutes=1)
# async def easterAnnouncement():
#     if datetime.datetime.now().strftime('%m %d %y %H:%M') == '04 12 20 06:00':
#         for server in bot.guilds:
#             try: await (await database.CalculateAnnouncementsChannel(server, True)).send('🐰🥚✝ Happy Easter! ✝🥚🐰\n\nWishing every one of you a happy and blessed day filled with new life no matter what the state of the world may be right now,\nRicoViking9000, the developer of Disguard')
#             except: pass

@bot.listen()
async def on_ready(): #Method is called whenever bot is ready after connection/reconnection. Mostly deals with database verification and creation
    '''Method called when bot connects and all the internals are ready'''
    global booted
    global loading
    if not booted:
        booted=True
        updatePrefixes.start()
        loading = bot.get_emoji(573298271775227914)
        await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name="my boss (Verifying database...)", type=discord.ActivityType.listening))
        for cog in cogs:
            try:
                bot.load_extension(cog)
            except:
                pass
        await database.Verification(bot)
        await Antispam.PrepareFilters(bot)
        await bot.get_cog('Birthdays').updateBirthdays()
        # easterAnnouncement.start()
        Cyberlog.ConfigureSummaries(bot)
        await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name="my boss (Indexing messages...)", type=discord.ActivityType.listening))
        print('Starting indexing...')
        for server in bot.guilds:
            print('Indexing {}'.format(server.name))
            await asyncio.gather(*[indexMessages(server, c) for c in server.text_channels])
            Cyberlog.indexed[server.id] = True
    print("Booted")
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name="{} servers".format(len(bot.guilds)), type=discord.ActivityType.watching))

async def indexMessages(server, channel, full=False):
    path = "{}/{}/{}".format(indexes,server.id, channel.id)
    start = datetime.datetime.now()
    try: os.makedirs(path)
    except FileExistsError: pass
    p = os.listdir(path)
    saveImages = await database.GetImageLogPerms(server)
    try: 
        async for message in channel.history(limit=None, oldest_first=full):
            if not message.author.bot:
                if '{}_{}.txt'.format(message.id, message.author.id) in p: 
                    if not full: break
                    else: 
                        continue #Skip the code below as to not overwrite message edit history, plus to skip saving message indexes we already have (program will keep running, however, this is intentional)
                try: f = open('{}/{}_{}.txt'.format(path, message.id, message.author.id), "w+")
                except FileNotFoundError: pass
                try: f.write('{}\n{}\n{}'.format(message.created_at.strftime('%b %d, %Y - %I:%M:%S %p'), message.author.name, f"<{len(message.attachments)} attachment{'s' if len(message.attachments) > 1 else f': {message.attachments[0].filename}'}>" if len(message.attachments) > 0 else f"<{len(message.embeds)} embed>" if len(message.embeds) > 0 else message.content if len(message.content) > 0 else "<No content>"))
                except UnicodeEncodeError: pass
                try: f.close()
                except: pass
                if (datetime.datetime.utcnow() - message.created_at).days < 7 and saveImages:
                    attach = 'Attachments/{}/{}/{}'.format(message.guild.id, message.channel.id, message.id)
                    try: os.makedirs(attach)
                    except FileExistsError: pass
                    for attachment in message.attachments:
                        if attachment.size / 1000000 < 8:
                            try: await attachment.save('{}/{}'.format(attach, attachment.filename))
                            except discord.HTTPException: pass
                if full: await asyncio.sleep(0.5)
    except discord.Forbidden: print('Index error for {}'.format(server.name))
    print('Indexed {}: {} in {} seconds'.format(server.name, channel.name, (datetime.datetime.now() - start).seconds))

@commands.is_owner()
@bot.command()
async def verify(ctx):
    status = await ctx.send("Verifying...")
    await database.Verification(bot)
    await status.delete()

@commands.is_owner()
@bot.command()
async def index(ctx, t: int):
    if t == 0: target = bot.guilds
    else:
        target = bot.get_channel(t)
        if target is None:
            target = bot.get_guild(t)
            if target is None: return await ctx.send('No target found for <{}>'.format(t))
    status = await ctx.send('Indexing...')
    if type(target) is discord.Guild: await asyncio.gather(*[indexMessages(target, c, True) for c in target.text_channels])
    elif type(target) is list:
        for t in target: await asyncio.gather(*[indexMessages(t, c, True) for c in t.text_channels])
    else: await asyncio.wait([indexMessages(ctx.guild, target, True)], return_when=asyncio.FIRST_COMPLETED)
    await status.delete()

@bot.command()
async def help(ctx):
    e=discord.Embed(description=f"[Click to view help on my website • Hover for quick help](https://disguard.netlify.com/commands 'This server\'s prefix is {prefixes.get(ctx.guild.id)}\n\n— ping: Bot response time\n— Say [user] [text]: Requires manage server. Imitate [user] with webhooks by saying [text]. Omit [user] to use yourself, [user] can be ID, name, name#discrim, nickname, or mention.\n")
    e.description+='— agekick [value]: Requires manage server. Configure ageKick antispam module, which kicks accounts that are under a number of days old, type a number for value to set up\n— purge [value]: Requires manage messages. Purge [value] messages. Omit [value] to enter interactive purge.\n'
    e.description+='— pause [value] [duration]: Value is either \'antispam\' or \'logging\', pauses that active module for specified duration, or indefinitely if duration is omitted\n— info [search term]: Searches through members, roles, channels, invites, emoji, etc to pull up information that matches your search term, or yourself if search term is omitted\n'
    e.description+='— birthday [value]: Value can be an action (date or age to set for your birthday module) or search term (to bring up birthday information for someone else). Omit value to show your own birthday, along with upcoming birthdays for people you know.\')'
    await ctx.send(embed=e)

@bot.command()
async def ping(ctx):
    if datetime.datetime.utcnow() > ctx.message.created_at: await ctx.send(f'Pong! Websocket latency: {round(bot.latency * 1000)}ms\nMessage latency: {round((datetime.datetime.utcnow() - ctx.message.created_at).microseconds / 1000)}ms')
    else: await ctx.send(f'Pong! Websocket latency: {round(bot.latency * 1000)}ms\nMessage latency: -{round((ctx.message.created_at - datetime.datetime.utcnow()).microseconds / 1000)}ms')

@commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
@bot.command()
async def say(ctx, m: typing.Optional[discord.Member] = None, c: typing.Optional[discord.TextChannel] = None, *, t='Hello World'):
    '''Uses webhook to say something. T is text to say, m is member. Author if none provided. C is channel, ctx.channel if none provided'''
    bot.get_cog('Cyberlog').AvoidDeletionLogging(ctx.message)
    await ctx.message.delete()
    if c is None: c = ctx.channel
    if m is None: m = ctx.author
    w = await c.create_webhook(name='automationSayCommand', avatar=await m.avatar_url_as().read(), reason='Initiated by {} to imitate {} by saying "{}"'.format(ctx.author.name, m.name, t))
    await w.send(t, username=m.name)
    await w.delete()

@commands.is_owner()
@bot.command(name='eval')
async def evaluate(ctx, *args):
    global variables
    args = ' '.join(args)
    result = eval(args)
    if inspect.iscoroutine(result): await ctx.send(await eval(args))
    else: await ctx.send(result)

@bot.command()
async def setLogging(ctx, channel: discord.TextChannel):
    await database.SetLogChannel(ctx.guild, channel)
    await ctx.send('Yes')

@commands.is_owner()
@bot.command()
async def nameVerify(ctx):
    await database.NameVerify(ctx.guild)
    await ctx.send('Successful')

def fileAbstraction(e, p, n):
    '''
    e: Emoji to use surrounding the embed title
    p: Path relative to the directory Other in my Google Drive
    n: Name between the emojis in the embed title'''
    image = False
    newDir = f'{oPath}/{p}'
    directory = os.listdir(newDir)
    while not image:
        result = random.randint(0, len(directory) - 1)
        if '.ini' not in directory[result]: image = True
    path = f'{newDir}/{directory[result]}'
    f = discord.File(path)
    embed = discord.Embed(title=f'{e} {n} {e}',description=f'{f.filename} • Image {result + 1} of {len(directory) - 1}',color=0xffff00)
    if any([ext in directory[result].lower() for ext in ['.png', '.jpeg', '.jpg', '.gif', '.webp']]): embed.set_image(url=f'attachment://{f.filename}')
    else: embed.description=f'<Attachment: {f.filename}> • File {result + 1} of {len(directory) - 1}'
    if ' ' in directory[result]: embed.set_footer(text='Discord does not allow direct image attachments with spaces in the filename to embeds')
    return (embed, f)

@commands.cooldown(2, 15, commands.BucketType.member)
@bot.command(aliases=['lex'])
async def lexy(ctx):
    if ctx.author.id not in [247412852925661185, 596381991151337482, 524391119564570664]: return
    r = fileAbstraction(bot.get_emoji(674389988363993116), 'ur mom', 'Lex')
    await ctx.send(embed=r[0],file=r[1])  

@bot.command(aliases=['max'])
async def _max(ctx):
    if ctx.author not in bot.get_guild(611301150129651763).members: return
    r = fileAbstraction(bot.get_emoji(696789467901591683), 'M A X', 'Max')
    await ctx.send(embed=r[0],file=r[1])

@bot.command(aliases=['davey'])
async def david(ctx):
    if ctx.author not in bot.get_guild(611301150129651763).members: return
    r = fileAbstraction(bot.get_emoji(708847959642603580), 'D A V I D', 'David')
    await ctx.send(embed=r[0],file=r[1])


database.Initialize(secure.token())
bot.run(secure.token()) #Bot token stored in another file, otherwise anyone reading this could start the bot
#database.Initialize(secure.beta())
#bot.run(secure.beta())
