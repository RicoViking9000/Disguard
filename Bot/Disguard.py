'''This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files'''

import discord
from discord.ext import commands, tasks
import dns
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


booted = False
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays']
print("Booting...")
prefixes = {}

""" logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler) """

def prefix(bot, message):
    return '.' if type(message.channel) is not discord.TextChannel else prefixes.get(message.guild.id)

bot = commands.Bot(command_prefix=prefix)
bot.remove_command('help')

indexes = 'Indexes'
urMom = 'G:/My Drive/Other/ur mom'

@tasks.loop(minutes=1)
async def updatePrefixes():
    for server in bot.guilds: prefixes[server.id] = await database.GetPrefix(server)

@tasks.loop(minutes=1)
async def anniversaryDayKickoff():
    if datetime.datetime.now().strftime('%m %d %y %H:%M') == '03 18 20 10:55':
        embed=discord.Embed(title=datetime.datetime.now().strftime('%B %d, %Y %H:%M %p'),description=secure.anniversary(),color=0xffff00, timestamp=datetime.datetime.utcnow())
        embed.set_image(url=secure.embedImage())
        await bot.get_user(596381991151337482).send(content=secure.anniversaryMessage(), embed=embed)
        anniversaryDayKickoff.cancel()

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
        anniversaryDayKickoff.start()
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
    try: 
        async for message in channel.history(limit=None, oldest_first=full):
            if not message.author.bot:
                if '{}_{}.txt'.format(message.id, message.author.id) in os.listdir(path): 
                    if not full: break
                    else: continue #Skip the code below as to not overwrite message edit history, plus to skip saving message indexes we already have (program will keep running, however, this is intentional)
                try: f = open('{}/{}_{}.txt'.format(path, message.id, message.author.id), "w+")
                except FileNotFoundError: pass
                try: f.write('{}\n{}\n{}'.format(message.created_at.strftime('%b %d, %Y - %I:%M %p'), message.author.name, message.content))
                except UnicodeEncodeError: pass
                try: f.close()
                except: pass
                if (datetime.datetime.utcnow() - message.created_at).days < 7 and await database.GetImageLogPerms(server):
                    attach = 'Attachments/{}/{}/{}'.format(message.guild.id, message.channel.id, message.id)
                    try: os.makedirs(attach)
                    except FileExistsError: pass
                    for attachment in message.attachments:
                        if attachment.size / 1000000 < 8:
                            try: await attachment.save('{}/{}'.format(attach, attachment.filename))
                            except discord.HTTPException: pass
    except discord.Forbidden: print('Index error for {}'.format(server.name))
    print('Indexed {}: {} in {} seconds'.format(server.name, channel.name, (datetime.datetime.now() - start).seconds))

@bot.listen()
async def on_reaction_add(r, u):
    if type(r.message.channel) is not discord.DMChannel: return
    if str(r) != '➡' or type(r.emoji) is discord.Emoji and r.emoji.id == 674389988363993116: return
    if u.id not in [247412852925661185, 596381991151337482, 524391119564570664, 282671063530209283]: return
    d = r.message.embeds[0].description
    resultingPic = int(d[d.find('Image') + 6:d.find('of')].strip()) - 1
    if str(r) == '➡': destination = '<#619549837578338306>'
    else: destination = '<@524391119564570664>'
    m2 = await u.send('Type a message to go along with the image, or react with a check to send it to {} without a message'.format(destination))
    await m2.add_reaction('✅')
    def messageCheck(m): return m.author == u and type(m.channel) is discord.DMChannel
    def checkCheck(r, u): return str(r) == '✅' and r.message.id == m2.id
    done, pending = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=checkCheck)], return_when=asyncio.FIRST_COMPLETED)
    stuff = done.pop().result()
    for future in pending: future.cancel()
    if type(stuff) is discord.Message: customMessage = '{}: {}'.format(stuff.author.name, stuff.content)
    else: customMessage = None
    if type(r.emoji) is discord.Emoji: await bot.get_user(524391119564570664).send(content=customMessage, file=discord.File('{}/{}'.format(urMom,os.listdir(urMom)[resultingPic]), os.listdir(urMom)[resultingPic]))
    else: await bot.get_channel(619549837578338306).send(content=customMessage, file=discord.File('{}/{}'.format(urMom,os.listdir(urMom)[resultingPic]), os.listdir(urMom)[resultingPic]))
    await u.send('Successfully sent image to {}'.format(destination))

@bot.command()
async def verify(ctx):
    if ctx.author.id == 247412852925661185:
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
    await ctx.send(embed=discord.Embed(description="[View help here](https://disguard.netlify.com/commands)"))

@bot.command()
async def ping(ctx):
    m = await ctx.send('Pong!')
    await m.edit(content='Pong! {}ms'.format(round((datetime.datetime.utcnow() - ctx.message.created_at).microseconds / 1000)))

@commands.is_owner()
@bot.command(name='eval')
async def evaluate(ctx, *args):
    args = ' '.join(args)
    result = eval(args)
    if inspect.iscoroutine(result): await ctx.send(await eval(args))
    else: await ctx.send(result)

@commands.cooldown(2, 15, commands.BucketType.member)
@bot.command()
async def lexy(ctx):
    if ctx.author.id in [247412852925661185, 596381991151337482, 524391119564570664, 282671063530209283]:
        lex = bot.get_emoji(674389988363993116)
        image = False
        while not image:
            resultingPic = random.randint(0, len(os.listdir(urMom)))
            if not any(n in os.listdir(urMom)[resultingPic] for n in ['.ini', 'VID_20191031_190028_2']): image = True
        e = discord.Embed(title='❤ Lexy ❤',description='**{0:-^83s}\n{2}**\n**{1:-^80s}**\n{3}'.format('OPTIONS', 'INFORMATION', '{}: Send to Lex\n➡: Send to <#619549837578338306>'.format(lex),
            'Image {} of {}'.format(resultingPic + 1, len([f for f in os.listdir(urMom) if '.ini' not in f]))), color=0xffff00, timestamp=datetime.datetime.utcnow())
        f = discord.File('{}/{}'.format(urMom,os.listdir(urMom)[resultingPic]), os.listdir(urMom)[resultingPic])
        if '.mp4' in f.filename: m = await ctx.author.send(embed=e,file=discord.File('{}/{}'.format(urMom,os.listdir(urMom)[resultingPic]), os.listdir(urMom)[resultingPic]))
        else: 
            e.set_image(url=(await bot.get_user(322059776710410241).send(file=f)).attachments[0].url)
            m = await ctx.author.send(embed=e)
        for r in [lex, '➡']: await m.add_reaction(r)


database.Initialize(secure.token())
bot.run(secure.token()) #Bot token stored in another file, otherwise anyone reading this could start the bot
#database.Initialize(secure.beta())
#bot.run(secure.beta())
