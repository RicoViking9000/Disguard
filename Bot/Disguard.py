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


booted = False
cogs = ['Cyberlog', 'Antispam', 'Moderation', 'Birthdays']
print("Booting...")
prefixes = {}

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
    if datetime.datetime.now().strftime('%m %d %y %H:%M') == '02 18 20 09:35':
        embed=discord.Embed(title=datetime.datetime.now().strftime('%B %d, %Y %H:%M %p'),description=secure.anniversary(),color=0xffff00, timestamp=datetime.datetime.utcnow())
        embed.set_image(url='https://cdn.discordapp.com/attachments/567741860559454210/679183155500154885/JPEG_20200124_114705.jpg')
        await bot.get_user(596381991151337482).send(embed=embed)
        anniversaryDayKickoff.cancel()

@bot.listen()
async def on_ready(): #Method is called whenever bot is ready after connection/reconnection. Mostly deals with database verification and creation
    '''Method called when bot connects and all the internals are ready'''
    global booted
    global loading
    if not booted:
        booted=True
        loading = bot.get_emoji(573298271775227914)
        await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name="my boss (Verifying database...)", type=discord.ActivityType.listening))
        for cog in cogs:
            try:
                bot.load_extension(cog)
            except:
                pass
        await database.Verification(bot)
        await Antispam.PrepareFilters(bot)
        updatePrefixes.start()
        anniversaryDayKickoff.start()
        Cyberlog.ConfigureSummaries(bot)
        await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name="my boss (Indexing messages...)", type=discord.ActivityType.listening))
        for server in bot.guilds:
            print('Indexing '+server.name)
            for channel in server.text_channels:
                path = "{}/{}/{}".format(indexes,server.id, channel.id)
                try: os.makedirs(path)
                except FileExistsError: pass
                try: 
                    async for message in channel.history(limit=None, after=datetime.datetime.now() - datetime.timedelta(days=30)):
                        if not message.author.bot:
                            if '{}_{}.txt'.format(message.id, message.author.id) in os.listdir(path): break
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
                except discord.Forbidden: pass
            Cyberlog.indexed[server.id] = True
        print("Indexed")
    print("Booted")
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name="your servers", type=discord.ActivityType.watching))

@bot.listen()
async def on_reaction_add(r, u):
    if not type(r.message.channel) is discord.DMChannel: return
    if not str(r) in ['❌', '➡'] or type(r.emoji) is discord.Emoji and r.emoji.id == 674389988363993116: return
    if not u.id == 596381991151337482: return
    k = bot.get_user(596381991151337482)
    if str(r) == '❌':
        await k.send('Cancelled picture sending. `.lexy` to restart.')
        valentinesDaySend.cancel()
    if str(r) == '➡' or type(r.emoji) is discord.Emoji and r.emoji.id == 674389988363993116:
        d = r.message.embeds[0].description
        resultingPic = int(d[d.find('Image') + 6:d.find('of')].strip()) - 1
        if str(r) == '➡': destination = '<#619549837578338306>'
        else: destination = '<@524391119564570664>'
        m2 = await k.send('Type a message to go along with the image, or react with a check to send it to {} without a message'.format(destination))
        await m2.add_reaction('✅')
        def messageCheck(m): return m.author.id == 596381991151337482 and type(m.channel) is discord.DMChannel
        def checkCheck(r, u): return str(r) == '✅' and u.id == 596381991151337482 and type(r.message.channel) is discord.DMChannel
        done, pending = await asyncio.wait([bot.wait_for('message', check=messageCheck), bot.wait_for('reaction_add', check=checkCheck)], return_when=asyncio.FIRST_COMPLETED)
        stuff = done.pop().result()
        for future in pending: future.cancel()
        if type(stuff) is discord.Message: customMessage = '{}: {}'.format(stuff.author.name, stuff.content)
        else: customMessage = None
        if type(r.emoji) is discord.Emoji: await bot.get_user(524391119564570664).send(content=customMessage, file=discord.File('{}/{}'.format(path,os.listdir(path)[resultingPic]), os.listdir(path)[resultingPic]))
        else: await bot.get_channel(619549837578338306).send(content=customMessage, file=discord.File('{}/{}'.format(path,os.listdir(path)[resultingPic]), os.listdir(path)[resultingPic]))
        await k.send('Successfully sent image to {}'.format(destination))

@bot.command()
async def verify(ctx):
    if ctx.author.id == 247412852925661185:
        status = await ctx.send("Verifying...")
        await database.Verification(bot)
        await status.delete()

@bot.command()
async def help(ctx):
    await ctx.send(embed=discord.Embed(description="[View help here](https://disguard.netlify.com/commands)"))

@bot.command()
async def ping(ctx):
    m = await ctx.send('Pong!')
    await m.edit(content='Pong! {}ms'.format(round((datetime.datetime.utcnow() - ctx.message.created_at).microseconds / 1000)))


database.Initialize(secure.token())
bot.run(secure.token()) #Bot token stored in another file, otherwise anyone reading this could start the bot
#database.Initialize(secure.beta())
#bot.run(secure.beta())
@commands.cooldown(2, 15, commands.BucketType.member)
@bot.command()
async def lexy(ctx):
    if ctx.author.id in [247412852925661185, 596381991151337482, 524391119564570664]:
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


