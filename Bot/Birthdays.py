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
    def __init__(self, bot: commands.Bot):
        cyber: Cyberlog.Cyberlog = bot.get_cog('Cyberlog')
        self.bot = bot
        self.loading: discord.Emoji = cyber.emojis['loading']
        self.emojis: typing.Dict[str, discord.Emoji] = cyber.emojis
        self.configureDailyBirthdayAnnouncements.start()
        self.configureServerBirthdayAnnouncements.start()
        self.configureDeleteBirthdayMessages.start()
    
    def cog_unload(self):
        self.configureDailyBirthdayAnnouncements.cancel()
        self.configureServerBirthdayAnnouncements.cancel()
        self.configureDeleteBirthdayMessages.cancel()

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
            user_data = await utility.get_user(user)
            try: bday: datetime.datetime = user_data.get('birthday')
            except KeyError: continue #User not in cache
            # If there's no birthday set for this user or they've disabled the birthday module, return
            if not bday or not await cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayDay'): continue
            # If this user has an age set on their profile, increment it
            if await cyber.privacyEnabledChecker(user, 'birthdayModule', 'age'):
                age = user_data.get('age', 0) + 1
                if age > 1: asyncio.create_task(database.SetAge(user, age))
            # Construct their next birthday to set in the database
            messages = user_data.get('birthdayMessages', []) if await cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayMessages') else []
            filteredMessages = [m for m in messages if user.dm_channel.id in m['servers']]
            # Construct the happy birthday embed
            embed = discord.Embed(title=f'🍰 Happy {f"{age - 1}{utility.suffix(age - 1)}" if age > 1 else ""}Birthday, {user.name}! 🍰', color=yellow[1])
            embed.description = f'Enjoy this special day just for you, {user.name}! In addition to the people you know who will hopefully send birthday wishes your way, my developer also wants to wish you only the best on your birthday. Take it easy today, and try to treat yourself in some fashion.\n\n~~RicoViking9000, developer of Disguard'
            if filteredMessages: embed.description += f'\n\n🍰 | Friends in your servers have also composed {len(filteredMessages)} messages for your birthday! They will be displayed below this message.'
            messageEmbeds = [embed] + [discord.Embed(title=f'✉ Birthday Message from {m["authName"]}', description=m['message'], color=yellow[1]) for m in filteredMessages]
            # Add a disclaimer footer to the last embed sent
            if filteredMessages:
                messageEmbeds[-1].set_footer('The developer of Disguard and server moderators have no say in the contents of messages sent by other users. If any of these messages are inappropriate, please contact the moderator of a server you share with the user, or get in contact with Disguard\'s developer. You may also delete one of these messages from our DMs with `.delete <ID of message containing offensive message>`.')
            # Split the embeds to send into groups of 10, since messages can hold a maximum of 10 embeds
            embedsToSend = utility.paginate(messageEmbeds, 10)
            try:
                for page in embedsToSend: await user.send(embeds=page)
            except (discord.HTTPException, discord.Forbidden): pass #Can't DM this user

    @tasks.loop(minutes=5)
    async def serverBirthdayAnnouncements(self):
        birthdayDict: typing.Dict[str, typing.List[int]] = await database.GetBirthdayList()
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        for userID in birthdayDict.get(datetime.date.today().strftime('%m%d'), []):
            user = self.bot.get_user(userID)
            user_data = await utility.get_user(user)
            if not await cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayDay'): continue
            try: bday: datetime.datetime = user_data.get('birthday')
            except KeyError: continue #User not in cache
            # If there's no birthday set for this user or they've disabled the birthday module, return
            if not bday or not await cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayDay'): continue
            # TODO: Make mutual servers member to member generator to improve speed
            servers = mutualServersMemberToMember(self, user, self.bot.user)
            for server in servers:
                timezone = await utility.time_zone(server)
                started = datetime.datetime.utcnow() + datetime.timedelta(hours=timezone)
                server_data = await utility.get_server(server)
                channel = self.bot.get_channel(server_data.get('birthday')) #Doing this instead of try/except since birthday channels usually default to 0 if not set
                if started.strftime('%H:%M') == server_data.get('birthdate', datetime.datetime.min).strftime('%H:%M') or not channel: continue
                # print(f'Announcing birthday for {member.name} to {server.name}')
                messages = [a for a in user_data.get('birthdayMessages', []) if server.id in a['servers']] if await cyber.privacyEnabledChecker(user, 'birthdayModule', 'birthdayMessages') else []
                messageString = f'Members from this server also wrote {len(messages)} birthday messages to be delivered here on {user.name}\'s birthday:' if messages else ''
                if userID == 247412852925661185: toSend = f'🍰🎊🍨🎈 Greetings {server.name}! It\'s my developer {user.mention}\'s birthday!! Let\'s wish him a very special day! 🍰🎊🍨🎈'
                else: 
                    if await cyber.privacyVisibilityChecker(user, 'birthdayModule', 'birthdayDay'): toSend = f"🍰 Greetings {server.name}, it\'s {user.mention}\'s birthday! Let\'s all wish them a very special day! 🍰"
                    else: toSend = f"🍰 Greetings {server.name}! We have an anonymous member with a birthday today! Let\'s all wish them a very special day! 🍰"
                if messages:
                    toSend += f'\n{messageString}'
                    messageEmbeds = [discord.Embed(title=f'✉ Birthday Message from {m["authName"]}', description=m['message'], color=yellow[1]) for m in messages]
                    embedsToSend = utility.paginate(messageEmbeds, 10)
                m = await self.bot.get_channel(channel).send(toSend, embeds=embedsToSend[0]) #Caveat: moderators can't delete individual embeds if inappropriate
                if len(embedsToSend) > 1:
                    for page in embedsToSend[1:]: await self.bot.get_channel(channel).send(embeds=embedsToSend[page])
                await m.add_reaction('🍰') #Consider the birthday wishes feature
                #Note: if any of these loops crash, I won't know

    @tasks.loop(hours=24)
    async def deleteBirthdayMessages(self):
        for user in self.bot.users:
            try: bday: datetime.datetime = (await utility.get_user(user)).get('birthday')
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

    async def verifyBirthdaysDict(self):
        '''Creates/updates the global birthday dictionary'''
        birthdayList = collections.defaultdict(list)
        globalList:dict = await database.GetBirthdayList()
        for k, v in globalList.items():
            birthdayList[k] = v
        for user in self.bot.users:
            try: bday: datetime.datetime = (await utility.get_user(user)).get('birthday')
            except AttributeError: 
                try: bday: datetime.datetime = await database.GetMemberBirthday(user)
                except AttributeError: continue
            if not bday: continue
            if user.id not in birthdayList[bday.strftime('%m%d')]: birthdayList[bday.strftime('%m%d')].append(user.id)
        await database.SetBirthdayList(birthdayList)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        '''Used for parsing and handling of birthday features'''
        if message.author.bot or message.channel.type == discord.ChannelType.private or not message.content: return
        if any(word in message.content.lower().replace("'", "").split(' ') for word in ['isnt', 'not', 'you', 'your']): return #Blacklisted words
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            if any([message.content.startswith(w) for w in [ctx.prefix + 'bday', ctx.prefix + 'birthday']]): return #Don't auto detect birthday information if the user is using a command
        try: 
            if (await utility.get_server(message.guild)).get('birthdayMode') in [None, 0]: return #Birthday auto detect is disabled
            if not await self.bot.get_cog('Cyberlog').privacyEnabledChecker(message.author, 'birthdayModule', 'birthdayDay'): return #This person disabled the birthday module
        except AttributeError: pass
        asyncio.create_task(self.birthdayMessagehandler(message))
        asyncio.create_task(self.ageMessageHandler(message))

    async def birthdayMessagehandler(self, message: discord.Message):
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        server_data = await utility.get_server(message.guild)
        if not await cyber.privacyEnabledChecker(message.author, 'birthdayModule', 'birthdayDay'): return #User disabled the birthday features
        adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=await utility.time_zone(message.guild))
        birthday = calculateDate(message.content, adjusted)
        #Now we either have a valid date in the message or we don't. So now we determine the situation and respond accordingly
        #First we make sure the user is talking about themself
        target = await verifyBirthday(message.content, adjusted, birthday)
        #Now, we need to make sure that the bot doesn't prompt people who already have a birthday set for the date they specified; and cancel execution of anything else if no new birthdays are detected
        if birthday and target:
            if server_data.get('birthdayMode') == 1:
                # Make user click button to proceed if the server setting is set like that
                def cakeAutoVerify(r:discord.Reaction, u:discord.User): return u == message.author and str(r) == '🍰' and r.message.id == message.id
                await message.add_reaction('🍰')
                await self.bot.wait_for('reaction_add', check=cakeAutoVerify)
            if birthday < adjusted: birthday = datetime.datetime(birthday.year + 1, birthday.month, birthday.day)
            if target: #If there's still at least one member referenced in the original message:
                for member in target:
                    view = BirthdayView(self, member, message, None, None, birthday)
                    embed = await view.createEmbed()
                    await message.channel.send(embed=embed, view=view)
    
    async def ageMessageHandler(self, message: discord.Message):
        cyber: Cyberlog.Cyberlog = self.bot.get_cog('Cyberlog')
        if not await cyber.privacyEnabledChecker(message.author, 'birthdayModule', 'age'): return #User disabled the age features
        ages = calculateAges(message.content)
        ages = [a for a in ages if await verifyAge(message.content, a)]
        if not ages: return #No ages detected in message
        if (await utility.get_server(message.guild)).get('birthdayMode') == 1: #Make user add candle reaction
            def candleAutoVerify(r:discord.Reaction, u:discord.User): return u == message.author and str(r) == '🕯' and r.message.id == message.id
            await message.add_reaction('🕯')
            await self.bot.wait_for('reaction_add', check=candleAutoVerify)
        ageToPass = ages[0]
        view = AgeView(self, message.author, message, None, None, ageToPass)
        embed = await view.createEmbed()
        if len(ages) > 1:
            embed.description=f'{message.author.name} | If you wish to update your age, select the desired value from the dropdown'
            ageView = AgeSelectView(ages)
            tempMessage = await message.channel.send(embed=embed, view=ageView)
            def interactionCheck(i: discord.Interaction): return i.data['custom_id'] == ageView.select.custom_id and i.user == message.author and i.channel == message.channel
            try: await self.bot.wait_for('interaction', check=interactionCheck, timeout=300)
            except asyncio.TimeoutError:
                embed.description = '⌚ | Timed out'
                return await tempMessage.edit(embed=embed)
            ageToPass = ageView.select.values[0]
            view.newAge = ageToPass #Update the class var for the new age
            await tempMessage.edit(embed=embed, view=view)
        else: 
            new = await message.channel.send(embed=embed, view=view)
            view.message = new

    @commands.hybrid_command(aliases=['bday'])
    async def birthday(self, ctx: commands.Context, search: str = ''):
        theme = await utility.color_theme(ctx.guild) if ctx.guild else 1
        if not search:
            homeView = BirthdayHomepageView(self, ctx, None)
            embed = await homeView.createEmbed()
            message: discord.Message = await ctx.send(embed=embed) #Consider removing this if load times are quick
            homeView.message = message
            embed = await homeView.finishEmbed(embed)
            await message.edit(embed=embed, view=homeView)
        else:
            embed=discord.Embed(title=f'{self.emojis["search"]} Birthdays', description=f'{self.loading} Searching', color=yellow[theme])
            message = await ctx.send(embed=embed)
            actionList = []
            ages = calculateAges(search)
            actionList += ages
            memberList = await utility.FindMoreMembers(self.bot.users, search)
            memberList.sort(key = lambda x: x.get('check')[1], reverse=True)
            memberList = [m.get('member') for m in memberList if m.get('check')[1] >= 33] #Only take member results with at least 33% relevance to avoid ID searches when people only want to get their age
            memberList = [m for m in memberList if mutualServerMemberToMember(self, ctx.author, m)]
            actionList += memberList
            date = calculateDate(search, datetime.datetime.utcnow() + datetime.timedelta(days=await utility.time_zone(ctx.guild)))
            if date:
                view = BirthdayView(self, ctx.author, ctx.message, message, None, date)
                embed = await view.createEmbed()
                return await message.edit(embed=embed, view=view)
            async def makeChoice(result, message: discord.Message):
                if type(result) in (discord.User, discord.ClientUser):
                    view = GuestBirthdayView(self, ctx, result)
                    embed = await view.createEmbed()
                    return await message.edit(embed=embed, view=view)
                elif type(result) is int:
                    view = AgeView(self, ctx.author, ctx.message, message, None, result)
                    embed = await view.createEmbed()
                    return await message.edit(embed=embed, view=view)
                else:
                    view = BirthdayView(self, ctx.author, ctx.message, message, None, result)
                    embed = await view.createEmbed()
                    return await message.edit(embed=embed, view=view)
            if len(actionList) == 1 and type(actionList[0]) in (discord.User, discord.ClientUser): await makeChoice(actionList[0], message)
            elif len(actionList) == 0:
                embed.description = f'No actions found for **{search}**'
                return await message.edit(embed=embed)
            elif len(actionList) > 1:
                parsed = []
                for entry in actionList:
                    if type(entry) in [discord.User, discord.ClientUser]: parsed.append(f'View {entry.name}\'s birthday profile')
                    elif type(entry) is int: parsed.append(f'{"⚠ " if entry < 13 or entry > 105 else ""}Set age: {entry}')
                    else: parsed.append(f'Set birthday: {entry:%A, %b %d}')
                final = parsed[:25] #Only deal with the top 25 results
                embed.description = 'Use the dropdown menu to select your desired result'
                view = BirthdayActionView(final)
                await message.edit(embed=embed, view=view)
                def interactionCheck(i: discord.Interaction): return i.data['custom_id'] == view.select.custom_id and i.user == ctx.author and i.channel == ctx.channel
                try: await self.bot.wait_for('interaction', check=interactionCheck, timeout=300)
                except asyncio.TimeoutError:
                    embed.description = '⌚ | Timed out'
                    return await message.edit(embed=embed)
                await makeChoice(actionList[int(view.select.values[0])], message)
    
    @commands.hybrid_command(aliases=['setage'], description='Shortcut to update your age under the birthday module')
    async def age(self, ctx: commands.Context, new_age: int):
        return await self.birthday(ctx, str(new_age))

    @commands.hybrid_command(description='View or edit your birthday wishlist')
    async def wishlist(self, ctx: commands.Context):
        return await wishlistHandler(self, ctx, None, None)
        
