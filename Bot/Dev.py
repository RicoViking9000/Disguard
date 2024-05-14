'''Cog that contains Disguard's dev-only commands'''

import asyncio
import inspect
import typing
import discord
from discord import app_commands
from discord.ext import commands
import utility
import Support
import textwrap
import database
# =============================================================================

def team_check():
    '''Ensures dev commands are only run by Disguard developers'''
    print('running team check')
    async def predicate(ctx: commands.Context) -> bool:
        return ctx.interaction.user in (await ctx.bot.application_info()).team.members
    return commands.check(predicate)

@team_check()
@app_commands.guilds(utility.DISGUARD_SERVER_ID)
class Dev(commands.GroupCog, name='dev', description='Dev-only commands'):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis: dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis
        super().__init__()
    
    @app_commands.command(name='verify_database')
    async def verify_database(self, interaction: discord.Interaction):
        '''Verify the database'''
        await interaction.response.send_message('Verifying database...')
        await database.Verification(self.bot)
        await interaction.edit_original_response(content='Database verified!')
        
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


async def indexMessages(server: discord.Guild, channel: discord.TextChannel, full=False):
    if channel.id in (534439214289256478, 910598159963652126): return
    start = datetime.datetime.now()
    try: saveImages = (await utility.get_server(server))['cyberlog'].get('image') and not channel.is_nsfw()
    except AttributeError: return
    if lightningdb.database.get_collection(str(channel.id)) is None: full = True
    existing_message_counter = 0
    async for message in channel.history(limit=None, oldest_first=full):
        try: await lightningdb.post_message(message)
        except mongoErrors.DuplicateKeyError:
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
