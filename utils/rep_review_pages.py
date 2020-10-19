import asyncio
import discord

from lib import SessionTimeout
from . import Pages, Embed, embed_timeout_handler


class RepReviewPages(Pages):
    def __init__(self, ctx, entries, categories, user, *, timeout=120.0):
        super().__init__(ctx, entries, per_page=10, timeout=timeout)
        self.paginating = True
        self.user = user
        self.guild = ctx.guild
        self.reps_db = self.bot.db['reputations']
        self.categories = categories
        self.reaction_emojis.append(('📝', self.review_rep))

    def prepare_embed(self, entries, page):
        self.embed.clear_fields()

        page_number = f'\nPage {page} / {self.maximum_pages}.' if self.maximum_pages > 1 else ''
        footer = f'{self.embed_footer}{page_number}'
        self.embed.add_footer(text=footer)

        self.embed.title = f'{self.user.display_name}\'s Unreviewed Reputations'

        for index, rep in enumerate(entries, 1 + ((page - 1) * self.per_page)):
            submitter = self.bot.get_user(rep['submitter_discord_id'])
            self.embed.add_field(
                name=f'{index}. {"Postive" if rep["positive"] else "Negative"} rep from {submitter.name if submitter is not None else rep["submitter_discord_id"]}',
                value=f'Reason: {rep["reason"]}',
                inline=False
            )

    async def show_page(self, page, *, first=False):
        self.current_page = page
        entries = self.get_page(page)
        embed = self.get_embed(entries, page)

        try:
            if not first:
                await self.message.edit(embed=embed)
            else:
                self.message = await self.embed.send()
                for (emoji, _) in self.reaction_emojis:
                    if self.maximum_pages == 1 and emoji in ('\u25c0', '\u25b6'):
                        continue
                    if self.maximum_pages <= 2 and emoji in ('\u23ed', '\u23ee'):
                        continue

                    await self.message.add_reaction(emoji)
        except discord.errors.Forbidden:
            self.paginating = False
            try:
                await self.ctx.send(
                    f'{self.ctx.author.mention}, Sorry, it looks like I don\'t have the permissions or roles to do that.\n'
                    f'Try enabling your DM or contract the server owner to give me more permissions.')
            except Exception:
                pass

    async def review_rep(self):
        to_delete = [await self.ctx.send(f'{self.author.mention}, Enter number of the rep you want to review.')]

        def message_check(m):
            if m.author.id == self.author.id and m.channel.id == self.channel.id:
                if m.clean_content.lower() == 'exit':
                    raise SessionTimeout
                if m.clean_content.isdigit():
                    return True
            return False

        try:
            msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
            to_delete.append(msg)

            if int(msg.clean_content) not in range(1, len(self.entries) + 1):
                to_delete.append(await self.ctx.send(f'{self.author.mention}, Invalid rep number given.'))
            else:
                selected_rep_index = int(msg.clean_content) - 1
                to_delete.append(await self.ctx.send(
                    f'{self.author.mention}, What category do you designate this reputation? (Enter category number)'))
                await self.show_category_page()

                msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
                to_delete.append(msg)

                if int(msg.clean_content) not in range(1, len(self.categories) + 1):
                    to_delete.append(await self.ctx.send(f'{self.author.mention}, Invalid category number given.'))
                else:
                    selected_cate_index = int(msg.clean_content) - 1

                    self.reps_db.update_one({'_id': self.entries[selected_rep_index]['_id']},
                                            {'$set': {'type': self.categories[selected_cate_index]['name'],
                                                      'staff_sorted_discord_id': self.author.id}})
                    self.entries.pop(selected_rep_index)

                    # Recalculate max pages
                    pages, left_over = divmod(len(self.entries), self.per_page)
                    if left_over:
                        pages += 1
                    self.maximum_pages = pages
                    if self.current_page > self.maximum_pages:
                        self.current_page = self.maximum_pages

                    to_delete.append(await self.ctx.send(f'{self.author.mention}, You reviewed a reputation!'))
        except (asyncio.TimeoutError, SessionTimeout):
            to_delete.append(await self.ctx.send(f'{self.author.mention}, Input session closed.'))

        await self.show_page(self.current_page)

        try:
            await asyncio.sleep(4)
            await self.channel.delete_messages(to_delete)
        except Exception:
            pass

    async def show_category_page(self):
        p = []
        for index, category in enumerate(self.categories, start=1):
            p.append(f'{index}. {category["name"]}')

        embed = Embed(
            ctx=self.ctx,
            title=f'Category List',
            description=f'{"".join(p)}'
        )

        await self.message.edit(embed=embed)

    async def paginate(self):
        self.bot.loop.create_task(self.show_page(1, first=True))

        while self.paginating:
            try:
                payload = await self.bot.wait_for('raw_reaction_add', check=self.react_check, timeout=self.timeout)
            except asyncio.TimeoutError as e:
                if not self.paginating:
                    pass
                self.paginating = False
                self.bot.loop.create_task(embed_timeout_handler(self.ctx, self.reaction_emojis, message=self.message))
                raise e from None

            try:
                await self.message.remove_reaction(payload.emoji, discord.Object(id=payload.user_id))
            except Exception:
                pass

            await self.match()