async def guestBirthdayHandler(self: Birthdays, ctx: commands.Context, target: discord.User):
    view = GuestBirthdayView(self, ctx, target)
    embed = await view.createEmbed()
    await ctx.send(embed=embed, view=view)

async def birthdayHandler(self: Birthdays, ctx: commands.Context, message: discord.Message, previousView):
    view = BirthdayView(self, ctx.author, message, None, previousView)
    embed = await view.createEmbed()
    newMessage = await ctx.send(embed=embed, view=view)
    view.message = newMessage

async def ageHandler(self: Birthdays, ctx: commands.Context, message: discord.Message, previousView):
    view = AgeView(self, ctx.author, message, None, previousView)
    embed = await view.createEmbed()
    newMessage = await ctx.send(embed=embed, view=view)
    view.message = newMessage

async def wishlistHandler(self: Birthdays, ctx: commands.Context, message: discord.Message, previousView):
    view = WishlistView(self, ctx, message, None, previousView)
    embed = await view.createEmbed()
    newMessage = await ctx.send(embed=embed, view=view)
    view.message = newMessage

async def upcomingBirthdaysPrep(self: Birthdays, ctx: commands.Context, message: discord.Message, currentServer, disguardSuggest, weekBirthday):
    namesOnly = [m['data'].name for m in currentServer + disguardSuggest + weekBirthday]
    view = UpcomingBirthdaysView(self, message, ctx, currentServer, disguardSuggest, weekBirthday, namesOnly, None, self.bot)
    await view.createEmbed()
    await view.loadHomepage()

