import discord
from discord.ext import commands
import time

from utils import Embed, CommandWithCooldown, GroupWithCooldown, RepConfigPages, RepReviewPages, checks
from constants.db_schema import REPUTATION


class Reputation(commands.Cog, name='Skyblock'):
    def __init__(self, bot):
        self.bot = bot
        self.reps_db = bot.db['reputations']
        self.rep_categories_db = bot.db['rep_categories']

    @commands.command(name='+rep', cls=CommandWithCooldown, cooldown_after_parsing=True)
    @commands.cooldown(1, 60.0, commands.BucketType.member)
    @commands.guild_only()
    @checks.is_player_verified()
    async def positive_rep(self, ctx, player: discord.Member, *, reason: str):
        """
        Give a player a postive reputation.
        """
        if ctx.author == player:
            return await ctx.send(f'{ctx.author.mention}, You can\'t rep yourself.')

        rep = REPUTATION.copy()
        rep['guild_id'] = ctx.guild.id
        rep['reported_discord_id'] = player.id
        rep['submitter_discord_id'] = ctx.author.id
        rep['reason'] = reason
        rep['submitted_timestamp'] = int(time.time())

        await self.reps_db.insert_one(rep)

        await ctx.send(f'{ctx.author.mention}\nYou gave {player.name} a positive rep!')

    @commands.command(name='-rep', cls=CommandWithCooldown, cooldown_after_parsing=True)
    @commands.cooldown(1, 60.0, commands.BucketType.member)
    @commands.guild_only()
    @checks.is_player_verified()
    async def negative_rep(self, ctx, player: discord.Member, *, reason: str):
        """
        Give a player a negative reputation.
        """
        if ctx.author == player:
            return await ctx.send(f'{ctx.author.mention}, You can\'t rep yourself.')

        rep = REPUTATION.copy()
        rep['guild_id'] = ctx.guild.id
        rep['reported_discord_id'] = player.id
        rep['submitter_discord_id'] = ctx.author.id
        rep['reason'] = reason
        rep['positive'] = False
        rep['submitted_timestamp'] = int(time.time())

        await self.reps_db.insert_one(rep)

        await ctx.send(f'{ctx.author.mention}\nYou gave {player.name} a negative rep!')

    @commands.group(cls=GroupWithCooldown, cooldown_after_parsing=True, invoke_without_command=True)
    @commands.cooldown(1, 10.0, commands.BucketType.member)
    @commands.guild_only()
    @checks.is_player_verified()
    async def rep(self, ctx, player: discord.Member):
        """
        Command to check user's reviewed reputation in this discord server.
        """
        positive_reviewed_reps = []
        positive_unreviewed_reps = []
        negative_reviewed_reps = []
        negative_unreviewed_reps = []

        async for rep in self.reps_db.find({'guild_id': ctx.guild.id, 'reported_discord_id': player.id}):
            if rep['type'] is None and rep['positive']:
                positive_unreviewed_reps.append(rep)
            elif rep['type'] is None and not rep['positive']:
                negative_unreviewed_reps.append(rep)
            elif rep['type'] is not None and rep['positive']:
                positive_reviewed_reps.append(rep)
            elif rep['type'] is not None and not rep['positive']:
                negative_reviewed_reps.append(rep)

        embed = Embed(
            ctx=ctx,
            title=f'{player.name} Reputations',
        ).add_field(
            name='All Positive Reps',
            value=f'{len(positive_reviewed_reps)}'
        ).add_field(
            name='All Negative Reps',
            value=f'{len(negative_reviewed_reps)}'
        )

        async for category in self.rep_categories_db.find({'guild_id': ctx.guild.id}):
            category_reps = [rep for rep in positive_reviewed_reps + negative_reviewed_reps if
                             rep['type'] == category['name']]
            embed.add_field(
                name=f'{category["name"]}',
                value=f'{len(category_reps)}'
            )

        await embed.add_field(
            name=f'Unreviewed',
            value=f'{len(negative_unreviewed_reps) + len(positive_unreviewed_reps)}'
        ).send()

    @rep.command()
    @checks.is_guild_admin()
    @checks.is_player_verified()
    async def config(self, ctx):
        """
        Command to config reputation categories for discord server.
        """
        categories = []
        async for category in self.rep_categories_db.find({'guild_id': ctx.guild.id}):
            categories.append(category)

        rep_config_pages = RepConfigPages(ctx, categories)
        await rep_config_pages.paginate()

    @rep.command()
    @checks.is_guild_mod()
    @checks.is_player_verified()
    async def review(self, ctx, player: discord.Member):
        """
        Command to review/sort reputations of a player.
        """
        unreviewed_reps = []
        async for rep in self.reps_db.find({'guild_id': ctx.guild.id, 'reported_discord_id': player.id, 'type': None}):
            unreviewed_reps.append(rep)

        categories = []
        async for category in self.rep_categories_db.find({'guild_id': ctx.guild.id}):
            categories.append(category)

        if not categories:
            return await ctx.send(f'{ctx.author.mention}, There is no category to designate reputation to!')

        rep_review_pages = RepReviewPages(ctx, unreviewed_reps, categories, player)
        await rep_review_pages.paginate()


def setup(bot):
    bot.add_cog(Reputation(bot))
