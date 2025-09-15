import discord
from redbot.core import commands, Config, checks
from discord.ext import tasks
import aiohttp
import asyncio
import datetime
from redbot.core.utils.chat_formatting import humanize_list


class APOD(commands.Cog):
    """NASA Astronomy Picture of the Day"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)

        default_guild = {
            "channel_id": None,
            "post_time": "09:00",
            "include_info": True,
            "api_key": None,
            "ping_roles": [],
        }

        self.config.register_guild(**default_guild)
        self.session = aiohttp.ClientSession()
        self.guild_tasks = {}

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
            key = "DEMO_KEY"

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

        role_ids = await self.config.guild(channel.guild).ping_roles()
        roles_to_ping = [channel.guild.get_role(rid) for rid in role_ids if channel.guild.get_role(rid)]
        ping_text = humanize_list([r.mention for r in roles_to_ping]) if roles_to_ping else ""

        explanation = data.get("explanation", "No info.")
        if len(explanation) > 1024:
            explanation = explanation[:1021] + "…"

        # Check if the channel allows embeds
        can_embed = channel.permissions_for(channel.guild.me).embed_links

        if can_embed:
            embed = discord.Embed(
                title=data.get("title", "Astronomy Picture of the Day"),
                timestamp=datetime.datetime.utcnow(),
                color=await self.bot.get_embed_color(channel)
            )

            if data.get("media_type") == "image":
                embed.set_image(url=data.get("url"))
            else:
                date_str = data.get("date", datetime.datetime.utcnow().strftime("%Y-%m-%d"))
                y, m, d = date_str.split("-")
                embed.description = f"📺 This is a video! [Click here to view it on APOD](https://apod.nasa.gov/apod/ap{y[2:]}{m}{d}.html)"

            if include_info:
                embed.add_field(name="Explanation", value=explanation, inline=False)

            embed.set_footer(text=f"Date: {data.get('date')}")
            if ping_text:
                await channel.send(ping_text, embed=embed)
            else:
                await channel.send(embed=embed)

        else:
            # Fallback for channels without embed permission
            msg_content = f"**{data.get('title', 'Astronomy Picture of the Day')}**\n"
            if data.get("media_type") == "image":
                msg_content += f"{data.get('url')}\n"
            else:
                date_str = data.get("date", datetime.datetime.utcnow().strftime("%Y-%m-%d"))
                y, m, d = date_str.split("-")
                msg_content += f"📺 This is a video! View it here: https://apod.nasa.gov/apod/ap{y[2:]}{m}{d}.html\n"

            if include_info:
                msg_content += f"\n{explanation}\n"
            msg_content += f"\nDate: {data.get('date')}"

            if ping_text:
                await channel.send(f"{ping_text}\n{msg_content}")
            else:
                await channel.send(msg_content)

    @commands.command()
    async def apod(self, ctx, date: str = None):
        """Get the Astronomy Picture of the Day. Optionally provide DD/MM/YYYY"""
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
            ping_roles = await self.config.guild(ctx.guild).ping_roles()
            roles = [ctx.guild.get_role(rid) for rid in ping_roles if ctx.guild.get_role(rid)]
            roles_display = humanize_list([r.name for r in roles]) if roles else "None"
            channel = ctx.guild.get_channel(channel_id) if channel_id else None

            msg = (
                f"**APOD Settings:**\n"
                f"Channel: {channel.mention if channel else 'Not set'}\n"
                f"Post Time (UTC): {post_time}\n"
                f"Include Info: {include_info}\n"
                f"API Key: {'Set' if api_key else 'Not set'}\n"
                f"Ping Roles: {roles_display}"
            )
            await ctx.send(msg)

    @apodset.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for daily APOD posts."""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ APOD channel set to {channel.mention}")
        await self.restart_guild_task(ctx.guild)

    @apodset.command()
    async def time(self, ctx, time: str):
        """Set UTC time for daily APOD posts. Format HH:MM"""
        try:
            datetime.datetime.strptime(time, "%H:%M")
        except ValueError:
            await ctx.send("❌ Invalid time format. Use HH:MM")
            return
        await self.config.guild(ctx.guild).post_time.set(time)
        await self.restart_guild_task(ctx.guild)
        await ctx.send(f"✅ APOD post time set to {time} UTC.")

    @apodset.command()
    async def includeinfo(self, ctx, value: bool):
        """Enable/disable APOD explanation text."""
        await self.config.guild(ctx.guild).include_info.set(value)
        await ctx.send(f"✅ Include info set to {value}.")

    @apodset.command()
    async def apikey(self, ctx, key: str):
        """Set NASA API key."""
        await self.config.guild(ctx.guild).api_key.set(key)
        await ctx.send("✅ NASA API key set successfully.")

    @apodset.command()
    async def pingroles(self, ctx, *roles: discord.Role):
        """Set roles to ping on APOD."""
        role_ids = [r.id for r in roles]
        await self.config.guild(ctx.guild).ping_roles.set(role_ids)
        await ctx.send(f"✅ Ping roles set to: {humanize_list([r.mention for r in roles])}")

    async def restart_guild_task(self, guild: discord.Guild):
        task = self.guild_tasks.get(guild.id)
        if task:
            task.cancel()

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
        for guild in self.bot.guilds:
            await self.restart_guild_task(guild)
