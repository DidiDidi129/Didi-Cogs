import discord
from redbot.core import commands, Config, checks
from discord.ext import tasks
import aiohttp
import asyncio
import datetime


class APOD(commands.Cog):
    """NASA Astronomy Picture of the Day"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)

        default_guild = {
            "channel_id": None,
            "post_time": "09:00",  # Default UTC time
            "include_info": True,
            "ping_target": None,  # role/user id
        }

        default_global = {
            "use_embeds": True,
        }

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.session = aiohttp.ClientSession()
        self.guild_tasks = {}  # guild_id -> task

    def cog_unload(self):
        for task in self.guild_tasks.values():
            task.cancel()
        asyncio.create_task(self.session.close())

    async def fetch_apod(self, date=None):
        base_url = "https://api.nasa.gov/planetary/apod"
        params = {"api_key": "DEMO_KEY"}  # replace with your real NASA key
        if date:
            params["date"] = date

        async with self.session.get(base_url, params=params) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

    async def send_apod(self, channel: discord.TextChannel, date=None, include_info=True, ping_target=None):
        # Try fetching API data
        data = await self.fetch_apod(date)

        # Build the APOD archive link (always works)
        if date:
            try:
                d = datetime.datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                d = datetime.datetime.utcnow()
        else:
            d = datetime.datetime.utcnow()
        archive_link = f"https://apod.nasa.gov/apod/ap{d.strftime('%y%m%d')}.html"

        # If API completely failed
        if not data:
            await channel.send(
                f"⚠️ Could not fetch the APOD image. "
                f"You can still view it here: {archive_link}"
            )
            return

        use_embeds = await self.config.use_embeds()

        # Message prefix if ping is set
        message_content = ""
        if ping_target:
            message_content += f"<@&{ping_target}> " if channel.guild.get_role(ping_target) else f"<@{ping_target}> "

        if use_embeds:
            embed = discord.Embed(
                title=data.get("title", "Astronomy Picture of the Day"),
                url=data.get("hdurl", data.get("url")),
                timestamp=datetime.datetime.utcnow(),
                color=discord.Color.blue(),
            )

            if data.get("media_type") == "image":
                embed.set_image(url=data.get("url"))
            else:
                embed.description = f"[Click here to view APOD page]({archive_link})"

            if include_info:
                embed.add_field(
                    name="Explanation",
                    value=data.get("explanation", "No info."),
                    inline=False,
                )

            embed.set_footer(text=f"Date: {data.get('date')}")
            await channel.send(content=message_content or None, embed=embed)
        else:
            msg = f"**{data.get('title', 'Astronomy Picture of the Day')}** ({data.get('date')})\n"
            if data.get("media_type") == "image":
                msg += data.get("url") + "\n"
            else:
                msg += f"Video detected, view it here: {archive_link}\n"
            if include_info:
                msg += "\n" + data.get("explanation", "No info.")
            await channel.send(content=(message_content or "") + msg)

    @commands.command()
    async def apod(self, ctx, date: str = None):
        """Get the Astronomy Picture of the Day.
        Optionally provide a date in DD/MM/YYYY format."""
        if date:
            try:
                parsed = datetime.datetime.strptime(date, "%d/%m/%Y").date()
            except ValueError:
                await ctx.send("❌ Invalid date format. Use **DD/MM/YYYY**.")
                return

            today = datetime.date.today()
            if parsed > today:
                await ctx.send("❌ That date is in the future. Please pick today or earlier.")
                return

            date_str = parsed.strftime("%Y-%m-%d")
        else:
            date_str = None

        include_info = await self.config.guild(ctx.guild).include_info()
        ping_target = await self.config.guild(ctx.guild).ping_target()
        await self.send_apod(ctx.channel, date_str, include_info, ping_target)

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def apodset(self, ctx):
        """Settings for APOD."""
        if ctx.invoked_subcommand is None:
            channel_id = await self.config.guild(ctx.guild).channel_id()
            post_time = await self.config.guild(ctx.guild).post_time()
            include_info = await self.config.guild(ctx.guild).include_info()
            ping_target = await self.config.guild(ctx.guild).ping_target()
            channel = ctx.guild.get_channel(channel_id) if channel_id else None
            role = ctx.guild.get_role(ping_target) if ping_target else None
            user = ctx.guild.get_member(ping_target) if ping_target else None

            ping_display = None
            if role:
                ping_display = role.mention
            elif user:
                ping_display = user.mention

            use_embeds = await self.config.use_embeds()

            msg = (
                f"**APOD Settings:**\n"
                f"Channel: {channel.mention if channel else 'Not set'}\n"
                f"Post Time (UTC): {post_time}\n"
                f"Include Info: {include_info}\n"
                f"Ping Target: {ping_display or 'None'}\n"
                f"Use Embeds (global): {use_embeds}"
            )
            await ctx.send(msg)

    @apodset.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Set the channel where daily APOD posts will appear."""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ APOD channel set to {channel.mention}")
        await self.restart_guild_task(ctx.guild)

    @apodset.command()
    async def time(self, ctx, time: str):
        """Set the UTC time for daily APOD posts. Format: HH:MM"""
        try:
            datetime.datetime.strptime(time, "%H:%M")
        except ValueError:
            await ctx.send("❌ Invalid time format. Use HH:MM (24-hour, UTC).")
            return
        await self.config.guild(ctx.guild).post_time.set(time)
        await ctx.send(f"✅ APOD post time set to {time} UTC.")
        await self.restart_guild_task(ctx.guild)

    @apodset.command()
    async def includeinfo(self, ctx, value: bool):
        """Enable or disable including the APOD explanation text."""
        await self.config.guild(ctx.guild).include_info.set(value)
        await ctx.send(f"✅ Include info set to {value}.")

    @apodset.command()
    async def ping(self, ctx, target: discord.Role | discord.Member | None):
        """Set a role or user to ping when the APOD is posted. Leave blank to clear."""
        if target:
            await self.config.guild(ctx.guild).ping_target.set(target.id)
            await ctx.send(f"✅ Will ping {target.mention} for daily APOD.")
        else:
            await self.config.guild(ctx.guild).ping_target.clear()
            await ctx.send("✅ Cleared APOD ping target.")

    @apodset.command()
    @checks.is_owner()
    async def embeds(self, ctx, value: bool):
        """Enable or disable embeds globally (bot owner only)."""
        await self.config.use_embeds.set(value)
        await ctx.send(f"✅ Embeds {'enabled' if value else 'disabled'} globally.")

    async def restart_guild_task(self, guild: discord.Guild):
        """Stop and restart a guild's daily task with the new settings."""
        task = self.guild_tasks.get(guild.id)
        if task:
            task.cancel()

        channel_id = await self.config.guild(guild).channel_id()
        post_time = await self.config.guild(guild).post_time()
        include_info = await self.config.guild(guild).include_info()
        ping_target = await self.config.guild(guild).ping_target()

        if not channel_id or not post_time:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        hour, minute = map(int, post_time.split(":"))
        time_obj = datetime.time(hour=hour, minute=minute)

        @tasks.loop(time=[time_obj])
        async def guild_task():
            await self.send_apod(channel, None, include_info, ping_target)

        guild_task.start()
        self.guild_tasks[guild.id] = guild_task

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.restart_guild_task(guild)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self.restart_guild_task(guild)
