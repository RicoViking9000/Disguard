'''Contains all code relating to Disguard's Birthdays module'''
import discord
from discord.ext import commands, tasks
import traceback
import datetime
import database
import Cyberlog
import utility
import asyncio
import collections
import copy
import nltk
import os
import typing
import re


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
        self.bot: commands.Bot = bot
        self.loading: discord.Emoji = bot.get_cog('Cyberlog').emojis['loading']
        self.emojis: typing.Dict[str, discord.Emoji] = self.bot.get_cog('Cyberlog').emojis
        # self.whitePlus = self.emojis['whitePlus']
        # self.whiteMinus = self.emojis['whiteMinus']
        # self.whiteCheck = self.emojis['whiteCheck']
        # self.configureDailyBirthdayAnnouncements.start()
        # self.configureServerBirthdayAnnouncements.start()
        # self.configureDeleteBirthdayMessages.start()
    
    def cog_unload(self):
        pass
        # self.configureDailyBirthdayAnnouncements.cancel()
        # self.configureServerBirthdayAnnouncements.cancel()
        # self.configureDeleteBirthdayMessages.cancel()

    @tasks.loop(hours=24)
    async def dailyBirthdayAnnouncements(self):
        # print('Checking daily birthday announcements')
        # Retrieves the global birthday dictionary to only iterate through users whose birthday is today
        birthdayDict: typing.Dict[str, typing.List[int]] = await database.GetBirthdayList()
        # if not birthdayDict: birthdayDict = {}
        # try:
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        for userID in birthdayDict[datetime.date.today().strftime('%m%d')]:
            user = self.bot.get_user(userID)
            try: bday: datetime.datetime = self.bot.lightningUsers[userID].get('birthday')
            except KeyError: continue #User not in cache
            # If there's no birthday set for this user or they've disabled the birthday module, return
            if not bday or not cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayDay'): continue
            # If this user has an age set on their profile, increment it
            if cyber.privacyEnabledChecker(user, 'birthdayModule', 'age'):
                age = self.bot.lightningUsers[userID].get('age', 0) + 1
                if age > 1: asyncio.create_task(database.SetAge(user, age))
            # Construct their next birthday to set in the database
            #TODO: potentially eliminate years for all this
            newBday = datetime.date(bday.year + 1, bday.month, bday.day)
            messages = self.bot.lightningUsers[userID].get('birthdayMessages', []) if cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayMessages') else []
            filteredMessages = messages #TODO: extract the messages that will be delivered to the DM channel
            # Construct the happy birthday embed
            embed = discord.Embed(title=f'🍰 Happy {f"{age - 1}{utility.suffix(age - 1)}" if age > 1 else ""}Birthday, {user.name}! 🍰', color=yellow[1])
            embed.description = f'Enjoy this special day just for you, {user.name}! In addition to the people you know who will hopefully send birthday wishes your way, my developer also wants to wish you only the best on your birthday. Take it easy today, and try to treat yourself in some fashion.\n\n~~RicoViking9000, developer of Disguard'
            if filteredMessages: embed.description += f'\n\n🍰 | Friends in your servers have also composed {len(filteredMessages)} messages for your birthday! They will be displayed below this message.'
            messageEmbeds = [embed] + [discord.Embed(title=f'✉ Birthday Message from {m["authName"]}', description=m['message'], color=yellow[1]) for m in filteredMessages]
            # Split the embeds to send into groups of 10, since messages can hold a maximum of 10 embeds
            embedsToSend = utility.paginate(messageEmbeds, 10)
            try:
                for page in embedsToSend: await user.send(embeds=page)
            except (discord.HTTPException, discord.Forbidden): pass #Can't DM this user
            asyncio.create_task(database.SetBirthday(user, newBday))

    @tasks.loop(minutes=5)
    async def serverBirthdayAnnouncements(self):
        birthdayDict: typing.Dict[str, typing.List[int]] = await database.GetBirthdayList()
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        for userID in birthdayDict[datetime.date.today().strftime('%m%d')]:
            user = self.bot.get_user(userID)
            if not cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayDay'): continue
            try: bday: datetime.datetime = self.bot.lightningUsers[userID].get('birthday')
            except KeyError: continue #User not in cache
            # If there's no birthday set for this user or they've disabled the birthday module, return
            if not bday or not cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayDay'): continue
            # TODO: Make mutual servers member to member generator to improve speed
            # TODO: if a server set their birthday channel in the meantime and somebody queued a message, account for that. check for server ID in the message channel ID
            servers = mutualServersMemberToMember(self, user, self.bot.user)
            for server in servers:
                timezone = cyber.timeZone(server)
                started = datetime.datetime.utcnow() + datetime.timedelta(hours=timezone)
                channel = self.bot.get_channel(self.bot.lightningLogging[server.id].get('birthday')) #Doing this instead of try/except since birthday channels usually default to 0 if not set
                if started.strftime('%H:%M') == self.bot.lightningLogging[server.id].get('birthdate', datetime.datetime.min).strftime('%H:%M') or not channel: continue
                # print(f'Announcing birthday for {member.name} to {server.name}')
                messages = [a for a in self.bot.lightningUsers[user.id].get('birthdayMessages', []) if server.id in a['servers']] if cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayMessages') else []
                messageVisibility = cyber.privacyVisibilityChecker(user, 'birthdayModule', 'birthdayMessages')
                messageString = '' #Figure out how to format this

                if userID == 247412852925661185:
                    toSend = f'🍰🎊🍨🎈 Greetings {server.name}! It\'s my developer {user.mention}\'s birthday!! Let\'s wish him a very special day! 🍰🎊🍨🎈{messageString if len(messages) > 0 else ""}'
                else: 
                    if cyber.privacyVisibilityChecker(member, 'birthdayModule', 'birthdayDay'): toSend = f"🍰 Greetings {server.name}, it\'s {user.mention}\'s birthday! Let\'s all wish them a very special day! 🍰{messageString if len(messages) > 0 else ''}"
                    else: toSend = f"🍰 Greetings {server.name}! We have an anonymous member with a birthday today! Let\'s all wish them a very special day! 🍰{messageString if len(messages) > 0 else ''}"
                # try: 
                m = await self.bot.get_channel(channel).send(toSend)
                await m.add_reaction('🍰') #Consider the birthday wishes feature
                # except discord.Forbidden as e: print(f'Birthdays error - server: {e}')


        started = datetime.datetime.utcnow()
        try:
            for server in self.bot.guilds:
                tz = self.bot.get_cog('Cyberlog').timeZone(server)
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
                                                newline = '\n'
                                                messageVisibility = self.bot.get_cog('Cyberlog').privacyVisibilityChecker(member, 'birthdayModule', 'birthdayMessages')
                                                messageString = f'''\n\nThey also have {len(messages)} birthday messages from server members here:\n\n{newline.join([f"• {server.get_member(m['author']).name if m['author'] in [mb.id for mb in server.members] else m['authName']}: {m['message'] if messageVisibility else '<Content hidden due to privacy settings>'}" for m in messages])}'''
                                                if member.id == 247412852925661185: toSend = f"🍰🎊🍨🎈 Greetings {server.name}! It's my developer {member.mention}'s birthday!! Let's wish him a very special day! 🍰🎊🍨🎈{messageString if len(messages) > 0 else ''}"
                                                else: 
                                                    if self.bot.get_cog('Cyberlog').privacyVisibilityChecker(member, 'birthdayModule', 'birthdayDay'): toSend = f"🍰 Greetings {server.name}, it\'s {member.mention}\'s birthday! Let\'s all wish them a very special day! 🍰{messageString if len(messages) > 0 else ''}"
                                                    else: toSend = f"🍰 Greetings {server.name}! We have one anonymous member with a birthday today! Let\'s all wish them a very special day! 🍰{messageString if len(messages) > 0 else ''}"
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
        for user in self.bot.users:
            try: bday: datetime.datetime = self.bot.lightningUsers[user.id].get('birthday')
            except KeyError: continue #if user not found in the cache
            if bday:
                if bday.strftime('%m%d%y') == datetime.datetime.now().strftime('%m%d%y'): await database.ResetBirthdayMessages(user)

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
        # print('Updating birthdays')
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

    async def verifyBirthdaysDict(self):
        '''Creates/updates the global birthday dictionary'''
        birthdayList = collections.defaultdict(list)
        globalList:dict = await database.GetBirthdayList()
        for k, v in globalList.items():
            birthdayList[k] = v
        for user in self.bot.users:
            try: bday: datetime.datetime = self.bot.lightningUsers[user.id].get('birthday')
            except KeyError: bday: datetime.datetime = await database.GetMemberBirthday(user)
            if not bday: continue
            if user.id not in birthdayList[bday.strftime('%m%d')]: birthdayList[bday.strftime('%m%d')].append(user.id)
        await database.SetBirthdayList(birthdayList)

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
        ages = calculateAges(message)
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
    async def birthday(self, ctx: commands.Context, *args):
        await ctx.trigger_typing()
        theme = self.colorTheme(ctx.guild) if ctx.guild else 1
        adjusted = datetime.datetime.now()
        if len(args) == 0:
            header = '👮‍♂️ » 🍰 Birthday » 🏠 Overview'
            header = f'👮‍♂️ {ctx.author.name:.{63 - len(header)}} » 🍰 Birthday » 🏠 Overview'
            embed = discord.Embed(title=header, color=yellow[theme])
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url) #V2.0
            if not self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'default', 'birthdayModule'):
                embed.description = 'Birthday module disabled. To edit your privacy settings or enable the birthday module, go [here](http://disguard.herokuapp.com/manage/profile).'
                return await ctx.send(embed=embed)
            user = self.bot.lightningUsers[ctx.author.id]
            bday, age, wishlist = user.get('birthday'), user.get('age'), user.get('wishlist', [])
            embed.add_field(name='Your Birthday',value='Not configured' if not bday else 'Hidden' if ctx.guild and not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'birthdayDay') else f'{bday:%a %b %d}\n(<t:{round(bday.timestamp())}:R>)')
            embed.add_field(name='Your Age', value='Not configured' if not age else 'Hidden' if ctx.guild and not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'age') else age)
            if len(wishlist) > 0: embed.add_field(name='Your Wishlist', value='Hidden' if ctx.guild and not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'wishlist') else f'{len(wishlist)} items')
            embed.description = f'{self.loading} Processing global birthday information'
            #message = await ctx.send(embed=embed)
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
            disguardSuggest.sort(key = lambda m: len(mutualServersMemberToMember(self, ctx.author, m['data'])), reverse=True) #Servers the author and target share
            firstNine = [m['data'].name for m in currentServer[:3] + disguardSuggest[:3] + weekBirthday[:3]]
            def fillBirthdayList(list, maxEntries):
                return [f"{qlfc}\\▪️ **{m['data'].name if firstNine.count(m['data'].name) == 1 else m['data']}** • {m['bday']:%a %b %d} • <t:{round(m['bday'].timestamp())}:R>" for m in list[:maxEntries]]
            embed.description = f'''**{"AVAILABLE OPTIONS":–^70}**\n🍰: Browse birthday profiles\n📪: View more upcoming birthdays\n📆: Update your birthday\n🕯: Update your age\n📝: {"Manage" if len(wishlist) > 0 else "Create"} your wish list\n**{"UPCOMING BIRTHDAYS":–^70}\n**{("__THIS SERVER__" + newline) if len(currentServer) > 0 else ""}'''
            embed.description+= f'''{newline.join(fillBirthdayList(currentServer, 3))}{(newline + newline) if len(currentServer) > 0 else ""}{("__DISGUARD SUGGESTIONS__" + newline) if len(disguardSuggest) > 0 else ""}{newline.join(fillBirthdayList(disguardSuggest, 3))}{(newline + newline) if len(disguardSuggest) > 0 else ""}{("__WITHIN A WEEK__" + newline) if len(weekBirthday) > 0 else ""}'''
            embed.description+= f'''{newline.join(fillBirthdayList(weekBirthday, 3))}{newline if len(weekBirthday) > 0 else ""}'''
            #await message.edit(embed=embed)
            message = await ctx.send(embed=embed)
            reactions = ['📪',  '📆', '🕯', '📝']
            for r in reactions: await message.add_reaction(r)
            def reactionCheck(r, u): return str(r) in reactions and r.message.id == message.id and u == ctx.author
            try: result = await self.bot.wait_for('reaction_add', check=reactionCheck)
            except asyncio.TimeoutError: return await message.edit(embed=birthdayCancelled)
            if str(result[0]) == '🍰': await messageManagement(self, ctx, message, result[1], [currentServer[:5], disguardSuggest[:5], weekBirthday[:5]]) #Figure out later
            elif str(result[0]) == '📪': await upcomingBirthdaysPrep(self, ctx, message, currentServer, disguardSuggest, weekBirthday) #Current
            elif str(result[0]) == '📆' and self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'birthdayDay'): await birthdayHandler(self, ctx, ctx.author, message) #Done
            elif str(result[0]) == '🕯' and self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'age'): await ageHandler(self, ctx, ctx.author, message) #Done
            elif str(result[0]) == '📝' and self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'wishlist'): await wishlistHandler(self, ctx, message) #Done
        else:
            embed=discord.Embed(title=f'{self.emojis["search"]} Birthdays', description=f'{self.loading} Searching', color=yellow[theme])
            message = await ctx.send(embed=embed)
            arg = ' '.join(args)
            actionList = []
            age = calculateAges(ctx.message)
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
        
