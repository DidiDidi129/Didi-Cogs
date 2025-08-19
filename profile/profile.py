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

        color = discord.Color(user_data['color']) if user_data['color'] else member.color
        embed = discord.Embed(
            title=f"{member.display_name}'s Profile",
            color=color,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        # Username + Pronouns
        username_line = str(member)
        if user_data.get('pronouns'):
            username_line += f' | {user_data["pronouns"]}'
        embed.add_field(name="Username", value=username_line, inline=False)

        # Discord bio
        if hasattr(member, 'bio') and member.bio:
            embed.add_field(name="Bio", value=member.bio, inline=False)

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
        """Set your profile information."""
        pass

    @cprofileset.command(name="color")
    async def set_color(self, ctx, color: discord.Color):
        """Set your profile embed color."""
        await self.config.user(ctx.author).color.set(color.value)
        await ctx.send(f"✅ Your profile color has been updated.")

    @cprofileset.command(name="pronouns")
    async def set_pronouns(self, ctx, *, pronouns: str):
        """Set your pronouns to display next to your username."""
        await self.config.user(ctx.author).pronouns.set(pronouns)
        await ctx.send(f"✅ Your pronouns have been updated to: {pronouns}")

    @cprofileset.command(name="reset")
    async def reset_profile(self, ctx):
        """Reset your profile."""
        await self.config.user(ctx.author).clear()
        await ctx.send("✅ Your profile has been reset.")

    @cprofileset.command()
    async def field(self, ctx, identifier: str, *, value: str):
        """Set a value for a predefined category."""
        guild_data = await self.config.guild(ctx.guild).all()
        if identifier not in guild_data["categories"]:
            return await ctx.send("❌ That category doesn't exist.")

        category = guild_data["categories"][identifier]
        if category['type'] == 'url' and not URL_REGEX.match(value):
            return await ctx.send("❌ That value must be a valid URL.")

        async with self.config.user(ctx.author).fields() as fields:
            fields[identifier] = value
        await ctx.send(f"✅ Your {category['name']} has been updated.")

    @cprofileset.command(name="setup")
    async def setup_profile(self, ctx):
        """Walk the user through setting up their profile in DMs."""
        try:
            dm = await ctx.author.create_dm()
        except discord.Forbidden:
            return await ctx.send("❌ I cannot send you DMs. Please allow DMs from this server.")

        # Ask for embed color
        await dm.send("Let's set up your profile! Type a hex color (e.g., #FF0000) for your embed or 'disable' to skip.")
        def check_color(m):
            return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await self.bot.wait_for('message', check=check_color, timeout=120)
            if msg.content.lower() != 'disable':
                try:
                    color = discord.Color(int(msg.content.strip('#'), 16))
                    await self.config.user(ctx.author).color.set(color.value)
                except ValueError:
                    await dm.send("⚠️ Invalid color, skipping.")
        except TimeoutError:
            await dm.send("⌛ Setup timed out, skipping color.")

        # Ask for pronouns
        await dm.send("Enter your pronouns to display next to your username or 'disable' to skip.")
        def check_pronouns(m):
            return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        try:
            msg = await self.bot.wait_for('message', check=check_pronouns, timeout=120)
            if msg.content.lower() != 'disable':
                await self.config.user(ctx.author).pronouns.set(msg.content)
        except TimeoutError:
            await dm.send("⌛ Setup timed out for pronouns, skipping.")

        # Ask for each predefined field
        guild_data = await self.config.guild(ctx.guild).all()
        for identifier, category in guild_data['categories'].items():
            await dm.send(f"Set your {category['name']} ({category['type']}) or type 'disable' to skip.")

            def check_field(m):
                return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)

            try:
                msg = await self.bot.wait_for('message', check=check_field, timeout=120)
                if msg.content.lower() != 'disable':
                    if category['type'] == 'url' and not URL_REGEX.match(msg.content):
                        await dm.send("⚠️ Invalid URL, skipping this field.")
                        continue
                    async with self.config.user(ctx.author).fields() as fields:
                        fields[identifier] = msg.content
            except TimeoutError:
                await dm.send(f"⌛ Setup timed out for {category['name']}, skipping.")

        await dm.send("✅ Profile setup complete!")

    # --------------------------
    # Admin commands
    # --------------------------
    @cprofileset.group(name="category")
    @checks.is_owner()
    async def category_group(self, ctx):
        """Manage profile categories."""
        pass

    @category_group.command(name="add")
    async def add_category(self, ctx, identifier: str, display_name: str, type: Literal["text", "url"]):
        async with self.config.guild(ctx.guild).categories() as cats:
            if identifier in cats:
                return await ctx.send("❌ That identifier already exists.")
            cats[identifier] = {"name": display_name, "type": type}
        await ctx.send(f"✅ Added category `{identifier}` with name `{display_name}` and type `{type}`.")

    @category_group.command(name="remove")
    async def remove_category(self, ctx, identifier: str):
        async with self.config.guild(ctx.guild).categories() as cats:
            if identifier not in cats:
                return await ctx.send("❌ That category doesn't exist.")
            del cats[identifier]
        await ctx.send(f"✅ Category `{identifier}` has been removed.")


async def setup(bot):
    await bot.add_cog(Profile(bot))