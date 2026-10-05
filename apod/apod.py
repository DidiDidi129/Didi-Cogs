import asyncio
import datetime
import html
import logging
import re
from html.parser import HTMLParser
from typing import Dict, Optional, Tuple

import aiohttp
import discord
from redbot.core import Config, checks, commands
from redbot.core.utils.chat_formatting import humanize_list

log = logging.getLogger("red.didi.apod")
EMBED_FIELD_MAX_LENGTH = 1024


class _ExplanationHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.current_link_href: Optional[str] = None
        self.current_link_text_parts = []

    def handle_starttag(self, tag: str, attrs):
        if tag == "a":
            self.current_link_href = dict(attrs).get("href")
            self.current_link_text_parts = []
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"p", "div", "li"} and self.parts and self.parts[-1] != "\n":
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag == "a":
            text = "".join(self.current_link_text_parts).strip()
            href = self.current_link_href
            if text:
                if href:
                    self.parts.append(f"[{text}]({href})")
                else:
                    self.parts.append(text)
            self.current_link_href = None
            self.current_link_text_parts = []
        elif tag in {"p", "div", "li"} and self.parts and self.parts[-1] != "\n":
            self.parts.append("\n")

    def handle_data(self, data: str):
        if self.current_link_href is not None:
            self.current_link_text_parts.append(data)
        else:
            self.parts.append(data)

    def get_text(self) -> str:
        raw_text = "".join(self.parts)
        lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in raw_text.splitlines()]
        return "\n".join(line for line in lines if line).strip()


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
        self.session: Optional[aiohttp.ClientSession] = None
        self.guild_tasks: Dict[int, asyncio.Task] = {}

    async def cog_load(self):
        await self._restart_all_guild_tasks()

    def cog_unload(self):
        for task in self.guild_tasks.values():
            task.cancel()
        self.guild_tasks.clear()
        if self.session is not None and not self.session.closed:
            asyncio.ensure_future(self.session.close())

    async def _restart_all_guild_tasks(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self.restart_guild_task(guild)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        return self.session

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
            session = await self._get_session()
            async with session.get(
                "https://science.nasa.gov/wp-json/wp/v2/apod-basic/", params=params
            ) as resp:
                if resp.status != 200:
                    return None, f"NASA API request failed (status {resp.status})."
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None, "Could not reach NASA APOD right now. Please try again later."
        except Exception:
            return None, "Received an invalid response from NASA APOD."

        normalized = self._normalize_apod_payload(payload)
        if normalized is None:
            return None, "Received an invalid APOD payload."
        return normalized, None

    @staticmethod
    def _sanitize_explanation(explanation: str) -> str:
        parser = _ExplanationHTMLParser()
        parser.feed(explanation)
        parser.close()
        return parser.get_text()

    @staticmethod
    def _normalize_apod_payload(payload: object) -> Optional[dict]:
        if isinstance(payload, list):
            if not payload or not isinstance(payload[0], dict):
                return None
            payload = payload[0]
        if not isinstance(payload, dict):
            return None

        def _value(value: object) -> object:
            if isinstance(value, dict):
                rendered = value.get("rendered")
                if rendered is not None:
                    return rendered
            return value

        date_value = _value(payload.get("date"))
        title_value = _value(payload.get("title"))
        explanation_value = _value(payload.get("explanation"))
        media_type_value = _value(payload.get("media_type"))
        hdurl_value = _value(payload.get("hdurl"))
        url_value = _value(payload.get("url"))
        permalink_value = _value(payload.get("permalink"))

        if not isinstance(date_value, str):
            date_value = None
        if not isinstance(title_value, str):
            title_value = None
        if not isinstance(explanation_value, str):
            explanation_value = None
        if not isinstance(media_type_value, str):
            media_type_value = None
        if not isinstance(hdurl_value, str):
            hdurl_value = None
        if not isinstance(url_value, str):
            url_value = None
        if not isinstance(permalink_value, str):
            permalink_value = None

        if (
            date_value is None
            and title_value is None
            and explanation_value is None
            and media_type_value is None
            and hdurl_value is None
            and url_value is None
            and permalink_value is None
        ):
            return None

        if title_value is not None:
            title_value = html.unescape(title_value)
        if explanation_value is not None:
            explanation_value = APOD._sanitize_explanation(html.unescape(explanation_value))
        if hdurl_value is not None:
            hdurl_value = html.unescape(hdurl_value)
        if url_value is not None:
            url_value = html.unescape(url_value)
        if permalink_value is not None:
            permalink_value = html.unescape(permalink_value)

        return {
            "date": date_value,
            "title": title_value,
            "explanation": explanation_value,
            "media_type": media_type_value,
            "hdurl": hdurl_value,
            "url": url_value,
            "permalink": permalink_value,
        }

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

        apod_url = data.get("permalink") or f"https://apod.nasa.gov/apod/ap{safe_date.strftime('%y%m%d')}.html"
        description_parts = []

        explanation = data.get("explanation") or "No explanation provided."
        explanation = re.sub(r"^\s*Explanation:\s*", "", explanation, count=1, flags=re.IGNORECASE)
        if not explanation:
            explanation = "No explanation provided."
        explanation_too_long = len(explanation) > EMBED_FIELD_MAX_LENGTH

        if include_info:
            if explanation_too_long:
                description_parts.append(
                    f"explaination too long. Read it on the official APOD website: [APOD Page]({apod_url})"
                )
            else:
                embed.add_field(name="Explanation", value=explanation, inline=False)

        media_type = data.get("media_type")
        if media_type == "video":
            description_parts.append(f"📺 This APOD is a video. [View it on the APOD page]({apod_url}).")

        if description_parts:
            embed.description = "\n\n".join(description_parts)

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
        if not isinstance(post_time, str) or ":" not in post_time:
            raise ValueError(f"Invalid post_time format: {post_time!r}")
        parsed_time = datetime.datetime.strptime(post_time, "%H:%M")
        hour, minute = parsed_time.hour, parsed_time.minute
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
                    log.exception("Invalid APOD post_time for guild %s: %r", guild_id, post_time)
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
        """Get APOD. Optional date format: DD/MM/YYYY (from 16/06/1995 to today UTC)."""
        if ctx.guild is None:
            await ctx.send("❌ This command can only be used in a server.")
            return

        parsed_date = None
        if date is not None:
            try:
                parsed_dt = datetime.datetime.strptime(date, "%d/%m/%Y").date()
            except ValueError:
                await ctx.send("❌ Invalid date format. Use DD/MM/YYYY.")
                return
            apod_start = datetime.date(1995, 6, 16)
            today_utc = datetime.datetime.now(datetime.timezone.utc).date()
            if parsed_dt < apod_start or parsed_dt > today_utc:
                await ctx.send(
                    f"❌ Date must be between {apod_start.strftime('%d/%m/%Y')} and {today_utc.strftime('%d/%m/%Y')}."
                )
                return
            parsed_date = parsed_dt.strftime("%Y-%m-%d")

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
        await self._restart_all_guild_tasks()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.restart_guild_task(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self._cancel_guild_task(guild.id)
