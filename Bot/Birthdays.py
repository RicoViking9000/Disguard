'''Contains all code relating to the birthday management feature of Disguard'''
import discord
from discord.ext import commands, tasks
import traceback
import datetime
import database
import asyncio
import collections


yellow=0xffff00
green=0x008000
red=0xff0000
blue=0x0000FF
loading = None

class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.configureDailyBirthdayAnnouncements.start()
        self.configureServerBirthdayAnnouncements.start()
    
    def cog_unload(self):
        self.configureDailyBirthdayAnnouncements.cancel()
        self.configureServerBirthdayAnnouncements.cancel()

    @tasks.loop(hours=24)
    async def dailyBirthdayAnnouncements(self):
        try:
            for member in self.bot.get_all_members():
                if await database.GetMemberBirthday(member) is not None:
                    if (await database.GetMemberBirthday(member)).day == datetime.datetime.now().day:
                        age = await database.GetAge(member) + 1
                        await database.SetAge(member, age)
                        messages = await database.GetBirthdayMessages(member)
                        embed=discord.Embed(title='🍰 Happy {}Birthday, {}! 🍰'.format('{}{}'.format(age, '{} '.format(Cyberlog.suffix(age))) if age is not None else '', member.name), timestamp=datetime.datetime.utcnow(), color=yellow)
                        embed.description='You have {} personal messages\n{:-^34s}\n{}'.format(len(messages), 'Messages', '\n'.join(['• {}: {} (sent @ {})'.format(m.get('authName') if self.bot.get_user(m.get('author')) is None else self.bot.get_user(m.get('author')).mention,
                        m.get('message'), 'N/A' if m.get('created') is None else (m.get('created') + datetime.timedelta(hours=await database.GetTimezone(server))).strftime("%b %d, %Y - %I:%M %p")) for m in messages]))
                        try: await member.send(embed=embed)
                        except: pass
                        await database.ResetBirthdayMessages(member)
        except: traceback.print_exc()

    @tasks.loop(minutes=5)
    async def serverBirthdayAnnouncements(self):
        try:
            for server in self.bot.guilds:
                channel = await database.GetBirthday(server)
                if channel > 0:
                    if (datetime.datetime.utcnow() + datetime.timedelta(hours=await database.GetTimezone(server))).strftime('%H:%M') == (await database.GetBirthdate(server)).strftime('%H:%M'):
                        for member in server.members:
                            if await database.GetMemberBirthday(member) is not None:
                                if (await database.GetMemberBirthday(member)).day == (datetime.datetime.utcnow() + datetime.timedelta(hours=await database.GetTimezone(server))).day:
                                    messages = [a for a in await database.GetBirthdayMessages(member) if server.id in a.get('servers')]
                                    toSend = '🍰 Hey hey, it\'s {}\'s birthday! Let\'s all wish them a very special day! 🍰{}'.format(member.mention, '' if len(messages) == 0 else '\nThey also have {} special birthday messages from people in this server!\n\n{}'.format(len(messages),
                                    '\n'.join(['• {}: {}'.format(server.get_member(m.get('author')).name, m.get('message')) for m in messages])))
                                    try: await self.bot.get_channel(channel).send(toSend)
                                    except discord.Forbidden: pass
        except: traceback.print_exc()

    @tasks.loop(minutes=1)
    async def configureDailyBirthdayAnnouncements(self):
        if datetime.datetime.utcnow().strftime('%H:%M') == '12:45': 
            self.dailyBirthdayAnnouncements.start()
            self.configureDailyBirthdayAnnouncements.cancel()

    @tasks.loop(minutes=1)
    async def configureServerBirthdayAnnouncements(self):
        if int(datetime.datetime.utcnow().strftime('%M')) % 5 == 0:
            self.serverBirthdayAnnouncements.start()
            self.configureServerBirthdayAnnouncements.cancel()

    @commands.Cog.listener()
    async def on_message(self, message):
        '''Used for parsing and handling of birthday features
        Birthday processing is done in two phases
        1. Find out of a valid date is in the message
        2. Find out of someone is talking about their own birthday based on context and words in the message'''
        if message.author.bot: return
        if type(message.channel) is discord.DMChannel: return
        if any(word in message.content.lower().split(' ') for word in ['isn', 'not', 'you', 'your']): return #Blacklisted words
        now = datetime.datetime.utcnow()
        adjusted = now + datetime.timedelta(hours=await database.GetTimezone(message.guild))
        shortDays = collections.deque(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])
        longDays = collections.deque(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])
        shortMonths = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        longMonths = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
        ref = collections.deque([(a, b) for a, b in {1:31, 2:29, 3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31}.items()]) #Number of days in each month. As with days, this dict may need to move around
        ref.rotate(-1 * (adjusted.month - 1)) #Current month moves to the front
        #Determine if user specified long or short day/month in response
        if any(c in message.content.lower().split(' ') for c in shortMonths): months = shortMonths
        else: months = longMonths
        if any(c in message.content.lower().split(' ') for c in shortDays): days = shortDays
        else: days = longDays
        #Check if name of month is in message. Before days because some ppl may specify a day and month
        birthday = None
        if any(c in message.content.lower().split(' ') for c in months) or 'the' in message.content.lower().split(' '):
            words = message.content.split(' ')
            for word in words:
                before = word
                #truncate the suffix if the user provided one
                if any(str(letter) in word for letter in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]):
                    word = word.replace('st', '')
                    word = word.replace('nd', '')
                    word = word.replace('rd', '')
                    word = word.replace('th', '')
                if any(c in message.content.lower().split(' ') for c in months):
                    try: 
                        birthday = datetime.datetime(2020, months.index([d for d in months if d in message.content.lower().split(' ')][0]) + 1, int(word))
                        break
                    except: pass
                else:
                    if before != word:
                        try: birthday = datetime.datetime(2020, datetime.datetime.now().month, int(word))
                        except: pass
        #Check if day of the week is in message
        elif any(c in message.content.lower().split(' ') for c in days):
            currentDay = days.index(adjusted.strftime('%a').lower())
            targetDay = days.index([d for d in days if d in message.content.lower()][0])
            days.rotate(-1 * currentDay) #Current day is now at the start for proper calculations
            #Target is days until the day the user typed in chat. targetDay - currentDay is still the same as before the rotation
            birthday = adjusted + datetime.timedelta(days=targetDay-currentDay)
            if birthday < adjusted and 'was' not in message.content.lower().split(' '): birthday += datetime.timedelta(days=7) #If target is a weekday already past, jump it to next week; since that's what they mean, if they didn't say 'was' in their sentence 
        elif any(c in message.content.lower().split(' ') for c in ['today', 'yesterday', 'ago', 'tomorrow']):
            if any(word in message.content.lower() for word in ['my birthday', 'my bday' 'mine is']) and 'today' in message.content.lower().split(' '):
                if 'half' not in message.content.lower().split(' '): await message.channel.send('Happy Birthday! 🍰')
                birthday = adjusted
            elif any(word in message.content.lower() for word in ['my birthday', 'my bday' 'mine was']) and 'yesterday' in message.content.lower().split(' '):
                if 'half' not in message.content.lower().split(' '): await message.channel.send('Happy Belated Birthday! 🍰')
                birthday = adjusted - datetime.timedelta(days=1)
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
            try: birthday = datetime.datetime.strptime(message.content, "%m/%d/%y")
            except:
                try: birthday = datetime.datetime.strptime(message.content, "%m-%d-%y")
                except:
                    try: birthday = datetime.datetime.strptime(message.content, "%m %d %y")
                    except: birthday = None
        if 'half' in message.content.lower().split(' ') and birthday: birthday = birthday + datetime.timedelta(days= sum(a[1] for a in list(ref)[:6])) #Deal with half birthdays; jump 6 months ahead
        birthdayStart = datetime.datetime.now()
        print('start of birthday on message')
        #Now we either have a valid date in the message or we don't. So now we determine the situation and respond accordingly
        #First we check to see if the user is talking about themself
        target = [message.author]
        successful = False
        if any(word in message.content.lower() for word in ['my birthday', 'my bday' 'mine is']): successful = True
        elif any(word in message.content.lower().split(' ') for word in ['is', 'are']) and not any(word in message.content.lower().split(' ') for word in ['my', 'mine']) and len(message.mentions) > 0 and any(word in message.content.lower() for word in ['birthday', 'bday']): 
            #The user most likely tagged someone else, referring to their birthday
            target = []
            for member in message.mentions: target.append(member)
            successful = True
        else:
            async for m in message.channel.history(limit=10): #How many messages to check back for question words
                if any(word in m.content.lower() for word in ['when', 'what']) and any(word in m.content.lower() for word in ['your birthday', 'yours']): successful = True
        #Now, we need to make sure that the bot doesn't prompt people who already have a birthday set for the date they specified; and cancel execution of anything else if no new birthdays are detected
        print('birthday checkpoint 1: {} seconds'.format((datetime.datetime.now() - birthdayStart).seconds))
        if birthday:
            bdays = {} #Local storage b/c database operations take time and resources
            for member in target:
                bday = await database.GetMemberBirthday(member)
                if bday is not None:
                    bdays[member.id] = bday.strftime('%B %d')
                    if bdays.get(member.id) == birthday.strftime('%B %d'): target.remove(member)
        print('birthday checkpoint 2: {} seconds'.format((datetime.datetime.now() - birthdayStart).seconds))
        if successful and birthday and len(target) > 0:
            draft=discord.Embed(title='🍰 Birthday Management Confirmation', color=yellow, timestamp=datetime.datetime.utcnow())
            draft.description='{}, would you like to set **{}** as your birthday?'.format(', '.join([a.name for a in target]), birthday.strftime('%B %d'))
            for member in target:
                if await database.GetMemberBirthday(member) is not None: draft.description+='\n\n{}I currently have {} as your birthday; reacting with the check will overwrite this.'.format('{}, '.format(member.name) if len(target) > 1 else '', bdays.get(member.id))
            mess = await message.channel.send(embed=draft)
            await mess.add_reaction('✅')
            await asyncio.gather(*[birthdayContinuation(self, birthday, target, draft, message, mess, t) for t in target]) #We need to do this to start multiple 'threads' for anyone to react to if necessary
        result = (datetime.datetime.now() - birthdayStart).seconds
        print('at the end of the birthdays on_message, took {} seconds'.format(result))
        return

        
        if any(word in message.content.lower().split(' ') for word in ['age', 'im', 'i\'m']) or 'i am' in message.content.lower(): #Deal with age
            if 'i am' in message.content.lower():
                if len(message.content.lower().split(' ')) > 3:
                    if 'year' not in message.content.lower().split(' ')[3]: return
            if await database.GetMemberBirthday(message.author) is None: return
            for w in message.content.lower().split(' '):
                try: num = int(w)
                except: num = None
                currentAge = await database.GetAge(message.author)
                if num != None and num != currentAge:
                    draft=discord.Embed(title='🍰 Birthday Management Confirmation', color=yellow, timestamp=datetime.datetime.utcnow())
                    draft.description='{}, would you like to set **{}** as your age?{}\n\nThis is purely for personalization purposes for the birthday module; my developer gains nothing by having your age in a database, and the only time your age will be displayed is on your birthday.'.format(message.author.name, num,
                    '' if currentAge == num or currentAge is None else '\n\nI currently have {} as your age; reacting with the check will overwrite this.'.format(currentAge))
                    mess = await message.channel.send(embed=draft)
                    await mess.add_reaction('✅')
                    def ageCheck(r, u): return u == message.author and str(r) == '✅' 
                    u = await self.bot.wait_for('reaction_add', check=ageCheck)
                    draft.description = '{} Saving'.format(loading)
                    await mess.edit(embed=draft)
                    try: await mess.clear_reactions()
                    except: pass
                    await database.SetAge(u[1], num)
                    embed=discord.Embed(title='🍰 Birthday Management',color=yellow, timestamp=datetime.datetime.utcnow())
                    embed.set_author(name=message.author.name, icon_url=message.author.avatar_url)
                    embed.description = 'Your age has been successfully saved, and will be used for your next birthday announcement.'
                    await mess.edit(embed=embed)
    
    @commands.command()
    async def birthday(self, ctx, *args):
       return await ctx.send('This command will be available soon')
    #     if len(args) == 0:
    #         m = await ctx.send(discord.Embed(description=loading))
    #         bday = await database.GetMemberBirthday(ctx.author)
    #         daysTill = bday.day - (datetime.datetime.utcnow() + datetime.timedelta(days=await database.GetTimezone(ctx.guild))).day
    #         currentYear = int(datetime.datetime.now().strftime('%Y')) #Gotta deal with leap year stuff
    #         currentMonth = int(datetime.datetime.now().strftime('%m'))
    #         #If it's after Feb and current year isn't leap year, check to see if next year is; and if it is, use 366 days as the max until next birthday
    #         maxDays = 365
    #         if currentMonth > 2 and not calculateLeapYear(datetime.datetime.now()): maxDays = 366 if calculateLeapYear(datetime.datetime.now() + datetime.timedelta(days=365)) else 365
    #         #Add a day for time remaining if member's birthday is 
    #         if calculateLeapYear(datetime.datetime.now()) and bday.day > 59: 

    #         if daysTill < 0: daysTill = 366 - daysTill if all([currentYear % 4 == 0, currentYear % 400 == 0 if currentYear % 100 == 0 else False]) else 365 - daysTill

    #         embed=discord.Embed(title='🍰 Birthday Management',color=yellow, timestamp=datetime.datetime.utcnow())
    #         embed.add_field(name='Your Birthday',value='%b %d, %Y\n%I:%M %p {}\n(In {} days)'.format(await database.GetNamezone(ctx.guild), 
    #         embed.add_field(name='Your Age', value=await database.GetAge(ctx.author))
    