def calculateDate(message: str, adjusted: datetime.datetime):
    '''Returns a datetime.datetime parsed from a message
    adjusted: Current time; with applicable timezone taken into consideration'''
    # Initialize variables
    birthday = None
    now = datetime.datetime.now()
    shortDays = collections.deque(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])
    longDays = collections.deque(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])
    shortMonths = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    longMonths = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
    message = message.lower()
    words = message.split(' ')
    # Number of days in each month. As with days, this dict may need to move around
    ref = collections.deque([(a, b) for a, b in {1:31, 2:29 if isLeapYear() else 28, 3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31}.items()])
    ref.rotate(-1 * (adjusted.month - 1)) #Current month moves to the front
    # Determine if user used long month format (such as March) or short (such as Mar)
    if any(month in words for month in longMonths): months = longMonths
    else: months = shortMonths
    # Determine if the user used long day format (such as Monday) or short (such as Mon)
    if any(day in words for day in longDays): days = longDays
    else: days = shortDays
    # Check if month's short or long name or the word "the" are in the list of words in the input string (message)
    containsMonth = any(month in words for month in months)
    if containsMonth or 'the' in words:
        # iterate through all passed words
        for word in words:
            before = word
            # get rid of commas
            word = word.replace(',', '')
            # truncate the suffix if the user provided one
            if any(str(letter) in word for letter in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]):
                word = word.replace('st', '')
                word = word.replace('nd', '')
                word = word.replace('rd', '')
                word = word.replace('th', '')
            # if we have the name of a month in the original message and the current word is a number, try to get a date from that
            if containsMonth:
                try: 
                    birthday = datetime.datetime(now.year, months.index([d for d in months if d in word][0]) + 1, int(word))
                    break
                except: pass
            # if there's no month in the word and the word was succesfully truncated above, try getting a date from the current year and month (such as the user passing "the 6th")
            else:
                if before != word:
                    try: birthday = datetime.datetime(now.year, now.month, int(word))
                    except: pass
    # Check if day of the week is in message
    elif any(day in words for day in days):
        parserString = '%a' if days == shortDays else '%A'
        currentDay = days.index(adjusted.strftime(parserString).lower())
        targetDay = days.index([d for d in days if d in message][0])
        days.rotate(-1 * currentDay) #Current day is now at the start for proper calculations
        #Target is days until the day the user typed in chat. targetDay - currentDay is still the same as before the rotation
        birthday = adjusted + datetime.timedelta(days=targetDay-currentDay)
        if birthday < adjusted and 'was' not in words: birthday += datetime.timedelta(days=7) #If target is a weekday already past, jump it to next week; since that's what they mean if they didn't say 'was' in their sentence 
    elif any(phrase in words for phrase in ['today', 'yesterday', 'ago', 'tomorrow']):
        if any(phrase in message for phrase in ['my birthday', 'my bday' 'mine is']) and 'today' in words: birthday = adjusted
        elif any(phrase in message for phrase in ['my birthday', 'my bday' 'mine was']) and 'yesterday' in words: birthday = adjusted - datetime.timedelta(days=1)
        elif 'tomorrow' in words: birthday = adjusted + datetime.timedelta(days=1)
        else:
            for word in words:
                try: num = int(word)
                except ValueError: continue
                if any(w in words for w in ['day', 'days']): birthday = adjusted - datetime.timedelta(days=num)
                if any(w in words for w in ['week', 'weeks']): birthday = adjusted - datetime.timedelta(days=num*7)
                if any(w in words for w in ['month', 'months']): birthday = adjusted - datetime.timedelta(days= sum(a[1] for a in list(ref)[-1 * num:])) #Jump back [num] months; starting from end of list because ago = back in time; need to get correct days
    else: #The user inputted either something vague or a format with slashes, etc. NEED TO TRIM WORDS TO CHECK ALL COMBINATIONS. Also check for word THE before number, above.
        '''NEXT UP: MENTIONS HANDLING: if you check for is, also check my/mine to make sure the user isnt saying 'mine is xxxx' Also ask the user if they want to set their birthday'''
        for word in words:
            try: birthday = datetime.datetime.strptime(word, "%m/%d/%y")
            except:
                try: birthday = datetime.datetime.strptime(word, "%m-%d-%y")
                except:
                    try: birthday = datetime.datetime.strptime(word, "%m %d %y")
                    except: birthday = None
    if 'half' in words and birthday: 
        ref.rotate(6)
        birthday = birthday + datetime.timedelta(days= sum(a[1] for a in list(ref)[:6])) #Deal with half birthdays; jump 6 months ahead
    return birthday

async def verifyBirthday(message: typing.Union[str, discord.Message], adjusted: datetime.datetime, birthday=None):
    '''Return a list of relevant members if the program determines that the member is talking about their own birthday or someone else's birthday given a message, None otherwise'''
    if not birthday: birthday = calculateDate(message, adjusted)
    words = message.lower().split(' ')
    #Now we either have a valid date in the message or we don't. So now we determine the situation and respond accordingly
    #User most likely talking about their own birthday
    if any(word in message.lower() for word in ['my birthday', 'my bday', 'mine is', 'my half birthday', 'my half bday']): return [message.author]
    #User most likely talking about someone else's birthday
    elif type(message) is discord.Message:
        if any(word in words for word in ['is', 'are']) and not any(word in words for word in ['my', 'mine']) and len(message.mentions) > 0 and any(word in message.content.lower() for word in ['birthday', 'bday']): return message.mentions
    return []
    #User most likely answered a question asked by a user
    # else:
    #     async for m in message.channel.history(limit=10): #How many messages to check back for question words
    #         if any(word in m.content.lower() for word in ['when', 'what']) and any(word in m.content.lower() for word in ['your birthday', 'your bday', 'yours']): return [message.author]

def calculateAges(message: str):
    '''Returns a list of numbers found in a message'''
    ages = []
    for word in message.lower().split(' '):
        try: ages.append(int(word))
        except: pass
    return ages

async def verifyAge(message: str, age):
    '''Verifies that a person was talking about their age. This is far more prone to false positives than birthday verification, and the catch all is return True, so I have to make sure I return False when necessary'''
    words = message.lower().split(' ')
    message = [word.replace('\'', '') for word in words] #replace any apostrophes with nothing (i'm --> im) for parsing convenience
    tagged = nltk.pos_tag(nltk.word_tokenize(message)) #record the parts of speech in the sentence for analysis later
    if any(word in message for word in ['im', 'i\'m']) or 'i am' in message: #Deal with age
        if 'i am' in message: finder = 'am'
        else: finder = 'im'
        try: number = int(message[1 + message.index(finder)])
        except: return False
        if abs(message.index(str(number)) - message.index(finder)) > 1: return False #I'm or I am is too far from the actual number so it's irrelevant
        if number:
            try: tail = message[message.index(str(number)):] #If there is content after the number, try to deal with it
            except: 
                if int(message[1 + message.index(finder)]) not in calculateAges(message): return False #If the relevant age is not the same one found in the message, return
                return False
            if len(tail) > 1:
                if 'year' not in tail[1]:
                    #Parts of speech analysis
                    if tagged[1 + message.index(str(number))][1] not in ['IN', 'CC']: return False #Part of speech after age number makes this not relevant
                else:
                    if len(tail) > 2:
                        if 'old' not in tail[2]: return False
    elif 'age is' in message:
        if 'my' not in words: return False
        try: int(message[message.index('age') + 2])
        except: return False
    else: return False
    return True

def mutualServerMemberToMember(self: Birthdays, memberA: discord.User, memberB: discord.User):
    '''Returns whether the two given members share at least one mutual server'''
    for g in self.bot.guilds:
        foundA = False
        foundB = False
        for m in g.members:
            if m.id == memberA.id == memberB.id: return True
            elif m.id == memberA.id: foundA = True
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
            if m.id == memberB.id: foundB = True
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

async def setup(bot: commands.Bot):
    await bot.add_cog(Birthdays(bot))

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
        
