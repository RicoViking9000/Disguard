'''Contains all the code for Disguard's reddit-related features'''
import discord
import secure
from discord.ext import commands, tasks
import traceback
import asyncio
from typing import Dict, List
import utility
import datetime
import asyncpraw

newline = '\n'

class Reddit(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot: commands.Bot = bot
        self.redditThreads: Dict[int, List[str]] = {}
        self.reddit = asyncpraw.Reddit(user_agent = 'Portal for Disguard - Auto link & reddit feed functionality. --RV9k--')
        self.emojis: Dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis

    @tasks.loop(hours=1)
    async def syncRedditFeeds(self):
        '''Goes through all servers and ensures reddit feeds are working'''
        print('Syncing Reddit feeds')
        try:
            for server in self.bot.guilds: asyncio.create_task(self.redditFeedHandler(server))
        except: 
            print(f'Reddit sync fail: ')
            traceback.print_exc()
    
    async def redditFeedHandler(self, server: discord.Guild):
        '''Handles starting/stopping of reddit feeds for servers, along with ensuring there are no duplicates, etc.'''
        runningFeeds = self.redditThreads.get(server.id, [])
        server_data = await utility.get_server(server)
        proposedFeeds = [entry['subreddit'] for entry in server_data.get('redditFeeds', []) if self.bot.get_channel(entry['channel'])]
        feedsToCreate = [entry for entry in server_data.get('redditFeeds', []) if entry['subreddit'] not in runningFeeds and self.bot.get_channel(entry['channel']) and not (await self.reddit.subreddit(entry['subreddit'], fetch=True)).over18]
        feedsToDelete = [entry for entry in runningFeeds if entry not in proposedFeeds]
        for feed in feedsToCreate: asyncio.create_task(self.createRedditStream(server, feed))
        for feed in feedsToDelete: self.redditThreads[server.id].remove(feed)
    
    async def createRedditStream(self, server: discord.Guild, data: dict, attempt=0):
        '''Data represents a singular subreddit customization data'''
        print(f'creating reddit stream for {server.name}: {data["subreddit"]}', attempt)
        if attempt > 2:
            return self.redditThreads[server.id].remove(data['subreddit']) #This will get picked up in the next syncRedditFeeds loop
        if self.redditThreads.get(server.id) and data['subreddit'] in self.redditThreads[server.id]: return #We already have a thread running for this server & subreddit
        channel = self.bot.get_channel(data['channel'])
        subreddit = await self.reddit.subreddit(data['subreddit'], fetch=True)
        try: self.redditThreads[server.id].append(data['subreddit']) #Marks that we have a running thread for this server & subreddit
        except (KeyError, AttributeError): self.redditThreads[server.id] = [data['subreddit']]
        try:
            async for submission in subreddit.stream.submissions(skip_existing=True):
                try:
                    if data['subreddit'] not in self.redditThreads[server.id]: return #This feed has been cancelled
                    embed = await self.redditSubmissionEmbed(server, submission, True, data['truncateTitle'], data['truncateText'], data['media'], data['creditAuthor'], data['color'], data['timestamp'], channel=channel)
                    await channel.send(embed=embed)
                except: 
                    print(f'reddit feed submission error')
                    traceback.print_exc()
        except:
            print(f'reddit feed error: {server.name} {server.id}')
            traceback.print_exc()
            await asyncio.sleep(60)
            asyncio.create_task(self.createRedditStream(server, data, attempt + 1))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await asyncio.gather(*[self.redditAutocomplete(message), self.redditEnhance(message)])

    async def redditAutocomplete(self, message: discord.Message):
        if 'r/' not in message.content: return
        try: config = (await utility.get_server(message.guild))['redditComplete']
        except KeyError: return
        if config == 0: return #Feature is disabled
        if message.author.id == self.bot.user.id: return
        for w in message.content.split(' '):
            if w.lower().startswith('r/') and 'https://' not in w:
                try:
                    subSearch = w[w.find('r/') + 2:]
                    result = await self.subredditEmbed(subSearch, config == 1)
                    if config == 1: await message.channel.send(result)
                    else: await message.channel.send(embed=result)
                except: pass

    async def redditEnhance(self, message: discord.Message):
        try: config = (await utility.get_server(message.guild))['redditEnhance']
        except KeyError: return
        if ('https://www.reddit.com/r/' not in message.content and 'https://old.reddit.com/r/' not in message.content) or config == (False, False): return
        if message.author.id == self.bot.user.id: return
        for w in message.content.split(' '):
            if ('https://www.reddit.com/r/' in w or 'https://old.reddit.com/r/' in w) and '/comments/' in w and config[0]:
                try:
                    embed = await self.redditSubmissionEmbed(message.guild, w, False, channel=message.channel)
                    await message.channel.send(embed=embed)
                except: pass
            elif ('https://www.reddit.com/r/' in w or 'https://old.reddit.com/r/' in w) and '/comments/' not in w and config[1]:
                try:
                    subSearch = w[w.find('r/') + 2:]
                    embed = await self.subredditEmbed(subSearch, False)
                    await message.channel.send(embed=embed)
                    message = await message.channel.fetch_message(message.id)
                except: pass
            else: continue
            message = await message.channel.fetch_message(message.id)
            if len(message.embeds) < 1:
                def check(b, a): return b.id == message.id and len(a.embeds) > len(b.embeds)
                result = (await self.bot.wait_for('message_edit', check=check))[1]
            else: result = message
            await result.edit(suppress=True)
            def reactionCheck(r, u): return r.emoji == self.emojis['expand'] and u.id == self.bot.user.id and r.message.id == message.id
            reaction, user = await self.bot.wait_for('reaction_add', check=reactionCheck)
            await message.remove_reaction(reaction, user)

    async def subredditEmbed(self, search, plainText = False):
        subreddit = await self.reddit.subreddit(search, fetch=True)
        url = f'https://www.reddit.com{subreddit.url}'
        if plainText: return f'<{url}>'
        else:
            keyColor = subreddit.key_color or subreddit.primary_color or '#2E97E5' #The last one is the default blue
            embed = discord.Embed(
                title=f'r/{subreddit.display_name}',
                description=f'''{subreddit.public_description}\n\n{subreddit.subscribers} subscribers • {subreddit.active_user_count} online\n{f"{self.emojis['alert']}This subreddit is NSFW" if subreddit.over18 else ""}''',
                color=utility.hexToColor(keyColor),
                url=url)
            embed.set_thumbnail(url=subreddit.icon_img)
            embed.set_image(url=subreddit.banner_background_image)
            return embed
    
    async def redditSubmissionEmbed(self, g, source, redditFeed=False, truncateTitle=100, truncateText=400, media=3, creditAuthor=True, color='colorCode', timestamp=True, channel=None):
        '''Media - 0: All off, 1: Only thumbnail, 2: Only images, 3: All on'''
        if truncateTitle < 1: truncateTitle = 256
        if truncateText < 1: truncateText = 1900
        if type(source) is str:
            if 'https://' in source: submission = await self.reddit.submission(url=source)
            else: submission = await self.reddit.submission(id=source)
        else: submission = source
        author = submission.author
        await author.load()
        subreddit = submission.subreddit
        await subreddit.load()
        if submission.is_self: submissionType, linkFlavor = 'text', ''
        elif submission.is_video:
            submissionType, url = 'video', submission.media['reddit_video']['fallback_url'][:submission.media['reddit_video']['fallback_url'].find('?source=')]
            linkFlavor = f"\n[Direct video link]({url} '{url}')"
        elif 'i.redd.it' in submission.url: submissionType, linkFlavor = 'image', ''
        elif 'www.reddit.com/gallery' in submission.url: submissionType, linkFlavor = 'gallery', f"\n[Gallery view]({submission.url} '{submission.url}')"
        else: submissionType, linkFlavor = 'link', f"\n[{utility.basicURL(submission.url)}]({submission.url} '{submission.url}')"
        flagForNSFW = submission.over_18 and channel and not channel.is_nsfw()
        typeKeys = {'text': '📜', 'video': self.emojis['camera'], 'image': self.emojis['images'], 'link': '🔗', 'gallery': self.emojis['details']}
        awards = submission.total_awards_received
        keyColor = subreddit.key_color or subreddit.primary_color or '#2E97E5' #The last one is the default blue
        if redditFeed: description=f'''{typeKeys[submissionType]}{submissionType[0].upper()}{submissionType[1:]} post • r/{subreddit.display_name}{linkFlavor}{f"{newline}👀(Spoiler)" if submission.spoiler else ""}{f"{newline}{self.emojis['alert']} NSFW" if submission.over_18 else ""}'''
        else: description=f'''{submissionType[0].upper()}{submissionType[1:]} post\n{submission.score} upvote{"s" if submission.score != 1 else ""} • {round(submission.upvote_ratio * 100)}% upvoted{f" • {awards} awards" if awards > 0 else ""}{f" • {submission.view_count} " if submission.view_count else ""} • {submission.num_comments} comment{"s" if submission.num_comments != 1 else ""} on r/{subreddit.display_name}{linkFlavor}{f"{newline}👀(Spoiler)" if submission.spoiler else ""}{f"{newline}{self.emojis['alert']}(NSFW)" if submission.over_18 else ""}'''
        embed = discord.Embed(
            title=f'{"🔒" if submission.locked and not redditFeed else ""}{"📌" if submission.stickied and not redditFeed else ""}{(submission.title[:truncateTitle] + "…") if len(submission.title) > truncateTitle else submission.title}', 
            description=description,
            color=utility.hexToColor(keyColor) if color == 'colorCode' else utility.hexToColor(color), url=f'https://www.reddit.com{submission.permalink}')
        if submissionType == 'text': embed.description += f'\n\n{(submission.selftext[:truncateText] + "…") if len(submission.selftext) > truncateText else submission.selftext}'
        if creditAuthor > 0:
            embed.set_author(name=author.name if creditAuthor != 2 else discord.Embed.Empty, icon_url=author.icon_img if creditAuthor != 1 else discord.Embed.Empty)
        if media > 0 and not flagForNSFW:
            if media != 2: embed.set_thumbnail(url=subreddit.icon_img)
            if submissionType == 'image': 
                if redditFeed and media != 1: embed.set_image(url=submission.url)
                elif not redditFeed: embed.set_thumbnail(url=submission.url)
        if timestamp and not flagForNSFW: embed.set_footer(text=f'{"Posted " if not redditFeed else ""}{(datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=submission.created_utc) + datetime.timedelta(hours=await utility.time_zone(g))):%b %d, %Y • %I:%M %p} {await utility.name_zone(g)}')
        if channel and flagForNSFW:
            embed.title = f"{self.emojis['alert']} | Title hidden: NSFW submission & this is not a NSFW channel"
            embed.description = f"r/{subreddit.display_name}\n\nTo comply with Discord guidelines, I cannot share content from NSFW reddit submissions to SFW Discord channels"
        return (embed, submission.over_18) if not channel else embed

async def setup(bot: commands.Bot):
    await bot.add_cog(Reddit(bot))