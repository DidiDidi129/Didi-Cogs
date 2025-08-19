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
            "bio": None,
            "fields": {},
        }
        default_guild = {
            "categories": {},  # {identifier: {"name": str, "type": str}}
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    # --------------------------
    # Profile view command
    # --------------------------
    @commands.command()
    async def cprofile(self, ctx, member: discord.Member = None):
        """Show a user's profile."""
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        guild_data = await self.config.guild(ctx.guild).all()

        embed = discord.Embed(
            title=f"{member.display_name}'s Profile",
            color=member.color,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        if user_data["bio"]:
            embed.add_field(name="Bio", value=user_data["bio"], inline=False)

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
        """Set your profile information."""
        pass

    @cprofileset.command(name="bio")
    async def set_bio(self, ctx, *, bio: str):
        """Set your bio."""
        await self.config.user(ctx.author).bio.set(bio)
        await ctx.send("✅ Your bio has been updated.")

    @cprofileset.command(name="reset")
    async def reset_profile(self, ctx):
        """Reset your profile."""
        await self.config.user(ctx.author).clear()
        await ctx.send("✅ Your profile has been reset.")

    @cprofileset.command()
    async def field(self, ctx, identifier: str, *, value: str):
        """Set one of your custom profile fields."""
        guild_data = await self.config.guild(ctx.guild).all()
        if identifier not in guild_data["categories"]:
            return await ctx.send("❌ That category doesn't exist.")

        category = guild_data["categories"][identifier]
        if category["type"] == "url":
            if not URL_REGEX.match(value):
                return await ctx.send("❌ That value must be a valid URL.")

        async with self.config.user(ctx.author).fields() as fields:
            fields[identifier] = value
        await ctx.send(f"✅ Your {category['name']} has been updated.")

    # --------------------------
    # Admin commands
    # --------------------------
    @cprofileset.group(name="category")
    @checks.is_owner()
    async def category_group(self, ctx):
        """Manage profile categories."""
        pass

    @category_group.command(name="add")
    async def add_category(
        self, ctx, identifier: str, display_name: str, type: Literal["text", "url"]
    ):
        """Add a new category. Type can be `text` or `url`."""
        async with self.config.guild(ctx.guild).categories() as cats:
            if identifier in cats:
                return await ctx.send("❌ That identifier already exists.")
            cats[identifier] = {"name": display_name, "type": type}
        await ctx.send(
            f"✅ Added category `{identifier}` with name `{display_name}` and type `{type}`."
        )

    @category_group.command(name="remove")
    async def remove_category(self, ctx, identifier: str):
        """Remove a category."""
        async with self.config.guild(ctx.guild).categories() as cats:
            if identifier not in cats:
                return await ctx.send("❌ That category doesn't exist.")
            del cats[identifier]
        await ctx.send(f"✅ Category `{identifier}` has been removed.")


async def setup(bot):
    await bot.add_cog(Profile(bot))
