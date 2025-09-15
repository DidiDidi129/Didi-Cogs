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
            "post_time": "09:00",  # Default time UTC
            "include_info": True,
        }

        self.config.register_guild(**default_guild)
        self.session = aiohttp.ClientSession()
        self.daily_apod_task.start()

    def cog_unload(self):
        self.daily_apod_task.cancel()
        asyncio.create_task(self.session.close())

    async def fetch_apod(self, date=None):
        """Fetch APOD data from NASA API."""
        base_url = "https://api.nasa.gov/planetary/apod"
        params = {"api_key": "DEMO_KEY"}  # Replace with real key if needed
        if date:
            params["date"] = date

        async with self.session.get(base_url, params=params) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

    async def send_apod(self, channel: discord.TextChannel, date=None, include_info=True):
        data = await self.fetch_apod(date)
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
            embed.add_field(name="Explanation", value=data.get("explanation", "No info."), inline=False)

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
            channel = ctx.guild.get_channel(channel_id) if channel_id else None

            msg = (
                f"**APOD Settings:**\n"
                f"Channel: {channel.mention if channel else 'Not set'}\n"
                f"Post Time (UTC): {post_time}\n"
                f"Include Info: {include_info}"
            )
            await ctx.send(msg)

    @apodset.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Set the channel where daily APOD posts will appear."""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ APOD channel set to {channel.mention}")

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

    @apodset.command()
    async def includeinfo(self, ctx, value: bool):
        """Enable or disable including the APOD explanation text."""
        await self.config.guild(ctx.guild).include_info.set(value)
        await ctx.send(f"✅ Include info set to {value}.")

    @tasks.loop(minutes=1)
    async def daily_apod_task(self):
        now = datetime.datetime.utcnow().strftime("%H:%M")

        for guild in self.bot.guilds:
            channel_id = await self.config.guild(guild).channel_id()
            post_time = await self.config.guild(guild).post_time()
            include_info = await self.config.guild(guild).include_info()

            if channel_id and now == post_time:
                channel = guild.get_channel(channel_id)
                if channel:
                    await self.send_apod(channel, None, include_info)

    @daily_apod_task.before_loop
    async def before_daily_apod_task(self):
        await self.bot.wait_until_ready()
