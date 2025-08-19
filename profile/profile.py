import discord
from redbot.core import commands, Config, checks
from typing import Literal
import re

URL_REGEX = re.compile(r"^(https?://[\w.-]+(?:\.[\w\.-]+)+[/\w\-._~:/?#[\]@!$&'()*+,;=.]+)?$")

class Profile(commands.Cog):
    """User profiles with customizable fields."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=13572468)
        default_user = {
            "color": None,
            "fields": {},
            "pronouns": None
        }
        default_guild = {
            "categories": {},  # {identifier: {"name": str, "type": str}}
            "allow_pronouns": False
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    # --------------------------
    # Profile view command
    # --------------------------
    @commands.command()
    async def cprofile(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        guild_data = await self.config.guild(ctx.guild).all()

        color = discord.Color(user_data['color']) if user_data['color'] else member.color
        embed = discord.Embed(
            title=f"{member.display_name}'s Profile",
            color=color,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        # Top inline fields: Username and Pronouns (if allowed)
        embed.add_field(name="Username", value=str(member), inline=True)
        if guild_data.get("allow_pronouns", False):
            embed.add_field(name="Pronouns", value=user_data.get('pronouns', 'None'), inline=True)

        # Custom fields
        for identifier, category in guild_data["categories"].items():
            if identifier in user_data["fields"]:
                embed.add_field(
                    name=category["name"],
                    value=user_data["fields"][identifier],
                    inline=False,
                )

        await ctx.send(embed=embed)

    # --------------------------
    # User settings
    # --------------------------
    @commands.group()
    async def cprofileset(self, ctx):
        pass

    @cprofileset.command(name="color")
    async def set_color(self, ctx, color: discord.Color):
        await self.config.user(ctx.author).color.set(color.value)
        await ctx.send(f"✅ Your profile color has been updated.")

    @cprofileset.command(name="pronouns")
    async def set_pronouns(self, ctx, *, pronouns: str):
        guild_data = await self.config.guild(ctx.guild).all()
        if not guild_data.get("allow_pronouns", False):
            return await ctx.send("❌ Pronouns are not enabled by the bot owner.")
        await self.config.user(ctx.author).pronouns.set(pronouns)
        await ctx.send(f"✅ Your pronouns have been updated to: {pronouns}")

    # ... rest of the cog remains unchanged ...

    @category_group.command(name="allowpronouns")
    @checks.is_owner()
    async def allow_pronouns(self, ctx, allow: bool):
        await self.config.guild(ctx.guild).allow_pronouns.set(allow)
        await ctx.send(f"✅ Pronouns are now {'enabled' if allow else 'disabled'} for this server.")


async def setup(bot):
    await bot.add_cog(Profile(bot))