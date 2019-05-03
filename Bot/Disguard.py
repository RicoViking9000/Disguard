'''This file contains the main runtime operations of Disguard. Cogs; the main features, are split into a trio of files'''

import discord
from discord.ext import commands
import pymongo
import dns
import secure
import database
import Antispam

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
        await bot.change_presence(status=discord.Status.idle, activity=discord.Game("Awaiting orders"))
        for cog in cogs:
            bot.load_extension(cog)
        database.Verification(bot)
        Antispam.PrepareFilters(bot)
    booted = True
    print("Booted")
    await bot.change_presence(status=discord.Status.online, activity=discord.Game("At attention"))

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