async def guestBirthdayViewer(self: Birthdays, ctx: commands.Context, target: discord.User, cake=False):
    '''Displays information about somebody else's birthday profile'''
    #adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.lightningLogging.get(ctx.guild.id).get('offset'))
    user = self.bot.lightningUsers[target.id]
    bday = user.get('birthday')
    age = user.get('age')
    wishlist = user.get('wishList')
    header = '👮‍♂️ » 🍰 Birthday'
    header = f'👮‍♂️ {target.name:.{63 - len(header)}} » 🍰 Birthday'
    embed = discord.Embed(title=header, color=yellow[self.colorTheme(ctx.guild)], description=f'**{"WISH LIST":–^70}**\n{newline.join([f"• {wish}" for wish in wishlist])}')
    embed.description += f'''\n**{"AVAILABLE OPTIONS":–^70}**\n{f"{self.emojis['settings']}: Enter Action Overview" if target == ctx.author else ''}{f"{newline}🍰 (Only anyone other than {target.name}): Write a personal birthday message to {target.name}" if not cake else ''}'''
    #embed.set_author(name=target.name, icon_url=target.avatar_url) #V1.5
    embed.set_author(name=target.name, icon_url=target.avatar.url) #V2.0
    embed.add_field(name='Birthday', value='Not configured' if bday is None else 'Hidden' if not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(target, 'birthdayModule', 'birthdayDay') else f'{bday:%a %b %d}\n(<t:{round(bday.timestamp())}:R>)')
    embed.add_field(name='Age', value='Not configured' if age is None else 'Hidden' if not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(target, 'birthdayModule', 'birthdayDay') else age)
    return embed

async def wishlistHandler(self: Birthdays, ctx: commands.Context, m: discord.Message, cont=False, new=None):
    wishlist = ['You have disabled birthday wishlist functionality'] if not self.bot.get_cog('Cyberlog').privacyEnabledChecker(ctx.author, 'birthdayModule', 'wishlist') else ['You have set your wishlist to private'] if not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'wishlist') and ctx.guild else self.bot.lightningUsers[ctx.author.id].get('wishlist', [])
    header = '👮‍♂️ » 🍰 Birthday » 📝 Wishlist' #TODO: implement privacy settings and potentially mimic the theme/feel of the birthday/age module
    embed=discord.Embed(title=f'📝 Wishlist home', description=f'**{"YOUR WISH LIST":–^70}**\n{newline.join([f"• {w}" for w in wishlist]) if wishlist else "Empty"}', color=yellow[self.colorTheme(ctx.guild)])
    embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
    new = await ctx.send(embed=embed, view=WishlistView(self, ctx, m, cont, new, wishlist, embed)) #Use default class var

async def ageHandler(self: Birthdays, ctx: commands.Context, author: discord.Member, message: discord.Message):
    ageHidden = ctx.guild and not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'age')
    currentAge = self.bot.lightningUsers[author.id].get('age')
    ageModuleDescription = 'Entering your age is a fun but optional feature of the birthday module and has no relation to Discord Inc. It will only be used to personalize the message DMd to you on your birthday. If you set your age, others can view it on your birthday profile by default. If you wish to set your age but don\'t want others to view it, [update your privacy settings](http://disguard.herokuapp.com/manage/profile).\n\n'
    instructions = 'Since your age visibility is set to private, use the virtual keyboard (edit privately button) to enter your age' if ageHidden else 'Type your desired age'
    embed=discord.Embed(title='🕯 Birthday age setup', description=f'{ageModuleDescription if not currentAge else ""}{instructions}\n\nCurrent value: **{"🔒 Hidden" if ageHidden else currentAge}**', color=yellow[self.colorTheme(ctx.guild)], timestamp=datetime.datetime.utcnow())
    embed.set_author(name=author.name, icon_url=author.avatar.url)
    view = AgeView(self, ctx, message, None, embed, currentAge, ageHidden)
    new = await ctx.send(embed=embed, view=view)
    view.message = new

