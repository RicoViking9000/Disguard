'''Contains all code relating to the Birthdays feature of Disguard'''
import discord
from discord.ext import commands, tasks
import traceback
import datetime
import database
import Cyberlog
import asyncio
import collections
import copy
import nltk
import os


green = (0x008000, 0x66ff66)
blue = (0x0000FF, 0x6666ff)
red = (0xff0000, 0xff6666)
yellow = (0xffff00, 0xffff66)
loading = None
newline = '\n'
qlfc = ' '

birthdayCancelled = discord.Embed(title='🍰 Birthdays', description='Timed out')

class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loading = bot.get_cog('Cyberlog').emojis['loading']
        self.emojis = self.bot.get_cog('Cyberlog').emojis
        self.whitePlus = bot.get_cog('Cyberlog').emojis['whitePlus']
        self.whiteMinus = bot.get_cog('Cyberlog').emojis['whiteMinus']
        self.whiteCheck = bot.get_cog('Cyberlog').emojis['whiteCheck']
        self.configureDailyBirthdayAnnouncements.start()
        self.configureServerBirthdayAnnouncements.start()
        self.configureDeleteBirthdayMessages.start()
    
    def cog_unload(self):
        self.configureDailyBirthdayAnnouncements.cancel()
        self.configureServerBirthdayAnnouncements.cancel()

    @tasks.loop(hours=24)
    async def dailyBirthdayAnnouncements(self):
        #6/10/21: So this *can* be made much faster by storing a dict with dates as keys and a list of member IDs with that birthday as the value under Disguard's data in the database. But this loop only runs once per day.
        # Update: I have decided to do as much as possible to stop the bot from looping through every single member unless it needs to, since that number can grow expontentially as Disguard grows.
        print('Checking daily birthday announcements')
        birthdayDict = await database.GetBirthdayList()
        if not birthdayDict: birthdayDict = {}
        try:
            for member in self.bot.users:
                try:
                    u = self.bot.lightningUsers[member.id]
                    bday = u['birthday']
                    if bday is not None and self.bot.get_cog('Cyberlog').privacyEnabledChecker(member, 'birthdayModule', 'birthdayDay'):
                        if bday.strftime('%m%d%y') == datetime.datetime.utcnow().strftime('%m%d%y'):
                            try: 
                                if self.bot.get_cog('Cyberlog').privacyEnabledChecker(member, 'birthdayModule', 'age'):
                                    age = self.bot.lightningUsers[member.id]['age']
                                else: age = None
                            except KeyError: age = None
                            if age is not None:
                                age += 1
                                asyncio.create_task(database.SetAge(member, age))
                            new = datetime.datetime(bday.year + 1, bday.month, bday.day)
                            asyncio.create_task(database.SetBirthday(member, new))
                            try: messages = self.bot.lightningUsers[member.id]['birthdayMessages']
                            except KeyError: messages = await database.GetBirthdayMessages(member)
                            embed=discord.Embed(title=f'''🍰 Happy {f"{age}{Cyberlog.suffix(age) if age else ''} "}Birthday, {member.name}! 🍰''', timestamp=datetime.datetime.utcnow(), color=yellow[1])
                            if not self.bot.get_cog('Cyberlog').privacyEnabledChecker(member, 'birthdayModule', 'birthdayMessages'): messages = []
                            if len(messages) > 0: embed.description=f'You have {len(messages)} personal messages that will be sent below this message.'
                            else: embed.description=f'Enjoy this special day just for you, {member.name}! You waited a whole year for it to come, and it\'s finally here! Wishing you a great day filled with food, friends, and family,\n  RicoViking9000, my developer'
                            await member.send(embed=embed)
                            for m in messages: await member.send(embed=discord.Embed(title=f'Personal Birthday Message from {m["authName"]}', description=m['message'], timestamp=m['created'], color=yellow[1]))
                except KeyError: pass
        except: traceback.print_exc()

    @tasks.loop(minutes=5)
    async def serverBirthdayAnnouncements(self):
        started = datetime.datetime.utcnow()
        try:
            for server in self.bot.guilds:
                tz = Cyberlog.timeZone(server)
                initial = started + datetime.timedelta(hours=tz)
                try: channel = self.bot.lightningLogging[server.id]['birthday']
                except KeyError: continue
                if channel > 0:
                    try:
                        if (initial.strftime('%H:%M') == self.bot.lightningLogging[server.id]['birthdate'].strftime('%H:%M')):
                            for member in server.members:
                                try:
                                    bday = self.bot.lightningUsers[member.id]['birthday']
                                    if bday is not None:
                                        if bday.strftime('%m%d') == initial.strftime('%m%d') and self.bot.get_cog('Cyberlog').privacyEnabledChecker(member, 'birthdayModule', 'birthdayDay'):
                                            print(f'Announcing birthday for {member.name}')
                                            try:
                                                messages = [a for a in self.bot.lightningUsers[member.id]['birthdayMessages'] if server.id in a['servers']] if self.bot.get_cog('Cyberlog').privacyEnabledChecker(member, 'birthdayModule', 'birthdayMessages') else []
                                                sentFirstMessage = self.bot.lightningLogging[server.id]['flags']['firstBirthdayAnnouncement']
                                                newline = '\n'
                                                messageVisibility = self.bot.get_cog('Cyberlog').privacyVisibilityChecker(member, 'birthdayModule', 'birthdayMessages')
                                                messageString = f'''\n\nThey also have {len(messages)} birthday messages from server members here:\n\n{newline.join([f"• {server.get_member(m['author']).name if m['author'] in [mb.id for mb in server.members] else m['authName']}: {m['message'] if messageVisibility else '<Content hidden due to privacy settings>'}" for m in messages])}'''
                                                if member.id == 247412852925661185: toSend = f"🍰🎊🍨🎈 Greetings {server.name}! It's my developer {member.mention}'s birthday!! Let's wish him a very special day! 🍰🎊🍨🎈{messageString if len(messages) > 0 else ''}"
                                                else: 
                                                    if self.bot.get_cog('Cyberlog').privacyVisibilityChecker(member, 'birthdayModule', 'birthdayDay'): toSend = f"🍰 Greetings {server.name}, it\'s {member.mention}\'s birthday! Let\'s all wish them a very special day! 🍰{messageString if len(messages) > 0 else ''}"
                                                    else: toSend = f"🍰 Greetings {server.name}! We have one anonymous member with a birthday today! Let\'s all wish them a very special day! 🍰{messageString if len(messages) > 0 else ''}"
                                                if not sentFirstMessage: 
                                                    toSend += f"\n\nMessage from developer: Dear members, due to an unintentional database configuration error, all members' stored birthday information was unintentionally deleted on June 3. While this only applies to the birthday and not the age or wishlist data, it's an unfortunate event, and I am unable to recover the data. If you previously set your birthday before this event, and you would like to set your birthday again, use the `birthday` command or natural lingo by typing `my birthday is <month and day of when your birthday is e.g. july 31st>` to repopulate the Disguard birthdays index."
                                                    await (await database.GetServerCollection()).update_one({'server_id': server.id}, {'$set': {'flags.firstBirthdayAnnouncement': True}})
                                                try: 
                                                    m = await self.bot.get_channel(channel).send(toSend)
                                                    await m.add_reaction('🍰')
                                                except discord.Forbidden as e: print(f'Birthdays error - server: {e}')
                                            except KeyError: pass
                                except KeyError: continue
                    except KeyError: pass
        except: traceback.print_exc()

    @tasks.loop(hours=24)
    async def deleteBirthdayMessages(self):
        try:
            for member in self.bot.users:
                try: bday = self.bot.lightningUsers[member.id]['birthday']
                except KeyError: continue
                if bday is not None:
                    if bday.strftime('%m%d%y') == datetime.datetime.now().strftime('%m%d%y'): await database.ResetBirthdayMessages(member)
        except: traceback.print_exc()

    @tasks.loop(minutes=1)
    async def configureDailyBirthdayAnnouncements(self):
        if datetime.datetime.utcnow().strftime('%H:%M') == '11:45': 
            self.dailyBirthdayAnnouncements.start()
            self.configureDailyBirthdayAnnouncements.cancel()

    @tasks.loop(minutes=1)
    async def configureServerBirthdayAnnouncements(self):
        if int(datetime.datetime.utcnow().strftime('%M')) % 5 == 0 and self.configureServerBirthdayAnnouncements.current_loop > 0:
            self.serverBirthdayAnnouncements.start()
            self.configureServerBirthdayAnnouncements.cancel()

    @tasks.loop(minutes=1)
    async def configureDeleteBirthdayMessages(self):
        if datetime.datetime.now().strftime('%H:%M') == '23:50':
            self.deleteBirthdayMessages.start()
            self.configureDeleteBirthdayMessages.cancel()

    async def updateBirthdays(self):
        print('Updating birthdays')
        updated = []
        for member in self.bot.users:
            try: bday = self.bot.lightningUsers[member.id]['birthday']
            except KeyError: continue
            if bday is not None:
                if bday < datetime.datetime.now():
                    new = datetime.datetime(bday.year + 1, bday.month, bday.day)
                    await database.SetBirthday(member, new)
                    updated.append(member)
        print(f'Updated birthdays for {len(updated)} members')

    @commands.Cog.listener()
    async def on_message(self, message):
        '''Used for parsing and handling of birthday features
        Birthday processing is done in two phases
        1. Find out of a valid date is in the message
        2. Find out of someone is talking about their own birthday based on context and words in the message'''
        if message.author.bot: return
        if type(message.channel) is discord.DMChannel: return
        if any(word in message.content.lower().split(' ') for word in ['isn', 'not', 'you', 'your']): return #Blacklisted words
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            if any([message.content.startswith(w) for w in [ctx.prefix + 'bday', ctx.prefix + 'birthday']]): return #Don't auto detect birthday information if the user is using a command
        try: 
            if self.bot.lightningLogging.get(message.guild.id).get('birthdayMode') in [None, 0]: return #Birthday auto detect is disabled
            if not self.bot.get_cog('Cyberlog').privacyEnabledChecker(message.author, 'birthdayModule', 'birthdayDay'): return #This person disabled the birthday module
        except AttributeError: pass
        self.bot.loop.create_task(self.messagehandler(message))

    async def messagehandler(self, message: discord.Message):
        theme = self.colorTheme(message.guild)
        try: adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(message.guild.id).get('offset'))
        except: adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=await database.GetTimezone(message.guild)) #Use database if local variables aren't available
        birthday = calculateDate(message, adjusted)
        #Now we either have a valid date in the message or we don't. So now we determine the situation and respond accordingly
        #First we check to see if the user is talking about themself
        target = await verifyBirthday(message, adjusted, birthday)
        #Now, we need to make sure that the bot doesn't prompt people who already have a birthday set for the date they specified; and cancel execution of anything else if no new birthdays are detected
        if birthday and target is not None and len(target) > 0:
            if self.bot.lightningLogging.get(message.guild.id).get('birthdayMode') == 1: #Make user add cake reaction
                def cakeAutoVerify(r,u): return u == message.author and str(r) == '🍰' and r.message.id == message.id
                await message.add_reaction('🍰')
                await self.bot.wait_for('reaction_add', check=cakeAutoVerify)
            bdays = {} #Local storage b/c database operations take time and resources
            if birthday < adjusted: birthday = datetime.datetime(birthday.year + 1, birthday.month, birthday.day)
            for member in target:
                bdays[member.id] = self.bot.lightningUsers.get(member.id).get('birthday')
                if bdays.get(member.id) is not None:
                    if bdays.get(member.id).strftime('%B %d') == birthday.strftime('%B %d'): target.remove(member)
            if len(target) > 0:
                draft=discord.Embed(title='🍰 Birthdays / 👮‍ {:.{diff}} / 📆 Configure Birthday / {} Confirmation'.format(target[0].name, self.whiteCheck, diff=63-len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Birthday / ✔ Confirmation')), color=yellow[theme], timestamp=datetime.datetime.utcnow())
                draft.description='{}, would you like to set your birthday as **{}**?'.format(', '.join([a.name for a in target]), birthday.strftime('%A, %B %d, %Y'))
                for member in target:
                    if bdays.get(member.id) is not None: draft.description+='\n\n{}I currently have {} as your birthday; reacting with the check will overwrite this.'.format('{}, '.format(member.name) if len(target) > 1 else '', bdays.get(member.id).strftime('%A, %B %d, %Y'))
                draft.description+=f'\n\n*Note:* Due to a database configuration error, all members\' birthday data was unintentionally deleted on June 3. Unfortunately, there is no way for me to recover the overwritten data. If you previously had a birthday configured, or you would like to set your birthday for the first time, you can use the `birthday` command or natural lingo by typing `my birthday is <month and day of whenever your birthday is, e.g. july 31st>`.'
                mess = await message.channel.send(embed=draft)
                await mess.add_reaction('✅')
                await asyncio.gather(*[birthdayContinuation(self, birthday, target, draft, message, mess, t) for t in target]) #We need to do this to start multiple processes for anyone to react to if necessary
        ages = calculateAge(message)
        ages = [a for a in ages if await verifyAge(message, a)]
        try: currentAge = self.bot.lightningUsers.get(message.author.id).get('age')
        except: currentAge = await database.GetMemberBirthday(message.author) #Use database if local variables aren't available
        try: ages.remove(currentAge) #Remove the user's current age if it's in there
        except ValueError: pass
        if len(ages) > 0:
            if self.bot.lightningLogging.get(message.guild.id).get('birthdayMode') == 1: #Make user add candle reaction
                def candleAutoVerify(r,u): return u == message.author and str(r) == '🕯' and r.message.id == message.id
                await message.add_reaction('🕯')
                await self.bot.wait_for('reaction_add', check=candleAutoVerify)
            if len(ages) == 1:
                if currentAge == ages[0]: return
            age = ages[0]
            letters = [letter for letter in ('🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿')]
            draft=discord.Embed(title='🍰 Birthdays / 👮 {:.{diff}} / 🕯 Configure Age / {} Confirmation'.format(message.author.name, self.whiteCheck, diff=63-len('🍰 Birthdays / 👮‍ / 🕯 Configure Age / ✔ Confirmation')), color=yellow[theme], timestamp=datetime.datetime.utcnow())
            if len(ages) == 1: 
                if age >= 13 and age <= 110: draft.description='{}, would you like to set your age as **{}**?\n\nI currently have {} as your age; reacting with the check will overwrite this.'.format(message.author.name, age, currentAge)
                else: 
                    draft.description = f"{message.author.name}, if you're trying to set your age as {age}, you can no longer set ages outside the range of 13 to 110 years old. Please be realistic if you wish to set your age and try again."
            else: draft.description='{}, if you would like to set your age as one of the listed values, react with the corresponding letter, otherwise you may ignore this message.\n\n{}\n\nI currently have {} as your age; reacting will overwrite this.'.format(message.author.name,
                '\n'.join(['{}: Set your age to **{}**'.format(letters[i], ages[i]) for i in range(len(ages))]), currentAge)
            mess = await message.channel.send(embed=draft)
            if len(ages) > 1:
                for r in letters[:len(ages)]: await mess.add_reaction(r)
                def letterCheck(r, u): return u == message.author and str(r) in letters[:len(ages)] and r.message.id == mess.id
                r = await self.bot.wait_for('reaction_add', check=letterCheck)
                age = ages[letters.index(str(r[0]))]
                draft.description='Great! Please react with ✅ to continue with setting your age as **{}**'.format(age)
                await mess.edit(embed=draft)
            await mess.add_reaction('✅')
            await ageContinuation(self, age, message.author, mess, draft)

    #7/12/21:  Began rewriting birthday command & some extras
    #7/17/21:  Finished rewriting birthday command & some extras
    #@commands.guild_only() #Target for allowability in DMs
    @commands.command(aliases=['bday'])
    async def birthday(self, ctx, *args):
        await ctx.trigger_typing()
        theme = self.colorTheme(ctx.guild) if ctx.guild else 1
        adjusted = datetime.datetime.now()
        if len(args) == 0:
            header = '👮‍♂️ » 🍰 Birthday » 🏠 Overview'
            header = f'👮‍♂️ {ctx.author.name:.{63 - len(header)}} » 🍰 Birthday » 🏠 Overview'
            embed = discord.Embed(title=header, color=yellow[theme])
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url) #V1.5
            #embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url) #V2.0
            if not self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'default', 'birthdayModule'):
                embed.description = 'Birthday module disabled. To edit your privacy settings or enable the birthday module, go [here](http://disguard.herokuapp.com/manage/profile).'
                return await ctx.send(embed=embed)
            user = self.bot.lightningUsers[ctx.author.id]
            bday, age, wishlist = user.get('birthday'), user.get('age'), user.get('wishlist', [])
            embed.add_field(name='Your Birthday',value='Not configured' if not bday else 'Hidden' if ctx.guild and not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'birthdayDay') else f'{bday:%a %b %d}\n(<t:{round(bday.timestamp())}:R>)')
            embed.add_field(name='Your Age', value='Not configured' if not age else 'Hidden' if ctx.guild and not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'age') else age)
            if len(wishlist) > 0: embed.add_field(name='Your Wishlist', value='Hidden' if ctx.guild and not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'wishlist') else f'{len(wishlist)} items')
            embed.description = f'{self.loading} Processing global birthday information'
            message = await ctx.send(embed=embed)
            #SUGGESTION » 7/13/21: Basic Disguard Wiki (after website improvements of course), maintaining an information database on various disguard features
            #Sort members into three categories: Members in the current server, Disguard suggestions (mutual servers based), and members that have their birthday in a week
            currentServer = []
            disguardSuggest = []
            weekBirthday = []
            memberIDs = set([m.id for m in ctx.guild.members]) if ctx.guild else () #June 2021 (v0.2.27): Changed from list to set to improve performance // Holds list of member IDs for the current server
            for u in self.bot.users:
                try:
                    #Skip members whose privacy settings show they don't want to partake in public features of the birthday module
                    if not (self.bot.get_cog('Cyberlog').privacyEnabledChecker(u, 'default', 'birthdayModule') and self.bot.get_cog('Cyberlog').privacyVisibilityChecker(u, 'default', 'birthdayModule') and self.bot.get_cog('Cyberlog').privacyEnabledChecker(u, 'birthdayModule', 'birthdayDay') and self.bot.get_cog('Cyberlog').privacyVisibilityChecker(u, 'birthdayModule', 'birthdayDay')): continue
                    userBirthday = self.bot.lightningUsers[u.id].get('birthday')
                    if not userBirthday: continue
                    if u.id in memberIDs: currentServer.append({'data': u, 'bday': userBirthday})
                    elif mutualServerMemberToMember(self, ctx.author, u):
                        if (userBirthday - adjusted).days < 8: weekBirthday.append({'data': u, 'bday': userBirthday})
                        else: disguardSuggest.append({'data': u, 'bday': userBirthday})
                except (AttributeError, TypeError, KeyError): pass
            currentServer.sort(key = lambda m: m.get('bday'))
            weekBirthday.sort(key = lambda m: m.get('bday'))
            disguardSuggest.sort(key = lambda m: mutualServersMemberToMember(self, ctx.author, m['data']), reverse=True) #Servers the author and target share
            firstNine = [m['data'].name for m in currentServer[:3] + disguardSuggest[:3] + weekBirthday[:3]]
            def fillBirthdayList(list, maxEntries):
                return [f"{qlfc}\\▪️ **{m['data'].name if firstNine.count(m['data'].name) == 1 else m['data']}** • {m['bday']:%a %b %d} • <t:{round(m['bday'].timestamp())}:R>" for m in list[:maxEntries]]
            embed.description = f'''**{"AVAILABLE OPTIONS":–^70}**\n🍰: Browse birthday profiles\n📪: View more upcoming birthdays\n📆: Update your birthday\n🕯: Update your age\n📝: {"Manage" if len(wishlist) > 0 else "Create"} your wish list\n**{"UPCOMING BIRTHDAYS":–^70}\n**{"__THIS SERVER__" if len(currentServer) > 0 else ""}\n'''
            embed.description+= f'''{newline.join(fillBirthdayList(currentServer, 3))}{(newline + newline) if len(currentServer) > 0 else ""}{"__DISGUARD SUGGESTIONS__" if len(disguardSuggest) > 0 else ""}{newline.join(fillBirthdayList(disguardSuggest, 3))}{(newline + newline) if len(disguardSuggest) > 0 else ""}{"__WITHIN A WEEK__" if len(weekBirthday) > 0 else ""}'''
            embed.description+= f'''{newline.join(fillBirthdayList(weekBirthday, 3))}{newline if len(weekBirthday) > 0 else ""}\n*Note*: Unfortunately, on June 3, all the dates of members' birthdays were accidentally purged. If you're interested in the features offered by the birthday module, you can help rebuild the birthday indexes by configuring your birthday.'''
            await message.edit(embed=embed)
            reactions = ['🍰', '📪',  '📆', '🕯', '📝', '👮‍♂️']
            for r in reactions: await message.add_reaction(r)
            def reactionCheck(r, u): return str(r) in reactions and r.message.id == message.id and u == ctx.author
            try: result = await self.bot.wait_for('reaction_add', check=reactionCheck)
            except asyncio.TimeoutError: return await message.edit(embed=birthdayCancelled)
            if str(result[0]) == '🍰': await messageManagement(self, ctx, message, result[1], [currentServer[:5], disguardSuggest[:5], weekBirthday[:5]])
            elif str(result[0]) == '📪': await upcomingBirthdaysViewer(self, ctx, message, currentServer, disguardSuggest, weekBirthday)
            elif str(result[0]) == '📆' and self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'birthdayDay'): await firstBirthdayContinuation(self, ctx, ctx.author, message)
            elif str(result[0]) == '🕯' and self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'age'): await firstAgeContinuation(self, ctx, ctx.author, message)
            elif str(result[0]) == '📝' and self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'wishlist'): await firstWishlistContinuation(self, ctx, message)
        else:
            embed=discord.Embed(title=f'{self.emojis["search"]} Birthdays', description=f'{self.loading} Searching', color=yellow[theme])
            message = await ctx.send(embed=embed)
            arg = ' '.join(args)
            actionList = []
            age = calculateAge(ctx.message)
            currentAge = self.bot.lightningUsers[ctx.author.id].get('age')
            try: age.remove(currentAge)
            except ValueError: pass
            for a in age: #Remove out of bounds of [0, 105]
                if a < 0 or a > 105: age.remove(a)
            actionList += age
            memberList = await self.bot.get_cog('Cyberlog').FindMoreMembers(self.bot.users, arg)
            memberList.sort(key = lambda x: x.get('check')[1], reverse=True)
            memberList = [m.get('member') for m in memberList] #Only take member results with at least 33% relevance to avoid ID searches when people only want to get their age
            memberList = [m for m in memberList if mutualServerMemberToMember(self, ctx.author, m)]
            actionList += memberList
            def actionCheck(r, u): return str(r) == str(self.emojis['settings']) and u == ctx.author and r.message.id == message.id
            date = calculateDate(ctx.message, datetime.datetime.utcnow() + datetime.timedelta(days=self.bot.lightningLogging.get(ctx.guild.id).get('offset')))
            if date: return await birthdayContinuation(self, date, [ctx.author], embed, message, message, ctx.author, partial=True)
            async def makeChoice(result, message):
                if type(result) in (discord.User, discord.ClientUser):
                    await message.edit(embed=await guestBirthdayViewer(self, ctx, actionList[0]))
                    if actionList[0] == ctx.author: await message.add_reaction(self.emojis['settings'])
                    await message.add_reaction('🍰')
                    #while True:
                    d, p = await asyncio.gather(*[self.bot.wait_for('reaction_add', check=actionCheck), writePersonalMessage(self, self.bot.lightningUsers.get(actionList[0].id).get('birthday'), [actionList[0]], message)])
                    try: r = d.pop().result()
                    except: r = None
                    for f in p: f.cancel()
                    if type(r) is tuple:
                        if r[0].emoji == self.emojis['settings']:
                            try: await message.delete()
                            except discord.Forbidden: pass
                            return await self.birthday(ctx)
                elif type(result) is int: return await ageContinuation(self, actionList[index], ctx.author, message, embed, partial=True)
                else: return await birthdayContinuation(self, date, [ctx.author], embed, message, message, ctx.author, partial=True)
            if len(actionList) == 1 and type(actionList[0]) in (discord.User, discord.ClientUser): await makeChoice(actionList[0], message)
            elif len(actionList) == 0:
                embed.description = f'No actions found for **{arg}**'
                return await message.edit(embed=embed)
            parsed = []
            for entry in actionList:
                if type(entry) in [discord.User, discord.ClientUser]: parsed.append(f'View {entry.name}\'s birthday profile')
                elif type(entry) is int: parsed.append(f'Set your age as **{entry}**')
                else: parsed.append(f'Set your birthday as **{entry:%A, %b %d, %Y}**')
            final = parsed[:20] #We only are dealing with the top 20 results
            letters = [letter for letter in ('🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿')]
            alphabet = 'abcdefghijklmnopqrstuvwxyz'
            embed.description=f'**{"AVAILABLE ACTIONS":–^70}**\nType the letter of or react with your choice\n\n{newline.join([f"{letters[i]}: {f}" for i, f in enumerate(final)])}'
            await message.edit(embed=embed)
            for l in letters[:len(final)]: await message.add_reaction(l)
            def messageCheck(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in alphabet
            def reacCheck(r, u): return str(r) in letters[:len(final)] and u == ctx.author and r.message.id == message.id
            d, p = await asyncio.wait([self.bot.wait_for('message', check=messageCheck), self.bot.wait_for('reaction_add', check=reacCheck)], return_when=asyncio.FIRST_COMPLETED)
            try: r = d.pop().result()
            except: return
            for f in p: f.cancel()
            if type(r) is discord.Message: 
                index = alphabet.index(r.content)
                try:
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(r)
                    await r.delete()
                except: pass
            else: index = letters.index(str(r[0]))
            try: await message.clear_reactions()
            except: pass
            await makeChoice(actionList[index], message)
    
    def colorTheme(self, s: discord.Guild):
        return self.bot.lightningLogging[s.id]['colorTheme']
                        

async def messageManagement(self, ctx, message, user, groups):
    '''Handles personal message sending
        ctx: context
        message: the message the bot sent in response to the command
        user: person who reacted
        groups: [currentServer, disguardSuggest, weekBirthday]
    '''
    target = ctx.author
    if ctx.author == user: #The person who reacted with the cake (desiring to send a message) is the one who initiated the command, so we want quick actions/suggestions
        oldEmbed = copy.deepcopy(message.embeds[0])
        message.embeds[0].clear_fields() #Clear all fields
        d = oldEmbed.description
        bulletCount = d.count('▪️') #Count bullets (corresponding to number of birthday suggestion entries) from embed description
        message.embeds[0].description = '{} Please wait...'.format(self.loading)
        await message.edit(embed=message.embeds[0])
        letters = [letter for letter in ('🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿')]
        d = d[d.find('view') + 4:] #Take only the birthday management part of the current embed
        d = d.replace('To send a message to someone, use reactions or type `{}birthday <recipient>`'.format(ctx.prefix), '')
        temp = d[d.find('view')+4:d.find('__THIS SERVER__')].strip()
        d = '\n**{}\nYou will be taken to DMs to write your message\n\n{}'.format(temp, d[d.find('__THIS SERVER__'):])
        try: indexes = [d.index('▪️'), d.index('▪️', d.index('▪️') + 1)] #Set of indexes for searching for bullet points
        except: indexes = [0, 0]
        newDesc = d[:indexes[0]]
        for bullet in range(bulletCount):
            newDesc += letters[bullet] + d[indexes[bullet] + 1:d.find('▪', indexes[-1])] #Basically, replace the bullet point with a letter by combining all before the bullet, the letter and all after the bullet
            indexes.append(d.find('▪️', indexes[-1] + 1)) #Step this up so that the algorithm finds the **next** bullet point
        allGroups = groups[0] + groups[1] + groups[2]
        for m in allGroups: newDesc = newDesc.replace(str(m.get('data')), m.get('data').mention)
        d = '**{0:–^70}**\n⬅: Back to Birthdays Home\n🇦 - {1}: Send a message to a person listed here\n🔎: Search to send a message to anybody you share a server with'.format('OPTIONS',
            letters[bulletCount - 1]) + newDesc + '_' #Append head (instructions)
        message.embeds[0].description = d
        message.embeds[0].title = '🍰 Birthdays / 👮‍♂️ {:.{diff}} / 📜 Messages / 🏠 Home'.format(ctx.author.name, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 📜 Messages / 🏠 Home'))
        await message.edit(embed=message.embeds[0])
        await message.clear_reactions()
        for r in (['⬅'] + letters[:bulletCount] + ['🔎']): await message.add_reaction(r)
        def sendCheck(r, u): return u == ctx.author and r.message.id == message.id and str(r) in ['⬅️'] + letters[:bulletCount] + ['🔎']
        try: stuff = await self.bot.wait_for('reaction_add', check=sendCheck, timeout=180)
        except asyncio.TimeoutError: return await messageManagementTimeout(message, oldEmbed)
        await message.remove_reaction(stuff[0], stuff[1])
        if str(stuff[0]) != '🔎': 
            if str(stuff[0]) == '⬅': return await messageManagementTimeout(message, oldEmbed)
            target = allGroups[letters.index(str(stuff[0]))].get('data')
        else: #Let user search for who they want their message to go to
            message.embeds[0].title = '🍰 Birthdays / 📜 Messages / 🔎 Search'
            message.embeds[0].description = 'Type a search term for your desired member. The search will match members\'s uernames, nicknames, IDs, discriminators, and many more criteria'
            await message.clear_reactions()
            await message.edit(embed=message.embeds[0])
            await message.add_reaction('⬅')
            def queryCheck(m): return m.author == ctx.author and m.channel.id == ctx.channel.id
            def paginationCheck(r, u): return str(r) in letters + ['◀', '▶', '⬅'] and u == ctx.author and r.message.id == message.id
            while True:
                d, p = await asyncio.wait([self.bot.wait_for('message', check=queryCheck, timeout=180), self.bot.wait_for('reaction_add', check=paginationCheck, timeout=180)], return_when=asyncio.FIRST_COMPLETED)
                try: result = d.pop().result()
                except asyncio.TimeoutError: return await messageManagementTimeout(message, oldEmbed)
                for f in p: f.cancel()
                if type(result) is discord.Message: 
                    message.embeds[0].description='{} Searching...'.format(self.loading)
                    self.bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                    await result.delete()
                    await message.edit(embed=message.embeds[0])
                    results = await self.bot.get_cog('Cyberlog').FindMoreMembers(self.bot.users, result.content)
                    results.sort(key = lambda x: x.get('check')[1], reverse=True) #Sort results be relevance (returned from the FindMoreMembers function)
                    results = [r.get('member') for r in results] #Only take the member objects; we've already sorted and can trash everything else we don't need
                    results = [m for m in results if len([s for s in self.bot.guilds if m in s.members and ctx.author in s.members])] #Filter by only reactor and target sharing a server with each other
                    def paginate():
                        for i in range(0, len(results), 18): yield results[i:i+18] #18 results per page since 20 max reactions (leeway of 2 for navigation buttons)
                    pages = list(paginate())
                    pageData = [0, 17, 0] #Start index of results, end index of results, current page index 
                    parsedResults = '\n'.join([' • {}: {}'.format(letters[a], results[a]) for a in range(len(pages[0]))])
                    if len(pages) > 1:
                        for r in ['◀', '▶']: await message.add_reaction(r)
                    else: 
                        for r in ['◀', '▶']: await message.remove_reaction(r, self.bot.user)
                else:
                    if str(result[0]) == '⬅': return await messageManagementTimeout(message, oldEmbed)
                    reactions = len((await ctx.channel.fetch_message(message.id)).reactions)
                    if len(pages) > 1 and str(result[0]) in ['◀', '▶']:
                        if str(result[0]) == '◀' and pageData[2] > 0:
                            pageData[2] -= 1
                            pageData[0] -= 17
                            pageData[1] -= 17
                            if pageData[0] < 0:
                                pageData[0] = 0
                                pageData[1] = 17
                        elif str(result[0]) == '▶' and pageData[2] < len(pages) - 1:
                            pageData[2] += 1
                            pageData[0] += 17
                            pageData[1] += 17
                            if pageData[1] > len(results) - 1:
                                pageData[1] = len(results) - 1
                                pageData[0] = 17 * pageData[2] #Start at the multiple of 18 corresponding to the current page
                    if str(result[0]) in letters: 
                        await message.remove_reaction(str(result[0]), self.bot.user)
                        target = pages[pageData[2]][letters.index(str(result[0]))]
                        #Check to make sure this member has 'receive birthday messages' enabled in their privacy settings
                        if not (self.bot.get_cog('Cyberlog').privacyEnabledChecker(target, 'default', 'birthdayModule') and self.bot.get_cog('Cyberlog').privacyEnabledChecker(target, 'birthdayModule', 'birthdayMessages')):
                            await message.edit(content = f'{target.name} has disabled receiving birthday messages, so you will be unable to write a message to them.')
                        break
                if type(result) is discord.Message or str(result[0]) in ['◀', '▶']:
                    flavorText = '{}{} - {}: Select this member (I will DM you)'.format('◀: Previous page\n▶: Next page\n' if len(pages) > 1 else '', letters[0], letters[len(pages[pageData[2]]) - 1])
                    resultText = 'Page {} of {}\nViewing {} - {} of {} results'.format(pageData[2] + 1, len(pages), pageData[0] + 1, pageData[1] + 1, len(results)) if len(pages) > 1 else '{} results'.format(len(results))
                    parsedResults = '\n'.join([' • {}: {}'.format(letters[a], pages[pageData[2]][a]) for a in range(len(pages[pageData[2]]))])
                    message.embeds[0].description='**{0:–^70}**\n{1}\n**{2:–^70}**\n{3}'.format('NAVIGATION', flavorText, 'RESULTS', '{}\n{}'.format(resultText, parsedResults))
                    await message.edit(embed=message.embeds[0])
                    if type(result) is tuple: #The purpose of putting this down here is so that reactions are added/removed **after** the message is edited
                        if str(result[0]) == '◀':
                            if len(pages[pageData[2]]) > reactions:
                                for l in letters[:len(pages[pageData[2]])]: await message.add_reaction(l)
                        else:
                            if reactions - 2 > len(pages[pageData[2]]):
                                for l in reversed(letters): 
                                    if l not in reversed(letters[:pageData[1] - pageData[0]]): await message.remove_reaction(l, self.bot.user)
                    for r in letters[:len(pages[pageData[2]])]: await message.add_reaction(r)
        auto=True          
    else: auto=False
    m = await user.send(embed=await guestBirthdayViewer(self, ctx, target, cake=auto))
    if not auto: await m.add_reaction('🍰')
    bday = await database.GetMemberBirthday(target)
    await writePersonalMessage(self, bday, [target], m, autoTrigger=auto, u=user)
    await message.delete()
    await self.birthday(ctx)
        
async def guestBirthdayViewer(self, ctx, target, cake=False):
    '''Displays information about somebody else's birthday profile'''
    #adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(ctx.guild.id).get('offset'))
    user = self.bot.lightningUsers[target.id]
    bday = user.get('birthday')
    age = user.get('age')
    wishlist = user.get('wishList')
    header = '👮‍♂️ » 🍰 Birthday'
    header = f'👮‍♂️ {ctx.author.name:.{63 - len(header)}} » 🍰 Birthday'
    embed = discord.Embed(title=header, color=yellow[self.colorTheme(ctx.guild)], description=f'**{"WISH LIST":–^70}**\n{newline.join([f"• {wish}" for wish in wishlist])}')
    embed.description += f'''\n**{"AVAILABLE OPTIONS":–^70}**\n{f"{self.emojis['settings']}: Enter Action Overview" if target == ctx.author else ''}{f"{newline}🍰 (Only anyone other than {target.name}): Write a personal birthday message to {target.name}" if not cake else ''}'''
    embed.description += f"\n\n*Note*: Unfortunately, on June 3, all the dates of members' birthdays were accidentally purged. If you're interested in the features offered by the birthday module, you can help rebuild the birthday indexes by configuring your birthday. To do that, use the `birthday` command or type `my birthday is july 31st` (replace july 31 with whenever your birthday is)\n\n"
    embed.set_author(name=target.name, icon_url=target.avatar_url) #V1.5
    #embed.set_author(name=target.name, icon_url=target.avatar.url) #V2.0
    embed.add_field(name='Birthday', value='Not configured' if bday is None else 'Hidden' if not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(target, 'birthdayModule', 'birthdayDay') else f'{bday:%a %b %d}\n(<t:{round(bday.timestamp())}:R>)')
    embed.add_field(name='Age', value='Not configured' if age is None else 'Hidden' if not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(target, 'birthdayModule', 'birthdayDay') else age)
    return embed

async def firstWishlistContinuation(self, ctx, m, cont=False, new=None):
    wishlist = await database.GetWishlist(ctx.author) if self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'wishlist') else ['You have disabled birthday wishlist functionality'] if self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'wishlist') else ['You have set your wishlist to private. Work to allow the birthday module to be used in DMs is underway.']
    embed=discord.Embed(title='🍰 Birthdays / 👮‍♂️ {:.{diff}} / 📝 Wish List / 🏠 Home'.format(ctx.author.name, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 📝 Wish List / 🏠 Home')), 
        description='**{0:–^70}**\n{2}\n**{1:–^70}**\n{3}'.format('YOUR WISH LIST', 'OPTIONS', 'Very spacious in here! Your wishlist is currently recruiting fabulous new wishes, and you seem to know just where to find them :)' if wishlist is None or len(wishlist) < 1 else '\n'.join(['• {}'.format(w) for w in wishlist]),
        '❌: Close this embed\n{}: Add entries to your wish list\n{}: Remove entries from your wish list'.format(self.whitePlus, self.whiteMinus)),color=yellow[self.colorTheme(ctx.guild)], timestamp=datetime.datetime.utcnow())
    if not cont: new = await ctx.send(embed=embed)
    else: await new.edit(embed=embed)
    await new.add_reaction('❌')
    if self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'wishlist') and self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'wishlist'):
        for r in ['➕', '➖']: await new.add_reaction(r)
    def navigChecks(r, u): return str(r) in ['❌', '➕', '➖'] and r.message.id == new.id and u == ctx.author
    while True:
        try: result = await self.bot.wait_for('reaction_add', check=navigChecks)
        except asyncio.TimeoutError: return await new.delete()
        if str(result[0]) == '❌': 
            await m.remove_reaction('📝', ctx.author)
            return await new.delete()
        elif str(result[0]) == '➕': await modifyWishlistItems(self, ctx, m, new, wishlist)
        else: await modifyWishlistItems(self, ctx, m, new, wishlist, False)

