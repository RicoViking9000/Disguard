'''Cog that contains Disguard's dev-only commands'''

import asyncio
import codecs
import datetime
import inspect
import json
import os
import shutil
import traceback
import typing
import discord
from discord import app_commands
from discord.ext import commands
import pymongo.errors
import utility
import Support
import textwrap
import database
import lightningdb
import pymongo
# =============================================================================


@app_commands.guilds(utility.DISGUARD_SERVER_ID)
class Dev(commands.GroupCog, name='dev', description='Dev-only commands'):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.emojis: dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis
    
    @app_commands.command(name='verify_database')
    async def verify_database(self, interaction: discord.Interaction):
        '''Verify the database'''
        await interaction.response.send_message('Verifying database...')
        await database.Verification(self.bot)
        await interaction.edit_original_response(content='Database verified!')

    @app_commands.command(name='unduplicate_history')
    async def unduplicate_history(self, interaction: discord.Interaction):
        '''Remove duplicate entries from status, username, avatar history'''
        self.bot.useAttributeQueue = True
        await database.UnduplicateUsers(self.bot.users, interaction)
        self.bot.useAttributeQueue = False
        await database.BulkUpdateHistory(self.bot.attributeHistoryQueue)
        
    @app_commands.command(name='index_server')
    async def index_server(self, interaction: discord.Interaction, *, server_arg: typing.Optional[str]):
        '''Index a server's messages'''
        if server_arg: servers: list[discord.Guild] = [self.bot.get_guild(int(server_arg))]
        else: servers: list[discord.Guild] = self.bot.guilds
        await interaction.response.send_message(f'Indexing [{",  ".join([str(s)[:15] for s in servers])}]...')
        for server in servers:
            await asyncio.gather(*[indexMessages(server, channel, True) for channel in server.text_channels])
        await interaction.edit_original_response(content='Server indexed!')

    @index_server.autocomplete('server_arg')
    async def index_server_autocomplete(self, interaction: discord.Interaction, argument: str):
        if argument: return [app_commands.Choice(name=str(server[0]), value=str(server[0].id)) for server in utility.FindServers(self.bot.guilds, argument)][:25]
        return [app_commands.Choice(name=str(server), value=str(server.id)) for server in self.bot.guilds][:25]
    
    @app_commands.command(name='index_channel')
    async def index_channel(self, interaction: discord.Interaction, channel_arg: str):
        '''Index a channel'''
        channel = self.bot.get_channel(int(channel_arg))
        await interaction.response.send_message(f'Indexing {channel.name}...')
        await indexMessages(channel.guild, channel, True)
        await interaction.edit_original_response(content='Channel indexed!')

    @index_channel.autocomplete('channel_arg')
    async def index_channel_autocomplete(self, interaction: discord.Interaction, argument: str):
        def filter_list(results: list[list[tuple[discord.TextChannel, int]]]) -> list[discord.TextChannel]:
            result = []
            for list_entry in results:
                result += [entry[0] for entry in list_entry if isinstance(entry[0], discord.TextChannel)]
            return result
        text_channel_results = [utility.FindChannels(server, argument) for server in self.bot.guilds]
        filtered_results = filter_list(text_channel_results)
        if argument: return [app_commands.Choice(name=channel.name, value=str(channel.id)) for channel in filtered_results][:25]
        return [app_commands.Choice(name=str(channel), value=str(channel.id)) for channel in self.bot.get_all_channels() if isinstance(channel, discord.TextChannel)][:25]
    
    @app_commands.command(name='eval')
    async def eval(self, interaction: discord.Interaction, *, code: str):
        '''Evaluate code'''
        code = textwrap.dedent(code)
        env = {
            'bot': self.bot,
            'interaction': interaction,
            'discord': discord,
            'commands': commands,
            'utility': utility,
            'Support': Support,
            'textwrap': textwrap,
            'self': self,
        }
        env.update(globals())
        try:
            result = eval(code, env)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            await interaction.response.send_message(f'```py\n{e.__class__.__name__}: {e}\n```')
        else:
            await interaction.response.send_message(f'```py\n{result}\n```')
    
    @app_commands.command(name='get_log_file')
    async def get_log_file(self, interaction: discord.Interaction):
        '''Get the log file'''
        await interaction.response.send_message(file=discord.File('discord.log'))

    @app_commands.command(name='sync')
    async def sync_tree(self, interaction: discord.Interaction):
        '''Sync the tree'''
        await self.bot.tree.sync()
        await self.bot.tree.sync(guild=discord.Object(utility.DISGUARD_SERVER_ID))
        await interaction.response.send_message('Synced tree')

    @app_commands.command(name='clear_commands')
    async def clear_commands(self, interaction: discord.Interaction):
        '''Clear the command cache'''
        await self.bot.tree.clear_commands()
        await self.bot.tree.sync()
        await interaction.response.send_message('Cleared tree')

    @app_commands.command(name='reload_cog')
    async def reload_cog(self, interaction: discord.Interaction, cog_name: str):
        '''Reload a cog'''
        cog = self.bot.get_cog(cog_name)
        if cog is None:
            await interaction.response.send_message(f'Cog {cog_name} not found')
            return
        try: await self.bot.reload_extension(cog.qualified_name)
        except commands.ExtensionNotLoaded:
            try:
                await self.bot.unload_extension(utility.first_letter_upper(cog_name))
                await self.bot.load_extension(utility.first_letter_upper(cog_name))
            except Exception as e:
                traceback.print_exc()
                return await interaction.response.send_message(f'Failed to load cog {cog_name}: {e}')
        except Exception as e:
            traceback.print_exc()
            return await interaction.response.send_message(f'Failed to reload cog {cog_name}: {e}')
        await interaction.response.send_message(f'Reloaded `{cog_name}`')
    
    @reload_cog.autocomplete('cog_name')
    async def reload_cog_autocomplete(self, interaction: discord.Interaction, argument: str):
        if argument: return [app_commands.Choice(name=cog_name, value=cog_name) for cog_name in self.bot.cogs.keys() if argument.lower() in cog_name.lower()][:25]
        return [app_commands.Choice(name=cog_name, value=cog_name) for cog_name in self.bot.cogs.keys()][:25]
    
    @app_commands.command(name='broadcast')
    async def broadcast(self,
                        interaction: discord.Interaction,
                        *,
                        message: str,
                        server_bucket: typing.Literal['all', 'none', 'eval'],
                        server_arg: typing.Optional[str] = '',
                        destination_bucket: typing.Literal['logging', 'moderator'],
                        embed: bool = False
                        ):
        '''Broadcast a message'''
        # Future: Modal for message, and openAI for destination channels
        match server_bucket:
            case 'all':
                servers = [await utility.get_server(server) for server in self.bot.guilds]
                if server_arg: servers = [server for server in servers if server['server_id'] not in server_arg]
            case 'none':
                servers = []
                if server_arg: servers = [await utility.get_server(server) for server in self.bot.guilds if server['server_id'] in server_arg]
            case _:
                all_servers = [await utility.get_server(server) for server in self.bot.guilds]
                servers = [server for server in all_servers if eval(f'server.{server_arg}')]
        newline = message.find('\n')
        payload = {
            'content': None if embed else message,
            'embed': discord.Embed(
                title=message[:newline],
                description=message[newline + 1:],
            ) if embed else None
        }
        log = {}
        for server in servers:
            if not server: continue
            match destination_bucket:
                case 'logging':
                    channel = self.bot.get_channel(server['cyberlog']['defaultChannel'])
                case _:
                    channel = self.bot.get_channel(server['moderatorChannel'])
            if channel is None: continue
            try: 
                await channel.send(**payload)
                log[server['server_id']] = f'{server["name"]} - successfully delivered to {channel.name}'
            except Exception as e:
                log[server['server_id']] = f'{server["name"]} - failed to deliver to {channel.name}: {e}'
        path = f"Attachments/Temp/Broadcast-{datetime.datetime.utcnow().strftime('%m%d%Y%H%M%S%f')}.json" #TODO - move this datetime into utility
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=4)
        f = discord.File(path)
        await interaction.response.send_message(file=f)
        # os.remove(path)

    @app_commands.command(name='bot_status')
    async def change_bot_status(self,
                         interaction: discord.Interaction,
                         status: typing.Literal['online', 'idle', 'dnd', 'invisible'],
                         activity_type: typing.Literal['playing', 'streaming', 'listening', 'watching', 'competing', 'custom'],
                         activity_name: str,
                         reset: bool = False):
        '''Set Disguard's status'''
        try:
            if reset:
                presence = {'status': discord.Status.online, 'activity': discord.Activity(name=f'{len(self.bot.guilds)} servers', type=discord.ActivityType.watching)}
                await self.bot.change_presence(**presence)
                return await interaction.response.send_message('Reset status')
            if activity_type == 'playing':
                presence = {'status': eval(f'discord.Status.{status}'), 'activity': discord.Game(name=activity_name)}
            elif activity_type == 'custom':
                presence = {'status': eval(f'discord.Status.{status}'), 'activity': discord.CustomActivity(name=activity_name)}
            else:
                presence = {
                    'status': eval(f'discord.Status.{status}'),
                    'activity': discord.Activity(name=activity_name, type=discord.ActivityType[activity_type])
                }
            await self.bot.change_presence(**presence)
            await interaction.response.send_message('Status updated')
        except Exception as e:
            await interaction.response.send_message(f'Failed to update status: {e}')

    @app_commands.command(name='retrieve_attachments')
    async def retrieve_attachments(self, interaction: discord.Interaction, user: discord.User):
        '''Retrieve all attachments a user has sent - part of the data command'''
        await interaction.response.send_message(f'Retrieving attachments for {user.display_name}...')
        base_path = f'Attachments/Temp/{datetime.datetime.utcnow().strftime('%m%d%Y%H%M%S%f')}'
        def strip_filename(string):
            illegal_char_list = '#%&\{\}\\<>*?/$!\'":@+`|='
            export = ''.join(char if char not in illegal_char_list else '-' for char in string if char != ' ')
            return export
        filtered_servers = [g for g in self.bot.guilds if user in g.members]
        for server in filtered_servers:
            server_path = f'{base_path}/MessageAttachments/{strip_filename(server.name)}'
            for channel in server.text_channels:
                with open(f'Indexes/{server.id}/{channel.id}.json') as f: indexData = json.load(f)
                channel_path = f'{server_path}/{strip_filename(channel.name)}'
                for message_id, data in indexData.items():
                    if data['author0'] == user.id: 
                        try: 
                            attachments_path = f'Attachments/{server.id}/{channel.id}/{message_id}'
                            for attachment in os.listdir(attachments_path):
                                try: os.makedirs(channel_path)
                                except FileExistsError: pass
                                savedFile = shutil.copy2(f'{attachments_path}/{attachment}', channel_path)
                                os.replace(savedFile, f'{channel_path}/{message_id}_{attachment}')
                        except FileNotFoundError: pass
        with codecs.open(f'{base_path}/README.txt', 'w+', 'utf-8-sig') as f: 
            f.write(f"📁MessageAttachments --> Master Folder\n|-- 📁[Server Name] --> Folder of channel names in this server\n|-- |-- 📁[Channel Name] --> Folder of message attachments sent by you in this channel in the following format: MessageID_AttachmentName.xxx\n\nWhy are message attachments stored? Solely for the purposes of message deletion logging. Additionally, attachment storing is a per-server basis, and will only be done if the moderators of the server choose to tick 'Log images and attachments that are deleted' on the web dashboard. If a message containing an attachment is sent in a channel, I attempt to save the attachment, and if a message containing an attachment is deleted, I attempt to retrieve the attachment - which is then permanently deleted from my records.")
        fileName = f'Attachments/Temp/MessageAttachments_{strip_filename(user.name)}_{(discord.utils.utcnow() + datetime.timedelta(hours=await utility.time_zone(ctx.guild) if ctx.guild else -4)):%m-%b-%Y %I %M %p}'
        shutil.make_archive(fileName, 'zip', base_path)
        await interaction.response.edit_message(content=f'{os.path.abspath(fileName)}.zip')


