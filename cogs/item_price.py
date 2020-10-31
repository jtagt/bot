from discord.ext import commands

from utils import Embed, CommandWithCooldown, get_item_price_stats, get_item_list, get_bazaar_product_prices
from difflib import get_close_matches
from math import floor


class ItemPrice(commands.Cog, name='Item Price'):
    """
    View average prices for items as well as past auctions for any player.
    """

    emoji = '💸'

    def __init__(self, bot):
        self.bot = bot

    # TODO: add check if item is bazaar's item
    @commands.command(cls=CommandWithCooldown, cooldown_after_parsing=True)
    @commands.cooldown(1, 10.0, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.channel, wait=False)
    async def price(self, ctx, *, item_name):
        """
        Displays the average price for any item on the auction or bazaar.
        """

        item_list = await get_item_list(item_name, session=self.bot.http_session)
        bazaar_list = await get_bazaar_product_prices(self.bot.hypixel_api_client)
        best_bazaar_match = get_close_matches(item_name.lower(),
                                              map(lambda item:
                                                  item['quick_status']['productId'].replace('_', ' ').lower(),
                                                  bazaar_list.values()))
        item_ah_adjusted = filter(lambda item_ah: item_ah.get('_source').get('name').lower() not in best_bazaar_match,
                                  item_list)
        item_ah_list = list(map(lambda item_ah: item_ah.get('_source').get('name'), item_ah_adjusted))
        item_bz_fixed = list(map(lambda item_bz: item_bz.title(), best_bazaar_match))
        item_list_merged = item_bz_fixed + item_ah_list

        ans = await ctx.prompt_with_list(item_list_merged, per_page=5,
                                         title='Which item do you want to check price?',
                                         footer='You may enter the corresponding item number.')

        selected_item = item_list_merged[ans - 1]
        if selected_item is None:
            return

        if selected_item.lower() in best_bazaar_match:
            product_id = selected_item.replace(' ', '_').upper()

            buy_list = list(map(lambda summary: summary['pricePerUnit'], bazaar_list[product_id]['buy_summary']))
            buy_list.reverse()

            sell_list = list(map(lambda summary: summary['pricePerUnit'], bazaar_list[product_id]['sell_summary']))

            return await Embed(ctx=ctx, title=f"{selected_item}") \
                .add_field(
                name='Instant Buy',
                value="{:,}".format(floor(bazaar_list[product_id]['quick_status']['buyPrice'])),
                inline=True
            ).add_field(
                name='Instant Sell',
                value="{:,}".format(floor(bazaar_list[product_id]['quick_status']['sellPrice'])),
                inline=True
            ).add_field().add_field(
                name='Buy Offer',
                value="{:,}".format(floor(buy_list[0])),
                inline=True
            ).add_field(
                name='Sell Offer',
                value="{:,}".format(floor(sell_list[0])),
                inline=True
            ).add_field().send()

        selected_ah_item = list(filter(lambda item_ah:
                                       item_ah.get('_source').get('name').lower() in selected_item.lower(),
                                       item_list))[0]
        if selected_ah_item is None:
            return

        item_price_stats = await get_item_price_stats(selected_ah_item['_id'], session=self.bot.http_session)

        if not item_price_stats:
            return await ctx.send(f'{ctx.author.mention}\nThere is no item called `{" ".join(item_name)}`.\n'
                                  f'Or there was a problem connecting to https://auctions.craftlink.xyz/.')

        _deviation = item_price_stats.get("deviation", 0.00)
        _average = item_price_stats.get("average", 0.00)
        _averageBids = item_price_stats.get("averageBids", 0.00)
        _median = item_price_stats.get("median", 0.00)
        _mode = item_price_stats.get("mode", 0.00)
        _averageQuantity = item_price_stats.get("averageQuantity", 0.00)
        _totalSales = item_price_stats.get("totalSales", 0.00)
        _totalBids = item_price_stats.get("totalBids", 0.00)

        await Embed(
            ctx=ctx,
            title=f'{item_price_stats.get("name", item_name)}',
            url=f"https://auctions.craftlink.xyz/items/{selected_ah_item['_id']}"
        ).add_field(
            name='Deviation',
            value=f'{_deviation or 0.00}'
        ).add_field(
            name='Average',
            value=f'{_average or 0.00}'
        ).add_field().add_field(
            name='Median',
            value=f'{_median or 0.00}',
        ).add_field(
            name='Mode',
            value=f'{_mode or 0.00}'
        ).add_field().add_field(
            name='Average bids',
            value=f'{_averageBids or 0.00}'
        ).add_field(
            name='Average quantity',
            value=f'{_averageQuantity or 0.00}'
        ).add_field().add_field(
            name='Total sales',
            value=f'{_totalSales or 0.00}'
        ).add_field(
            name='Total bids',
            value=f'{_totalBids or 0.00}'
        ).send()


def setup(bot):
    bot.add_cog(ItemPrice(bot))