async def modifyWishlistItems(self, ctx, m, new, wishlist, add=True): #If add is false, remove mode is on
    if add: 
        verb='add'
        preposition='to'
    else: 
        verb='remove'
        preposition='from'
    new.embeds[0].title = '🍰 Birthdays / 👮‍♂️ {:.{diff}} / 📝 Wish List / {} {}'.format(ctx.author.name, self.whitePlus, verb[0].upper() + verb[1:], diff=63 - len('🍰 Birthdays / 👮‍♂️ / 📝 Wish List / 🏠 {}'.format(verb)))
    d = '**{0:–^70}**\n{1}\n\nType{4} to {2} entries {3} your wish list. To {2} multiple entries in one message, separate entries with a space and a comma.{5} When you\'re done, react with ✅ to save, or react with ❌ to cancel without saving'
    if add: new.embeds[0].description=d.format('YOUR WISH LIST', '(Empty)' if len(wishlist) == 0 else '\n'.join(['• {}'.format(w) for w in wishlist]), verb, preposition, 'the number or contents of an entry' if not add else '', 'Type `clear` to empty your wish list.' if not add else '')
    else: new.embeds[0].description=d.format('YOUR WISH LIST', '(Empty)' if len(wishlist) == 0 else '\n'.join(['{}. {}'.format(w+1, wishlist[w]) for w in range(len(wishlist))]), verb, preposition, ' the number or text of an entry' if not add else '', ' Type `clear` to empty your wish list.' if not add else '')
    await new.edit(embed=new.embeds[0])
    await new.clear_reactions()
    for r in ['❌', '✅']: await new.add_reaction(r)
    toModify = []
    def checkCheck(r, u): return u == ctx.author and r.message.id == new.id and str(r) == '✅'
    def cancelCheck(r, u): return u == ctx.author and r.message.id == new.id and str(r) == '❌'
    def addCheck(m): return m.author == ctx.author and m.channel == ctx.channel
    while True:
        done, p = await asyncio.wait([self.bot.wait_for('reaction_add', check=checkCheck, timeout=300), self.bot.wait_for('reaction_add', check=cancelCheck, timeout=300), self.bot.wait_for('message', check=addCheck, timeout=300)], return_when=asyncio.FIRST_COMPLETED)
        try: stuff = done.pop().result()
        except asyncio.TimeoutError: await new.delete()
        for future in p: future.cancel()
        if type(stuff) is discord.Message:
            if len(stuff.attachments) == 1:
                if stuff.attachments[0].height: #We have an image or a video, so we will create a permanent URL via the private image hosting channel
                    await stuff.add_reaction(self.loading)
                    imageLogChannel = self.bot.get_channel(534439214289256478)
                    tempDir = 'Attachments/Temp'
                    savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), stuff.attachments[0].filename[stuff.attachments[0].filename.rfind('.')+1:]))
                    await stuff.attachments[0].save(savePath)
                    f = discord.File(savePath)
                    hostMessage = await imageLogChannel.send(file=f)
                    toModify.append(hostMessage.attachments[0].url)
                    if os.path.exists(savePath): os.remove(savePath)
            elif stuff.content is not None and len(stuff.content) > 0: toModify += stuff.content.split(', ')
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(stuff)
                await stuff.delete()
            except discord.Forbidden: pass
            if add: new.embeds[0].description=d.format('YOUR WISH LIST', '\n'.join(['• {}'.format(w) for w in wishlist] + ['• **{}**'.format(w) for w in toModify]), verb, preposition, ' the number or text of an entry' if not add else '', ' Type `clear` to empty your wish list.' if not add else '')
            else: 
                if stuff.content.lower() == 'clear': toModify = copy.copy(wishlist)
                for w in wishlist:
                    for wo in range(len(toModify)):
                        try: toModify[wo] = wishlist[int(toModify[wo]) - 1]
                        except: pass
                new.embeds[0].description=d.format('YOUR WISH LIST', '\n'.join(['{}. {}'.format(w+1,'~~{}~~'.format(wishlist[w]) if wishlist[w] in toModify else wishlist[w]) for w in range(len(wishlist))]), verb, preposition, ' the number or text of an entry' if not add else '', ' Type `clear` to empty your wish list.' if not add else '')
            await new.edit(embed=new.embeds[0])
        else:
            if str(stuff[0]) == '✅':
                new.embeds[0].description = '{} Saving...'.format(self.loading)
                await new.edit(embed=new.embeds[0])
                if add:
                    for e in toModify: await database.AppendWishlistEntry(ctx.author, e)
                else:
                    for w in toModify: wishlist.remove(w)
                    await database.SetWishlist(ctx.author, wishlist)
            await new.clear_reactions()
            await m.remove_reaction('📝', ctx.author)
            return await firstWishlistContinuation(self, ctx, m, True, new)

