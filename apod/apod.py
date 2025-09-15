import discord
from redbot.core import commands, Config, checks
from discord.ext import tasks
import aiohttp
import asyncio
import datetime
from bs4 import BeautifulSoup  # make sure beautifulsoup4 is installed


class APOD(commands.Cog):
    """NASA Astronomy Picture of the Day"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)

        default_guild = {
            "channel_id": None,
            "post_time": "09:00",  # UTC
            "include_info": True,
            "ping_target": None,  # role/user ID
        }

        default_global = {
            "use_embeds": True,
            "api_key": "DEMO_KEY"  # replace with your own
        }

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.session = aiohttp.ClientSession()
        self.guild_tasks = {}

    def cog_unload(self):
        for task in self.guild_tasks.values():
            task.cancel()
        asyncio.create_task(self.session.close())

    async def fetch_apod(self, date=None):
        key = await self.config.api_key()
        url = "https://api.nasa.gov/planetary/apod"
        params = {"api_key": key}
        if date:
            params["date"] = date
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except aiohttp.ClientError:
            return None

    async def send_apod(self, channel: discord.TextChannel, date=None, include_info=True, ping_target=None):
        use_embeds = await self.config.use_embeds()
        data = await self.fetch_apod(date)

        # Build archive link
        try:
            d = datetime.datetime.strptime(date, "%Y-%m-%d") if date else datetime.datetime.utcnow()
        except ValueError:
            d = datetime.datetime.utcnow()
        archive_link = f"https://apod.nasa.gov/apod/ap{d.strftime('%y%m%d')}.html"

        message_content = f"<@&{ping_target}> " if ping_target else ""

        # If API returns valid image/video
        if data:
            media_type = data.get("media_type")
            if media_type == "image":
                if use_embeds:
                    embed = discord.Embed(
                        title=data.get("title", "Astronomy Picture of the Day"),
                        url=data.get("hdurl", data.get("url", archive_link)),
                        color=discord.Color.blue(),
                        timestamp=datetime.datetime.utcnow()
                    )
                    embed.set_image(url=data.get("url"))
                    if include_info:
                        embed.add_field(name="Explanation", value=data.get("explanation", "No info."), inline=False)
                    embed.set_footer(text=f"Date: {data.get('date')}")
                    await channel.send(content=message_content or None, embed=embed)
                else:
                    msg = f"**{data.get('title', 'Astronomy Picture of the Day')}** ({data.get('date')})\n"
                    msg += data.get("url") + "\n"
                    if include_info:
                        msg += "\n" + data.get("explanation", "No info.")
                    await channel.send(content=message_content + msg)
                return
            elif media_type == "video":
                content = f"📹 Videos are not yet supported, go here to see today's video: {archive_link}"
                if use_embeds:
                    embed = discord.Embed(
                        title=data.get("title", "Astronomy Picture of the Day"),
                        url=archive_link,
                        description=content,
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.utcnow()
                    )
                    if include_info:
                        embed.add_field(name="Explanation", value=data.get("explanation", "No info."), inline=False)
                    embed.set_footer(text=f"Date: {data.get('date')}")
                    await channel.send(content=message_content or None, embed=embed)
                else:
                    await channel.send(content=message_content + content)
                return

        # If API failed or returned None, scrape HTML page
        try:
            async with self.session.get(archive_link) as resp:
                if resp.status != 200:
                    content = f"⚠️ Could not fetch APOD image. See here: {archive_link}"
                    if use_embeds:
                        embed = discord.Embed(title="Astronomy Picture of the Day", url=archive_link,
                                              description=content, color=discord.Color.red(),
                                              timestamp=datetime.datetime.utcnow())
                        await channel.send(content=message_content or None, embed=embed)
                    else:
                        await channel.send(content=message_content + content)
                    return

                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                img_tag = soup.find("img")
                if img_tag:
                    img_src = "https://apod.nasa.gov/apod/" + img_tag.get("src")
                    title_tag = soup.find("b")
                    title = title_tag.text.strip() if title_tag else "Astronomy Picture of the Day"
                    if use_embeds:
                        embed = discord.Embed(title=title, url=archive_link,
                                              color=discord.Color.blue(),
                                              timestamp=datetime.datetime.utcnow())
                        embed.set_image(url=img_src)
                        await channel.send(content=message_content or None, embed=embed)
                    else:
                        await channel.send(content=message_content + f"**{title}**\n{img_src}")
                else:
                    content = f"📹 Videos are not yet supported, go here to see today's video: {archive_link}"
                    if use_embeds:
                        embed = discord.Embed(title="Astronomy Picture of the Day", url=archive_link,
                                              description=content, color=discord.Color.orange(),
                                              timestamp=datetime.datetime.utcnow())
                        await channel.send(content=message_content or None, embed=embed)
                    else:
                        await channel.send(content=message_content + content)
        except aiohttp.ClientError:
            content = f"⚠️ Could not fetch APOD image. See here: {archive_link}"
            if use_embeds:
                embed = discord.Embed(title="Astronomy Picture of the Day", url=archive_link,
                                      description=content, color=discord.Color.red(),
                                      timestamp=datetime.datetime.utcnow())
                await channel.send(content=message_content or None, embed=embed)
            else:
                await channel.send(content=message_content + content)

    @commands.command()
    async def apod(self, ctx, date: str = None):
        """Get the Astronomy Picture of the Day. Optional: DD/MM/YYYY"""
        if date:
            try:
                parsed = datetime.datetime.strptime(date, "%d/%m/%Y").date()
            except ValueError:
                await ctx.send("❌ Invalid date format. Use DD/MM/YYYY.")
                return
            if parsed > datetime.date.today():
                await ctx.send("❌ Date is in the future. Use today or earlier.")
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
        """APOD settings"""
        if ctx.invoked_subcommand is None:
            guild_conf = self.config.guild(ctx.guild)
            channel_id = await guild_conf.channel_id()
            post_time = await guild_conf.post_time()
            include_info = await guild_conf.include_info()
            ping_target = await guild_conf.ping_target()
            channel = ctx.guild.get_channel(channel_id) if channel_id else None
            role = ctx.guild.get_role(ping_target) if ping_target else None
            user = ctx.guild.get_member(ping_target) if ping_target else None
            ping_display = role.mention if role else user.mention if user else "None"
            use_embeds = await self.config.use_embeds()
            api_key = await self.config.api_key()
            await ctx.send(
                f"**APOD Settings:**\n"
                f"Channel: {channel.mention if channel else 'Not set'}\n"
                f"Post Time (UTC): {post_time}\n"
                f"Include Info: {include_info}\n"
                f"Ping Target: {ping_display}\n"
                f"Use Embeds (owner only): {use_embeds}\n"
                f"API Key: {'Set' if api_key else 'Not Set'}"
            )

    @apodset.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ APOD channel set to {channel.mention}")
        await self.restart_guild_task(ctx.guild)

    @apodset.command()
    async def time(self, ctx, time: str):
        try:
            datetime.datetime.strptime(time, "%H:%M")
        except ValueError:
            await ctx.send("❌ Invalid time format. Use HH:MM (24h, UTC).")
            return
        await self.config.guild(ctx.guild).post_time.set(time)
        await ctx.send(f"✅ APOD post time set to {time} UTC.")
        await self.restart_guild_task(ctx.guild)

    @apodset.command()
    async def includeinfo(self, ctx, value: bool):
        await self.config.guild(ctx.guild).include_info.set(value)
        await ctx.send(f"✅ Include info set to {value}.")

    @apodset.command()
    async def ping(self, ctx, target: discord.Role | discord.Member | None):
        if target:
            await self.config.guild(ctx.guild).ping_target.set(target.id)
            await ctx.send(f"✅ Will ping {target.mention} for daily APOD.")
        else:
            await self.config.guild(ctx.guild).ping_target.clear()
            await ctx.send("✅ Cleared APOD ping target.")

    @apodset.command()
    @checks.is_owner()
    async def embeds(self, ctx, value: bool):
        await self.config.use_embeds.set(value)
        await ctx.send(f"✅ Embeds {'enabled' if value else 'disabled'} globally.")

    @apodset.command()
    @checks.is_owner()
    async def apikey(self, ctx, key: str):
        await self.config.api_key.set(key)
        await ctx.send("✅ NASA API key updated.")

    async def restart_guild_task(self, guild: discord.Guild):
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
