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
            "api_key": None,  # User-configurable NASA API key
        }

        self.config.register_guild(**default_guild)
        self.session = aiohttp.ClientSession()
        self.guild_tasks = {}  # guild_id -> task

    def cog_unload(self):
        for task in self.guild_tasks.values():
            task.cancel()
        asyncio.create_task(self.session.close())

    async def fetch_apod(self, date=None, guild=None):
        base_url = "https://api.nasa.gov/planetary/apod"
        key = None
        if guild:
            key = await self.config.guild(guild).api_key()
        if not key:
            key = "DEMO_KEY"  # fallback

        params = {"api_key": key}
        if date:
            params["date"] = date

        async with self.session.get(base_url, params=params) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

    async def send_apod(self, channel: discord.TextChannel, date=None, include_info=True):
        data = await self.fetch_apod(date, guild=channel.guild)
        if not data:
            await channel.send("⚠️ Could not fetch the APOD image.")
            return

        embed = discord.Embed(
            title=data.get("title", "Astronomy Picture of the Day"),
            url=data.get("hdurl", data.get("url")),
            timestamp=datetime.datetime.utcnow(),
            color=discord.Color.blue(),
        )

        if data.get("media_type") == "image":
            embed.set_image(url=data.get("url"))
        else:
            embed.description = f"[Click here to view video]({data.get('url')})"

        if include_info:
            embed.add_field(
                name="Explanation",
                value=data.get("explanation", "No info."),
                inline=False,
            )

        embed.set_footer(text=f"Date: {data.get('date')}")
        await channel.send(embed=embed)

    @commands.command()
    async def apod(self, ctx, date: str = None):
        """Get the Astronomy Picture of the Day.
        Optionally provide a date in DD/MM/YYYY format."""
        if date:
            try:
                parsed = datetime.datetime.strptime(date, "%d/%m/%Y")
                date_str = parsed.strftime("%Y-%m-%d")
            except ValueError:
                await ctx.send("❌ Invalid date format. Use DD/MM/YYYY.")
                return
        else:
            date_str = None

        await self.send_apod(ctx.channel, date_str, include_info=True)

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def apodset(self, ctx):
        """Settings for APOD."""
        if ctx.invoked_subcommand is None:
            channel_id = await self.config.guild(ctx.guild).channel_id()
            post_time = await self.config.guild(ctx.guild).post_time()
            include_info = await self.config.guild(ctx.guild).include_info()
            api_key = await self.config.guild(ctx.guild).api_key()
            channel = ctx.guild.get_channel(channel_id) if channel_id else None

            msg = (
                f"**APOD Settings:**\n"
                f"Channel: {channel.mention if channel else 'Not set'}\n"
                f"Post Time (UTC): {post_time}\n"
                f"Include Info: {include_info}\n"
                f"API Key: {'Set' if api_key else 'Not set'}"
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
    async def apikey(self, ctx, key: str):
        """Set your NASA API key for APOD requests."""
        await self.config.guild(ctx.guild).api_key.set(key)
        await ctx.send("✅ NASA API key set successfully.")

    async def restart_guild_task(self, guild: discord.Guild):
        """Stop and restart a guild's daily task with the new settings."""
        # cancel old
        task = self.guild_tasks.get(guild.id)
        if task:
            task.cancel()

        # get new settings
        channel_id = await self.config.guild(guild).channel_id()
        post_time = await self.config.guild(guild).post_time()
        include_info = await self.config.guild(guild).include_info()

        if not channel_id or not post_time:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        hour, minute = map(int, post_time.split(":"))
        time_obj = datetime.time(hour=hour, minute=minute)

        @tasks.loop(time=[time_obj])
        async def guild_task():
            await self.send_apod(channel, None, include_info)

        guild_task.start()
        self.guild_tasks[guild.id] = guild_task

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.restart_guild_task(guild)

    @commands.Cog.listener()
    async def on_ready(self):
        # Start tasks for all guilds on startup
        for guild in self.bot.guilds:
            await self.restart_guild_task(guild)