async def firstAgeContinuation(self, ctx, author, message):
    revert = copy.deepcopy(message.embeds[0])
    embed=discord.Embed(title='🍰 Birthdays / 👮‍♂️ {:.{diff}} / 🕯 Configure Age / ❔ Query'.format(author.name, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Age / ❔ Query')), description='''What is your age?\n\n(Your age is currently **{}**)'''.format('not set' if await database.GetAge(author) is None else await database.GetAge(author)), color=yellow[self.colorTheme(ctx.guild)], timestamp=datetime.datetime.utcnow())
    embed.set_author(name=author.name, icon_url=author.avatar_url)
    new = await ctx.send(embed=embed)
    message.embeds[0].set_author(icon_url='https://cdn.discordapp.com/emojis/605060517861785610.gif', name='Waiting for callback...')
    await message.edit(embed=message.embeds[0])
    currentAge = await database.GetAge(author)
    def messageCheck(m): return m.author == author and m.channel == ctx.channel
    def checkCheck(r, u): return u == author and r.message.id == new.id and str(r) == '✅'
    satisfied = False
    while not satisfied:
        done, pending = await asyncio.wait([self.bot.wait_for('reaction_add', check=checkCheck, timeout=180), self.bot.wait_for('message', check=messageCheck, timeout=180)], return_when=asyncio.FIRST_COMPLETED)
        try: stuff = done.pop().result()
        except asyncio.TimeoutError: return await birthdayCancellation(message, birthdayCancelled, revert, new, author)
        for future in pending: future.cancel()
        if type(stuff) is discord.Message: #User typed an age, so we must parse it
            result = calculateAge(stuff)[0]
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(stuff)
                await stuff.delete()
            except: pass
            if result:
                embed.title = '🍰 Birthdays / 👮‍♂️ {:.{diff}} / 🕯 Configure Age / {} Confirmation'.format(author.name, self.whiteCheck, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Age / ✔ Confirmation'))
                if result != currentAge:
                    embed.description='**{}**\n\nIs this correct?{}eady to save it? React with ✅, otherwise type another age or wait 3 minutes for timeout'.format(result,
                        'Looks a bit funky... but anyway, r' if result < 0 or result > 100 else ' R')
                    await new.add_reaction('✅')
                else:
                    embed.description='Wow, you\'re right on top of things here; your age is already set to **{}**! 👍\n\nIf you would like to change your age, react with 🕯 again on the embed above ☝'.format(currentAge)
                    await new.edit(embed=embed, delete_after=20)
                    revert.set_author(name=author.name, icon_url=author.avatar_url)
                    return await message.edit(embed=revert)
            else: embed.description='{} isn\'t an age, please try again or wait 3 minutes for this to time out'.format(stuff.content)
            await new.edit(embed=embed)
        else: #user reacted with a checkmark; they are satisfied with the age they have typed
            satisfied = True
            embed.description='{} Please wait...'.format(self.loading)
            await stuff[0].message.edit(embed=embed)
            def editCheck(b, a): return a.embeds[0].footer.text is not discord.Embed.Empty and str(new.id) in a.embeds[0].footer.text
            new = await new.channel.fetch_message(new.id)
            done2, pending2 = await asyncio.wait([self.bot.wait_for('message_edit', check=editCheck, timeout=300), ageContinuation(self, result, author, new, embed, new.id)], return_when=asyncio.FIRST_COMPLETED)
            try: done2.pop().result()
            except asyncio.TimeoutError: return await birthdayCancellation(message, birthdayCancelled, revert, new, author)
            for future in pending2: future.cancel
            message.embeds[0].set_field_at(1, name='Your Age',value='**Age Successfully Updated**\n{}'.format(result))
            message.embeds[0].set_author(name=author.name, icon_url=author.avatar_url)
            await message.edit(embed=message.embeds[0])
            await new.delete()
            return await message.remove_reaction('🕯', stuff[1])

async def ageContinuation(self, age, author, mess, draft, callback=None, partial=False):
    '''If partial, all we're doing is confirming an age and we start here'''    
    def ageCheck(r, u): return u == author and str(r) == '✅' and r.message.id == mess.id
    if partial: 
        draft.title='🍰 Birthdays / 👮‍♂️ {:.{diff}} / 🕯 Configure Age / {} Confirmation'.format(author.name, self.whiteCheck, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Age / ✔ Confirmation'))
        draft.description='Would you like to set your age as **{}**?'.format(age)
        await mess.edit(embed=draft)
        await mess.add_reaction('✅')
    if callback is None: u = await self.bot.wait_for('reaction_add', check=ageCheck)
    else: u = [None, author]
    draft.description = '{} Saving'.format(self.loading)
    await mess.edit(embed=draft)
    try: await mess.clear_reactions()
    except: pass
    if age >= 13 and age <= 110:
        await database.SetAge(u[1], age)
        embed=discord.Embed(title='🍰 Birthdays / 👮‍♂️ {:.{diff}} / 🕯 Configure Age / ✅ Success'.format(author.name, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Age / ✔ Success')),color=yellow[self.colorTheme(mess.guild)], timestamp=datetime.datetime.utcnow())
        embed.set_author(name=author.name, icon_url=author.avatar_url)
        embed.description = 'Your age has successfully been saved, and will be used for your next birthday announcement in your DMs.'
        try: 
            if not self.lightningUsers[author.id]['birthday']: embed.description = f'Your age ({age}) has successfully been saved.\n\nYou do not have a birthday configured yet - set your birthday by typing `my birthday is [date]` or using the birthday command (no args) & subsequently reacting with 🍰'
        except: pass
    else:
        embed=discord.Embed(title='🍰 Birthdays / 👮‍♂️ {:.{diff}} / 🕯 Configure Age / ❌ Failure'.format(author.name, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Age / ❌ Failure')),color=yellow[self.colorTheme(mess.guild)], timestamp=datetime.datetime.utcnow())
        embed.set_author(name=author.name, icon_url=author.avatar_url)
        embed.description = f'As of April 12, 2021, only ages between 13 and 110 will be accepted. Please try again using the casual format (`I am <age>`) or the birthday command `{self.bot.lightningLogging.get(author.guild.id).get("prefix")}birthday <age>`, without the angle brackets.'
    if callback is not None: embed.set_footer(text='Callback: {}'.format(callback))
    await mess.edit(embed=embed)

async def firstBirthdayContinuation(self, ctx, author, message):
    revert = copy.deepcopy(message.embeds[0])
    bday = await database.GetMemberBirthday(author)
    embed=discord.Embed(title='🍰 Birthdays / 👮‍♂️ {:.{diff}} / 📆 Configure Birthday / ❔ Query'.format(author.name, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Birthday / ✔ Query')), description='''When is your birthday?\n\n(Your birthday is currently **{}**)'''.format('not set' if bday is None else bday.strftime('%b %d')), color=yellow[self.colorTheme(ctx.guild)], timestamp=datetime.datetime.utcnow())
    embed.set_author(name=author.name, icon_url=author.avatar_url)
    new = await ctx.send(embed=embed)
    message.embeds[0].set_author(icon_url='https://cdn.discordapp.com/emojis/605060517861785610.gif', name='Waiting for callback...')
    await message.edit(embed=message.embeds[0])
    adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=await database.GetTimezone(ctx.guild))
    def messageCheck(m): return m.author == author and m.channel == ctx.channel
    def checkCheck(r, u): return u == author and r.message.id == new.id and str(r) == '✅'
    satisfied = False
    while not satisfied:
        done, pending = await asyncio.wait([self.bot.wait_for('reaction_add', check=checkCheck, timeout=180), self.bot.wait_for('message', check=messageCheck, timeout=180)], return_when=asyncio.FIRST_COMPLETED)
        try: stuff = done.pop().result()
        except asyncio.TimeoutError: return await birthdayCancellation(message, birthdayCancelled, revert, new, author)
        for future in pending: future.cancel()
        if type(stuff) is discord.Message: #If the user typed a date
            result = calculateDate(stuff, adjusted)
            try:
                self.bot.get_cog('Cyberlog').AvoidDeletionLogging(stuff)
                await stuff.delete()
            except: pass
            if result:
                now = datetime.datetime.now()
                if result < now: result = datetime.datetime(now.year + 1, result.month, result.day)
                embed.title = '🍰 Birthdays / 👮‍♂️ {:.{diff}} / 📆 Configure Birthday / {} Confirmation'.format(author.name, self.whiteCheck, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Birthday / ✔ Confirmation'))
                if bday is None or result.day != bday.day:
                    embed.description='**{}**\n\nIs this correct? Ready to save it? React with ✅, otherwise type another date or wait 3 minutes for timeout'.format(result.strftime('%A, %b %d, %Y'))
                    await new.add_reaction('✅')
                else:
                    embed.description='Wow, you\'re right on top of things here; your birthday is already set to **{}**! 👍\n\nIf you would like to change your birthday, react with 📆 again on the embed above ☝'.format(result.strftime('%a %b %d'))
                    await new.edit(embed=embed, delete_after=20)
                    return await message.edit(embed=revert)
            else: embed.description='{} does not seem to be a date, please try again or wait 3 minutes for timeout'.format(stuff.content)
            await new.edit(embed=embed)
        else: #If the user reacted with a check mark
            satisfied = True
            embed.description='{} Please wait...'.format(self.loading)
            await stuff[0].message.edit(embed=embed)
            def editCheck(b, a): return a.embeds[0].footer.text is not discord.Embed.Empty and str(new.id) in a.embeds[0].footer.text
            new = await new.channel.fetch_message(new.id)
            done2, pending2 = await asyncio.wait([self.bot.wait_for('message_edit', check=editCheck, timeout=300), birthdayContinuation(self, result, [author], new.embeds[0], message, new, author, new.id)], return_when=asyncio.FIRST_COMPLETED)
            try: done2.pop().result()
            except asyncio.TimeoutError: return await birthdayCancellation(message, birthdayCancelled, revert, new, author)
            for future in pending2: future.cancel
            message.embeds[0].set_field_at(0, name='Your Birthday',value='**Birthday Successfully Updated**\n{}'.format(result.strftime('%a %b %d\n(In {} days)').format((result - adjusted).days)))
            message.embeds[0].set_author(name=author.name, icon_url=author.avatar_url)
            await message.edit(embed=message.embeds[0])
            await new.delete()
            return await message.remove_reaction('📆', stuff[1])
        
async def birthdayContinuation(self, birthday, target, draft, message, mess, user, callback=None, partial=False):
    def check(r, u):
        return u == user and str(r) == '✅' and r.message.id == mess.id
    if partial: 
        draft.title='🍰 Birthdays / 👮‍♂️ {:.{diff}} / 📆 Configure Birthday / {} Confirmation'.format(target[0].name, self.whiteCheck, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Birthday / ✔ Confirmation'))
        draft.description='Would you like to set your birthday as **{}**?'.format(birthday.strftime('%A, %b %d, %Y'))
        await mess.edit(embed=draft)
        await mess.add_reaction('✅')
    if callback is None: u = await self.bot.wait_for('reaction_add', check=check)
    else:  u = [None, user]
    draft.description = '{} Saving'.format(self.loading)
    adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=await database.GetTimezone(user.guild))
    if len(target) == 1 or all([await database.GetMemberBirthday(m) == birthday for m in target if m != u[1]]): #Clear confirmation embed if only one person or if everybody already set their birthday
        await mess.edit(embed=draft)
        try: await mess.clear_reactions()
        except: pass
        await database.SetBirthday(u[1], birthday)
    else:
        draft.description = '{} Saving {}\'s birthday'.format(self.loading, u[1].name)
        mess = await message.channel.send(embed=draft)
        await database.SetBirthday(u[1], birthday)
    embed=discord.Embed(title='🍰 Birthdays / 👮‍♂️ {:.{diff}} / 📆 Configure Birthday / ✅ Success'.format(target[0].name, diff=63 - len('🍰 Birthdays / 👮‍♂️ / 🕯 Configure Birthday / ✔ Success')),color=yellow[self.colorTheme(message.guild)], timestamp=datetime.datetime.utcnow())
    embed.description='''{}, your birthday has been successfully recorded: **{}** (which is {} days from now on a {} {} year).\nIf you would like, you can include your age in your birthday profile by typing 'I am <age>' or 'I'm <age>'\n
        {}\n\nEveryone else, you may use the `birthday` command or react to this message with the 🍰 emoji to add a personal message that will be displayed on {}'s birthday.'''.format(u[1].name,
        birthday.strftime('%B %d'), (await database.GetMemberBirthday(u[1]) - adjusted).days, birthday.strftime('%A'), 'this' if birthday.year == adjusted.year else 'next',
        'Your birthday will be announced at {} {} to the channel {}'.format((await database.GetBirthdate(message.guild)).strftime('%I:%M %p'), await database.GetNamezone(message.guild), 
        self.bot.get_channel(await database.GetBirthday(message.guild)).mention) if (await database.GetBirthday(message.guild)) > 0 else '''Moderators, please visit [my web dashboard](http://disguard.herokuapp.com/manage/{}/server) to configure
        a channel and time for birthday announcements to be sent. If you are not currently signed in to my web dashboard, then connect your Discord account, click on this server icon [{}] on the homepage, then 'General Server Settings',
        then you may adjust your settings.'''.format(message.guild.id, message.guild.name), u[1].name)
    embed.set_author(icon_url=user.avatar_url, name=user.name)
    if callback is not None: 
        embed.set_footer(text='Callback: {} '.format(callback))
        return await mess.edit(embed=embed)
    await mess.edit(embed=embed)
    await mess.add_reaction('🍰')
    await writePersonalMessage(self, birthday, target, mess)

async def writePersonalMessage(self, birthday, target, mess, autoTrigger=False, u=None):
    '''Handles writing of a personal birthday message
    birthday: The datetime of the target's birthday
    target: The person who will receive the message
    mess: the message the person reacted to (used to remove reaction because my view is people shouldn't know when others are writing a message to them; it's a birthday gift)
    autoTrigger: go straight to query rather than waiting for cake reaction
    u: User who is sending a message, used when this differs from person reacting with cake (such as when autoTrigger is True)'''
    def cakeReac(r, u): return str(r) == '🍰' and not u.bot and r.message.id == mess.id
    theme = self.colorTheme(mess.guild)
    while True:
        try: 
            if not autoTrigger:
                haveAppropriateUser = False
                while not haveAppropriateUser:
                    r, u = await self.bot.wait_for('reaction_add', check=cakeReac)
                    if u in target: #User attempts to send a message to themself
                        await mess.channel.send(embed=discord.Embed(description=f'Sorry {u.name}, you can\'t write a personal birthday message to yourself!', color=yellow[theme]), delete_after=15)
                    else:
                        try: await mess.remove_reaction(r, u)
                        except discord.Forbidden: pass
                        haveAppropriateUser = True
            if len(target) > 1: 
                while True:
                    await u.send('Who would you like to write a personal message to? Type the number corresponding of the person\n\n{}'.format('\n'.join(['{}: {}'.format(a, target[a].name) for a in range(len(target))])))
                    def chooseUser(m):
                        return m.channel.guild is None and m.author == u
                    m = await self.bot.wait_for('message', check=chooseUser, timeout=180)
                    try: 
                        recipient = target[int(m) - 1]
                        break
                    except: pass
            else: recipient = target[0]
            if birthday is None: return await mess.channel.send(embed=discord.Embed(description=f'{recipient.name} must set a birthday before you can write personal messages to them.', color=yellow[theme]))
            verifying = await u.send('{} Verifying...'.format(self.loading))
            recipientMessages = await database.GetBirthdayMessages(recipient)
            alreadySent = [m for m in recipientMessages if u.id == m.get('author')]
            if len(alreadySent) > 0:
                await verifying.edit(content='You already have {} message(s) to {} [{}], react with ✅ to send another message'.format(len(alreadySent), recipient.name, ' • '.join([m.get('message')[:1800 // len(alreadySent)] for m in alreadySent]))[:2000])
                def verifyCheck(r, user): return user == u and str(r) == '✅' and r.message.id == verifying.id
                await verifying.add_reaction('✅')
                await self.bot.wait_for('reaction_add', check=verifyCheck, timeout=300)
            else: await verifying.delete()
            passInspection=False
            while not passInspection:
                await u.send('What would you like your personal message to **{0}** say? (Note that you *will* be able to choose whether this message is displayed publicly in servers or just to {0}\'s DMs.)'.format(recipient.name))
                def awaitMessage(m):
                    return type(m.channel) is discord.DMChannel and m.author == u
                script = await self.bot.wait_for('message', check=awaitMessage, timeout=300)
                if not any(w in script.content for w in ['discord.gg/', 'http://', 'https://']): passInspection = True
                else: await u.send('Your message contains either a server invite or a web URL hyperlink, please try again')
            await u.send('Where would you like your message to be displayed? Type the corresponding number\n1: Only to {0} (their DMs on their birthday)\n2: To {0} and at least one mutual server\'s birthday announcement channel (you will select which server(s))'.format(recipient.name))
            def messageLocation(m):
                return type(m.channel) is discord.DMChannel and m.author == u
            m = await self.bot.wait_for('message', check=messageLocation, timeout=180)
            if '2' in m.content or 'w' in m.content:
                mutual = [s for s in self.bot.guilds if all(m in s.members for m in [u, recipient])]
                letters = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯']
                m = await u.send('{} Retrieving server birthday information from database, please wait...'.format(self.loading))
                await m.edit(content='Select which servers you would like your personal message to be sent to by reacting with the corresponding letters, then react ➡️ when you\'re done. \n🍰 = server with birthday announcements channel configured (in other words, selecting servers without this icon means that your birthday message will only be delivered there if that server configures its birthday accouncements channel in the meantime)\n\n{}'.format('\n'.join(['{}: {}{}'.format(letters[a], mutual[a].name, ' 🍰' if await database.GetBirthday(mutual[a]) > 0 else '' ) for a in range(len(mutual))])))
                for a in range(len(mutual)):
                    await m.add_reaction(letters[a])
                await m.add_reaction('➡️')
                def moveOn(r, user):
                    return user == u and str(r) == '➡️' and r.message.id == m.id
                await self.bot.wait_for('reaction_add', check=moveOn, timeout=300)
                selected = [recipient]
                m = (await u.history(limit=1).flatten())[0] #refresh message
                for r in m.reactions: 
                    if str(r) != '➡️' and r.count > 1: selected.append(mutual[letters.index(str(r))])
            else: selected = [recipient]
            m = await u.send('Your personal birthday message says `{}`. \n\nIt will be delivered to {} on {}\'s birthday ({}). If you are satisfied with this, react ✅, otherwise react 🔁 to restart or ❌ to cancel without saving.'.format(script.clean_content,
                ' • '.join(a.name for a in selected), recipient.name, birthday.strftime('%B %d')))
            for r in ['✅', '🔁', '❌']: await m.add_reaction(r)
            def finalConfirm(r, user):
                return u == user and str(r) in ['✅', '🔁', '❌'] and r.message.id == m.id
            r = await self.bot.wait_for('reaction_add', check=finalConfirm, timeout=180)
            if str(r[0]) == '✅':
                await database.SetBirthdayMessage(recipient, script, u, [a for a in selected if type(a) is discord.Guild])
                await u.send(f'Your personal message for {recipient} has been successfully set. To write personal messages, set your birthday, age, wishlist, or view your Birthday Profile, you may use the `birthday` command.')
            elif str(r[0]) == '🔁': await writePersonalMessage(self, birthday, target, mess, True, u)
            else: return await u.send('Cancelled birthday message configuration')
        except asyncio.TimeoutError:
            await u.send('Birthday management timed out')
            break
        if autoTrigger: break

async def upcomingBirthdaysViewer(self, ctx, message, currentServer, disguardSuggest, weekBirthday):
    namesOnly = [m['data'].name for m in currentServer + disguardSuggest + weekBirthday]
    def fillBirthdayList(list, maxEntries):
        return [f"{qlfc}\\▪️ **{m['data'].name if namesOnly.count(m['data'].name) == 1 else m['data']}** • {m['bday']:%a %b %d} • <t:{round(m['bday'].timestamp())}:R>" for m in list[:maxEntries]]
    embed = message.embeds[0]
    embed.clear_fields()
    embed.description = f'''The ability to expand specific sections will arrive when Discord Buttons arrive**\n{"UPCOMING BIRTHDAYS":-^70}**\n__THIS SERVER__\n{newline.join(fillBirthdayList(currentServer, 10))}\n\n__DISGUARD SUGGESTIONS__\n{newline.join(fillBirthdayList(disguardSuggest, 10))}\n\n__WITHIN A WEEK__\n{newline.join(fillBirthdayList(weekBirthday, 10))}'''
    await message.edit(embed=embed)
    try: await message.clear_reactions()
    except: pass
    await message.add_reaction('⬅')
    def reactionCheck(r, u): return str(r) == '⬅' and r.message.id == message.id and u == ctx.author
    await self.bot.wait_for('reaction_add', check=reactionCheck)
    await message.delete() #Rework the system so we don't have to delete the message to go back
    await self.birthday(ctx)

def calculateDate(message, adjusted):
    '''Returns a datetime.datetime parsed from a message
    adjusted: Current time; with applicable timezone taken into consideration'''
    now = datetime.datetime.now()
    shortDays = collections.deque(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])
    longDays = collections.deque(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])
    shortMonths = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    longMonths = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
    def isLeapYear(): 
        y = datetime.datetime.today().year
        if y % 4 != 0: return False
        else:
            if y % 100 == 0:
                if y % 400 != 0:
                    return False
                else:
                    return True
            else:
                return True
        return False
    ref = collections.deque([(a, b) for a, b in {1:31, 2:29 if isLeapYear() else 28, 3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31}.items()]) #Number of days in each month. As with days, this dict may need to move around
    ref.rotate(-1 * (adjusted.month - 1)) #Current month moves to the front
    #Determine if user specified long or short day/month in response
    if any(c in message.content.lower().split(' ') for c in longMonths): months = longMonths
    else: months = shortMonths
    if any(c in message.content.lower().split(' ') for c in longDays): days = longDays
    else: days = shortDays
    #Check if name of month is in message. Before days because some ppl may specify a day and month
    birthday = None
    if any(c in message.content.lower().split(' ') for c in months) or 'the' in message.content.lower().split(' '):
        #Check if month short or long (depending on context) name or the word "the" are in the list of words in the input string (message)
        words = message.content.split(' ')
        for word in words:
            before = word
            word = word.replace(',', '')
            #truncate the suffix if the user provided one
            if any(str(letter) in word for letter in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]):
                word = word.replace('st', '')
                word = word.replace('nd', '')
                word = word.replace('rd', '')
                word = word.replace('th', '')
            if any(c in message.content.lower().split(' ') for c in months):
                try: 
                    birthday = datetime.datetime(now.year, months.index([d for d in months if d in message.content.lower().split(' ')][0]) + 1, int(word))
                    break
                except: pass
            else:
                if before != word:
                    try: birthday = datetime.datetime(now.year, now.month, int(word))
                    except: pass
    #Check if day of the week is in message
    elif any(c in message.content.lower().split(' ') for c in days):
        parserString = '%a' if days == shortDays else '%A' #We have to go with what's in the message
        currentDay = days.index(adjusted.strftime(parserString).lower())
        targetDay = days.index([d for d in days if d in message.content.lower()][0])
        days.rotate(-1 * currentDay) #Current day is now at the start for proper calculations
        #Target is days until the day the user typed in chat. targetDay - currentDay is still the same as before the rotation
        birthday = adjusted + datetime.timedelta(days=targetDay-currentDay)
        if birthday < adjusted and 'was' not in message.content.lower().split(' '): birthday += datetime.timedelta(days=7) #If target is a weekday already past, jump it to next week; since that's what they mean, if they didn't say 'was' in their sentence 
    elif any(c in message.content.lower().split(' ') for c in ['today', 'yesterday', 'ago', 'tomorrow']):
        if any(word in message.content.lower() for word in ['my birthday', 'my bday' 'mine is']) and 'today' in message.content.lower().split(' '): birthday = adjusted
        elif any(word in message.content.lower() for word in ['my birthday', 'my bday' 'mine was']) and 'yesterday' in message.content.lower().split(' '): birthday = adjusted - datetime.timedelta(days=1)
        elif 'tomorrow' in message.content.lower().split(' '): birthday = adjusted + datetime.timedelta(days=1)
        else:
            for word in message.content.split(' '):
                try: num = int(word)
                except: num = None
                if num: 
                    if any(w in message.content.lower().split(' ') for w in ['day', 'days']): birthday = adjusted - datetime.timedelta(days=num)
                    if any(w in message.content.lower().split(' ') for w in ['week', 'weeks']): birthday = adjusted - datetime.timedelta(days=num*7)
                    if any(w in message.content.lower().split(' ') for w in ['month', 'months']): birthday = adjusted - datetime.timedelta(days= sum(a[1] for a in list(ref)[-1 * num:])) #Jump back [num] months; starting from end of list because ago = back in time; need to get correct days
    else: #The user inputted either something vague or a format with slashes, etc. NEED TO TRIM WORDS TO CHECK ALL COMBINATIONS. Also check for word THE before number, above.
        '''NEXT UP: MENTIONS HANDLING: if you check for is, also check my/mine to make sure the user isnt saying 'mine is xxxx' Also ask the user if they want to set their birthday'''
        for word in message.content.split(' '):
            try: birthday = datetime.datetime.strptime(word, "%m/%d/%y")
            except:
                try: birthday = datetime.datetime.strptime(word, "%m-%d-%y")
                except:
                    try: birthday = datetime.datetime.strptime(word, "%m %d %y")
                    except: birthday = None
    if 'half' in message.content.lower().split(' ') and birthday: 
        ref.rotate(6)
        birthday = birthday + datetime.timedelta(days= sum(a[1] for a in list(ref)[:6])) #Deal with half birthdays; jump 6 months ahead
    return birthday

async def verifyBirthday(message, adjusted, birthday=None):
    '''Return a list of relevant members if the program determines that the member is talking about their own birthday or someone else's birthday given a message, None otherwise'''
    if birthday is None: birthday = calculateDate(message, adjusted)
    #Now we either have a valid date in the message or we don't. So now we determine the situation and respond accordingly
    #User most likely talking about their own birthday
    if any(word in message.content.lower() for word in ['my birthday', 'my bday', 'mine is', 'my half birthday', 'my half bday']): return [message.author]
    #User most likely talking about someone else's birthday
    elif any(word in message.content.lower().split(' ') for word in ['is', 'are']) and not any(word in message.content.lower().split(' ') for word in ['my', 'mine']) and len(message.mentions) > 0 and any(word in message.content.lower() for word in ['birthday', 'bday']): return message.mentions
    #User most likely answered a question asked by a user
    else:
        async for m in message.channel.history(limit=10): #How many messages to check back for question words
            if any(word in m.content.lower() for word in ['when', 'what']) and any(word in m.content.lower() for word in ['your birthday', 'your bday', 'yours']): return [message.author]

def calculateAge(m):
    '''Returns a list of numbers found in a message'''
    ages = []
    for w in m.content.lower().split(' '):
        try: ages.append(int(w))
        except: pass
    return ages

async def verifyAge(message, age):
    '''Verifies that a person was talking about their age. This is far more prone to false positives than birthday verification, and the catch all is return True, so I have to make sure I return False when necessary'''
    s = message.content.lower().split(' ')
    s = [w.replace('\'', '') for w in s] #replace any apostrophes with nothing (i'm --> im) for parsing convenience
    t = nltk.pos_tag(nltk.word_tokenize(message.content.lower()))
    if any(word in s for word in ['im', 'i\'m']) or 'i am' in message.content.lower(): #Deal with age
        if 'i am' in message.content.lower(): finder = 'am'
        else: finder = 'im'
        try: number = int(s[1 + s.index(finder)])
        except: return False
        if abs(s.index(str(number)) - s.index(finder)) > 1: return False #I'm or I am is too far from the actual number so it's irrelevant
        if number:
            try: tail = s[s.index(str(number)):] #If there is content after the number, try to deal with it
            except: 
                if int(s[1 + s.index(finder)]) not in calculateAge(message): return False #If the relevant age is not the same one found in the message, return
                return False
            if len(tail) > 1:
                if 'year' not in tail[1]:
                    #Parts of speech analysis
                    if t[1 + s.index(str(number))][1] not in ['IN', 'CC']: return False #Part of speech after age number makes this not relevant
                else:
                    if len(tail) > 2:
                        if 'old' not in tail[2]: return False
    elif 'age is' in message.content.lower():
        if 'my' not in s: return False
        try: int(s[s.index('age') + 2])
        except: return False
    else: return False
    return True

async def birthdayCancellation(message, embed, revert, new, author):
    await new.edit(embed=embed, delete_after=20)
    revert.set_author(name=author.name, icon_url=author.avatar_url)
    await message.edit(embed=revert)
    for r in ['🍰', '📆', '🕯', '📝']: await message.remove_reaction(r, author)

async def messageManagementTimeout(message, oldEmbed):
    await message.edit(embed=oldEmbed)
    await message.clear_reactions()
    for r in ['🍰', '📆', '🕯', '📝']: await message.add_reaction(r)

async def mutualServerMemberToMember(self, memberA, memberB):
    '''Returns True if these two members share at least one mutual server'''
    for g in self.bot.guilds:
        foundA = False
        foundB = False
        for m in g.members:
            if m.id == memberA.id: foundA = True
            elif m.id == memberB.id: foundB = True
            if foundA and foundB: return True
    return False

async def mutualServersMemberToMember(self, memberA, memberB):
    '''Returns the number of servers shared by the two given members'''
    counter = 0
    for g in self.bot.guilds:
        foundA = False
        foundB = False
        for m in g.members:
            if m.id == memberA.id: foundA = True
            elif m.id == memberB.id: foundB = True
            if foundA and foundB: counter += 1
    return counter


def setup(bot):
    bot.add_cog(Birthdays(bot))

