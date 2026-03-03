import discord
from redbot.core import commands, Config, checks


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
        }
        self.config.register_guild(**default_guild)

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

        # Check if the message is a valid number
        try:
            number = int(message.content.strip())
        except ValueError:
            await message.channel.send(
                f"❌ {message.author.mention} That's not a valid number! "
                f"The count has been broken. Restart from **1**."
            )
            await self.config.guild(message.guild).current_count.set(0)
            await self.config.guild(message.guild).last_counter_id.set(None)
            return

        # Check if the same user is counting twice in a row
        if message.author.id == last_counter_id:
            await message.channel.send(
                f"❌ {message.author.mention} You can't count twice in a row! "
                f"The count has been broken. Restart from **1**."
            )
            await self.config.guild(message.guild).current_count.set(0)
            await self.config.guild(message.guild).last_counter_id.set(None)
            return

        # Check if the number is correct
        if number != expected:
            await message.channel.send(
                f"❌ {message.author.mention} Wrong number! Expected **{expected}**. "
                f"The count has been broken. Restart from **1**."
            )
            await self.config.guild(message.guild).current_count.set(0)
            await self.config.guild(message.guild).last_counter_id.set(None)
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

        # React with the configured emoji
        emoji = await self.config.guild(message.guild).emoji()
        try:
            await message.add_reaction(emoji)
        except (discord.HTTPException, discord.NotFound):
            await message.add_reaction("✅")

    # ---------------------------
    # Leaderboard
    # ---------------------------
    @commands.command(name="countleaderboard", aliases=["countlb"])
    @commands.guild_only()
    async def countleaderboard(self, ctx):
        """Show the counting game leaderboard."""
        counts = await self.config.guild(ctx.guild).counts()
        if not counts:
            return await ctx.send("📊 No counting data yet!")

        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        entries = []
        for rank, (user_id, total) in enumerate(sorted_counts[:20], start=1):
            member = ctx.guild.get_member(int(user_id))
            name = member.display_name if member else f"Unknown ({user_id})"
            entries.append(f"**{rank}.** {name} — {total} count{'s' if total != 1 else ''}")

        embed = discord.Embed(
            title="🔢 Counting Leaderboard",
            description="\n".join(entries),
            color=discord.Color.gold(),
        )
        current_count = await self.config.guild(ctx.guild).current_count()
        high_score = await self.config.guild(ctx.guild).high_score()
        embed.set_footer(text=f"Current count: {current_count} | High score: {high_score}")
        await ctx.send(embed=embed)

    # ---------------------------
    # Settings
    # ---------------------------
    @commands.group(name="countset")
    @commands.guild_only()
    async def countset(self, ctx):
        """Settings for the counting game."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @countset.command(name="channel")
    @commands.admin_or_permissions(administrator=True)
    async def countset_channel(self, ctx, channel: discord.TextChannel):
        """Set the counting channel. Only one channel can be active at a time. (Admin only)"""
        current_channel_id = await self.config.guild(ctx.guild).channel_id()
        if current_channel_id == channel.id:
            return await ctx.send(f"⚠️ {channel.mention} is already the counting channel.")

        if current_channel_id is not None:
            old_channel = ctx.guild.get_channel(current_channel_id)
            old_name = old_channel.mention if old_channel else f"deleted channel ({current_channel_id})"
            await ctx.send(
                f"⚠️ Switching counting channel from {old_name} to {channel.mention}. "
                f"Only one counting channel can be active at a time."
            )

        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await self.config.guild(ctx.guild).current_count.set(0)
        await self.config.guild(ctx.guild).last_counter_id.set(None)
        await ctx.send(f"✅ Counting channel set to {channel.mention}. Count starts from **1**.")

    @countset.command(name="reset")
    @commands.admin_or_permissions(administrator=True)
    async def countset_reset(self, ctx):
        """Reset the current count back to 0. (Admin only)"""
        await self.config.guild(ctx.guild).current_count.set(0)
        await self.config.guild(ctx.guild).last_counter_id.set(None)
        await ctx.send("✅ The count has been reset to **0**.")

    @countset.command(name="setcount")
    @commands.admin_or_permissions(administrator=True)
    async def countset_setcount(self, ctx, number: int):
        """Set the current count to a specific number. (Admin only)"""
        if number < 0:
            return await ctx.send("❌ The count cannot be set to a negative number.")
        await self.config.guild(ctx.guild).current_count.set(number)
        await self.config.guild(ctx.guild).last_counter_id.set(None)
        await ctx.send(f"✅ The count has been set to **{number}**. The next number is **{number + 1}**.")

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
        await ctx.send(f"✅ Counting reaction emoji set to {emoji}.")

    @countset.command(name="edit")
    @commands.admin_or_permissions(administrator=True)
    async def countset_edit(self, ctx, member: discord.Member, amount: int):
        """Edit a user's total count. Use positive to increase or negative to decrease. (Admin only)"""
        async with self.config.guild(ctx.guild).counts() as counts:
            user_id = str(member.id)
            current = counts.get(user_id, 0)
            new_total = max(current + amount, 0)
            counts[user_id] = new_total

        msg = f"✅ {member.display_name}'s count updated: {current} → {new_total}."
        if current + amount < 0:
            msg += " (Clamped to 0, cannot go below zero.)"
        await ctx.send(msg)
