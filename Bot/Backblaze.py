import typing

import b2sdk.v2
from discord.ext import commands

import secure

PROD_BOT_ID = 558025201753784323
PROD_BUCKET = 'disguard'
PROD_CREDS = secure.backblaze()
BETA_BUCKET = 'disguard-beta'
BETA_CREDS = secure.backblaze_beta()


class Backblaze(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prod = self.bot.user.id == PROD_BOT_ID
        bucket_name = PROD_BUCKET if self.prod else BETA_BUCKET
        self.backblaze = self.setup_backblaze(bucket_name)
        self.url_head = f'https://{bucket_name}.s3.us-east-005.backblazeb2.com/'

    def setup_backblaze(self, bucket_name: str) -> b2sdk.v2.Bucket:
        info = b2sdk.v2.InMemoryAccountInfo()
        b2_api = b2sdk.v2.B2Api(info)
        application_key_id = PROD_CREDS['keyId'] if self.prod else BETA_CREDS['keyId']
        application_key = PROD_CREDS['applicationKey'] if self.prod else BETA_CREDS['applicationKey']
        b2_api.authorize_account('production', application_key_id, application_key)
        bucket = b2_api.get_bucket_by_name(bucket_name)
        return bucket

    def direct_file_url(self, file_path: str) -> str:
        if not file_path:
            return ''
        return self.url_head + file_path.replace(' ', '%20')

    async def upload_disk_file(self, file_path: str, file_name: str) -> b2sdk.v2.FileVersion:
        with open(file_path, 'rb') as f:
            return await self.backblaze.upload_bytes(f.read(), file_name)

    async def upload_bytes(self, data: bytes, file_name: str) -> b2sdk.v2.FileVersion:
        return self.backblaze.upload_bytes(data, file_name)

    def download_and_save_file(self, file_name: str, save_path) -> bytes:
        return self.backblaze.download_file_by_name(file_name).save(save_path)

    def ls(self, dir: str, recursive: bool = False) -> typing.Iterator[tuple[b2sdk.v2.FileVersion, str]]:
        return self.backblaze.ls(dir, recursive=recursive)

    def delete_file(self, file_id: str, file_name: str) -> None:
        self.backblaze.delete_file_version(file_id, file_name)


async def setup(bot: commands.Bot):
    await bot.add_cog(Backblaze(bot))
