import asyncio
import discord

from lib import SessionTimeout
from . import Embed, embed_timeout_handler
from constants.db_schema import REP_CATEGORY


class RepConfigPages:
    def __init__(self, ctx, categories, *, timeout=120.0):
        self.ctx = ctx
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.message = ctx.message
        self.channel = ctx.channel
        self.author = ctx.author
        self.embed = Embed(ctx=ctx)
        self.categories = categories
        self.timeout = timeout
        self.match = None
        self.paginating = True
        self.rep_categories_db = self.bot.db['rep_categories']
        self.reaction_emojis = [
            ('🆕', self.add_category),
            ('✏️', self.edit_category),
            ('❌', self.delete_category)
        ]

    async def add_category(self):
        new_category = REP_CATEGORY.copy()
        new_category['guild_id'] = self.guild.id

        to_delete = [await self.ctx.send(f'{self.author.mention}, Enter name for the category you want to add.')]

        def message_check(m):
            if m.author.id == self.author.id and m.channel.id == self.channel.id:
                if m.clean_content.lower() == 'exit':
                    raise SessionTimeout
                return True
            return False

        try:
            msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
            to_delete.append(msg)

            for category in self.categories:
                if msg.clean_content == category['name']:
                    to_delete.append(await self.ctx.send(f'{self.author.mention}, This category already exists.'))
                    break
            else:
                new_category['name'] = msg.clean_content

                to_delete.append(
                    await self.ctx.send(f'{self.author.mention}, Enter description for the category you want to add.'))

                msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
                to_delete.append(msg)
                new_category['description'] = msg.clean_content

                await self.rep_categories_db.insert_one(new_category)
                self.categories.append(new_category)

                to_delete.append(await self.ctx.send(f'{self.author.mention}, You created a new category!'))
                await self.send_embed()
        except (asyncio.TimeoutError, SessionTimeout):
            to_delete.append(await self.ctx.send(f'{self.author.mention}, Input session closed.'))

        try:
            await asyncio.sleep(4)
            await self.channel.delete_messages(to_delete)
        except Exception:
            pass

    async def edit_category(self):
        to_delete = [await self.ctx.send(f'{self.author.mention}, Enter the name of category you want to edit.')]

        def message_check(m):
            if m.author.id == self.author.id and m.channel.id == self.channel.id:
                if m.clean_content.lower() == 'exit':
                    raise SessionTimeout
                return True
            return False

        try:
            msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
            to_delete.append(msg)
            for category in self.categories:
                if msg.clean_content == category['name']:
                    to_delete.append(await self.ctx.send(f'{self.author.mention}, Enter new name for this category.'))
                    msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
                    to_delete.append(msg)

                    if msg.clean_content in [c['name'] for c in self.categories if c['name'] != category['name']]:
                        to_delete.append(await self.ctx.send(f'{self.author.mention}, This category already exists.'))
                        break

                    new_name = msg.clean_content
                    to_delete.append(
                        await self.ctx.send(f'{self.author.mention}, Enter new description for this category.'))
                    msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
                    to_delete.append(msg)
                    new_description = msg.clean_content

                    await self.rep_categories_db.update_one({'_id': category["_id"]}, {
                        '$set': {'name': new_name, 'description': new_description}})
                    category['name'] = new_name
                    category['description'] = new_description

                    to_delete.append(await self.ctx.send(f'{self.author.mention}, You edited a category!'))
                    await self.send_embed()
                    break
            else:
                to_delete.append(await self.ctx.send(f'{self.author.mention}, Invalid category name.'))
        except (asyncio.TimeoutError, SessionTimeout):
            to_delete.append(await self.ctx.send(f'{self.author.mention}, Input session closed.'))

        try:
            await asyncio.sleep(4)
            await self.channel.delete_messages(to_delete)
        except Exception:
            pass

    async def delete_category(self):
        to_delete = [await self.ctx.send(f'{self.author.mention}, Enter the name of category you want to delete.')]

        def message_check(m):
            if m.author.id == self.author.id and m.channel.id == self.channel.id:
                if m.clean_content.lower() == 'exit':
                    raise SessionTimeout
                return True
            return False

        try:
            msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
            to_delete.append(msg)
            for category in self.categories[:]:
                if msg.clean_content == category['name']:
                    await self.rep_categories_db.delete_one({'guild_id': self.guild.id, 'name': msg.clean_content})
                    self.categories.remove(category)

                    to_delete.append(await self.ctx.send(f'{self.author.mention}, You deleted a catergory!'))
                    await self.send_embed()
                    break
            else:
                to_delete.append(await self.ctx.send(f'{self.author.mention}, Invalid category name.'))
        except (asyncio.TimeoutError, SessionTimeout):
            to_delete.append(await self.ctx.send(f'{self.author.mention}, Input session closed.'))

        try:
            await asyncio.sleep(4)
            await self.channel.delete_messages(to_delete)
        except Exception:
            pass

    async def send_embed(self, *, first=False):
        self.embed.title = 'Reputation Categories Configuration'
        self.embed.clear_fields()

        if not self.categories:
            self.embed.add_field(name='There is currently no category.', inline=False)
        else:
            for category in self.categories:
                self.embed.add_field(
                    name=f'{category["name"]}',
                    value=f'{category["description"]}',
                    inline=False
                )

        try:
            if first:
                self.message = await self.embed.send()
                for (emoji, _) in self.reaction_emojis:
                    await self.message.add_reaction(emoji)
            else:
                await self.message.edit(embed=self.embed)
        except discord.errors.Forbidden:
            self.paginating = False
            try:
                await self.ctx.send(
                    f'{self.ctx.author.mention}, Sorry, it looks like I don\'t have the permissions or roles to do that.\n'
                    f'Try enabling your DM or contract the server owner to give me more permissions.')
            except Exception:
                pass

    def react_check(self, payload):
        if payload.user_id != self.author.id:
            return False

        if payload.message_id != self.message.id:
            return False

        to_check = str(payload.emoji)
        for (emoji, func) in self.reaction_emojis:
            if to_check == emoji:
                self.match = func
                return True
        return False

    async def paginate(self):
        self.bot.loop.create_task(self.send_embed(first=True))

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