async def birthdayHandler(self: Birthdays, ctx: commands.Context, author: discord.Member, message: discord.Message):
    bdayHidden = ctx.guild and not self.bot.get_cog('Cyberlog').privacyVisibilityChecker(ctx.author, 'birthdayModule', 'birthdayDay')
    currentBday = self.bot.lightningUsers[author.id].get('birthday')
    birthdayModuleDescription = 'The Disguard birthday module provides fun, voluntary features for those wanting to use it. Setting your birthday will allow Disguard to make an announcement on your birthday in servers with this feature enabled, and Disguard will DM you a message on your birthday. By default, others can view your birthday on your profile. If you wish to change this, [update your privacy settings](http://disguard.herokuapp.com/manage/profile).\n\n'
    instructions = 'Since your birthday visibility is set to private, please use the virtual keyboard (edit privately button) to enter your birthday' if bdayHidden else 'Type your birthday or use the virtual keyboard for your input. Examples of acceptable birthday formats include Jan 1, 5/25 (mm/dd), "next tuesday", "two months from now". Disguard does not process your birth year, so just enter a month and a day.'
    embed=discord.Embed(title='📆 Birthday date setup', description=f'{birthdayModuleDescription if not currentBday else ""}{instructions}\n\nCurrent value:  **{"🔒 Hidden" if bdayHidden else currentBday.strftime("%B %d")}**', color=yellow[self.colorTheme(ctx.guild)], timestamp=datetime.datetime.utcnow())
    embed.set_author(name=author.name, icon_url=author.avatar.url)
    view = BirthdayView(self, ctx, message, None, embed, currentBday, bdayHidden)
    new = await ctx.send(embed=embed, view=view)
    view.message = new

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

async def upcomingBirthdaysPrep(self: Birthdays, ctx: commands.Context, message: discord.Message, currentServer, disguardSuggest, weekBirthday):
    namesOnly = [m['data'].name for m in currentServer + disguardSuggest + weekBirthday]
    def fillBirthdayList(list, maxEntries):
        return [f"{qlfc}\\▪️ **{m['data'].name if namesOnly.count(m['data'].name) == 1 else m['data']}** • {m['bday']:%a %b %d} • <t:{round(m['bday'].timestamp())}:R>" for m in list[:maxEntries]]
    embed = message.embeds[0]
    embed.clear_fields()
    embed.description = f'''Click a button to expand that section**\n{"UPCOMING BIRTHDAYS":-^70}**\n__THIS SERVER__\n{newline.join(fillBirthdayList(currentServer, 8))}\n\n__DISGUARD SUGGESTIONS__\n{newline.join(fillBirthdayList(disguardSuggest, 8))}\n\n__WITHIN A WEEK__\n{newline.join(fillBirthdayList(weekBirthday, 8))}'''
    view = UpcomingBirthdaysView(None, ctx.author, currentServer, disguardSuggest, weekBirthday, namesOnly, embed, self.bot)
    message = await message.edit(embed=embed, view=view)
    view.message = message

def calculateDate(message, adjusted):
    '''Returns a datetime.datetime parsed from a message
    adjusted: Current time; with applicable timezone taken into consideration'''
    now = datetime.datetime.now()
    shortDays = collections.deque(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])
    longDays = collections.deque(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])
    shortMonths = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    longMonths = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
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

def calculateAges(m):
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
                if int(s[1 + s.index(finder)]) not in calculateAges(message): return False #If the relevant age is not the same one found in the message, return
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

def mutualServerMemberToMember(self: Birthdays, memberA: discord.User, memberB: discord.User):
    '''Returns whether the two given members share at least one mutual server'''
    for g in self.bot.guilds:
        foundA = False
        foundB = False
        for m in g.members:
            if m.id == memberA.id: foundA = True
            elif m.id == memberB.id: foundB = True
            if foundA and foundB: return True
    return False

def mutualServersMemberToMember(self: Birthdays, memberA: discord.User, memberB: discord.User):
    '''Returns the list of servers shared by the two given members'''
    servers: typing.List[discord.Guild] = []
    for g in self.bot.guilds:
        foundA = False
        foundB = False
        for m in g.members:
            if m.id == memberA.id: foundA = True
            elif m.id == memberB.id: foundB = True
            if foundA and foundB: 
                servers.append(g)
                break
    return servers

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

def setup(bot):
    bot.add_cog(Birthdays(bot))

class UpcomingBirthdayDict(typing.TypedDict):
    data: discord.Member
    bday: datetime.datetime

class SuccessView(discord.ui.View):
    def __init__(self, text):
        super().__init__()
        self.add_item(discord.ui.Button(label=text, style=discord.ButtonStyle.green, disabled=True))

class SuccessAndDeleteView(discord.ui.View):
    def __init__(self):
        super().__init__()
    
    @discord.ui.button(label='Delete message immediately')
    async def delete(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.message.delete()

class CancelledView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.Button(label='You may now dismiss this message', disabled=True))

