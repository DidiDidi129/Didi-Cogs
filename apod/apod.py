import asyncio
import datetime
import logging
from typing import Dict, Optional, Tuple

import aiohttp
import discord
from redbot.core import Config, checks, commands
from redbot.core.utils.chat_formatting import humanize_list

log = logging.getLogger("red.didi.apod")


class APOD(commands.Cog):
    """NASA Astronomy Picture of the Day."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_guild(
            channel_id=None,
            post_time="09:00",
            include_info=True,
            api_key=None,
            ping_roles=[],
        )
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        self.guild_tasks: Dict[int, asyncio.Task] = {}

    def cog_unload(self):
        for task in self.guild_tasks.values():
            task.cancel()
        self.guild_tasks.clear()
        if not self.session.closed:
            asyncio.create_task(self.session.close())

    async def fetch_apod(
        self, guild: Optional[discord.Guild], date: Optional[str] = None
    ) -> Tuple[Optional[dict], Optional[str]]:
        key = "DEMO_KEY"
        if guild is not None:
            guild_key = await self.config.guild(guild).api_key()
            if guild_key:
                key = guild_key

        params = {"api_key": key}
        if date:
            params["date"] = date

        try:
            async with self.session.get("https://api.nasa.gov/planetary/apod", params=params) as resp:
                if resp.status != 200:
                    return None, f"NASA API request failed (status {resp.status})."
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None, "Could not reach NASA APOD right now. Please try again later."
        except Exception:
            return None, "Received an invalid response from NASA APOD."

        if not isinstance(payload, dict):
            return None, "Received an invalid APOD payload."
        return payload, None

    async def send_apod(
        self,
        channel: discord.TextChannel,
        date: Optional[str] = None,
        include_info: bool = True,
        ping_roles: bool = False,
    ) -> None:
        if channel.guild is None:
            return

        data, error = await self.fetch_apod(channel.guild, date=date)
        if error:
            await channel.send(f"⚠️ {error}")
            return
        if not data:
            await channel.send("⚠️ Could not fetch APOD data.")
            return

        raw_date = data.get("date")
        safe_date = datetime.datetime.now(datetime.timezone.utc).date()
        if isinstance(raw_date, str):
            try:
                safe_date = datetime.datetime.strptime(raw_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        embed = discord.Embed(
            title=data.get("title") or "Astronomy Picture of the Day",
            color=await self.bot.get_embed_color(channel),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        explanation = data.get("explanation") or "No explanation provided."
        if len(explanation) > 1024:
            explanation = explanation[:1021] + "..."
        if include_info:
            embed.add_field(name="Explanation", value=explanation, inline=False)

        media_type = data.get("media_type")
        if media_type == "video":
            apod_url = f"https://apod.nasa.gov/apod/ap{safe_date.strftime('%y%m%d')}.html"
            embed.description = f"📺 This APOD is a video. [View it on the APOD page]({apod_url})."

        embed.set_footer(text=f"Date: {safe_date.isoformat()}")

        message_content = None
        allowed_mentions = None
        if ping_roles:
            role_ids = await self.config.guild(channel.guild).ping_roles()
            roles = [channel.guild.get_role(role_id) for role_id in role_ids]
            roles = [role for role in roles if role is not None]
            if roles:
                message_content = humanize_list([role.mention for role in roles])
                allowed_mentions = discord.AllowedMentions(roles=True)

        if message_content:
            await channel.send(message_content, embed=embed, allowed_mentions=allowed_mentions)
        else:
            await channel.send(embed=embed)

        if media_type == "image":
            image_url = data.get("hdurl") or data.get("url")
            if image_url:
                await channel.send(image_url)

    async def _cancel_guild_task(self, guild_id: int) -> None:
        task = self.guild_tasks.pop(guild_id, None)
        if not task:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _next_sleep_seconds(self, post_time: str) -> float:
        hour, minute = map(int, post_time.split(":"))
        now = datetime.datetime.now(datetime.timezone.utc)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return (target - now).total_seconds()

    async def _guild_scheduler(self, guild_id: int) -> None:
        while True:
            try:
                post_time = await self.config.guild_from_id(guild_id).post_time()
                try:
                    sleep_seconds = await self._next_sleep_seconds(post_time)
                except Exception:
                    log.warning("Invalid APOD post_time for guild %s: %r", guild_id, post_time)
                    sleep_seconds = 60.0

                await asyncio.sleep(sleep_seconds)

                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    continue

                channel_id = await self.config.guild(guild).channel_id()
                channel = guild.get_channel(channel_id) if channel_id else None
                if not isinstance(channel, discord.TextChannel):
                    continue

                include_info = await self.config.guild(guild).include_info()
                await self.send_apod(channel, include_info=include_info, ping_roles=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Unexpected error in APOD scheduler for guild %s", guild_id)
                await asyncio.sleep(60)

    async def restart_guild_task(self, guild: discord.Guild) -> None:
        await self._cancel_guild_task(guild.id)

        channel_id = await self.config.guild(guild).channel_id()
        post_time = await self.config.guild(guild).post_time()
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            datetime.datetime.strptime(post_time, "%H:%M")
        except ValueError:
            return

        self.guild_tasks[guild.id] = asyncio.create_task(
            self._guild_scheduler(guild.id), name=f"apod-scheduler-{guild.id}"
        )

    @commands.command()
    async def apod(self, ctx: commands.Context, date: Optional[str] = None):
        """Get the Astronomy Picture of the Day. Optionally provide DD/MM/YYYY."""
        if ctx.guild is None:
            await ctx.send("❌ This command can only be used in a server.")
            return

        parsed_date = None
        if date is not None:
            try:
                parsed_date = datetime.datetime.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                await ctx.send("❌ Invalid date format. Use DD/MM/YYYY.")
                return

        include_info = await self.config.guild(ctx.guild).include_info()
        await self.send_apod(ctx.channel, date=parsed_date, include_info=include_info, ping_roles=False)

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def apodset(self, ctx: commands.Context):
        """Settings for APOD."""
        if ctx.guild is None:
            await ctx.send("❌ This command can only be used in a server.")
            return

        if ctx.invoked_subcommand is None:
            channel_id = await self.config.guild(ctx.guild).channel_id()
            post_time = await self.config.guild(ctx.guild).post_time()
            include_info = await self.config.guild(ctx.guild).include_info()
            api_key = await self.config.guild(ctx.guild).api_key()
            ping_roles = await self.config.guild(ctx.guild).ping_roles()
            channel = ctx.guild.get_channel(channel_id) if channel_id else None
            roles = [ctx.guild.get_role(role_id) for role_id in ping_roles]
            roles = [role.name for role in roles if role is not None]

            await ctx.send(
                "\n".join(
                    [
                        "**APOD Settings:**",
                        f"Channel: {channel.mention if channel else 'Not set'}",
                        f"Post Time (UTC): {post_time}",
                        f"Include Info: {include_info}",
                        f"API Key: {'Set' if api_key else 'Not set'}",
                        f"Ping Roles: {humanize_list(roles) if roles else 'None'}",
                    ]
                )
            )

    @apodset.command()
    async def channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel for daily APOD posts."""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await self.restart_guild_task(ctx.guild)
        await ctx.send(f"✅ APOD channel set to {channel.mention}")

    @apodset.command()
    async def time(self, ctx: commands.Context, time: str):
        """Set UTC time for daily APOD posts. Format HH:MM."""
        try:
            datetime.datetime.strptime(time, "%H:%M")
        except ValueError:
            await ctx.send("❌ Invalid time format. Use HH:MM")
            return

        await self.config.guild(ctx.guild).post_time.set(time)
        await self.restart_guild_task(ctx.guild)
        await ctx.send(f"✅ APOD post time set to {time} UTC.")

    @apodset.command()
    async def includeinfo(self, ctx: commands.Context, value: bool):
        """Enable/disable APOD explanation text."""
        await self.config.guild(ctx.guild).include_info.set(value)
        await self.restart_guild_task(ctx.guild)
        await ctx.send(f"✅ Include info set to {value}.")

    @apodset.command()
    async def apikey(self, ctx: commands.Context, *, key: str):
        """Set NASA API key."""
        await self.config.guild(ctx.guild).api_key.set(key)
        await ctx.send("✅ NASA API key set successfully.")

    @apodset.command()
    async def pingroles(self, ctx: commands.Context, *roles: discord.Role):
        """Set roles to ping for scheduled APOD posts."""
        role_ids = [role.id for role in roles]
        await self.config.guild(ctx.guild).ping_roles.set(role_ids)
        await self.restart_guild_task(ctx.guild)
        if roles:
            await ctx.send(f"✅ Ping roles set to: {humanize_list([role.mention for role in roles])}")
        else:
            await ctx.send("✅ Cleared APOD ping roles.")

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self.restart_guild_task(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.restart_guild_task(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self._cancel_guild_task(guild.id)
