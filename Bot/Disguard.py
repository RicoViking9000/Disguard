'''This file contains the main runtime operations of Disguard. Cogs; the main features, are split into a trio of files'''

import discord
from discord.ext import commands
import pymongo
import dns
import secure
import database
import Antispam
import os

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
            bot.load_extension(cog)
        database.Verification(bot)
        Antispam.PrepareFilters(bot)
        await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name="my boss (Indexing messages...)", type=discord.ActivityType.listening))
        print("Indexing...")
        for server in bot.guilds:
            for channel in server.text_channels:
                path = "Indexes/{}/{}".format(server.id, channel.id)
                try: os.makedirs(path)
                except FileExistsError: pass
                try:
                    async for message in channel.history(limit=10000000):
                        if str(message.id)+".txt" in os.listdir(path): break
                        try: f = open(path+"/"+str(message.id)+".txt", "w+")
                        except FileNotFoundError: pass
                        try: f.write(message.author.name+"\n"+str(message.author.id)+"\n"+message.content)
                        except UnicodeEncodeError: pass
                        try: f.close()
                        except: pass
                except discord.Forbidden:
                    pass
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
