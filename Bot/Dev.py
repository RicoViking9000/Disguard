'''Cog that contains Disguard's dev-only commands'''

import inspect
import discord
from discord import app_commands
from discord.ext import commands
import utility
import Support
import textwrap
# =============================================================================

def team_check():
    '''Ensures dev commands are only run by Disguard developers'''
    print('running team check')
    async def predicate(ctx: commands.Context) -> bool:
        return ctx.interaction.user in (await ctx.bot.application_info()).team.members
    return commands.check(predicate)

class Dev(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis: dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis

    @commands.group(fallback='help', invoke_without_command=True)
    async def dev(self, ctx: commands.Context):
        '''View or execute dev commands'''
        pass
    
    @dev.command(name='verify_database', guild=discord.Object(utility.DISGUARD_SERVER_ID))
    async def verify_database(self, ctx: commands.Context):
        '''Verify the database'''
        await ctx.send('Verifying database...')
        await ctx.send('Database verified!')

    @dev.command(name='index_server', guild=discord.Object(utility.DISGUARD_SERVER_ID))
    async def index_server(self, ctx: commands.Context):
        '''Index the server'''
        await ctx.send('Indexing server...')
        await ctx.send('Server indexed!')
    
    @dev.command(name='index_channel', guild=discord.Object(utility.DISGUARD_SERVER_ID))
    async def index_channel(self, ctx: commands.Context):
        '''Index the channel'''
        await ctx.send('Indexing channel...')
        await ctx.send('Channel indexed!')
    
    @dev.command(name='eval', guild=discord.Object(utility.DISGUARD_SERVER_ID))
    async def eval(self, ctx: commands.Context, *, code: str):
        '''Evaluate code'''
        code = textwrap.dedent(code)
        env = {
            'bot': self.bot,
            'ctx': ctx,
            'discord': discord,
            'commands': commands,
            'utility': utility,
            'Support': Support,
            'textwrap': textwrap,
            'self': self
        }
        env.update(globals())
        try:
            result = eval(code, env)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
        else:
            await ctx.send(f'```py\n{result}\n```')
    
    @dev.command(name='get_log_file', guild=discord.Object(utility.DISGUARD_SERVER_ID))
    async def get_log_file(self, ctx: commands.Context):
        '''Get the log file'''
        await ctx.send(file=discord.File('discord.log'))

    @dev.command(name='sync')
    async def sync_tree(self, ctx: commands.Context):
        '''Sync the tree'''
        print('syncing...')
        await self.bot.tree.sync()
        await self.bot.tree.sync(guild=discord.Object(utility.DISGUARD_SERVER_ID))
        await ctx.send('Synced tree')
        print('synced')

    @dev.command(name='clear_commands', guild=discord.Object(utility.DISGUARD_SERVER_ID))
    async def clear_commands(self, ctx: commands.Context):
        '''Clear the command cache'''
        await self.bot.tree.clear_commands()
        await self.bot.tree.sync()
        await ctx.send('Cleared tree')


async def setup(bot: commands.Bot):
    await bot.add_cog(Dev(bot))
