"""This cog contains privacy module commands and functions"""

import codecs
import json
import os
import shutil
import textwrap
import typing

import discord
import py7zr
from discord import app_commands
from discord.ext import commands

import database
import lightningdb
import utility

# =============================================================================


class Privacy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis: dict[str, discord.Emoji] = bot.get_cog('Cyberlog').emojis

    @commands.hybrid_command()
    async def privacy(self, ctx: commands.Context):
        """
        View and edit your privacy settings
        """
        user = await utility.get_user(ctx.author)
        privacy = user['privacy']

        def slideToggle(i):
            return (
                self.emojis['slideToggleOff'] if i == 0 else self.emojis['slideToggleOn'] if i == 1 else slideToggle(privacy['default'][0])
            )  # Uses recursion to use default value if specific setting says to

        def viewerEmoji(i):
            return '🔒' if i == 0 else '🔓' if i == 1 else viewerEmoji(privacy['default'][1]) if i == 2 else self.emojis['members']

        def viewerText(i):
            return (
                'only you'
                if i == 0
                else 'everyone you share a server with'
                if i == 1
                else viewerText(privacy['default'][1])
                if i == 2
                else f'{len(i)} users'
            )

        def enabled(i):
            return False if i == 0 else True if i == 1 else enabled(privacy['default'][0])

        embed = discord.Embed(title=f'Privacy Settings » {ctx.author.display_name} » Overview', color=utility.YELLOW[1])
        embed.description = """To view Disguard's privacy policy, [click here](https://disguard.netlify.app/privacybasic)\nTo view and edit all settings, visit your profile on my [web dashboard](http://disguard.herokuapp.com/manage/profile)"""
        embed.add_field(
            name='Default Settings',
            value=f"""{slideToggle(privacy['default'][0])}Allow Disguard to use your customization settings for its features: {"Enabled" if enabled(privacy['default'][0]) else "Disabled"}\n{viewerEmoji(privacy['default'][1])}Default visibility of your customization settings: {viewerText(privacy['default'][1])}""",
            inline=False,
        )
        embed.add_field(
            name='Personal Profile Features',
            value=f"""{slideToggle(privacy['profile'][0])}{"Enabled" if enabled(privacy['profile'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['profile'][1])}Personal profile features: Visible to {viewerText(privacy['profile'][1])}" if enabled(privacy['profile'][0]) else ""}""",
            inline=False,
        )
        embed.add_field(
            name='Birthday Module Features',
            value=f"""{slideToggle(privacy['birthdayModule'][0])}{"Enabled" if enabled(privacy['birthdayModule'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['birthdayModule'][1])}Birthday profile features: Visible to {viewerText(privacy['birthdayModule'][1])}" if enabled(privacy['birthdayModule'][0]) else ""}""",
            inline=False,
        )
        embed.add_field(
            name='Attribute History',
            value=f"""{slideToggle(privacy['attributeHistory'][0])}{"Enabled" if enabled(privacy['attributeHistory'][0]) else "Disabled"}\n{f"{viewerEmoji(privacy['attributeHistory'][1])}Attribute History: Visible to {viewerText(privacy['attributeHistory'][1])}" if enabled(privacy['attributeHistory'][0]) else ""}""",
            inline=False,
        )
        await ctx.send(embed=embed)

    @app_commands.command(description='Request a copy of your data that Disguard stores')
    async def data(self, interaction: discord.Interaction, compression_format: typing.Literal['zip', '7z']):
        """
        Request a copy of your data that Disguard stores
        -------------------------------------------------
        Parameters:
        compression_format: str
            The format to compress the data into. Must be either "zip" or "7z"
        """
        template = textwrap.dedent(f"""
            • I will create a `.{compression_format}` file containing all relevant data about you from each applicable server
            • All data will be exported to `.json` format, which can be opened in any text editor or web browser
            • If you have Administrator permissions in a server, one of the exported files for that server will be the entire database entry for that server
            • You will also receive a file containing your global user data (which is not linked to server-specific data)
        """)
        await interaction.response.send_message(f"{template}\n{self.emojis['loading']}Retrieving data...")
        base_path = f'Attachments/Temp/{utility.date_to_filename(discord.utils.utcnow())}'
        if not os.path.exists(base_path):
            os.makedirs(base_path)
        user_data = await database.GetUser(interaction.user)
        # global user data
        if user_data:
            user_data.pop('_id')
            user_dumps = json.dumps(user_data, indent=4, default=utility.serialize_json)
            attachment_count = 0
            with open(f'{base_path}/{utility.sanitize_filename(str(interaction.user))}_-_UserData.json', 'w+') as f:
                f.write(user_dumps)
        # each server's data
        for server in [g for g in self.bot.guilds if interaction.user in g.members]:
            member = server.get_member(interaction.user.id)
            server_path = f'{base_path}/{utility.sanitize_filename(server.name)}'
            attachments_path = f'{server_path}/MessageAttachments'
            if not os.path.exists(attachments_path):
                os.makedirs(attachments_path)
            if any(role.permissions.administrator for role in member.roles) or server.owner.id == member.id:
                # try: os.makedirs(serverPath)
                # except FileExistsError: pass
                server_data = await database.GetServer(server)
                if server_data:
                    server_data.pop('_id')
                    server_dumps = json.dumps(server_data, indent=4, default=utility.serialize_json)
                    with open(f'{server_path}/ServerDatabaseEntry.json', 'w+') as f:
                        f.write(server_dumps)
            member_dumps = json.dumps(await lightningdb.get_member(server.id, member.id), indent=4, default=utility.serialize_json)
            with open(f'{server_path}/ServerMemberInfo.json', 'w+') as f:
                f.write(member_dumps)
            for channel in server.text_channels:
                index_data = await lightningdb.get_messages_by_author(member.id, [channel.id])
                if not index_data:
                    continue
                filtered_index_data = {}
                # pull metadata from first index
                index_path = f'{server_path}/MessageIndexes'
                if not os.path.exists(index_path):
                    os.makedirs(index_path)
                for message_id, data in index_data[0].items():
                    filtered_index_data.update({message_id: data})
                    try:
                        attachment_path = f'Attachments/{server.id}/{channel.id}/{message_id}'
                        attachment_count += len(os.listdir(attachment_path))
                    except FileNotFoundError:
                        pass
                if filtered_index_data:
                    with open(f'{attachments_path}/{utility.sanitize_filename(channel.name)}.json', 'w+') as f:
                        f.write(json.dumps(filtered_index_data, indent=4))
            if attachment_count:
                with open(f'{attachments_path}/README.txt', 'w+') as f:
                    f.write(
                        textwrap.dedent(f"""
                        I also have {attachment_count} file attachments that you've uploaded over time, but I can't attach them due to the upload size limit. If you would like to receive these files, contact my support team in one of the following ways:
                            •Use the `invite` command to join my support server and each out to my team
                            •Use the `ticket` command to open a support ticket with my team
                    """)
                    )
        readme = textwrap.dedent("""
            Directory Format\n
            📁DisguardUserDataRequest_[Timestamp]
            |-- 📄UserData.json --> Contains the database entry for your global data, not specific to a server
            |-- 📁[Server name] --> Contains the data for this server
            |-- |-- 📄ServerDatabaseEntry.json --> The whole database entry for this server (server admin only)
            |-- |-- 📄Server-MemberInfo.json --> Contains your member data entry for this server
            |-- |-- 📁MessageAttachments --> Contains a ReadMe file explaining how to obtain message attachment data
            |-- |-- 📁MessageIndexes --> Contains message indexes authored by you for this server
            |-- |-- |-- 📄[Channel name].json --> File containing message indexes authored by you for this channel\n
            This ReadMe is also saved just inside of the zipped folder. Any text editor can open JSON files, along with web browsers (drag the file into new tab area or use ctrl + o in your web browser)\n
            If you need any further assistance, the `invite` command` will provide you with a link to my support server, and the `ticket` command will open a support ticket with my team
        """)
        with codecs.open(f'{base_path}/README.txt', 'w+', 'utf-8-sig') as f:
            f.write(readme)
        fileName = f'Attachments/Temp/DisguardUserDataRequest_{utility.date_to_filename(discord.utils.utcnow())}'
        await interaction.edit_original_response(content=f"{template}\n{self.emojis['loading']}Zipping data...")
        shutil.register_archive_format('7zip', py7zr.pack_7zarchive, description='7zip archive')
        shutil.make_archive(fileName, '7zip' if compression_format == '7z' else 'zip', base_path)
        archive = discord.File(f'{fileName}.{compression_format}')
        await interaction.delete_original_response()
        await interaction.followup.send(content=f'```{readme}```', file=archive, ephemeral=not interaction.channel.is_private())

    @commands.hybrid_command()
    async def delete(ctx: commands.Context, message_id: str):
        """Delete one of Disguard\'s messages from the user\'s DMs
        Parameters
        ----------
        message_id : str
            The ID of the message to delete
        """
        try:
            message = await ctx.author.fetch_message(int(message_id))
            await message.delete()
            await ctx.send('✅Successfully deleted the message', ephemeral=True)
        except Exception as e:
            await ctx.send(f'❌An error occurred: {e}', ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Privacy(bot))