async def birthdayContinuation(self, birthday, target, draft, message, mess, user):
    def check(r, u):
        return u == user and str(r) == '✅' and r.message.id == mess.id
    u = await self.bot.wait_for('reaction_add', check=check)
    draft.description = '{} Saving'.format(loading)
    if len(target) == 1 or all([await database.GetMemberBirthday(m) == birthday for m in target if m != u[1]]): #Clear confirmation embed if only one person or if everybody already set their birthday
        await mess.edit(embed=draft)
        try: await mess.clear_reactions()
        except: pass
        await database.SetBirthday(u[1], birthday)
    else:
        draft.description = '{} Saving {}\'s birthday'.format(loading, u[1].name)
        mess = await message.channel.send(embed=draft)
        await database.SetBirthday(u[1], birthday)
    embed=discord.Embed(title='🍰 Birthday Management',color=yellow, timestamp=datetime.datetime.utcnow())
    embed.description='''{}, your birthday has been successfully recorded: **{}**.\nIf you would like, you can include your age in the Birthday Management by typing 'I am <age>' or 'I'm <age>'\n\n
    {}\n\nEveryone else, you may use the `birthday` command or react to this message with the 🍰 emoji to add a personal message that will be displayed on {}'s birthday.'''.format(u[1].name,
    birthday.strftime('%B %d'), 'Your birthday will be announced at {} {} to the channel {}'.format((await database.GetBirthdate(message.guild)).strftime('%I:%M %p'), await database.GetNamezone(message.guild), 
    self.bot.get_channel(await database.GetBirthday(message.guild)).mention) if (await database.GetBirthday(message.guild)) > 0 else '''Moderators, please visit [my web dashboard](http://disguard.herokuapp.com/manage/{}/server) to configure
    a channel and time for birthday announcements to be sent. If you are not currently signed in to my web dashboard, then connect your Discord account, click on this server icon [{}] on the homepage, then 'General Server Settings',
    then you may adjust your settings.'''.format(message.guild.id, message.guild.name), u[1].name)
    embed.set_author(icon_url=user.avatar_url, name=user.name)
    await mess.edit(embed=embed)
    await mess.add_reaction('🍰')
    def cakeReac(r, u):
        return str(r) == '🍰' and u not in target and not u.bot and r.message.id == mess.id
    while True:
        try: 
            r, u = await self.bot.wait_for('reaction_add', check=cakeReac)
            try: await mess.remove_reaction(r, u)
            except discord.Forbidden: pass
            if len(target) > 1: 
                while True:
                    await u.send('Who would you like to write a personal message to? Type the number corresponding to the person\n\n{}'.format('\n'.join(['{}: {}'.format(a, target[a].name) for a in range(len(target))])))
                    def chooseUser(m):
                        return m.channel.guild is None and m.author == u
                    m = await self.bot.wait_for('message', check=chooseUser, timeout=180)
                    try: 
                        recipient = target[int(m) - 1]
                        break
                    except: pass
            else: recipient = target[0]
            await u.send('What would you like your personal message to **{}** say? (You will be able to choose if this message is displayed publicly)'.format(recipient.name))
            def awaitMessage(m):
                return type(m.channel) is discord.DMChannel and m.author == u
            script = await self.bot.wait_for('message', check=awaitMessage, timeout=300)
            await u.send('Where would you like your message to be displayed? Type the corresponding number\n1: Only to {0} (their DMs on their birthday)\n2: To {0} and at least one mutual server\'s birthday announcement channel (you will select which server(s))'.format(recipient.name))
            def messageLocation(m):
                return type(m.channel) is discord.DMChannel and m.author == u
            m = await self.bot.wait_for('message', check=messageLocation, timeout=180)
            if '2' in m.content:
                mutual = [s for s in self.bot.guilds if all(m in s.members for m in [u, recipient])]
                letters = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯']
                m = await u.send('{} Retrieving server birthday information from database, please wait...'.format(loading))
                await m.edit(content='You may now select the server(s) where you would like your message to be displayed. To select a server, react with the letter of the corresponding server(s), then react with ➡️ when you\'re done. Only servers that you, me, and {} share will be displayed. Servers with a cake icon mean that they currently have birthday announcements configured; if you choose servers without that icon, the message will be sent there if they configure their birthday announcements channel.\n\n{}'.format(recipient.name,
                '\n'.join(['{}: {}{}'.format(letters[a], mutual[a].name, ' 🍰' if await database.GetBirthday(message.guild) > 0 else '' ) for a in range(len(mutual))])))
                for a in range(len(mutual)):
                    await m.add_reaction(letters[a])
                await m.add_reaction('➡️')
                def moveOn(r, user):
                    return user == u and str(r) == '➡️'
                await self.bot.wait_for('reaction_add', check=moveOn, timeout=300)
                selected = [recipient]
                m = (await u.history(limit=1).flatten())[0] #refresh message
                for r in m.reactions: 
                    if str(r) != '➡️': selected.append(mutual[letters.index(str(r))])
            else: selected = [recipient]
            m = await u.send('Your message to **{}** says "{}". Ready to save it? The message will be sent on {}; their birthday.'.format(', '.join(a.name for a in selected),
                script.content, birthday.strftime('%B %d')))
            await m.add_reaction('✅')
            def finalConfirm(r, user):
                return u == user and str(r) == '✅'
            await self.bot.wait_for('reaction_add', check=finalConfirm, timeout=180)
            await database.SetBirthdayMessage(recipient, script, u, [a for a in selected if type(a) is discord.Guild])
            await u.send('Your personal message for {} has been successfully set. To add a personal message to anyone, set your birthday, age, or view your birthday management, you may use the `birthday` command.'.format(recipient))
        except asyncio.TimeoutError:
            await u.send('Birthday management timed out')
            break

    # def calculateLeapYear(d: datetime.datetime):
    #     currentYear = int(datetime.datetime.now().strftime('%Y')) #Gotta deal with leap year stuff
    #     return all([currentYear % 4 == 0, currentYear % 400 == 0 if currentYear % 100 == 0 else False])
    
def setup(bot):
    bot.add_cog(Birthdays(bot))