class BirthdayHomepageView(discord.ui.View):
    def __init__(self, birthdays, ctx, message = None):
        super().__init__()
        self.birthdays: Birthdays = birthdays
        self.ctx: commands.Context = ctx
        self.message: discord.Message = message
        self.cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')

    async def createEmbed(self):
        theme = await utility.color_theme(self.ctx.guild) if self.ctx.guild else 1
        cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
        user = await utility.get_user(self.ctx.author)
        bday, age, wishlist = user.get('birthday'), user.get('age'), user.get('wishlist', [])
        embed = discord.Embed(title = '🍰 Birthday Overview', color=yellow[theme])
        embed.set_author(name=self.ctx.author.name, icon_url=self.ctx.author.avatar.url)
        if not await cyber.privacyEnabledChecker(self.ctx.author, 'default', 'birthdayModule'):
            embed.description = 'Birthday module disabled due to your privacy settings'
            self.add_item(discord.ui.Button(label='Edit privacy settings', url='http://disguard.herokuapp.com/manage/profile'))
            if not self.message: return await self.ctx.send(embed=embed, view=self)
            else: return await self.message.edit(embed=embed, view=self)
        embed.add_field(name='Your Birthday',value='Not configured' if not bday else 'Hidden' if self.ctx.guild and not await cyber.privacyVisibilityChecker(self.ctx.author, 'birthdayModule', 'birthdayDay') else f'{bday:%a %b %d}\n(<t:{round(bday.timestamp())}:R>)')
        embed.add_field(name='Your Age', value='Not configured' if not age else 'Hidden' if self.ctx.guild and not await cyber.privacyVisibilityChecker(self.ctx.author, 'birthdayModule', 'age') else age)
        if len(wishlist) > 0: embed.add_field(name='Your Wishlist', value='Hidden' if self.ctx.guild and not await cyber.privacyVisibilityChecker(self.ctx.author, 'birthdayModule', 'wishlist') else f'{len(wishlist)} items')
        embed.description = f'{self.birthdays.loading} Processing global birthday information'
        return embed

    async def finishEmbed(self, embed: discord.Embed):
        #Sort members into three categories: Members in the current server, Disguard suggestions (mutual servers based), and members that have their birthday in a week
        currentServer = []
        disguardSuggest = []
        weekBirthday = []
        user = await utility.get_user(self.ctx.author)
        bday, age, wishlist = user.get('birthday'), user.get('age'), user.get('wishlist', [])
        memberIDs = set([m.id for m in self.ctx.guild.members]) if self.ctx.guild else () #June 2021 (v0.2.27): Changed from list to set to improve performance // Holds list of member IDs for the current server
        cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
        for u in self.birthdays.bot.users:
            try:
                #Skip members whose privacy settings show they don't want to partake in public features of the birthday module
                if not all((
                    await cyber.privacyEnabledChecker(u, 'default', 'birthdayModule'),
                    await cyber.privacyEnabledChecker(u, 'default', 'birthdayModule'),
                    await cyber.privacyEnabledChecker(u, 'birthdayModule', 'birthdayDay'),
                    await cyber.privacyVisibilityChecker(u, 'birthdayModule', 'birthdayDay')
                    )):
                    continue
                userBirthday: datetime.datetime = (await utility.get_user(u)).get('birthday')
                if not userBirthday: continue
                if u.id in memberIDs: currentServer.append({'data': u, 'bday': userBirthday})
                elif mutualServerMemberToMember(self.birthdays, self.ctx.author, u):
                    if (userBirthday - datetime.datetime.now()).days < 8: weekBirthday.append({'data': u, 'bday': userBirthday})
                    else: disguardSuggest.append({'data': u, 'bday': userBirthday})
            except (AttributeError, TypeError, KeyError): pass
        currentServer.sort(key = lambda m: m.get('bday'))
        weekBirthday.sort(key = lambda m: m.get('bday'))
        disguardSuggest.sort(key = lambda m: len(mutualServersMemberToMember(self.birthdays, self.ctx.author, m['data'])), reverse=True) #Servers the author and target share
        firstNine = [m['data'].name for m in currentServer[:3] + disguardSuggest[:3] + weekBirthday[:3]]
        def fillBirthdayList(list, maxEntries):
            return [f"{qlfc}\\▪️ **{m['data'].name if firstNine.count(m['data'].name) == 1 else m['data']}** • {m['bday']:%a %b %d} • <t:{round(m['bday'].timestamp())}:R>" for m in list[:maxEntries]]
        finalSeparator = f'{"UPCOMING BIRTHDAYS":–^70}' if currentServer or weekBirthday or disguardSuggest else f'{"":–^70}'
        embed.description = f'''**{finalSeparator}\n**{("__THIS SERVER__" + newline) if len(currentServer) > 0 else ""}'''
        embed.description+= f'''{newline.join(fillBirthdayList(currentServer, 3))}{(newline + newline) if len(currentServer) > 0 else ""}{("__DISGUARD SUGGESTIONS__" + newline) if len(disguardSuggest) > 0 else ""}{newline.join(fillBirthdayList(disguardSuggest, 3))}{(newline + newline) if len(disguardSuggest) > 0 else ""}{("__WITHIN A WEEK__" + newline) if len(weekBirthday) > 0 else ""}'''
        embed.description+= f'''{newline.join(fillBirthdayList(weekBirthday, 3))}{newline if len(weekBirthday) > 0 else ""}'''
        bdayVerb = 'Update' if bday else 'Set'
        ageVerb = 'Update' if age else 'Set'
        wishlistVerb = 'Update' if wishlist else 'Create'
        self.currentServer = currentServer
        self.disguardSuggest = disguardSuggest
        self.weekBirthday = weekBirthday
        self.birthdayButton = self.editBirthday(bdayVerb)
        self.ageButton = self.editAge(ageVerb)
        self.wishlistButton = self.editWishlist(wishlistVerb)
        for item in [self.birthdayButton, self.ageButton, self.wishlistButton]: self.add_item(item)
        return embed

    @discord.ui.button(label='Browse birthday profiles', emoji='📁')
    async def profiles(self, button: discord.ui.Button, interaction: discord.Interaction):
        await upcomingBirthdaysPrep(self.birthdays, self.ctx, self.message, self.currentServer, self.disguardSuggest, self.weekBirthday)

    class editBirthday(discord.ui.Button):
        def __init__(self, verb: str):
            super().__init__(label=f'{verb} birthday', emoji='📆')
        async def callback(self, interaction: discord.Interaction):
            view: BirthdayHomepageView = self.view
            if await view.cyber.privacyEnabledChecker(view.ctx.author, 'birthdayModule', 'birthdayDay'):
                self.disabled = True
                await interaction.response.edit_message(view=view)
                await birthdayHandler(view.birthdays, view.ctx, view.message, view)
            else:
                await interaction.response.send_message('You have disabled the birthday feature of the birthday module. Review your settings: http://disguard.herokuapp.com/manage/profile', ephemeral=True)

    class editAge(discord.ui.Button):
        def __init__(self, verb: str):
            super().__init__(label=f'{verb} age', emoji='🕯')
        async def callback(self, interaction: discord.Interaction):
            view: BirthdayHomepageView = self.view
            if await view.cyber.privacyEnabledChecker(view.ctx.author, 'birthdayModule', 'age'):
                self.disabled = True
                await interaction.response.edit_message(view=view)
                await ageHandler(view.birthdays, view.ctx, view.message, view)
            else:
                await interaction.response.send_message('You have disabled the age feature of the birthday module. Review your settings: http://disguard.herokuapp.com/manage/profile', ephemeral=True)

    class editWishlist(discord.ui.Button):
        def __init__(self, verb: str):
            super().__init__(label=f'{verb} wishlist', emoji='📝')
        async def callback(self, interaction: discord.Interaction):
            view: BirthdayHomepageView = self.view
            if await view.cyber.privacyEnabledChecker(view.ctx.author, 'birthdayModule', 'wishlist'):
                self.disabled = True
                await interaction.response.edit_message(view=view)
                await wishlistHandler(view.birthdays, view.ctx, view.message, view)
            else:
                await interaction.response.send_message('You have disabled the wishlist feature of the birthday module. Review your settings: http://disguard.herokuapp.com/manage/profile', ephemeral=True)
 
class GuestBirthdayView(discord.ui.View):
    '''Displays basic information about someone's birthday profile'''
    def __init__(self, birthdays: Birthdays, ctx: commands.Context, target: discord.User):
        super().__init__()
        self.birthdays = birthdays
        self.ctx = ctx
        self.target = target
        if ctx.author == target: self.add_item(self.OverviewButton(birthdays))
        self.add_item(self.MessageButton(birthdays))

    async def createEmbed(self):
        cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
        user = await utility.get_user(self.target)
        bday = user.get('birthday')
        age = user.get('age')
        wishlist = user.get('wishList', []) #TODO: implement privacy settings
        wishlistHidden = not await cyber.privacyVisibilityChecker(self.target, 'birthdayModule', 'wishlist')
        description = f'**{"WISH LIST":–^70}**\n{newline.join([f"• {wish}" for wish in wishlist]) if wishlist and not wishlistHidden else "Set to private by user" if wishlistHidden else ""}'
        embed = discord.Embed(title = f'🍰 {self.target.name}\'s Birthday Page', description=description, color=yellow[await utility.color_theme(self.ctx.guild)])
        embed.set_author(name=self.target.name, icon_url=self.target.avatar.url)
        embed.add_field(name='Birthday', value='Not configured' if bday is None else 'Hidden' if not await cyber.privacyVisibilityChecker(self.target, 'birthdayModule', 'birthdayDay') else f'{bday:%a %b %d}\n(<t:{round(bday.timestamp())}:R>)')
        embed.add_field(name='Age', value='Not configured' if age is None else 'Hidden' if not await cyber.privacyVisibilityChecker(self.target, 'birthdayModule', 'birthdayDay') else age)
        return embed

    class OverviewButton(discord.ui.Button):
        def __init__(self, birthdays: Birthdays):
            super().__init__(label='Enter action view', emoji=birthdays.emojis['details'])
        async def callback(self, interaction: discord.Interaction):
            view: GuestBirthdayView = self.view
            homeView = BirthdayHomepageView(view.birthdays, view.ctx, None)
            embed = await homeView.createEmbed()
            await interaction.message.edit(embed=embed, view=None)
            homeView.message = interaction.message
            embed = await homeView.finishEmbed(embed)
            await interaction.message.edit(embed=embed, view=homeView)

    class MessageButton(discord.ui.Button):
        def __init__(self, birthdays: Birthdays):
            super().__init__(label='Write birthday message', emoji='✉')
            self.birthdays = birthdays
        async def callback(self, interaction: discord.Interaction):
            view: GuestBirthdayView = self.view
            if interaction.user == view.target: await interaction.response.send_message('You can\'t write a birthday message to yourself!', ephemeral=True)
            else:
                newView = ComposeMessageView(self.birthdays, view.target, view.ctx.author, interaction.message, view)
                embed = await newView.createEmbed()
                await interaction.response.edit_message(embed=embed, view=newView)
                await newView.writeMessagePrompt()

