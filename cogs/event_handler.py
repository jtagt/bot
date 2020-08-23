import discord
from discord.ext import commands
import time

from utils import get_guild_config
from constants.discord import SKYBLOCK_EVENTS


class EventHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Start all skyblock event schedules
        cog = self.bot.get_cog('Skyblock')
        text = ''
        for event in SKYBLOCK_EVENTS.keys():
            text += await cog.schedule_event(event)
        print(text)

        print(f'Logged on as {self.bot.user}! (ID: {self.bot.user.id})')

    @commands.Cog.listener()
    async def on_command(self, ctx):
        filtered_args = ctx.message.clean_content.split()[2:] or []
        print(f'{ctx.author} used {ctx.command} {filtered_args} in '
              f'{"a DM" if isinstance(ctx.channel, discord.DMChannel) else ctx.guild.name} '
              f'at {ctx.message.created_at}.')

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        """
        Executes when a guild updates.
        """
        # Skip blacklisted guilds
        if before.id in self.bot.blacklisted_guild_ids:
            return

        to_update = {}
        if before.name != after.name:
            to_update.update({'name': after.name})
        if str(before.icon_url) != str(after.icon_url):
            to_update.update({'icon': str(after.icon_url)})
        if str(before.banner_url) != str(before.banner_url):
            to_update.update({'banner': str(after.icon_url)})

        if to_update:
            to_update.update({'last_update': int(time.time())})
            await self.bot.db['guilds'].update_one({'_id': before.id}, {'$set': to_update})

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """
        Executes when bot joins a guild.
        """
        await get_guild_config(self.bot.db['guilds'], guild=guild)


def setup(bot):
    bot.add_cog(EventHandler(bot))
