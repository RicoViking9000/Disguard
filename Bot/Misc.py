'''Contains code relating to various bonus/extra features of Disguard
This will initially only contain the Easter/April Fools Day events code, but over time will be expanded to include things that don't belong in other files
'''

import discord
import secure
from discord.ext import commands
import database
import lyricsgenius
import re
import asyncio
import copy

yellow = (0xffff00, 0xffff66)
placeholderURL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emojis = bot.get_cog('Cyberlog').emojis
        self.genius = lyricsgenius.Genius(secure.geniusToken(), remove_section_headers=True, verbose=False)
        self.songSessions = {} #Dict key: Channel ID, Dict value: String (if song is unconfirmed) or Genius Song object
        self.privacyUpdaterCache = {} #Key: UserID_ChannelID, Value: Message ID

    @commands.Cog.listener()
    async def on_message(self, message):
        '''This message listener is currently use for: April Fools Day event [Song Lyrics] automater'''
        return
        if message.author.bot: return
        prefix = self.bot.lightningLogging[message.guild.id]['prefix']
        if message.guild and message.content.startswith(prefix): return
        haveToSearch = False
        cache = self.songSessions.get(message.channel.id, {})
        cleanContent = re.sub(r'[^\w\s]', '', message.content.lower())
        def findPositionInSong(start=0):
            '''Determines where in the song the message content is. Handles entries that are partway through a song or line'''
            nonlocal cache
            lyricList = cache['lyrics'].split('\n')
            for num, line in enumerate(lyricList):
                if num < start: continue
                cleanLine = re.sub(r'[^\w\s]', '', line.lower())
                if cleanContent in cleanLine:
                    if cleanLine == cleanContent: cache['line'] = num + 1
                    else:
                        cache['line'] = num
                        cache['cursor'] = line.lower().find(message.content.lower()) + len(message.content)
                    break
            lyricList = cache['lyrics'].split('\n')
            toSend = lyricList[cache['line']][cache['cursor']:]
            while toSend == '':
                cache['line'] += 1
                cache['cursor'] = 0
                toSend = lyricList[cache['line']][cache['cursor']:]
            if toSend[0] == ',': toSend = toSend[1:]
            return toSend
        def searchSong(search):
            '''Searches a song based on a given input, returns the top result'''
            #nonlocal cache
            #nonlocal lyricList
            results = self.genius.search_lyrics(search, 1)
            top = results['sections'][0]['hits'][0]
            lyrics = self.genius.search_song(song_id=top['result']['id'], artist=top['result']['primary_artist']['name']).to_text()
            storageObject = {'lyrics': lyrics, 'cleanLyrics': clean(lyrics), 'title': top['result']['title'], 'id': top['result']['id'], 'queries': [search], 'confirmed': False, 'line': 0, 'cursor': 0}
            #lyricList = lyrics.split('\n')
            #findPositionInSong()
            #self.songSessions[message.channel.id] = cache
            return (top, storageObject)
        async def verifySong():
            '''Performs some processing to determine what action to take next, based on the message sent in chat and the song confirmation status'''
            nonlocal cache
            nonlocal cleanContent
            nonlocal result
            #Analyze the most recent entry to see if it fits into the current song
            if not cache['confirmed']:
                if cleanContent in cache['cleanLyrics']:
                    if len(cache['queries']) >= 3 and not cache['confirmed']:
                        #If we have at least two entries and no confirmed song, mark the song as confirmed if the last two entries match the first probable song
                        if clean(cache['queries'][-2]) in cache['cleanLyrics'] and clean(cache['queries'][-1]) in cache['cleanLyrics']:
                            cache['confirmed'] = True
                            result = searchSong(cache['queries'][-2])[0]
                            await message.channel.send(f"{self.emojis['greenCheck']} | Current karaoke song: {result['result']['title']} by {result['result']['primary_artist']['name']}\nType `{prefix}karaoke end` to clear the cache/change song or have a moderator use `{prefix}karaoke disable` to turn off this feature\nNote that this feature is only available on April Fools Day")
                        #Otherwise, switch to the second probable song
                        else:
                            cache = result
                            await message.channel.send(f"Maybe {result['result']['title']} by {result['result']['primary_artist']['name']} is a better match")
                    elif len(cache['queries']) == 1 and not cache['confirmed']:
                        #If this is the first message sent, and it matches a line in the top matched song exactly, we'll confirm this song
                        if cleanContent in (cache['cleanLyrics'].split('\n'))[cache['line']]:
                            cache['confirmed'] = True
                            await message.channel.send(f"{self.emojis['greenCheck']} | Current karaoke song: {result['result']['title']} by {result['result']['primary_artist']['name']}\nType `{prefix}karaoke end` to clear the cache/change song or have a moderator use `{prefix}karaoke disable` to turn off this feature\nNote that this feature is only available on April Fools Day")
                else: 
                    if result['result']['id'] != cache['id']:
                        oldCache = copy.deepcopy(cache)
                        cache = storageObject
                        cache.update({'queries': oldCache['queries']})
                        self.songSessions[message.channel.id] = cache
            else:
                if len(cache['queries']) >= 3:
                    print(message.content, storageObject['queries'][-1])
                    if clean(cache['queries'][-2]) in storageObject['cleanLyrics'] and clean(cache['queries'][-1]) in storageObject['cleanLyrics']:
                        previousSearch = searchSong(cache['queries'][-2])[0]
                        currentSearch = searchSong(cache['queries'][-1])[0]
                        if previousSearch['result']['id'] == currentSearch['result']['id'] != cache['id']: #We found a different song
                            cache = currentSearch
                            self.songSessions[message.channel.id] = cache
        #If we don't have a confirmed song registered to this channel, we want to perform a search & manage the song lyrics cache that will be used afterwards for processing/analysis
        #if result['id'] == cache['id']: 
        #cache['queries'].append(message.content)
        #else:
        #    cache['queries'].append(message.content)
        async with message.channel.typing():
            result = None
            preconfirmed = cache.get('confirmed')
            precached = copy.deepcopy(cache)
            if not cache or not cache['confirmed']:
                result, storageObject = searchSong(message.content)
                if not cache: 
                    cache = storageObject
                    self.songSessions[message.channel.id] = cache
            if precached: cache['queries'].append(message.content)
            if not cache['confirmed']:
                if not result: result, storageObject = searchSong(message.content)[0]
                await verifySong()
            print(cache['queries'])
            if len(cache['queries']) >= 3:
                cache['queries'].pop(0)
            toSend = findPositionInSong(cache['line'])
            lyricList = cache['lyrics'].split('\n')
            cache['line'] += 1
            while lyricList[cache['line']] == '':
                cache['line'] += 1
            cache['cursor'] = 0
            await asyncio.sleep(0.4 * len(toSend.split(' ')))
            await message.channel.send(toSend)
        #If we already have a song confirmed, we'll double check to make sure the one marked as confirmed matches what the user typed in chat
        if preconfirmed:
            oldCache = copy.deepcopy(cache)
            oldID = cache['id']
            if not result: result, storageObject = searchSong(message.content)
            oldSong = cache['title']
            await verifySong()
            if result['result']['id'] != oldID:
                m = await message.channel.send(f"It seems like the last two messages sent here match {result['result']['title']} by {result['result']['primary_artist']['name']}. React ❌ to stick with {oldSong}, {self.emojis['greenCheck']} to switch to {result['result']['title']}, or {self.emojis['darkRedDisconnect']} to end the session.")
                reactions = ['❌', self.emojis['greenCheck'], self.emojis['darkRedDisconnect']]
                for reaction in reactions: await m.add_reaction(reaction)
                def check(r, u): return r.emoji in reactions and r.message.id == m.id and u.id == message.author.id
                try: res = await self.bot.wait_for('reaction_add', check=check, timeout=300)
                except asyncio.TimeoutError: res = None
                if res:
                    if res[0].emoji == '❌': cache = oldCache
                    elif res[0].emoji == '✔':
                        toSend = findPositionInSong(cache['line'])
                        lyricList = cache['lyrics'].split('\n')
                        cache['line'] += 1
                        while lyricList[cache['line']] == '':
                            cache['line'] += 1
                        cache['cursor'] = 0
                        await asyncio.sleep(0.4 * len(toSend.split(' ')))
                        await message.channel.send(toSend)
                    else: cache = {}

    @commands.command()
    async def privacy(self, ctx):
        user = self.bot.lightningUsers[ctx.author.id]
        users = database.GetUserCollection()
        privacy = user['privacy']
        prefix = self.bot.lightningLogging[ctx.guild.id]['prefix'] if ctx.guild else '.'
        def slideToggle(i): return self.emojis['slideToggleOff'] if i == 0 else self.emojis['slideToggleOn'] if i == 1 else slideToggle(privacy['default'][0]) #Uses recursion to use default value if specific setting says to
        def viewerEmoji(i): return '🔒' if i == 0 else '🔓' if i == 1 else viewerEmoji(privacy['default'][1]) if i == 2 else self.emojis['members']
        def viewerText(i): return 'only you' if i == 0 else 'everyone you share a server with' if i == 1 else viewerText(privacy['default'][1]) if i == 2 else f'{len(i)} users'
        def enabled(i): return False if i == 0 else True if i == 1 else enabled(privacy['default'][0])
        embed = discord.Embed(title=f'Privacy Settings » {ctx.author.name} » Overview', color=user['profile'].get('favColor') or yellow[user['profile']['colorTheme']])
        embed.description = f'''To view Disguard's privacy policy, [click here](https://disguard.netlify.app/privacybasic).\n\nTo view and edit all settings, visit my [web dashboard](http://disguard.herokuapp.com/manage/profile)'''
        embed.add_field(name='Default Settings', value=f'''{slideToggle(privacy['default'][0])}Allow Disguard to use your customization settings for its features: {"Enabled" if enabled(privacy['default'][0]) else "Disabled"}\n{viewerEmoji(privacy['default'][1])}Default visibility of your customization settings: {viewerText(privacy['default'][1])}''', inline=False)
        embed.add_field(name='Personal Profile Features', value=f'''{slideToggle(privacy['profile'][0])}{"Enabled" if enabled(privacy['profile'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['profile'][1])}Personal profile features: Visible to {viewerText(privacy['profile'][1])}" if enabled(privacy['profile'][0]) else ""}''', inline=False)
        embed.add_field(name='Birthday Module Features', value=f'''{slideToggle(privacy['birthdayModule'][0])}{"Enabled" if enabled(privacy['birthdayModule'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['birthdayModule'][1])}Birthday profile features: Visible to {viewerText(privacy['birthdayModule'][1])}" if enabled(privacy['birthdayModule'][0]) else ""}''', inline=False)
        embed.add_field(name='Attribute History', value=f'''{slideToggle(privacy['attributeHistory'][0])}{"Enabled" if enabled(privacy['attributeHistory'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['attributeHistory'][1])}Attribute History: Visible to {viewerText(privacy['attributeHistory'][1])}" if enabled(privacy['attributeHistory'][0]) else ""}''', inline=False)
        m = await ctx.send(embed=embed)

def clean(s):
    return re.sub(r'[^\w\s]', '', s.lower())

def setup(bot):
    bot.add_cog(Misc(bot))
