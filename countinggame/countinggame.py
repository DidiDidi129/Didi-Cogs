import discord
from redbot.core import commands, Config, checks


class CountingGame(commands.Cog):
    """A counting game for your server."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9517538264, force_registration=True)
        default_guild = {
            "channel_id": None,
            "current_count": 0,
            "last_counter_id": None,
            "counts": {},
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

        async with self.config.guild(message.guild).counts() as counts:
            user_id = str(message.author.id)
            counts[user_id] = counts.get(user_id, 0) + 1

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
        embed.set_footer(text=f"Current count: {current_count}")
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
    @checks.is_owner()
    async def countset_channel(self, ctx, channel: discord.TextChannel):
        """Set the counting channel. (Bot owner only)"""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ Counting channel set to {channel.mention}.")

    @countset.command(name="reset")
    @commands.admin_or_permissions(administrator=True)
    async def countset_reset(self, ctx):
        """Reset the current count back to 0. (Admin only)"""
        await self.config.guild(ctx.guild).current_count.set(0)
        await self.config.guild(ctx.guild).last_counter_id.set(None)
        await ctx.send("✅ The count has been reset to **0**.")

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
