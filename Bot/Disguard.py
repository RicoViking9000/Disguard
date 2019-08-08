'''This file contains the main runtime operations of Disguard. Cogs, the main features, are split into a trio of files'''

import discord
from discord.ext import commands
import pymongo
import dns
import secure
import database
import Antispam
import Cyberlog
import os
import datetime

booted = False
cogs = ['Cyberlog', 'Antispam', 'Moderation']
print("Booting...")

def prefix(bot, message):
    return database.GetPrefix(message.guild)

bot = commands.Bot(command_prefix=prefix)
bot.remove_command('help')

@bot.listen()
async def on_ready(): #Method is called whenever bot is ready after connection/reconnection. Mostly deals with database verification and creation
    '''Method called when bot connects and all the internals are ready'''
    global booted
    if not booted:
        await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name="my boss (Verifying database...)", type=discord.ActivityType.listening))
        for cog in cogs:
            try:
                bot.load_extension(cog)
            except:
                pass
        database.Verification(bot)
        Antispam.PrepareFilters(bot)
        Cyberlog.ConfigureSummaries(bot)
        await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name="my boss (Indexing messages...)", type=discord.ActivityType.listening))
        for server in bot.guilds:
            print('Indexing '+server.name)
            for channel in server.text_channels:
                path = "Indexes/{}/{}".format(server.id, channel.id)
                try: os.makedirs(path)
                except FileExistsError: pass
                try: 
                    async for message in channel.history(limit=None):
                        if '{}_{}.txt'.format(message.id, message.author.id) in os.listdir(path): break
                        try: f = open('{}/{}_{}.txt'.format(path, message.id, message.author.id), "w+")
                        except FileNotFoundError: pass
                        try: f.write('{}\n{}\n{}'.format(message.created_at.strftime('%b %d, %Y - %I:%M %p'), message.author.name, message.content))
                        except UnicodeEncodeError: pass
                        try: f.close()
                        except: pass
                        if (datetime.datetime.utcnow() - message.created_at).days < 30 and database.GetImageLogPerms(server):
                            attach = 'Attachments/{}/{}/{}'.format(message.guild.id, message.channel.id, message.id)
                            try: os.makedirs(attach)
                            except FileExistsError: pass
                            for attachment in message.attachments:
                                try: await attachment.save('{}/{}'.format(attach, attachment.filename))
                                except discord.HTTPException: pass
                except discord.Forbidden: pass
            Cyberlog.indexed[server.id] = True
        print("Indexed")
    booted = True
    print("Booted")
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name="your servers", type=discord.ActivityType.watching))

@bot.command()
async def verify(ctx):
    if ctx.author.id == 247412852925661185:
        status = await ctx.send("Verifying...")
        database.Verification(bot)
        await status.delete()

@bot.command()
async def help(ctx):
    await ctx.send(embed=discord.Embed(description="[View help here](https://disguard.netlify.com/commands)"))
    

database.Initialize(secure.token())
bot.run(secure.token()) #Bot token stored in another file, otherwise anyone reading this could start the bot
#database.Initialize(secure.beta())
#bot.run(secure.beta())