class NumberInputInterface(discord.ui.View):
    def __init__(self, finale=None):
        super().__init__()
        self.result = ''
        self.finale = finale

    @discord.ui.button(emoji='✖', row=3, style=discord.ButtonStyle.red, custom_id='cancel')
    async def backspace(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result = self.result[:-1]
        await self.postProcess(interaction)

    @discord.ui.button(label='0', row=3)
    async def zero(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '0'
        await self.postProcess(interaction)
    
    @discord.ui.button(label='Submit', emoji='➡', row=3, style=discord.ButtonStyle.green, custom_id='submit')
    async def submit(self, button: discord.ui.Button, interaction: discord.Interaction):
        #await interaction.response.defer()
        if self.finale: await self.finale(self.result)
        await interaction.response.edit_message(embed=None, view=SuccessView('Press "confirm" on the original embed to complete setup'))

    @discord.ui.button(label='1', row=2)
    async def one(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '1'
        await self.postProcess(interaction)
        
    @discord.ui.button(label='2', row=2)
    async def two(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '2'
        await self.postProcess(interaction)
    
    @discord.ui.button(label='3', row=2)
    async def three(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '3'
        await self.postProcess(interaction)
        
    @discord.ui.button(label='4', row=1)
    async def four(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '4'
        await self.postProcess(interaction)
     
    @discord.ui.button(label='5', row=1)
    async def five(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '5'
        await self.postProcess(interaction)
     
    @discord.ui.button(label='6', row=1)
    async def six(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '6'
        await self.postProcess(interaction)
    
    @discord.ui.button(label='7', row=0)
    async def seven(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '7'
        await self.postProcess(interaction)
     
    @discord.ui.button(label='8', row=0)
    async def eight(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '8'
        await self.postProcess(interaction)
     
    @discord.ui.button(label='9', row=0)
    async def nine(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.result += '9'
        await self.postProcess(interaction)

    async def postProcess(self, interaction: discord.Interaction):
        #await interaction.channel.send(content = (self.result, self.children[0].emoji, self.children[0].emoji == '✖'))
        #print(self.result, self.children[0].emoji, self.children[0].emoji == '✖')
        if not self.result:
            if str(self.children[0].emoji) == '✖':
                return await interaction.response.edit_message(content='Cancelled', embed=None, view=CancelledView())
            self.children[0].emoji = '✖'
            self.children[0].custom_id = 'cancel'
        elif str(self.children[0].emoji) == '✖': 
            self.children[0].emoji = '⬅'
            self.children[0].custom_id = 'backspace'
        await interaction.response.edit_message(content=self.result, view=self)

class DateInputInterface(discord.ui.View):
    '''Uses a lower-level implementation to save space given how many similar buttons we're using'''
    def __init__(self, bot, message, author, finale=None):
        super().__init__()
        self.result: datetime.datetime = datetime.datetime(datetime.datetime.now().year, 1, 1)
        self.bot: commands.Bot = bot
        self.message: discord.Message = message
        self.author: discord.User = author
        self.finale = finale
        self.lastInteraction = None
        self.backButton = discord.ui.Button(label='Cancel', emoji='✖', style=discord.ButtonStyle.red, custom_id='back')
        self.add_item(self.backButton)
        for month in 'January.February.March.April.May.June.July.August.September.October.November.December'.split('.'):
            self.add_item(discord.ui.Button(label=month, custom_id=month))
        asyncio.create_task(self.selectMonth())

    def interactionCheck(self, i: discord.Interaction):
        return self.author == i.user and i.channel == self.message.channel

    def setupMonths(self):
        self.clear_items()
        self.backButton = discord.ui.Button(label='Cancel', emoji='✖', style=discord.ButtonStyle.red, custom_id='back')
        months = {1:'January', 2:'February', 3:'March', 4:'April', 5:'May', 6:'June', 7:'July', 8:'August', 9:'September', 10:'October', 11:'November', 12:'December'}
        for i, month in enumerate(months.values(), 1):
            self.add_item(discord.ui.Button(label=month, style=discord.ButtonStyle.blurple if self.result.month == i else discord.ButtonStyle.gray, custom_id=month))
        asyncio.create_task(self.selectMonth(True))

    async def selectMonth(self, comeFromSetup=False):
        if comeFromSetup: await self.lastInteraction.edit_original_message(view=self)
        try: interaction: discord.Interaction = await self.bot.wait_for('interaction', check=self.interactionCheck, timeout=300)
        except asyncio.TimeoutError: return
        if interaction.data['custom_id'] == 'back':
            return await interaction.edit_original_message(content='Cancelled', embed=None, view=CancelledView())
        months = {'January':1, 'February':2, 'March':3, 'April':4, 'May':5, 'June':6, 'July':7, 'August':8, 'September':9, 'October':10, 'November':11, 'December':12}
        self.lastInteraction = interaction
        self.result = self.result.replace(month = months[interaction.data['custom_id']])
        self.backButton = discord.ui.Button(label=interaction.data['custom_id'], emoji='⬅', custom_id='back')
        self.setupDays()

    def setupDays(self):
        self.clear_items()
        self.add_item(self.backButton)
        for i in range(1, 24): #The rest will be handled within the actual method
            self.add_item(discord.ui.Button(label=i, style=discord.ButtonStyle.blurple if self.result.day == i else discord.ButtonStyle.gray, custom_id=i))
        asyncio.create_task(self.selectDay())

    async def selectDay(self):
        daysPerMonth = {1:31, 2:29 if isLeapYear() else 28, 3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31}
        firstHalf = True
        self.add_item(discord.ui.Button(label='Rest of month', custom_id='switch'))
        await self.lastInteraction.edit_original_message(view=self)
        while True:
            try: interaction: discord.Interaction = await self.bot.wait_for('interaction', check=self.interactionCheck, timeout=300)
            except asyncio.TimeoutError: return
            if interaction.data['custom_id'] == 'switch':
                self.clear_items()
                self.add_item(self.backButton)
                if firstHalf: bounds = (24, daysPerMonth[self.result.month] + 1)
                else: bounds = (1, 24)
                for i in range(*bounds):
                    self.add_item(discord.ui.Button(label=i, style=discord.ButtonStyle.blurple if self.result.day == i else discord.ButtonStyle.gray, custom_id=i))
                self.add_item(discord.ui.Button(label='Rest of month', custom_id='switch'))
                firstHalf =  not firstHalf
                await self.lastInteraction.edit_original_message(view=self)
            elif interaction.data['custom_id'] == 'back':
                return self.setupMonths()
            else:
                self.result = self.result.replace(day = int(interaction.data['custom_id']))
                self.backButton = discord.ui.Button(label='Redo', custom_id='back')
                break
        asyncio.create_task(self.confirmation())

    async def confirmation(self):
        self.clear_items()
        self.add_item(self.backButton)
        self.add_item(discord.ui.Button(label=f'Pass {self.result:%B %d} to the original embed', style=discord.ButtonStyle.green, custom_id='submit'))
        await self.lastInteraction.edit_original_message(view=self)
        while True:
            await asyncio.sleep(2)
            break
        try: result: discord.Interaction = await self.bot.wait_for('interaction', check=self.interactionCheck, timeout=300)
        except asyncio.TimeoutError: return
        if result.data['custom_id'] == 'back':
            self.setupMonths()
        else:
            if self.result < datetime.datetime.now(): self.result.replace(year = self.result.year + 1)
            if self.finale: await self.finale(self.result)
            await result.edit_original_message(content = f'{self.result:%B %d}', embed=None, view=SuccessView('Press "confirm" on the original embed to complete setup'))
        
class AgeView(discord.ui.View):
    def __init__(self, birthdays: Birthdays, ctx: commands.Context, originalMessage: discord.Message, message: discord.Message, embed: discord.Embed, currentAge: int, ageHidden: bool, newAge: int = None):
        super().__init__()
        self.birthdays = birthdays
        self.ctx = ctx
        self.originalMessage = originalMessage
        self.message = message #Current message; obtain from an interaction
        self.embed = embed
        self.currentAge = currentAge
        self.newAge = newAge
        self.usedPrivateInterface = False
        self.ageHidden = ageHidden
        self.finishedSetup = False
        asyncio.create_task(self.confirmation())

    @discord.ui.button(label='Cancel', emoji='✖', style=discord.ButtonStyle.red, custom_id='cancelSetup')
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.message.delete()
        self.finishedSetup = True

    @discord.ui.button(label='Edit privately', emoji='⌨')
    async def privateInterface(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.usedPrivateInterface = True
        for child in self.children: child.disabled = True #Disable all buttons for proper control flow
        await interaction.message.edit(view=self)
        embed = discord.Embed(title='Birthday age setup', description='Use the virtual keyboard to enter your desired age. Note that Disguard is unable to delete this message when you\'re done.')
        kb = NumberInputInterface(self.submitValue)
        await interaction.response.send_message(embed=embed, view=kb, ephemeral=True)
        result: discord.Interaction = await self.birthdays.bot.wait_for('interaction', check=lambda i: i.data['custom_id'] in ('submit', 'cancel'))
        for child in self.children: child.disabled = False
        if result.data['custom_id'] == 'cancel': await interaction.message.edit(view=self) #Enable buttons if cancelling virtual keybaord operation
    
    @discord.ui.button(label='Confirm', emoji='✔', style=discord.ButtonStyle.green, disabled=True, custom_id='confirmSetup')
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        button.disabled = True #set this as clicked
        await interaction.response.edit_message(view=self)
        await self.saveChanges()
        self.finishedSetup = True

    async def confirmation(self):
        while not self.birthdays.bot.is_closed() and not self.finishedSetup:
            def messageCheck(m: discord.Message): return m.author == self.ctx.author and m.channel == self.ctx.channel
            def interactionCheck(i: discord.Interaction):
                if i.data['custom_id'] == 'cancel': self.usedPrivateInterface = False
                return i.data['custom_id'] in ('submit', 'cancel', 'confirmSetup', 'cancelSetup')
            if not self.usedPrivateInterface and not self.ageHidden:
                done, pending = await asyncio.wait([self.birthdays.bot.wait_for('message', check=messageCheck, timeout=300), self.birthdays.bot.wait_for('interaction', check=interactionCheck)], return_when=asyncio.FIRST_COMPLETED)
                try: result = done.pop().result()
                except asyncio.TimeoutError: 
                    try: await self.message.delete()
                    except: pass
                    break #Close the loop if we time out
                for f in pending: f.cancel()
                if type(result) is discord.Interaction and result.data['custom_id'] in ('confirmSetup', 'cancelSetup'): break #If the user cancels or finishes setup, close the loop
                if not self.usedPrivateInterface: self.newAge = calculateAges(result)[0] #If private interface was used, submitValue will store the value
                try:
                    self.birthdays.bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                    await result.delete()
                except: pass
            if self.newAge:
                if self.newAge != self.currentAge:
                    self.embed.description=f'{"Update" if self.currentAge else "Set"} your age to **{"the input from the virtual keyboard" if self.usedPrivateInterface else self.newAge}**?\n\nYou may also type another age'
                    for child in self.children: child.disabled = False
                else:
                    self.embed.description=f'Your age is already set to **{"the value you entered" if self.usedPrivateInterface else self.newAge}** 👍\n\nYou may type another age or cancel setup'
                    for child in self.children[:2]: child.disabled = False
            else: self.embed.description=f'{self.birthdays.emojis["alert"]} | **{"the value you entered" if self.usedPrivateInterface else self.newAge}** isn\'t an age. You may type a new age or cancel the setup.'
            try: await self.message.edit(embed=self.embed, view=self)
            except discord.errors.NotFound: break
    
    async def saveChanges(self):
        #TODO: add age verification
        if self.newAge == self.currentAge: return await self.message.delete()
        await database.SetAge(self.ctx.author, self.newAge)
        if not self.usedPrivateInterface:
            self.embed.description = f'✔ | Age successfully updated to {"<Value hidden>" if self.usedPrivateInterface else self.newAge}'
            if not self.birthdays.bot.lightningUsers[self.ctx.author.id].get('birthday'):
                self.embed.description += '\n\nYou may add your birthday from the menu on the original embed if desired'
            await self.message.edit(embed=self.embed, view=SuccessAndDeleteView(), delete_after=30)
        else: await self.message.delete()
        self.originalMessage.embeds[0].set_field_at(1, name='Your Age',value=f'**Age Successfully Updated**\n{"🔒 Hidden" if self.usedPrivateInterface else self.newAge}')
        await self.originalMessage.edit(embed=self.originalMessage.embeds[0])

    async def submitValue(self, result):
        '''Writes the value from the KB interface to the class variable'''
        self.newAge = int(result)       

class BirthdayView(discord.ui.View):
    '''The interface for setting one's birthday'''
    #Almost a carbon copy from AgeView
    def __init__(self, birthdays: Birthdays, ctx: commands.Context, originalMessage: discord.Message, message: discord.Message, embed: discord.Embed, currentBday: datetime.datetime, bdayHidden: bool, newBday: datetime.datetime = None):
        super().__init__()
        self.birthdays = birthdays
        self.ctx = ctx
        self.originalMessage = originalMessage
        self.message = message
        self.embed = embed
        self.currentBday = currentBday
        self.newBday = newBday
        self.usedPrivateInterface = False
        self.bdayHidden = bdayHidden
        self.finishedSetup = False
        asyncio.create_task(self.confirmation())

    @discord.ui.button(label='Cancel', emoji='✖', style=discord.ButtonStyle.red, custom_id='cancelSetup')
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.message.delete()
        self.finishedSetup = True

    @discord.ui.button(label='Edit privately', emoji='⌨')
    async def privateInterface(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.usedPrivateInterface = True
        for child in self.children: child.disabled = True #Disable all buttons for proper control flow
        await interaction.message.edit(view=self)
        embed = discord.Embed(title='Birthday date setup', description='Use the virtual keyboard to enter your birthday. Note that Disguard is unable to delete this message when you\'re done.')
        kb = DateInputInterface(self.birthdays.bot, self.message, self.ctx.author, self.submitValue)
        await interaction.response.send_message(embed=embed, view=kb, ephemeral=True)
        result: discord.Interaction = await self.birthdays.bot.wait_for('interaction', check=lambda i: i.data['custom_id'] in ('submit', 'cancel'))
        for child in self.children: child.disabled = False
        if result.data['custom_id'] == 'cancel': await interaction.message.edit(view=self) #Enable buttons if cancelling virtual keybaord operation
    
    @discord.ui.button(label='Confirm', emoji='✔', style=discord.ButtonStyle.green, disabled=True, custom_id='confirmSetup')
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        button.disabled = True #set this as clicked
        await interaction.response.edit_message(view=self)
        await self.saveChanges()
        self.finishedSetup = True
    
    async def confirmation(self):
        while not self.birthdays.bot.is_closed() and not self.finishedSetup:
            def messageCheck(m: discord.Message): return m.author == self.ctx.author and m.channel == self.ctx.channel
            def interactionCheck(i: discord.Interaction): #TODO: needs more verification
                if i.data['custom_id'] == 'cancel': self.usedPrivateInterface = False
                return i.data['custom_id'] in ('submit', 'cancel', 'confirmSetup', 'cancelSetup')
            if not self.usedPrivateInterface and not self.bdayHidden:
                done, pending = await asyncio.wait([self.birthdays.bot.wait_for('message', check=messageCheck, timeout=300), self.birthdays.bot.wait_for('interaction', check=interactionCheck)], return_when=asyncio.FIRST_COMPLETED)
                try: result = done.pop().result()
                except asyncio.TimeoutError: 
                    try: await self.message.delete()
                    except: pass
                    break #Close the loop if we time out
                for f in pending: f.cancel()
                if type(result) is discord.Interaction and result.data['custom_id'] in ('confirmSetup', 'cancelSetup'): break #If the user cancels or finishes setup, close the loop
                if not self.usedPrivateInterface:
                    adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=self.birthdays.bot.lightningLogging.get(self.message.guild.id).get('offset', -5))
                    self.newBday = calculateDate(result, adjusted) #If private interface was used, submitValue will store the value
                try:
                    self.birthdays.bot.get_cog('Cyberlog').AvoidDeletionLogging(result)
                    await result.delete()
                except: pass
            if self.newBday:
                if self.newBday != self.currentBday:
                    self.embed.description=f'{"Update" if self.currentBday else "Set"} your birthday to **{"the input from the virtual keyboard" if self.usedPrivateInterface else self.newBday.strftime("%B %d")}**?\n\nYou may also type another date'
                    for child in self.children: child.disabled = False
                else:
                    self.embed.description=f'Your birthday is already set to **{"the value you entered" if self.usedPrivateInterface else self.newBday.strftime("%B %d")}** 👍\n\nYou may type another date or cancel setup'
                    for child in self.children[:2]: child.disabled = False
            else: self.embed.description=f'{self.birthdays.emojis["alert"]} | Unable to parse a date from **{"the value you entered" if self.usedPrivateInterface else self.newBday.strftime("%B %d")}**. You may type a new date or cancel the setup.'
            try: await self.message.edit(embed=self.embed, view=self)
            except discord.errors.NotFound: break
    
    async def saveChanges(self):
        if self.newBday == self.currentBday: return await self.message.delete()
        await database.SetBirthday(self.ctx.author, self.newBday)
        if not self.usedPrivateInterface:
            self.embed.description = f'✔ | Birthday successfully updated to {"<Value hidden>" if self.usedPrivateInterface else self.newBday.strftime("%B %d")}'
            bdayAnnounceChannel = self.birthdays.bot.lightningLogging[self.message.guild.id].get('birthday', 0)
            if bdayAnnounceChannel > 0: bdayAnnounceText = f'Since birthday announcements are enabled for this server, your birthday will be announced to {self.birthdays.bot.get_channel(bdayAnnounceChannel).mention}.'
            else: bdayAnnounceText = f'Birthday announcements are not enabled for this server. Moderators may enable this feature [here](http://disguard.herokuapp.com/manage/{self.message.guild.id}/server).'
            self.embed.description += f'\n\n{bdayAnnounceText}'
            if not self.birthdays.bot.lightningUsers[self.ctx.author.id].get('age'):
                self.embed.description += '\n\nYou may add your age from the menu on the original embed if desired'
            await self.message.edit(embed=self.embed, view=SuccessAndDeleteView(), delete_after=30)
        else: await self.message.delete()
        self.originalMessage.embeds[0].set_field_at(1, name='Your Birthday',value=f'**Birthday Successfully Updated**\n{"🔒 Hidden" if self.usedPrivateInterface else self.newBday.strftime("%B %d")}')
        await self.originalMessage.edit(embed=self.originalMessage.embeds[0])

    async def submitValue(self, result):
        '''Writes the value from the KB interface to the class variable'''
        self.newBday = result

class WishlistView(discord.ui.View):
    def __init__(self, birthdays: Birthdays, ctx: commands.Context, msg: discord.Message, cont: bool=False, new: discord.Message=None, wishlist: typing.List[str]=[], embed: discord.Embed=None):
        super().__init__()
        self.birthdays = birthdays
        self.ctx = ctx
        self.msg = msg
        self.cont = cont
        self.new = new
        self.wishlist = wishlist
        self.defaultEmbed = embed
        self.add_item(self.addButton(self.birthdays))
        self.add_item(self.removeButton(self.birthdays))

    @discord.ui.button(label='Close Viewer', style=discord.ButtonStyle.red)
    async def close(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.message.delete()
        # and re-enable the wishlist button on original message

    class addButton(discord.ui.Button):
        def __init__(self, birthdays: Birthdays):
            super().__init__(label='Add items', style=discord.ButtonStyle.gray, emoji=birthdays.emojis['whitePlus'])
        
        async def callback(self, interaction: discord.Interaction):
            view: WishlistView = self.view
            await view.wishlistEditPreview(interaction, add=True)
        
    class removeButton(discord.ui.Button):
        def __init__(self, birthdays: Birthdays):
            super().__init__(label='Remove items', style=discord.ButtonStyle.gray, emoji=birthdays.emojis['whiteMinus'])
        
        async def callback(self, interaction: discord.Interaction):
            view: WishlistView = self.view
            await view.wishlistEditPreview(interaction, add=False)

    async def wishlistEditPreview(self, interaction: discord.Interaction, add=True):
        '''Adds or removes items from one's wishlist, depending on the variable'''
        verb = 'remove'
        preposition = 'from'
        if add: 
            verb = 'add'
            preposition = 'to'
        self.new = interaction.message
        embed = self.new.embeds[0]
        header = f'👮‍♂️ » 📝{self.birthdays.whitePlus if add else self.birthdays.whiteMinus} {verb[0].upper()}{verb[1:]} entries {preposition} wishlist'
        embed.title = f'👮‍♂️ {self.ctx.author.name:.{63 - len(header)}} » 📝{self.birthdays.whitePlus if add else self.birthdays.whiteMinus} {verb[0].upper()}{verb[1:]} entries {preposition} wishlist'
        embed.description = f'**{"WISHLIST":–^70}**\n{"(Empty)" if not self.wishlist else newline.join([f"• {w}" for w in self.wishlist]) if add else newline.join([f"{i}) {w}" for i, w in enumerate(self.wishlist, 1)])}\n\nType{" the number or text of an entry" if not add else ""} to {verb} {"entries" if add else "it"} {preposition} your wish list. To {verb} multiple entries in one message, separate entries with a comma and a space.'
        await interaction.message.edit(embed=embed, view=WishlistEditView(self.birthdays, self.ctx, interaction.message, self.new, add))

class WishlistEditView(discord.ui.View):
    def __init__(self, birthdays: Birthdays, ctx: commands.Context, msg: discord.Message, new: discord.Message, add=True, wishlist: typing.List[str]=[]):
        super().__init__()
        self.birthdays = birthdays
        self.ctx = ctx
        self.msg = msg
        self.new = new
        self.add = add
        self.wishlist = wishlist
        self.tempWishlist = wishlist or []
        self.toModify = {} #First 16 chars of entries must be unique due to being used as dict keys
        self.children[1].emoji = self.birthdays.emojis['delete']
        asyncio.create_task(self.editWishlist(add)) #Probably don't need to pass if we're using class variables

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red, emoji='✖')
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.tempWishlist = self.wishlist or []
        await self.new.edit(embed=self.regenEmbed(), view=WishlistView(self.birthdays, self.ctx, self.msg, False, self.new))
        # TODO: and re-enable the wishlist button on original message

    @discord.ui.button(label='Clear entries', style=discord.ButtonStyle.gray, disabled=True)
    async def clear(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.tempWishlist = []
        await self.refreshDisplay()

    @discord.ui.button(label='Save', style=discord.ButtonStyle.green, emoji='✅')
    async def save(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.wishlist = self.tempWishlist #Should handle local state
        asyncio.create_task(database.SetWishlist(self.ctx.author, self.wishlist)) #And this will wrap up global state
        await self.new.edit(embed=self.regenEmbed(), view=WishlistView(self.birthdays, self.ctx, self.msg, False, self.new)) #Maybe add some sort of banner/message to communicate to the user that their changes were saved
        #Upon save success, edit embed to signify success and disable the buttons for about 1-2 seconds, then delete the wishlist embed & re-enable the wishlist button on the original message
        #Need to update embed title/entry icons to signify no longer being in edit mode
        # TODO: and re-enable the wishlist button on original message

    def regenEmbed(self):
        header = '👮‍♂️ » 🍰 Birthday » 📝 Wishlist'
        return discord.Embed(title=f'👮‍♂️ {self.ctx.author.name:.{63 - len(header)}} » 🍰 Birthday » 📝 Wishlist', description=f'**{"YOUR WISH LIST":–^70}**\n{newline.join([f"• {w}" for w in self.wishlist]) if self.wishlist else "Empty"}', color=yellow[self.birthdays.colorTheme(self.ctx.guild)])

    async def editWishlist(self, add=True):
        #await new.clear_reactions()
        #for r in ['❌', '✅']: await new.add_reaction(r)
        #def checkCheck(r, u): return u == ctx.author and r.message.id == new.id and str(r) == '✅'
        #def cancelCheck(r, u): return u == ctx.author and r.message.id == new.id and str(r) == '❌'
        def addCheck(m: discord.Message): return m.author == self.ctx.author and m.channel == self.ctx.channel
        while not self.birthdays.bot.is_closed():
            #done, p = await asyncio.wait([self.bot.wait_for('reaction_add', check=checkCheck, timeout=300), self.bot.wait_for('reaction_add', check=cancelCheck, timeout=300), self.bot.wait_for('message', check=addCheck, timeout=300)], return_when=asyncio.FIRST_COMPLETED)
            #try: stuff = done.pop().result()
            #except asyncio.TimeoutError: await new.delete()
            #for future in p: future.cancel()
            try: message: discord.Message = await self.birthdays.bot.wait_for('message', check=addCheck, timeout=300)
            except asyncio.TimeoutError: return await self.new.edit(view=WishlistView)
            #if type(stuff) is discord.Message:
            ### Deprecedated ability to send an image attachment as a wishlist entry
            # if len(message.attachments) > 0:
            #     if message.attachments[0].height: #We have an image or a video, so we will create a permanent URL via the private image hosting channel
            #         await stuff.add_reaction(self.loading)
            #         imageLogChannel = self.bot.get_channel(534439214289256478)
            #         tempDir = 'Attachments/Temp'
            #         savePath = '{}/{}'.format(tempDir, '{}.{}'.format(datetime.datetime.now().strftime('%m%d%Y%H%M%S%f'), stuff.attachments[0].filename[stuff.attachments[0].filename.rfind('.')+1:]))
            #         await stuff.attachments[0].save(savePath)
            #         f = discord.File(savePath)
            #         hostMessage = await imageLogChannel.send(file=f)
            #         toModify.append(hostMessage.attachments[0].url)
            #         if os.path.exists(savePath): os.remove(savePath)
            if message.content:
                words = message.content.split(', ') #O(n)
                for word in words: self.toModify[word[:16]] = word #O(n)
                self.tempWishlist += words #O(k)
            try:
                self.birthdays.bot.get_cog('Cyberlog').AvoidDeletionLogging(message)
                await message.delete()
            except discord.Forbidden: pass
            await self.refreshDisplay()
            # def formatWishlistEntry(s: str):
            #     # if add and toModify.get(s[:16]): return f'**+ {s}**'
            #     # elif not add and toModify.get(s[:16]): return f'~~{s}~~'
            #     # else: return f'• {s}'
            #     return f'**+ {s}**' if add and toModify.get(s[:16]) else f'~~{s}~~' if not add and toModify.get(s[:16]) else f'• {s}'
            # if add:
            #     verb='add'
            #     preposition='to'
            # else:
            #     verb='remove'
            #     preposition='from'
            #     #if stuff.content.lower() == 'clear': toModify = copy.copy(wishlist) #TODO: add a button for this
            #     # for w in wishlist: #Figure this stuff out - i think it shifts all the entries to the left??
            #     #     for wo in range(len(toModify)):
            #     #         try: toModify[wo] = wishlist[int(toModify[wo]) - 1]
            #     #         except: pass
            # self.new.embeds[0].description = f'Type{" the number or text of an entry" if verb != "add" else ""} to {verb} {"entries" if verb == "add" else "it"} {preposition} your wish list. To {verb} multiple entries in one message, separate entries with a comma and a space.\n\n**{"WISHLIST":–^70}**\n{"(Empty)" if not tempWishlist else newline.join([formatWishlistEntry(w) for w in tempWishlist]) if add else newline.join([f"{i}) {formatWishlistEntry(w)}" for i, w in enumerate(tempWishlist, 1)])}'
            # await self.new.edit(embed=self.new.embeds[0])
            # else:
            #     if str(stuff[0]) == '✅':
            #         new.embeds[0].description = '{} Saving...'.format(self.loading)
            #         await new.edit(embed=new.embeds[0])
            #         if add:
            #             for e in toModify: await database.AppendWishlistEntry(ctx.author, e)
            #         else:
            #             for w in toModify: wishlist.remove(w)
            #             await database.SetWishlist(ctx.author, wishlist)
            #     await new.clear_reactions()
            #     await m.remove_reaction('📝', ctx.author)
            #     return await firstWishlistContinuation(self, ctx, m, True, new)
    async def refreshDisplay(self):
        def formatWishlistEntry(s: str):
            # if add and toModify.get(s[:16]): return f'**+ {s}**'
            # elif not add and toModify.get(s[:16]): return f'~~{s}~~'
            # else: return f'• {s}'
            return f'**+ {s}**' if self.add and self.toModify.get(s[:16]) else f'~~{s}~~' if not self.add and self.toModify.get(s[:16]) else f'• {s}'
        verb = 'remove'
        preposition = 'from'
        if self.add:
            verb = 'add'
            preposition = 'to'
        #if stuff.content.lower() == 'clear': toModify = copy.copy(wishlist) #TODO: add a button for this
        # for w in wishlist: #Figure this stuff out - i think it shifts all the entries to the left??
        #     for wo in range(len(toModify)):
        #         try: toModify[wo] = wishlist[int(toModify[wo]) - 1]
        #         except: pass
        self.new.embeds[0].description = f'Type{" the number or text of an entry" if self.add else ""} to {verb} {"entries" if self.add else "it"} {preposition} your wish list. To {verb} multiple entries in one message, separate entries with a comma and a space.\n\n**{"WISHLIST":–^70}**\n{"(Empty)" if not self.tempWishlist else newline.join([formatWishlistEntry(w) for w in self.tempWishlist]) if self.add else newline.join([f"{i}) {formatWishlistEntry(w)}" for i, w in enumerate(self.tempWishlist, 1)])}'
        if self.tempWishlist: self.children[1].disabled = False
        else: self.children[1].disabled = True
        await self.new.edit(embed=self.new.embeds[0], view=self)

class UpcomingBirthdaysView(discord.ui.View):
    def __init__(self, message: discord.Message, author: discord.User, currentServer, disguardSuggest, weekBirthday, namesOnly, embed: discord.Embed, bot: commands.Bot, jumpStart=0):
        super().__init__()
        self.message = message
        self.author = author
        self.currentServer = list(self.paginate(currentServer))
        self.disguardSuggest = list(self.paginate(disguardSuggest))
        self.weekBirthday = list(self.paginate(weekBirthday))
        self.bot = bot
        self.namesOnly = namesOnly
        self.embed = embed
        self.currentView = (self.currentServer[0][:8] if self.currentServer else []) + (self.disguardSuggest[0][:8] if self.disguardSuggest else []) + (self.weekBirthday[0][:8] if self.weekBirthday else [])
        self.currentPage = 0
        self.finalPage = 0
        self.buttonClose = self.closeButton()
        self.buttonCurrentServer = self.currentServerButton()
        self.buttonDisguardSuggest = self.disguardSuggestButton()
        self.buttonWeekBirthday = self.weekBirthdayButton()
        self.buttonWriteMessage = self.writeMessageButton()
        self.buttonBack = self.backButton()
        self.buttonPrev = self.prevPage()
        self.buttonNext = self.nextPage()
        self.buttonSearch = self.searchMembersButton()
        self.memberDropdown = self.selectMemberDropdown()
        self.add_item(self.buttonClose)
        self.add_item(self.buttonCurrentServer)
        self.add_item(self.buttonDisguardSuggest)
        self.add_item(self.buttonWeekBirthday)
        self.add_item(self.buttonWriteMessage)
        if jumpStart == 1: asyncio.create_task(self.writeMessagePrompt(author))

    #TODO: I think I need to fully implement privacy settings here too

    def fillBirthdayList(self, list, page = 0, entries = 25):
        return [f"{qlfc}\\▪️ **{m['data'].name if self.namesOnly.count(m['data'].name) == 1 else m['data']}** • {m['bday']:%a %b %d} • <t:{round(m['bday'].timestamp())}:R>" for m in list[page][:entries]]

    def paginate(self, data):
        for i in range(0, len(data), 25): yield data[i:i+25] #25 entries per page

    async def loadHomepage(self):
        self.clear_items()
        self.add_item(self.buttonClose) #probably dont need to create new buttons all the time
        self.add_item(self.buttonCurrentServer)
        self.add_item(self.buttonDisguardSuggest)
        self.add_item(self.buttonWeekBirthday)
        self.add_item(self.buttonWriteMessage)
        self.embed.description = f'''Click a button to expand that section**\n{"UPCOMING BIRTHDAYS":-^70}**\n__THIS SERVER__\n{newline.join(self.fillBirthdayList(self.currentServer, entries=8))}\n\n__DISGUARD SUGGESTIONS__\n{newline.join(self.fillBirthdayList(self.disguardSuggest, entries=8))}\n\n__WITHIN A WEEK__\n{newline.join(self.fillBirthdayList(self.weekBirthday, entries=8))}'''
        await self.message.edit(embed=self.embed, view=self)
    
    class closeButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Close', style=discord.ButtonStyle.red)
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
    
    class backButton(discord.ui.Button):
        def __init__(self):
            super().__init__(emoji='⬅', label='Back')
            self.code = 0 #determines callback action
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            if self.code == 0: await view.loadHomepage()
    
    class prevPage(discord.ui.Button):
        def __init__(self):
            super().__init__(emoji='⏮', label='Previous Page')
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            if view.currentPage == 0: return await interaction.response.pong()
            view.currentPage -= 1
            if view.currentPage == 0: self.disabled = True #teething issues
            else: self.disabled = False
            view.embed.description = f'''Page {view.currentPage + 1} of {view.finalPage + 1}\n{newline.join(view.fillBirthdayList(view.currentView, view.currentPage))}'''
            await view.message.edit(embed=view.embed, view=view)

    class nextPage(discord.ui.Button):
        def __init__(self):
            super().__init__(emoji='⏭', label='Next Page')
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            if view.currentPage == view.finalPage: return await interaction.response.pong()
            view.currentPage += 1
            if view.currentPage == view.finalPage: self.disabled = True #teething issues
            else: self.disabled = False
            view.embed.description = f'''Page {view.currentPage + 1} of {view.finalPage + 1}\n{newline.join(view.fillBirthdayList(view.currentView, view.currentPage))}'''
            await view.message.edit(embed=view.embed, view=view)

    class currentServerButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Current Server')
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            view.clear_items()
            view.buttonPrev.disabled = True
            if len(view.currentServer) == 1: view.buttonNext.disabled = True
            view.add_item(view.buttonBack)
            view.add_item(view.buttonPrev)
            view.add_item(view.buttonNext)
            view.add_item(view.buttonWriteMessage)
            view.currentView = view.currentServer
            view.currentPage = 0
            view.finalPage = len(view.currentView) - 1
            view.embed.title = '🍰 Upcoming birthdays for this server'
            view.embed.description = f'''Page 1 of {view.finalPage + 1}\n{newline.join(view.fillBirthdayList(view.currentView))}'''
            await interaction.response.edit_message(embed=view.embed, view=view)

    class disguardSuggestButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Disguard Suggestions')
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            view.clear_items()
            view.buttonPrev.disabled = True
            if len(view.currentServer) == 1: view.buttonNext.disabled = True
            view.add_item(view.buttonBack)
            view.add_item(view.buttonPrev)
            view.add_item(view.buttonNext)
            view.add_item(view.buttonWriteMessage)
            view.currentView = view.disguardSuggest
            view.currentPage = 0
            view.finalPage = len(view.currentView) - 1
            view.embed.title = '🍰 Upcoming birthdays for members you share the most servers with'
            view.embed.description = f'''Page 1 of {view.finalPage + 1}\n{newline.join(view.fillBirthdayList(view.disguardSuggest))}'''
            await interaction.response.edit_message(embed=view.embed, view=view)

    class weekBirthdayButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Within a Week')
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            view.clear_items()
            view.buttonPrev.disabled = True
            if len(view.currentServer) == 1: view.buttonNext.disabled = True
            view.add_item(view.buttonBack)
            view.add_item(view.buttonPrev)
            view.add_item(view.buttonNext)
            view.add_item(view.buttonWriteMessage)
            view.currentView = view.weekBirthday
            view.currentPage = 0
            view.finalPage = len(view.currentView) - 1
            view.embed.title = '🍰 Upcoming global birthdays'
            view.embed.description = f'''Page 1 of {view.finalPage + 1}\n{newline.join(view.fillBirthdayList(view.weekBirthday))}'''
            await interaction.response.edit_message(embed=view.embed, view=view)
    
    class writeMessageButton(discord.ui.Button):
        def __init__(self):
            super().__init__(emoji='✉', label='Write message')
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            view.memberDropdown.updatePopulation(view.currentView)
            view.clear_items()
            view.add_item(view.memberDropdown)
            view.add_item(view.buttonBack)
            view.add_item(view.buttonSearch)
            description = 'You may write a message that will be delivered to someone on their birthday. Use the dropdown to select a member listed here or the search button to find someone we share a server with.'
            await interaction.response.edit_message(content=description, view=view)

    class selectMemberDropdown(discord.ui.Select):
        def __init__(self, population=[], custom_id = None):
            if custom_id: super().__init__(placeholder=f'Select a member ({len(population)} result{"" if len(population) == 1 else "s"})', custom_id=custom_id)
            else: super().__init__(placeholder=f'Select a member ({len(population)} result{"" if len(population) == 1 else "s"})')
            view: UpcomingBirthdaysView = self.view
            #self.row = 0
            self.userDict: typing.Dict[int, discord.User] = {}
            for d in population:
                u: discord.User = d['data']
                b: datetime.datetime = d['bday']
                self.add_option(label=u.name[:100], value=u.id, description=f'{b.strftime("%B %d") if b else "⚠ No birthday set"}')
                self.userDict[u.id] = u
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            await view.writeMessagePrompt(self.userDict[int(self.values[0])])

        def updatePopulation(self, population, custom_id=None):
            if custom_id: self.custom_id = custom_id
            self.options = []
            for d in population:
                u: discord.User = d['data']
                b: datetime.datetime = d['bday']
                self.add_option(label=u.name[:100], value=u.id, description=f'{b.strftime("%B %d") if b else "⚠ No birthday set"}')
                self.userDict[u.id] = u
            self.placeholder = f'Select a member ({len(population)} result{"" if len(population) == 1 else "s"})'

    class searchMembersButton(discord.ui.Button):
        def __init__(self):
            super().__init__(emoji='🔎', label='Search for someone else')
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            view.clear_items()
            view.add_item(view.buttonBack)
            view.embed.title= '🔎 Search members for a birthday message'
            view.embed.description = 'Send a message to search members in across our mutual servers, then select your desired result from the dropdown'
            select = view.memberDropdown
            def messageCheck(m: discord.Message): return m.author == view.author and m.channel == view.message.channel
            def selectCheck(i: discord.Interaction): return i.user == view.author and i.data['custom_id'] == str(view.message.id)
            def getBirthday(u: discord.User): return view.bot.lightningUsers[u.id].get('birthday')
            await interaction.response.edit_message(content=None, embed=view.embed, view=view)
            while not view.bot.is_closed():
                done, pending = await asyncio.wait([view.bot.wait_for('message', check=messageCheck, timeout=300), view.bot.wait_for('interaction', check=selectCheck, timeout=300)], return_when=asyncio.FIRST_COMPLETED)
                try: result = done.pop().result()
                except asyncio.TimeoutError: await view.loadHomepage()
                for f in pending: f.cancel()
                if type(result) is discord.Interaction: break
                # result: discord.Message = await view.bot.wait_for('message', check=messageCheck, timeout=300)
                result: discord.Message = result
                cyberlog: Cyberlog.Cyberlog = view.bot.get_cog('Cyberlog')
                results = await utility.FindMoreMembers(view.bot.users, result.content)
                try:
                    cyberlog.AvoidDeletionLogging(result)
                    await result.delete()
                except (discord.Forbidden, discord.HTTPException): pass
                users = [r['member'] for r in results]
                listToPass = [{'data': u, 'bday': getBirthday(u)} for u in users]
                #select = view.selectMemberDropdown(listToPass, view.message.id)
                select.updatePopulation(listToPass, str(view.message.id))
                if len(view.children) == 1: view.add_item(select)
                await view.message.edit(view=view)
    
    class switchToDMsButton(discord.ui.Button):
        def __init__(self, target: discord.User):
            super().__init__(label='Switch to DMs')
            self.target = target
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            message = await view.author.send(embed=view.embed, view=view)
            await interaction.response.pong()
            view.message = message
            await view.writeMessagePrompt(self.target)

    async def writeMessagePrompt(self, target: discord.User):
        self.clear_items()
        self.add_item(self.buttonBack)
        if self.message.guild:
            intro = 'Until [input forms](https://cdn.discordapp.com/attachments/697138785317814292/940761395883024424/c896cb74-1206-4632-bcb4-99eccf1c0356.png) are fully implmented, this process will take place in DMs. Make sure your DMs are open, then press the button below this embed.'
            self.add_item(self.switchToDMsButton(target))
        else:
            intro = f'Type your message for {target.name}. Note that you cannot send server invites or hyperlinks in birthday messages.'
            existingMessages = self.bot.lightningUsers[target.id].get('birthdayMessages')
            filtered = [m for m in existingMessages if target.id == m['author']]
            if filtered:
                intro += f'\n\nℹ | You already have {len(filtered)} messages queued for {target.name}. If you wish to add another, you may continue by sending your desired message.'
            if not self.bot.lightningUsers[target.id].get('birthday'): intro += f'\n\nℹ | {target.name} hasn\'t set their birthday yet. You may still write a message, but it will only be delivered if they set their birthday.'
        self.embed.title = f'Compose birthday message for {target.name}'
        self.embed.description = intro
        await self.message.edit(content=None, embed=self.embed, view=self)
        if type(self.message.channel) is not discord.DMChannel: return #ensures we only proceed if in DMs
        def messageCheck(m: discord.Message): return m.author == self.author# and type(m.channel) is discord.DMChannel
        satisfactoryMessage = False
        while not satisfactoryMessage:
            try: msgInBottle: discord.Message = await self.bot.wait_for('message', check=messageCheck, timeout=300)
            except asyncio.TimeoutError: return await self.loadHomepage()
            satisfactoryMessage = not re.search('.*discord.gg/.*', msgInBottle.content) and not re.search('.*htt(p|ps)://.*', msgInBottle.content) and len(msgInBottle.content) < 1024
            if not satisfactoryMessage:
                self.embed.description += f'\n\n⚠ | Your message contains hyperlinks, server invites, or is too long (the message must be < 1024 characters). Please try again.'
                await self.message.channel.send(embed=self.embed)
        self.embed.description = 'Select the destinations you want your message to be delivered to. Messages won\'t be delivered to channels with birthday announcements off unless they\'re turned on in the meantime.'
        mutualServers = mutualServersMemberToMember(self.bot.get_cog('Birthdays'), self.bot.user, target)
        dropdown = discord.ui.Select(min_values=1, placeholder='Select destination channels')
        dmChannel = target.dm_channel
        if not target.dm_channel:
            try:
                await target.create_dm()
                dmChannel = target.dm_channel
            except: dmChannel = None
        dropdown.add_option(label=f'{target.name}\'s DMs', value=target.dm_channel.id, description='Recommended' if dmChannel else 'Unable to DM')
        for server in mutualServers:
            birthdayChannel = server.get_channel(self.bot.lightningLogging[server.id].get('birthday'))
            dropdown.add_option(label=server.name, value=server.id, description=f'#{birthdayChannel.name}' if birthdayChannel else 'No announcement channel configured')
        dropdown.max_values = len(mutualServers) + 1
        next = discord.ui.Button(label='Next', style=discord.ButtonStyle.green, custom_id='next')
        self.add_item(dropdown)
        self.add_item(next)
        await self.message.channel.send(embed=self.embed, view=self)
        def interactionCheck(i: discord.Interaction): return i.data['custom_id'] == 'next' and i.user == self.author# and type(i.channel) is discord.DMChannel
        try: result = await self.bot.wait_for('interaction', check=interactionCheck, timeout=300)
        except asyncio.TimeoutError: return await self.loadHomepage()
        birthday = self.bot.lightningUsers[target.id].get('birthday')
        destinations = [f'• {self.bot.get_channel(int(dropdown.values[0]))}'] + [f'• {self.bot.get_guild(int(v))}' for v in (dropdown.values[1:] if len(dropdown.values) > 1 else [])]
        serverDestinations = [self.bot.get_guild(int(v)) for v in dropdown.values[1:]]
        self.embed.description = f'Your message to {target.name} says `{msgInBottle.content}`. It will be delivered on their birthday ({birthday:%B %d}) to the following destinations:\n{newline.join(destinations)}\n\nNote that if this message ends up being inapporpriate, {target.name} can flag it for investigation by Rick Astley and/or Disguard\'s developer. Learn more here.\n\nIf this all looks good, press the green button.'
        self.clear_items()
        self.add_item(self.buttonBack)
        #self.add_item(discord.ui.Button(label='Restart', custom_id='restart'))
        self.add_item(discord.ui.Button(label='Looks good', custom_id='confirm', style=discord.ButtonStyle.green))
        await self.message.channel.send(embed=self.embed, view=self)
        def finalCheck(i: discord.Interaction): return i.data['custom_id'] in ('restart', 'confirm') and i.user == self.author# and type(i.channel) is discord.DMChannel
        try: result: discord.Interaction = await self.bot.wait_for('interaction', check=finalCheck, timeout=300)
        except asyncio.TimeoutError: return await self.loadHomepage()
        #print(result.data['custom_id'])
        if result.data['custom_id'] == 'restart': return await self.writeMessagePrompt(target) #TODO: restart button
        await database.SetBirthdayMessage(target, msgInBottle, self.author, serverDestinations)
        await self.message.channel.send(f'Successfully queued the message for {target.name}')


        
    
