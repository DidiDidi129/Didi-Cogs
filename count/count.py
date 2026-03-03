import asyncio

import discord
from redbot.core import commands, Config


ITEMS_PER_PAGE = 10
LEADERBOARD_UPDATE_INTERVAL = 10  # seconds between persistent leaderboard edits


class SaveView(discord.ui.View):
    """Accept / Deny buttons shown when a save is available."""

    def __init__(self, user_id):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.result = None

    @discord.ui.button(label="Use Save", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "Only the person who broke the count can decide.", ephemeral=True
            )
        self.result = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Don't Save", style=discord.ButtonStyle.danger)
    async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "Only the person who broke the count can decide.", ephemeral=True
            )
        self.result = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class LeaderboardView(discord.ui.View):
    """Paginated view for the counting leaderboard."""

    def __init__(self, pages, current_count, high_score, saves_enabled=False, saves=0, counts_until_save=0):
        super().__init__(timeout=120)
        self.pages = pages
        self.current_page = 0
        self.current_count = current_count
        self.high_score = high_score
        self.saves_enabled = saves_enabled
        self.saves = saves
        self.counts_until_save = counts_until_save
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    def build_embed(self):
        embed = discord.Embed(
            title="Counting Leaderboard",
            color=discord.Color.gold(),
        )
        description = ""
        if self.saves_enabled and self.counts_until_save > 0:
            description += f"**{self.counts_until_save}** successful count(s) until next save!\n\n"
        description += self.pages[self.current_page]
        embed.description = description
        footer = f"High Score: {self.high_score}"
        if self.saves_enabled:
            footer += f" | Saves: {self.saves}"
        if len(self.pages) > 1:
            footer = f"Page {self.current_page + 1}/{len(self.pages)} | {footer}"
        embed.set_footer(text=footer)
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class Count(commands.Cog):
    """A counting game for your server."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9517538264, force_registration=True)
        default_guild = {
            "channel_id": None,
            "current_count": 0,
            "last_counter_id": None,
            "counts": {},
            "high_score": 0,
            "emoji": "✅",
            "saves_enabled": False,
            "saves": 0,
            "save_interval": 1000,
            "total_counts": 0,
            "funnyreactions": False,
            "leaderboard_channel_id": None,
            "leaderboard_message_id": None,
        }
        self.config.register_guild(**default_guild)
        self._lb_update_tasks = {}  # guild_id -> asyncio.Task

    def cog_unload(self):
        for task in self._lb_update_tasks.values():
            task.cancel()
        self._lb_update_tasks.clear()

    # Number → keycap digit emoji mapping used for funny reactions
    _DIGIT_EMOJIS = {
        "0": "0️⃣",
        "1": "1️⃣",
        "2": "2️⃣",
        "3": "3️⃣",
        "4": "4️⃣",
        "5": "5️⃣",
        "6": "6️⃣",
        "7": "7️⃣",
        "8": "8️⃣",
        "9": "9️⃣",
    }
    _FUNNY_NUMBERS = {67, 69, 420}
    _SKULL_EMOJI = "💀"

    # ---------------------------
    # Helpers
    # ---------------------------
    def _parse_number(self, content):
        """Try to interpret *content* as the next count value.

        Returns ``int`` on success, ``None`` on failure.
        """
        try:
            return int(content)
        except ValueError:
            return None

    async def _handle_break(self, message, reason):
        """Handle a count break, optionally offering a save."""
        guild = message.guild
        current_count = await self.config.guild(guild).current_count()
        saves_enabled = await self.config.guild(guild).saves_enabled()
        saves = await self.config.guild(guild).saves() if saves_enabled else 0

        if saves_enabled and saves > 0 and current_count > 0:
            view = SaveView(message.author.id)
            save_msg = await message.channel.send(
                f"{message.author.mention} {reason} "
                f"Your server has **{saves}** save(s). "
                f"Would you like to use one to restore the count to **{current_count}**?",
                view=view,
            )
            await view.wait()

            if view.result is True:
                await self.config.guild(guild).saves.set(saves - 1)
                await self.config.guild(guild).last_counter_id.set(None)
                await save_msg.edit(
                    content=(
                        f"🛡️ Save used! The count has been restored to **{current_count}**. "
                        f"Remaining saves: **{saves - 1}**"
                    ),
                    view=None,
                )
                return

            # Denied or timed out
            await self.config.guild(guild).current_count.set(0)
            await self.config.guild(guild).last_counter_id.set(None)
            if view.result is False:
                await save_msg.edit(
                    content=(
                        f"{message.author.mention} {reason} "
                        f"The count has been broken. Restart from **1**."
                    ),
                    view=None,
                )
            else:
                await save_msg.edit(
                    content=(
                        f"{message.author.mention} {reason} "
                        f"No response received. The count has been broken. Restart from **1**."
                    ),
                    view=None,
                )
        else:
            await message.channel.send(
                f"{message.author.mention} {reason} "
                f"The count has been broken. Restart from **1**."
            )
            await self.config.guild(guild).current_count.set(0)
            await self.config.guild(guild).last_counter_id.set(None)

        self._schedule_leaderboard_update(guild)

    # ---------------------------
    # Counting listener
    # ---------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        channel_id = await self.config.guild(message.guild).channel_id()
        if channel_id is None or message.channel.id != channel_id:
            return

        current_count = await self.config.guild(message.guild).current_count()
        last_counter_id = await self.config.guild(message.guild).last_counter_id()
        expected = current_count + 1

        content = message.content.strip()
        number = self._parse_number(content)

        if number is None:
            await self._handle_break(message, "That's not a valid number!")
            return

        if message.author.id == last_counter_id:
            try:
                await message.delete()
            except (discord.HTTPException, discord.Forbidden):
                pass
            await message.channel.send(
                f"{message.author.mention} Can't count consecutively, wait for your turn!"
            )
            return

        if number != expected:
            await self._handle_break(message, "Wrong number!")
            return

        # Valid count
        await self.config.guild(message.guild).current_count.set(number)
        await self.config.guild(message.guild).last_counter_id.set(message.author.id)

        # Update high score if current count exceeds it
        high_score = await self.config.guild(message.guild).high_score()
        if number > high_score:
            await self.config.guild(message.guild).high_score.set(number)

        async with self.config.guild(message.guild).counts() as counts:
            user_id = str(message.author.id)
            counts[user_id] = counts.get(user_id, 0) + 1

        # Award a save every <save_interval> counts
        saves_enabled = await self.config.guild(message.guild).saves_enabled()
        if saves_enabled:
            total_counts = await self.config.guild(message.guild).total_counts()
            total_counts += 1
            await self.config.guild(message.guild).total_counts.set(total_counts)
            save_interval = await self.config.guild(message.guild).save_interval()
            if save_interval > 0 and total_counts % save_interval == 0:
                saves = await self.config.guild(message.guild).saves()
                await self.config.guild(message.guild).saves.set(saves + 1)
                await message.channel.send(
                    f"🛡️ The server earned a save! Total saves: **{saves + 1}**"
                )

        emoji = await self.config.guild(message.guild).emoji()
        funnyreactions = await self.config.guild(message.guild).funnyreactions()

        if funnyreactions and number in self._FUNNY_NUMBERS:
            # Configured emoji first, then one emoji per digit, then skull
            reactions = [emoji] + [self._DIGIT_EMOJIS[d] for d in str(number)] + [self._SKULL_EMOJI]
        else:
            reactions = [emoji]

        for reaction in reactions:
            try:
                await message.add_reaction(reaction)
            except (discord.HTTPException, discord.NotFound):
                if reaction == emoji:
                    await message.add_reaction("✅")

        self._schedule_leaderboard_update(message.guild)

    # ---------------------------
    # Leaderboard helpers
    # ---------------------------
    @staticmethod
    def _build_leaderboard_pages(sorted_counts, guild):
        """Build paginated leaderboard pages in tabular format."""
        pages = []
        for i in range(0, len(sorted_counts), ITEMS_PER_PAGE):
            chunk = sorted_counts[i : i + ITEMS_PER_PAGE]
            # Determine column widths dynamically
            names = []
            for user_id, _ in chunk:
                member = guild.get_member(int(user_id))
                name = member.display_name if member else f"Unknown ({user_id})"
                if len(name) > 20:
                    name = name[:17] + "..."
                names.append(name)
            name_width = max(len(n) for n in names)
            name_width = max(name_width, 4)  # minimum width for "User"

            header = f"{'#':>3} {'User':<{name_width}} {'Count':>5}"
            separator = f"{'-' * 3} {'-' * name_width} {'-' * 5}"
            lines = [header, separator]
            for idx, ((user_id, total), name) in enumerate(zip(chunk, names)):
                rank = i + idx + 1
                lines.append(f"{rank:>3} {name:<{name_width}} {total:>5}")
            pages.append("```\n" + "\n".join(lines) + "\n```")
        return pages

    # ---------------------------
    # Persistent leaderboard
    # ---------------------------
    async def _build_persistent_leaderboard_embed(self, guild):
        """Build a standalone embed for the persistent leaderboard."""
        counts = await self.config.guild(guild).counts()
        current_count = await self.config.guild(guild).current_count()
        high_score = await self.config.guild(guild).high_score()
        saves_enabled = await self.config.guild(guild).saves_enabled()
        saves = await self.config.guild(guild).saves() if saves_enabled else 0

        embed = discord.Embed(
            title="Counting Leaderboard",
            color=discord.Color.gold(),
        )

        if not counts:
            embed.description = "No counting data yet!"
        else:
            sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            pages = self._build_leaderboard_pages(sorted_counts, guild)

            description = ""
            if saves_enabled:
                total_counts = await self.config.guild(guild).total_counts()
                save_interval = await self.config.guild(guild).save_interval()
                if save_interval > 0:
                    counts_until_save = save_interval - (total_counts % save_interval)
                    description += f"**{counts_until_save}** successful count(s) until next save!\n\n"

            if pages:
                description += pages[0]
            embed.description = description.rstrip()

        footer = f"Current Count: {current_count} | High Score: {high_score}"
        if saves_enabled:
            footer += f" | Saves: {saves}"
        embed.set_footer(text=footer)
        return embed

    async def _update_persistent_leaderboard(self, guild_id):
        """Edit the persistent leaderboard message with fresh data."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return

        lb_channel_id = await self.config.guild(guild).leaderboard_channel_id()
        lb_message_id = await self.config.guild(guild).leaderboard_message_id()
        if lb_channel_id is None or lb_message_id is None:
            return

        channel = guild.get_channel(lb_channel_id)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(lb_message_id)
        except (discord.NotFound, discord.HTTPException):
            await self.config.guild(guild).leaderboard_channel_id.set(None)
            await self.config.guild(guild).leaderboard_message_id.set(None)
            return

        embed = await self._build_persistent_leaderboard_embed(guild)
        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

    def _schedule_leaderboard_update(self, guild):
        """Schedule a rate-limited update of the persistent leaderboard."""
        guild_id = guild.id
        if guild_id in self._lb_update_tasks and not self._lb_update_tasks[guild_id].done():
            return  # update already pending

        async def _delayed_update():
            await asyncio.sleep(LEADERBOARD_UPDATE_INTERVAL)
            try:
                await self._update_persistent_leaderboard(guild_id)
            finally:
                self._lb_update_tasks.pop(guild_id, None)

        self._lb_update_tasks[guild_id] = asyncio.create_task(_delayed_update())

    # ---------------------------
    # Leaderboard
    # ---------------------------
    @commands.command(name="countleaderboard", aliases=["countlb"])
    @commands.guild_only()
    async def countleaderboard(self, ctx):
        """Show the counting game leaderboard."""
        counts = await self.config.guild(ctx.guild).counts()
        if not counts:
            return await ctx.send("No counting data yet!")

        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        pages = self._build_leaderboard_pages(sorted_counts, ctx.guild)

        current_count = await self.config.guild(ctx.guild).current_count()
        high_score = await self.config.guild(ctx.guild).high_score()
        saves_enabled = await self.config.guild(ctx.guild).saves_enabled()
        saves = await self.config.guild(ctx.guild).saves() if saves_enabled else 0
        counts_until_save = 0
        if saves_enabled:
            total_counts = await self.config.guild(ctx.guild).total_counts()
            save_interval = await self.config.guild(ctx.guild).save_interval()
            if save_interval > 0:
                counts_until_save = save_interval - (total_counts % save_interval)

        view = LeaderboardView(pages, current_count, high_score, saves_enabled, saves, counts_until_save)
        await ctx.send(embed=view.build_embed(), view=view)

    # ---------------------------
    # Settings helpers
    # ---------------------------
    async def _react_confirm(self, ctx):
        """React to a settings command with the configured emoji."""
        emoji = await self.config.guild(ctx.guild).emoji()
        try:
            await ctx.message.add_reaction(emoji)
        except (discord.HTTPException, discord.NotFound):
            await ctx.message.add_reaction("✅")

    # ---------------------------
    # Settings
    # ---------------------------
    @commands.group(name="countset")
    @commands.guild_only()
    async def countset(self, ctx):
        """Settings for the counting game."""
        pass

    @countset.command(name="channel")
    @commands.admin_or_permissions(administrator=True)
    async def countset_channel(self, ctx, channel: discord.TextChannel):
        """Set the counting channel. Only one channel can be active at a time. (Admin only)"""
        current_channel_id = await self.config.guild(ctx.guild).channel_id()
        if current_channel_id == channel.id:
            return await ctx.send(f"⚠️ {channel.mention} is already the counting channel.")

        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await self.config.guild(ctx.guild).current_count.set(0)
        await self.config.guild(ctx.guild).last_counter_id.set(None)
        await self._react_confirm(ctx)

    @countset.command(name="count")
    @commands.admin_or_permissions(administrator=True)
    async def countset_count(self, ctx, number: int):
        """Set the current count to a specific number. (Admin only)"""
        if number < 0:
            return await ctx.send("❌ The count cannot be set to a negative number.")
        await self.config.guild(ctx.guild).current_count.set(number)
        await self.config.guild(ctx.guild).last_counter_id.set(None)
        await self._react_confirm(ctx)

    @countset.command(name="highscore")
    @commands.admin_or_permissions(administrator=True)
    async def countset_highscore(self, ctx, number: int):
        """Overwrite the current high score with a specific number. (Admin only)"""
        if number < 0:
            return await ctx.send("❌ The high score cannot be set to a negative number.")
        await self.config.guild(ctx.guild).high_score.set(number)
        await self._react_confirm(ctx)

    @countset.command(name="emoji")
    @commands.admin_or_permissions(administrator=True)
    async def countset_emoji(self, ctx, emoji: str):
        """Set the emoji the bot reacts with for correct counts. Supports built-in and server emojis. (Admin only)"""
        # Try to react to the command message to verify the emoji is valid
        try:
            await ctx.message.add_reaction(emoji)
        except (discord.HTTPException, discord.NotFound):
            return await ctx.send("❌ That doesn't appear to be a valid emoji I can use.")

        await self.config.guild(ctx.guild).emoji.set(emoji)

    @countset.command(name="edit")
    @commands.admin_or_permissions(administrator=True)
    async def countset_edit(self, ctx, member: discord.Member, amount: int):
        """Edit a user's total count. Use positive to increase or negative to decrease. (Admin only)"""
        async with self.config.guild(ctx.guild).counts() as counts:
            user_id = str(member.id)
            current = counts.get(user_id, 0)
            new_total = max(current + amount, 0)
            counts[user_id] = new_total

        await self._react_confirm(ctx)

    @countset.command(name="saves")
    @commands.admin_or_permissions(administrator=True)
    async def countset_saves(self, ctx):
        """Toggle the saves feature on or off. Off by default. (Admin only)"""
        current = await self.config.guild(ctx.guild).saves_enabled()
        await self.config.guild(ctx.guild).saves_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"✅ Saves have been **{state}**.")

    @countset.command(name="saveinterval")
    @commands.admin_or_permissions(administrator=True)
    async def countset_saveinterval(self, ctx, number: int):
        """Set how many counts are needed to earn a save. Default is 1000. (Admin only)"""
        if number < 1:
            return await ctx.send("❌ The save interval must be at least 1.")
        await self.config.guild(ctx.guild).save_interval.set(number)
        await self._react_confirm(ctx)

    @countset.command(name="addsave")
    @commands.admin_or_permissions(administrator=True)
    async def countset_addsave(self, ctx, amount: int = 1):
        """Add one or more saves to the server. Defaults to 1. (Admin only)"""
        if amount < 1:
            return await ctx.send("❌ You must add at least 1 save.")
        saves = await self.config.guild(ctx.guild).saves()
        new_saves = saves + amount
        await self.config.guild(ctx.guild).saves.set(new_saves)
        await ctx.send(f"🛡️ Added **{amount}** save(s). Total saves: **{new_saves}**")

    @countset.command(name="funnyreactions")
    @commands.admin_or_permissions(administrator=True)
    async def countset_funnyreactions(self, ctx):
        """Toggle funny reactions for 67, 69, and 420. Off by default. (Admin only)"""
        current = await self.config.guild(ctx.guild).funnyreactions()
        await self.config.guild(ctx.guild).funnyreactions.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"✅ Funny reactions have been **{state}**.")

    @countset.command(name="leaderboard")
    @commands.admin_or_permissions(administrator=True)
    async def countset_leaderboard(self, ctx, channel: discord.TextChannel = None):
        """Set a channel for the persistent auto-updating leaderboard. Use without a channel to remove it. (Admin only)"""
        if channel is None:
            await self.config.guild(ctx.guild).leaderboard_channel_id.set(None)
            await self.config.guild(ctx.guild).leaderboard_message_id.set(None)
            return await ctx.send("✅ Persistent leaderboard has been removed.")

        embed = await self._build_persistent_leaderboard_embed(ctx.guild)
        try:
            msg = await channel.send(embed=embed)
        except discord.HTTPException:
            return await ctx.send("❌ I couldn't send a message in that channel. Check my permissions.")

        await self.config.guild(ctx.guild).leaderboard_channel_id.set(channel.id)
        await self.config.guild(ctx.guild).leaderboard_message_id.set(msg.id)
        await self._react_confirm(ctx)


