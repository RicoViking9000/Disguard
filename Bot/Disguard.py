'''This file contains the main runtime operations of Disguard. Cogs; the main features, are split into a trio of files'''

import discord
from discord.ext import commands
import pymongo
import dns
import secure
import database

bot = commands.Bot(command_prefix=".")
bot.remove_command('help')

booted = False
cogs = ['Cyberlog', 'Antispam']
print("Booting...")

@bot.listen()
async def on_ready(): #Method is called whenever bot is ready after connection/reconnection. Mostly deals with database verification and creation
    '''Method called when bot connects and all the internals are ready'''
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game("Awaiting orders"))
    global booted
    database.Verification(bot)
    if not booted:
        for cog in cogs:
            bot.load_extension(cog)
    booted = True
    print("Booted")
    await bot.change_presence(status=discord.Status.online, activity=discord.Game("At attention"))

bot.run(secure.token()) #Bot token stored in another file, otherwise anyone reading this could start the bot