class AgeView(discord.ui.View):
    def __init__(self, birthdays: Birthdays, author: discord.User, originalMessage: discord.Message, message: discord.Message, previousView: BirthdayHomepageView, newAge: int = None):
        super().__init__()
        self.birthdays = birthdays
        self.author = author
        self.originalMessage = originalMessage
        self.message = message #Current message; obtain from an interaction
        self.previousView = previousView
        self.newAge = newAge
        self.usedPrivateInterface = False
        self.finishedSetup = False
        self.autoDetected = False
        if self.newAge: # Assume we're coming from message autocomplete
            if 13 <= self.newAge <= 105:
                self.remove_item(self.children[1]) #Private interface button
                self.children[1].disabled = False #Enable the confirm button
            self.autoDetected = True
        asyncio.create_task(self.confirmation())

    async def createEmbed(self):
        cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
        self.ageHidden = self.originalMessage.guild and not await cyber.privacyVisibilityChecker(self.author, 'birthdayModule', 'age')
        self.currentAge = (await utility.get_user(self.author)).get('age')
        ageModuleDescription = 'Entering your age is a fun but optional feature of the birthday module and has no relation to Discord Inc. It will only be used to personalize the message DMd to you on your birthday. If you set your age, others can view it on your birthday profile by default. If you wish to set your age but don\'t want others to view it, [update your privacy settings](http://disguard.herokuapp.com/manage/profile).\n\n'
        instructions = 'Since your age visibility is set to private, use the virtual keyboard (edit privately button) to enter your age' if self.ageHidden else 'Type your desired age' if not self.newAge else f'{self.author.name} | Update your age to **{self.newAge}**?' if 13 <= self.newAge <= 105 else f'⚠ | **{self.newAge}** falls outside the age range of 13 to 105, inclusive. Please type a new age.'
        embed=discord.Embed(title='🕯 Birthday age setup', description=f'{ageModuleDescription if not self.currentAge else ""}{instructions}\n\nCurrent value: {"🔒 Hidden" if self.ageHidden else self.currentAge}', color=yellow[await utility.color_theme(self.originalMessage.guild)], timestamp=datetime.datetime.utcnow())
        embed.set_author(name=self.author.name, icon_url=self.author.avatar.url)
        self.embed = embed
        return embed
    
    @discord.ui.button(label='Cancel', emoji='✖', style=discord.ButtonStyle.red, custom_id='cancelSetup')
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.message.delete()
        if not self.previousView: return
        self.previousView.ageButton.disabled = False
        await self.originalMessage.edit(view=self.previousView)
        self.finishedSetup = True

    @discord.ui.button(label='Edit privately', emoji='⌨')
    async def privateInterface(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.usedPrivateInterface = True
        for child in self.children: child.disabled = True #Disable all buttons for proper control flow
        await interaction.message.edit(view=self)
        embed = discord.Embed(title='Birthday age setup', description='Use the virtual keyboard to enter your desired age. Note that Disguard is unable to delete this message when you\'re done.')
        kb = NumberInputInterface(self.submitValue)
        await interaction.response.send_message(embed=embed, view=kb, ephemeral=True)
        def iCheck(i: discord.Interaction): return i.data['custom_id'] in ('submit', 'cancel') and i.user == self.author and i.message.id == self.message.id
        result: discord.Interaction = await self.birthdays.bot.wait_for('interaction', check=iCheck)
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
            def messageCheck(m: discord.Message): return m.author == self.author and m.channel == self.message.channel
            def interactionCheck(i: discord.Interaction): #TODO: needs more verification
                if i.data['custom_id'] == 'cancel': self.usedPrivateInterface = False
                return i.data['custom_id'] in ('submit', 'cancel', 'confirmSetup', 'cancelSetup') and i.user == self.author and i.message.id == self.message.id
            try: self.ageHidden
            except AttributeError:
                cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
                self.ageHidden = self.originalMessage.guild and not await cyber.privacyVisibilityChecker(self.author, 'birthdayModule', 'age')
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
                if self.newAge < 13 or self.newAge > 110:
                    self.embed.description=f'⚠ | **{self.newAge}** falls outside the valid age range of 13 to 110, inclusive. Please type another age.'
                if self.newAge != self.currentAge:
                    self.embed.description=f'{"Update" if self.currentAge else "Set"} your age to **{"the input from the virtual keyboard" if self.usedPrivateInterface else self.newAge}**?\n\nYou may also type another age'
                    for child in self.children: child.disabled = False
                else:
                    self.embed.description=f'Your age is already set to **{"the value you entered" if self.usedPrivateInterface else self.newAge}** 👍\n\nYou may type another age or cancel setup'
                    for child in self.children[:2]: child.disabled = False
            else: self.embed.description=f'{self.birthdays.emojis["alert"]} | **{"the value you entered" if self.usedPrivateInterface else self.newAge}** isn\'t an age. You may type a new age or cancel the setup.'
            try: 
                if self.message: await self.message.edit(embed=self.embed, view=self)
                elif self.autoDetected: break
            except discord.errors.NotFound: break
    
    async def saveChanges(self):
        #TODO: add age verification
        if self.newAge == self.currentAge: return await self.message.delete()
        await database.SetAge(self.author, self.newAge)
        if not self.usedPrivateInterface:
            self.embed.description = f'✔ | Age successfully updated to {"<Value hidden>" if self.usedPrivateInterface else self.newAge}'
            if not (await utility.get_user(self.author)).get('birthday'):
                self.embed.description += '\n\nYou may add your birthday from the menu on the original embed if desired'
            await self.message.edit(embed=self.embed, view=SuccessAndDeleteView(), delete_after=30)
        else: await self.message.delete()
        if not self.autoDetected:
            self.originalMessage.embeds[0].set_field_at(1, name='Your Age',value=f'**Age Successfully Updated**\n{"🔒 Hidden" if self.usedPrivateInterface else self.newAge}')
            await self.originalMessage.edit(embed=self.originalMessage.embeds[0])

    async def submitValue(self, result):
        '''Writes the value from the KB interface to the class variable'''
        self.newAge = int(result)       

class BirthdayView(discord.ui.View):
    '''The interface for setting one's birthday'''
    #Almost a carbon copy from AgeView
    def __init__(self, birthdays: Birthdays, author: discord.User, originalMessage: discord.Message, message: discord.Message, previousView: BirthdayHomepageView, newBday: datetime.datetime = None):
        super().__init__()
        self.birthdays = birthdays
        self.author = author
        self.originalMessage = originalMessage
        self.message = message
        self.previousView = previousView
        self.newBday = newBday
        self.usedPrivateInterface = False
        self.finishedSetup = False
        self.autoDetected = False
        if self.newBday: # Assume we're coming from message autocomplete
            self.remove_item(self.children[1]) #Private interface button
            self.children[1].disabled = False #Enable the confirm button
            self.autoDetected = True
        asyncio.create_task(self.confirmation())

    async def createEmbed(self):
        cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
        self.bdayHidden = self.originalMessage.guild and not await cyber.privacyVisibilityChecker(self.author, 'birthdayModule', 'birthdayDay')
        self.currentBday = (await utility.get_user(self.author)).get('birthday')
        birthdayModuleDescription = 'The Disguard birthday module provides fun, voluntary features for those wanting to use it. Setting your birthday will allow Disguard to make an announcement on your birthday in servers with this feature enabled, and Disguard will DM you a message on your birthday. By default, others can view your birthday on your profile. If you wish to change this, [update your privacy settings](http://disguard.herokuapp.com/manage/profile).\n\n'
        instructions = 'Since your birthday visibility is set to private, please use the virtual keyboard (edit privately button) to enter your birthday' if self.bdayHidden else 'Type your birthday or use the virtual keyboard for your input. Disguard does not process your birth year, so just enter a month and a day.' if not self.newBday else f'{self.author.name} | Update your birthday to **{self.newBday}**?'
        acceptableFormats = 'Inputs are not case sensitive. Examples of acceptable birthday formats:\nFebruary 28\nFeb 28\nFeb 28th\n2/28\n2-28\n02 28\nin two weeks\nin 5 days\nnext monday\ntomorrow'
        embed=discord.Embed(title='📆 Birthday date setup', description=f'{birthdayModuleDescription if not self.currentBday else ""}{instructions}{f"{newline}{newline}{acceptableFormats}" if not self.newBday else ""}\n\nCurrent value:  {"🔒 Hidden" if self.bdayHidden else self.currentBday.strftime("%B %d")}', color=yellow[await utility.color_theme(self.originalMessage.guild)], timestamp=datetime.datetime.utcnow())
        embed.set_author(name=self.author.name, icon_url=self.author.avatar.url)
        self.embed = embed
        return embed
    
    @discord.ui.button(label='Cancel', emoji='✖', style=discord.ButtonStyle.red, custom_id='cancelSetup')
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.message.delete()
        if not self.previousView: return
        self.previousView.birthdayButton.disabled = False
        await self.originalMessage.edit(view=self.previousView)
        self.finishedSetup = True

    @discord.ui.button(label='Edit privately', emoji='⌨')
    async def privateInterface(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.usedPrivateInterface = True
        for child in self.children: child.disabled = True #Disable all buttons for proper control flow
        await interaction.message.edit(view=self)
        embed = discord.Embed(title='Birthday date setup', description='Use the virtual keyboard to enter your birthday. Note that Disguard is unable to delete this message when you\'re done.')
        kb = DateInputInterface(self.birthdays.bot, self.message, self.author, self.submitValue)
        await interaction.response.send_message(embed=embed, view=kb, ephemeral=True)
        def iCheck(i: discord.Interaction): return i.data['custom_id'] in ('submit', 'cancel') and i.user == self.author and i.message.id == self.message.id
        result: discord.Interaction = await self.birthdays.bot.wait_for('interaction', check=iCheck)
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
            def messageCheck(m: discord.Message): return m.author == self.author and m.channel == self.message.channel
            def interactionCheck(i: discord.Interaction): #TODO: needs more verification
                if i.data['custom_id'] == 'cancel': self.usedPrivateInterface = False
                return i.data['custom_id'] in ('submit', 'cancel', 'confirmSetup', 'cancelSetup') and i.user == self.author and i.message.id == self.message.id
            try: self.ageHidden
            except AttributeError:
                cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
                self.bdayHidden = self.originalMessage.guild and not await cyber.privacyVisibilityChecker(self.author, 'birthdayModule', 'birthdayDay')
            if not self.usedPrivateInterface and not self.bdayHidden and not self.newBday:
                done, pending = await asyncio.wait([self.birthdays.bot.wait_for('message', check=messageCheck, timeout=300), self.birthdays.bot.wait_for('interaction', check=interactionCheck)], return_when=asyncio.FIRST_COMPLETED)
                try: result = done.pop().result()
                except asyncio.TimeoutError: 
                    try: await self.message.delete()
                    except: pass
                    break #Close the loop if we time out
                for f in pending: f.cancel()
                if type(result) is discord.Interaction and result.data['custom_id'] in ('confirmSetup', 'cancelSetup'): break #If the user cancels or finishes setup, close the loop
                if not self.usedPrivateInterface:
                    adjusted = datetime.datetime.utcnow() + datetime.timedelta(hours=(await utility.get_server(self.message.guild)).get('offset', -5))
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
            try:
                if self.message: await self.message.edit(embed=self.embed, view=self)
                elif self.autoDetected: break
            except discord.errors.NotFound: break
    
    async def saveChanges(self):
        if self.newBday == self.currentBday: return await self.message.delete()
        await database.SetBirthday(self.author, self.newBday)
        if not self.usedPrivateInterface:
            self.embed.description = f'✔ | Birthday successfully updated to {"<Value hidden>" if self.usedPrivateInterface else self.newBday.strftime("%B %d")}'
            bdayAnnounceChannel = (await utility.get_server(self.message.guild)).get('birthday', 0)
            if bdayAnnounceChannel > 0: bdayAnnounceText = f'Since birthday announcements are enabled for this server, your birthday will be announced to {self.birthdays.bot.get_channel(bdayAnnounceChannel).mention}.'
            else: bdayAnnounceText = f'Birthday announcements are not enabled for this server. Moderators may enable this feature [here](http://disguard.herokuapp.com/manage/{self.message.guild.id}/server).'
            self.embed.description += f'\n\n{bdayAnnounceText}'
            if not (await utility.get_user(self.author)).get('age'):
                self.embed.description += '\n\nYou may add your age from the menu on the original embed if desired'
            await self.message.edit(embed=self.embed, view=SuccessAndDeleteView(), delete_after=30)
        else: await self.message.delete()
        if not self.autoDetected:
            self.originalMessage.embeds[0].set_field_at(1, name='Your Birthday',value=f'**Birthday Successfully Updated**\n{"🔒 Hidden" if self.usedPrivateInterface else self.newBday.strftime("%B %d")}')
            await self.originalMessage.edit(embed=self.originalMessage.embeds[0])

    async def submitValue(self, result):
        '''Writes the value from the KB interface to the class variable'''
        self.newBday = result

class WishlistView(discord.ui.View):
    def __init__(self, birthdays: Birthdays, ctx: commands.Context, originalMessage: discord.Message, message: discord.Message, previousView: BirthdayHomepageView, cameFromSaved = []):
        super().__init__()
        self.birthdays = birthdays
        self.ctx = ctx
        self.originalMessage = originalMessage
        self.message = message
        self.new = None
        self.cameFromSaved = cameFromSaved
        self.wishlist = []
        self.previousView = previousView
        self.wishlistHidden = False
        self.add_item(self.addButton(self.birthdays))
        self.add_item(self.removeButton(self.birthdays))

    async def createEmbed(self):
        cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
        self.wishlistHidden = self.ctx.guild and not await cyber.privacyVisibilityChecker(self.ctx.author, 'birthdayModule', 'wishlist')
        self.wishlist = (await utility.get_user(self.ctx.author)).get('wishlist', []) if not self.wishlistHidden and not self.cameFromSaved else self.cameFromSaved if self.cameFromSaved else []
        wishlistDisplay = ['You have set your wishlist to private'] if self.wishlistHidden else self.wishlist
        embed=discord.Embed(title=f'📝 Wishlist home', description=f'**{"YOUR WISH LIST":–^70}**\n{newline.join([f"• {w}" for w in wishlistDisplay]) if wishlistDisplay else "Empty"}', color=yellow[await utility.color_theme(self.ctx.guild)])
        embed.set_author(name=self.ctx.author.name, icon_url=self.ctx.author.avatar.url)
        if self.cameFromSaved: embed.set_footer(text='Wishlist changes successfully saved')
        return embed
    
    @discord.ui.button(label='Close Viewer', style=discord.ButtonStyle.red)
    async def close(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.message.delete()
        if not self.previousView: return
        self.previousView.wishlistButton.disabled = False
        await self.originalMessage.edit(view=self.previousView)

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
        if self.wishlistHidden and self.ctx.guild:
            return await interaction.response.send_message('Editing your wishlist in a server is disabled since your wishlist visibility is set to private. You may retry from DMs or review your settings: http://disguard.herokuapp.com/manage/profile', ephemeral=True)
        verb, preposition = 'remove', 'from'
        if add: 
            verb, preposition = 'add', 'to'
        self.new = interaction.message
        embed = self.new.embeds[0]
        embed.title = f'📝{self.birthdays.emojis["whitePlus"] if add else self.birthdays.emojis["whiteMinus"]} {verb[0].upper()}{verb[1:]} entries {preposition} wishlist'
        embed.description = f'Type{" the number or text of an entry" if not add else ""} to {verb} {"entries" if add else "it"} {preposition} your wish list. To {verb} multiple entries in one message, separate entries with a comma and a space.\n**{"WISHLIST":–^70}**\n{"(Empty)" if not self.wishlist else newline.join([f"• {w}" for w in self.wishlist]) if add else newline.join([f"{i}) {w}" for i, w in enumerate(self.wishlist, 1)])}'
        await interaction.message.edit(embed=embed, view=WishlistEditView(self.birthdays, self.ctx, self.originalMessage, self.new, self.previousView, add, self.wishlist))

class WishlistEditView(discord.ui.View):
    def __init__(self, birthdays: Birthdays, ctx: commands.Context, originalMessage: discord.Message, message: discord.Message, previousView: BirthdayHomepageView, add=True, wishlist: typing.List[str]=[]):
        super().__init__()
        self.birthdays = birthdays
        self.ctx = ctx
        self.originalMessage = originalMessage
        self.message = message
        self.previousView = previousView
        self.add = add
        self.wishlist = wishlist
        self.tempWishlist = wishlist or []
        self.toModify = {} #First 16 chars of entries must be unique due to being used as dict keys. Tracks changes in progress
        self.buttonClear = self.clearButton(self, self.birthdays)
        self.buttonSave = self.saveButton()
        self.add_item(self.buttonClear)
        self.add_item(self.buttonSave)
        asyncio.create_task(self.editWishlist())

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red, emoji='✖')
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.tempWishlist = self.wishlist or []
        view = WishlistView(self.birthdays, self.ctx, self.originalMessage, None, self.previousView)
        embed = await view.createEmbed()
        await self.message.edit(embed=embed, view=view)

    class clearButton(discord.ui.Button):
        def __init__(self, view, birthdays: Birthdays):
            super().__init__(label='Clear entries', style=discord.ButtonStyle.gray, emoji = birthdays.emojis['delete'])
            view: WishlistEditView = view
            if not view.tempWishlist: self.disabled = True
        
        async def callback(self, interaction: discord.Interaction):
            view: WishlistEditView = self.view
            view.tempWishlist = []
            await view.refreshDisplay()
            self.disabled = True

    class saveButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Save', style=discord.ButtonStyle.green, emoji = '✅')
        
        async def callback(self, interaction: discord.Interaction):
            view: WishlistEditView = self.view
            if not view.add: self.tempWishlist = [w for w in self.tempWishlist if not view.toModify.get(w[:16])]
            view.wishlist = view.tempWishlist #Should handle local state
            await database.SetWishlist(view.ctx.author, view.wishlist) #And this will wrap up global state
            newView = WishlistView(view.birthdays, view.ctx, view.originalMessage, None, view.previousView, view.wishlist)
            embed = await newView.createEmbed()
            await view.message.edit(embed=embed, view=newView)

    async def regenEmbed(self):
        return discord.Embed('📝 Edit Wishlist', description=f'**{"YOUR WISH LIST":–^70}**\n{newline.join([f"• {w}" for w in self.wishlist]) if self.wishlist else "Empty"}', color=yellow[await utility.color_theme(self.ctx.guild)])

    async def editWishlist(self):
        def addCheck(m: discord.Message): return m.author == self.ctx.author and m.channel == self.ctx.channel
        while not self.birthdays.bot.is_closed():
            try: message: discord.Message = await self.birthdays.bot.wait_for('message', check=addCheck, timeout=300)
            except asyncio.TimeoutError: 
                view = WishlistView(self.birthdays, self.ctx, self.originalMessage, None, self.previousView)
                embed = await view.createEmbed()
                return await self.message.edit(embed=embed, view=view)
            if message.content:
                words = message.content.split(', ') #O(n)
                if self.add: 
                    for word in words: self.toModify[word[:16]] = word #O(n)
                    self.tempWishlist += words #O(k)
                else:
                    for word in words:
                        try:
                            number = int(word)
                            reference = self.tempWishlist[number - 1]
                            self.toModify[reference[:16]] = reference
                        except ValueError: self.toModify[word[:16]] = word
            try:
                cyber: Cyberlog.Cyberlog = self.birthdays.bot.get_cog('Cyberlog')
                cyber.AvoidDeletionLogging(message)
                await message.delete()
            except discord.Forbidden: pass
            await self.refreshDisplay()

    async def refreshDisplay(self):
        def formatWishlistEntry(s: str): return f'**+ {s}**' if self.add and self.toModify.get(s[:16]) else f'~~{s}~~' if not self.add and self.toModify.get(s[:16]) else f'• {s}' if self.add else s
        verb, preposition = 'remove', 'from'
        preposition = 'from'
        if self.add:
            verb, preposition = 'add', 'to'
        self.message.embeds[0].description = f'Type{" the number or text of an entry" if not self.add else ""} to {verb} {"entries" if self.add else "it"} {preposition} your wish list. To {verb} multiple entries in one message, separate entries with a comma and a space.\n\n**{"WISHLIST":–^70}**\n{"(Empty)" if not self.tempWishlist else newline.join([formatWishlistEntry(w) for w in self.tempWishlist]) if self.add else newline.join([f"{i}) {formatWishlistEntry(w)}" for i, w in enumerate(self.tempWishlist, 1)])}'
        #Now set the clear button
        if self.tempWishlist and not (all([w == self.toModify[w[:16]] for w in self.tempWishlist]) and not self.add): self.buttonClear.disabled = False
        else: self.buttonClear.disabled = True
        await self.message.edit(embed=self.message.embeds[0], view=self)

class UpcomingBirthdaysView(discord.ui.View):
    def __init__(self, birthdays: Birthdays, message: discord.Message, ctx: commands.Context, currentServer, disguardSuggest, weekBirthday, namesOnly, embed: discord.Embed, bot: commands.Bot, jumpStart=0):
        super().__init__()
        self.birthdays = birthdays
        self.message = message
        self.ctx = ctx
        self.author = self.ctx.author
        self.currentServer = list(self.paginate(currentServer))
        self.disguardSuggest = list(self.paginate(disguardSuggest))
        self.weekBirthday = list(self.paginate(weekBirthday))
        self.bot = bot
        self.birthdays = birthdays
        self.namesOnly = namesOnly
        self.embed = embed
        self.currentView = (self.currentServer[0][:8] if self.currentServer else []) + (self.disguardSuggest[0][:8] if self.disguardSuggest else []) + (self.weekBirthday[0][:8] if self.weekBirthday else [])
        self.currentPage = 0
        self.finalPage = 0
        self.buttonCurrentServer = self.currentServerButton()
        self.buttonDisguardSuggest = self.disguardSuggestButton()
        self.buttonWeekBirthday = self.weekBirthdayButton()
        self.buttonWriteMessage = self.writeMessageButton()
        self.buttonBack = self.backButton()
        self.buttonPrev = self.prevPage()
        self.buttonNext = self.nextPage()
        self.buttonSearch = self.searchMembersButton()
        self.memberDropdown = self.selectMemberDropdown()
        self.add_item(self.buttonBack)
        self.add_item(self.buttonCurrentServer)
        self.add_item(self.buttonDisguardSuggest)
        self.add_item(self.buttonWeekBirthday)
        self.add_item(self.buttonWriteMessage)
        #if jumpStart == 1: asyncio.create_task(self.writeMessagePrompt(self.author))

    async def createEmbed(self):
        homeView = BirthdayHomepageView(self.birthdays, self.ctx, self.message)
        embed = await homeView.createEmbed()
        embed = await homeView.finishEmbed(embed)
        embed.clear_fields()
        embed.description = f'''Click a button to expand that section**\n{"UPCOMING BIRTHDAYS":-^70}**\n__THIS SERVER__\n{newline.join(self.fillBirthdayList(self.currentServer, entries = 8))}\n\n__DISGUARD SUGGESTIONS__\n{newline.join(self.fillBirthdayList(self.disguardSuggest, entries = 8))}\n\n__WITHIN A WEEK__\n{newline.join(self.fillBirthdayList(self.weekBirthday, entries = 8))}'''
        self.embed = embed
        return embed

    def fillBirthdayList(self, list, page = 0, entries = 25):
        return [f"{qlfc}\\▪️ **{m['data'].name if self.namesOnly.count(m['data'].name) == 1 else m['data']}** • {m['bday']:%a %b %d} • <t:{round(m['bday'].timestamp())}:R>" for m in (list[page][:entries] if list else [])]

    def paginate(self, data):
        for i in range(0, len(data), 25): yield data[i:i+25] #25 entries per page

    async def loadHomepage(self):
        self.clear_items()
        self.add_item(self.buttonBack)
        self.add_item(self.buttonCurrentServer)
        self.add_item(self.buttonDisguardSuggest)
        self.add_item(self.buttonWeekBirthday)
        self.add_item(self.buttonWriteMessage)
        self.embed.description = f'''Click a button to expand that section**\n{"UPCOMING BIRTHDAYS":-^70}**\n__THIS SERVER__\n{newline.join(self.fillBirthdayList(self.currentServer, entries=8))}\n\n__DISGUARD SUGGESTIONS__\n{newline.join(self.fillBirthdayList(self.disguardSuggest, entries=8))}\n\n__WITHIN A WEEK__\n{newline.join(self.fillBirthdayList(self.weekBirthday, entries=8))}'''
        await self.message.edit(embed=self.embed, view=self)
    
    class backButton(discord.ui.Button):
        def __init__(self):
            super().__init__(emoji='⬅', label='Back', style=discord.ButtonStyle.red)
            self.code = 0 #determines callback action
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            if self.code == 0:
                homeView = BirthdayHomepageView(view.birthdays, view.ctx, view.message)
                embed = await homeView.createEmbed()
                await interaction.message.edit(embed=embed, view=None)
                homeView.message = interaction.message
                embed = await homeView.finishEmbed(embed)
                await interaction.response.edit_message(embed=embed, view=homeView)
            if self.code == 1:
                view.buttonBack.code = 1
                await view.loadHomepage()
    
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
            view.buttonBack.code = 1
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
            view.buttonBack.code = 1
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
            view.buttonBack.code = 1
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
            self.userDict: typing.Dict[int, discord.User] = {}
            for d in population:
                u: discord.User = d['data']
                b: datetime.datetime = d['bday']
                self.add_option(label=u.name[:100], value=u.id, description=f'{b.strftime("%B %d") if b else "⚠ No birthday set"}')
                self.userDict[u.id] = u
        async def callback(self, interaction: discord.Interaction):
            view: UpcomingBirthdaysView = self.view
            newView = ComposeMessageView(view.birthdays, self.userDict[int(self.values[0])], view.author, view.message, view)
            embed = await newView.createEmbed()
            await interaction.response.edit_message(embed=embed, view=newView)
            await newView.writeMessagePrompt()

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
            async def getBirthday(u: discord.User): return (await utility.get_user(u)).get('birthday')
            await interaction.response.edit_message(content=None, embed=view.embed, view=view)
            while not view.bot.is_closed():
                done, pending = await asyncio.wait([view.bot.wait_for('message', check=messageCheck, timeout=300), view.bot.wait_for('interaction', check=selectCheck, timeout=300)], return_when=asyncio.FIRST_COMPLETED)
                try: result = done.pop().result()
                except asyncio.TimeoutError: await view.loadHomepage()
                for f in pending: f.cancel()
                if type(result) is discord.Interaction: break
                result: discord.Message = result
                cyber: Cyberlog.Cyberlog = view.bot.get_cog('Cyberlog')
                results = await utility.FindMoreMembers(view.bot.users, result.content)
                try:
                    cyber.AvoidDeletionLogging(result)
                    await result.delete()
                except (discord.Forbidden, discord.HTTPException): pass
                users = [r['member'] for r in results if all((
                    await cyber.privacyEnabledChecker(r['member'], 'default', 'birthdayModule'),
                    await cyber.privacyEnabledChecker(r['member'], 'default', 'birthdayModule'),
                    await cyber.privacyEnabledChecker(r['member'], 'birthdayModule', 'birthdayDay'),
                    await cyber.privacyVisibilityChecker(r['member'], 'birthdayModule', 'birthdayDay')
                ))] #filter out members who have designated not wanting to participate in the birthday module
                listToPass = [{'data': u, 'bday': await getBirthday(u)} for u in users]
                select.updatePopulation(listToPass, str(view.message.id))
                if len(view.children) == 1: view.add_item(select)
                await view.message.edit(view=view)
        
class ComposeMessageView(discord.ui.View):
    def __init__(self, birthdays: Birthdays, target: discord.User, author: discord.User, message: discord.Message, previousView: discord.ui.View):
        super().__init__()
        self.birthdays = birthdays
        self.target = target
        self.msgInABottle = None
        self.author = author
        self.message = message
        self.stage: int = 0
        self.buttonBack = self.backButton()
        self.buttonDM = self.switchToDMsButton(self.target)
        self.previousView = previousView
        self.add_item(self.buttonBack)

    class backButton(discord.ui.Button):
        def __init__(self):
            super().__init__(emoji='⬅', label='Back', style=discord.ButtonStyle.red)
        async def callback(self, interaction: discord.Interaction):
            view: ComposeMessageView = self.view
            if type(view.previousView) is GuestBirthdayView and view.stage == 0:
                embed = await view.previousView.createEmbed()
                return await interaction.response.edit_message(embed=embed, view=view.previousView)
            prev: UpcomingBirthdaysView = view.previousView
            if view.stage == 0:
                prev.message = interaction.message
                await prev.createEmbed()
                await prev.loadHomepage()
            elif view.stage == 1:
                view.stage -= 1
                view.clear_items()
                view.buttonBack = self
                view.add_item(view.buttonBack)
                embed = await view.createEmbed()
                await interaction.message.edit(embed=embed, view=view)
                await view.writeMessagePrompt()
            else:
                view.stage -= 1
                view.clear_items()
                view.add_item(view.buttonBack)
                await view.selectDestinationsPrompt()

    class switchToDMsButton(discord.ui.Button):
        def __init__(self, target: discord.User):
            super().__init__(label='Switch to DMs', style=discord.ButtonStyle.blurple)
            self.target = target
        async def callback(self, interaction: discord.Interaction):
            view: ComposeMessageView = self.view
            prev: UpcomingBirthdaysView = view.previousView
            # DM the user
            message = await view.author.send(embed=view.embed, view=view)
            # Set the previous view's message to the current message for control flow
            prev.message = message #ok but why
            # Prepare a button allowing the user to jump the message that was just DMd to them
            view.clear_items()
            view.add_item(discord.ui.Button(style=discord.ButtonStyle.blurple, label='Jump to message', url=message.jump_url))
            await interaction.response.edit_message(view=view)
            # Continue setting up the DM space
            view.message = message
            embed = await view.createEmbed()
            view.clear_items()
            view.add_item(view.buttonBack)
            await view.message.edit(embed=embed, view=view)
            await view.writeMessagePrompt()
    
    async def createEmbed(self):
        if self.message.guild:
            intro = 'Until [input forms](https://cdn.discordapp.com/attachments/697138785317814292/940761395883024424/c896cb74-1206-4632-bcb4-99eccf1c0356.png) are fully implmented, this process will take place in DMs. Make sure your DMs are open, then press the button below this embed.'
            self.add_item(self.buttonDM)
        else:
            user_data = await utility.get_user(self.target)
            intro = f'Type your message for {self.target.name}. Note that you cannot send server invites or hyperlinks in birthday messages.'
            existingMessages = user_data.get('birthdayMessages')
            filtered = [m for m in existingMessages if self.target.id == m['author']]
            if filtered:
                intro += f'\n\nℹ | You already have {len(filtered)} messages queued for {self.target.name}. If you wish to add another, you may continue by sending your desired message.'
            if not user_data.get('birthday'): intro += f'\n\nℹ | {self.target.name} hasn\'t set their birthday yet. You may still write a message, but it will only be delivered if they set their birthday.'
        self.embed = discord.Embed(title=f'Compose birthday message for {self.target.name}', description=intro)
        return self.embed

    async def writeMessagePrompt(self):
        if type(self.message.channel) is not discord.DMChannel: return #ensures we only proceed if in DMs
        def messageCheck(m: discord.Message): return m.author == self.author and type(m.channel) is not discord.TextChannel
        satisfactoryMessage = False
        self.stage = 0
        while not satisfactoryMessage:
            try: self.msgInBottle: discord.Message = await self.birthdays.bot.wait_for('message', check=messageCheck, timeout=300)
            except asyncio.TimeoutError:
                prev: UpcomingBirthdaysView = self.previousView
                await prev.createEmbed()
                return await prev.loadHomepage()
            satisfactoryMessage = not re.search('.*discord.gg/.*', self.msgInBottle.content) and not re.search('.*htt(p|ps)://.*', self.msgInBottle.content) and len(self.msgInBottle.content) < 1024
            if not satisfactoryMessage:
                self.embed.description += f'\n\n⚠ | Your message contains hyperlinks, server invites, or is too long (the message must be < 1024 characters). Please try again.'
                await self.message.channel.send(embed=self.embed)
        await self.selectDestinationsPrompt()
        
    async def selectDestinationsPrompt(self):
        self.stage = 1
        self.embed.description = 'Select the destinations you want your message to be delivered to. Messages won\'t be delivered to channels with birthday announcements off unless they\'re turned on in the meantime.'
        mutualServers = mutualServersMemberToMember(self.birthdays.bot.get_cog('Birthdays'), self.birthdays.bot.user, self.target)
        dropdown = discord.ui.Select(min_values=1, placeholder='Select destination channels')
        dmChannel = self.target.dm_channel
        if not self.target.dm_channel:
            try:
                await self.target.create_dm()
                dmChannel = self.target.dm_channel
            except: dmChannel = None
        dropdown.add_option(label=f'{self.target.name}\'s DMs', value=self.target.dm_channel.id, description='Recommended' if dmChannel else 'Unable to DM')
        for server in mutualServers:
            birthdayChannel = server.get_channel((await utility.get_server(server)).get('birthday'))
            dropdown.add_option(label=server.name, value=server.id, description=f'#{birthdayChannel.name}' if birthdayChannel else 'No announcement channel configured')
        dropdown.max_values = len(mutualServers) + 1
        next = discord.ui.Button(label='Next', style=discord.ButtonStyle.green, custom_id='next')
        self.add_item(dropdown)
        self.add_item(next)
        await self.message.channel.send(embed=self.embed, view=self)
        def interactionCheck(i: discord.Interaction):
            return i.data['custom_id'] == 'next' and i.user == self.author and type(i.channel) is not discord.TextChannel
        try: await self.birthdays.bot.wait_for('interaction', check=interactionCheck, timeout=300)
        except asyncio.TimeoutError:
            prev: UpcomingBirthdaysView = self.previousView
            await prev.createEmbed()
            return await prev.loadHomepage()
        await self.confirmationPrompt(dropdown)
        
    async def confirmationPrompt(self, dropdown: discord.ui.Select):
        self.stage = 2
        birthday = (await utility.get_user(self.target)).get('birthday')
        destinations = [f'• {self.birthdays.bot.get_channel(int(dropdown.values[0]))}'] + [f'• {self.birthdays.bot.get_guild(int(v))}' for v in (dropdown.values[1:] if len(dropdown.values) > 1 else [])]
        serverDestinations = [self.birthdays.bot.get_guild(int(v)) for v in dropdown.values[1:]]
        self.embed.description = f'Your message to {self.target.name} says `{self.msgInBottle.content}`. It will be delivered on their birthday ({birthday:%B %d}) to the following destinations:\n{newline.join(destinations)}\n\nBy composing this message, you affirm the message conforms with Discord\'s [community guidelines](https://discord.com/guidelines).'
        self.embed.description+= f'If this message is not appropriate for Discord, the recipient(s) may flag it for further action by server moderators or the developer of Disguard.\n\nIf this all looks good, press the green button.'
        self.clear_items()
        self.add_item(self.buttonBack)
        self.add_item(discord.ui.Button(label='Restart', custom_id='restart'))
        self.add_item(discord.ui.Button(label='Looks good', custom_id='confirm', style=discord.ButtonStyle.green))
        msg = await self.message.channel.send(embed=self.embed, view=self)
        def finalCheck(i: discord.Interaction): return i.data['custom_id'] in ('restart', 'confirm') and i.user == self.author and type(i.channel) is not discord.TextChannel
        try: result: discord.Interaction = await self.birthdays.bot.wait_for('interaction', check=finalCheck, timeout=300)
        except asyncio.TimeoutError:
            prev: UpcomingBirthdaysView = self.previousView
            await prev.createEmbed()
            return await prev.loadHomepage()
        if result.data['custom_id'] == 'restart':
            self.clear_items()
            self.add_item(self.buttonBack)
            self.message = msg
            embed = await self.createEmbed()
            await msg.edit(embed=embed, view=self)
            return await self.writeMessagePrompt()
        await database.SetBirthdayMessage(self.target, self.msgInBottle, self.author, serverDestinations) #TODO: figure out how this relates to members receiving DMs, maybe enable by default and the dropdown can be to select additional servers
        await self.message.channel.send(f'Successfully queued the message for {self.target.name}')

class AgeSelectView(discord.ui.View):
    def __init__(self, ages):
        super().__init__()
        self.select = self.Dropdown(ages)
        self.add_item(self.select)
    
    class Dropdown(discord.ui.Select):
        def __init__(self, ages):
            super().__init__()
            for age in ages: self.add_option(label=age)

class BirthdayActionView(discord.ui.View):
    def __init__(self, entries):
        super().__init__()
        self.select = self.Dropdown(entries)
        self.add_item(self.select)
    
    class Dropdown(discord.ui.Select):
        def __init__(self, entries):
            super().__init__()
            for i, entry in enumerate(entries): self.add_option(label=entry, value=i)