async def indexMessages(server: discord.Guild, channel: discord.TextChannel, full=False):
    if channel.id in (534439214289256478, 910598159963652126): return
    start = datetime.datetime.now()
    try: saveImages = (await utility.get_server(server))['cyberlog'].get('image') and not channel.is_nsfw()
    except AttributeError: return
    if lightningdb.database.get_collection(str(channel.id)) is None: full = True
    existing_message_counter = 0
    async for message in channel.history(limit=None, oldest_first=full):
        try: await lightningdb.post_message(message)
        except pymongo.errors.DuplicateKeyError:
            if not full:
                existing_message_counter += 1
                if existing_message_counter >= 15: break
        if not message.author.bot and (discord.utils.utcnow() - message.created_at).days < 7 and saveImages:
            attachments_path = f'Attachments/{message.guild.id}/{message.channel.id}/{message.id}'
            try: os.makedirs(attachments_path)
            except FileExistsError: pass
            for attachment in message.attachments:
                if attachment.size / 1000000 < 8:
                    try: await attachment.save(f'{attachments_path}/{attachment.filename}')
                    except discord.HTTPException: pass
        if full: await asyncio.sleep(0.0015)
    print(f'Indexed {server.name}: {channel.name} in {(datetime.datetime.now() - start).seconds} seconds')

async def setup(bot: commands.Bot):
    await bot.add_cog(Dev(bot))
