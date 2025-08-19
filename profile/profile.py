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
            "can_edit": True
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
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        guild_data = await self.config.guild(ctx.guild).all()

        color = discord.Color(user_data['color']) if user_data['color'] else member.color
        embed = discord.Embed(
            title=f"{member.display_name}'s Profile",
            color=color,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Username", value=str(member), inline=True)

        for identifier, category in guild_data["categories"].items():
            if identifier in user_data["fields"]:
                embed.add_field(name=category["name"], value=user_data["fields"][identifier], inline=False)

        await ctx.send(embed=embed)

    # --------------------------
    # User settings
    # --------------------------
    @commands.group()
    async def cprofileset(self, ctx):
        pass

    @cprofileset.command(name="color")
    async def set_color(self, ctx, color: discord.Color, member: discord.Member = None):
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        if member == ctx.author and not user_data.get("can_edit", True):
            return await ctx.send("❌ You are not allowed to edit your profile.")
        await self.config.user(member).color.set(color.value)
        await ctx.send(f"✅ {member.display_name}'s profile color has been updated.")

    @cprofileset.command(name="reset")
    async def reset_profile(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        if member == ctx.author and not user_data.get("can_edit", True):
            return await ctx.send("❌ You are not allowed to edit your profile.")
        await self.config.user(member).clear()
        await ctx.send(f"✅ {member.display_name}'s profile has been reset.")

    @cprofileset.command(name="setup")
    async def setup_profile(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        if member == ctx.author and not user_data.get("can_edit", True):
            return await ctx.send("❌ You are not allowed to edit your profile.")

        try:
            dm = await member.create_dm()
        except discord.Forbidden:
            return await ctx.send("❌ I cannot send DMs to the user.")

        await dm.send("Let's set up your profile! Type a hex color (e.g., #FF0000) for your embed or 'disable' to skip.")
        def check_color(m):
            return m.author == member and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await self.bot.wait_for('message', check=check_color, timeout=120)
            if msg.content.lower() != 'disable':
                try:
                    color = discord.Color(int(msg.content.strip('#'), 16))
                    await self.config.user(member).color.set(color.value)
                except ValueError:
                    await dm.send("⚠️ Invalid color, skipping.")
        except TimeoutError:
            await dm.send("⌛ Setup timed out, skipping color.")

        guild_data = await self.config.guild(ctx.guild).all()
        for identifier, category in guild_data['categories'].items():
            await dm.send(f"Set your {category['name']} ({category['type']}) or type 'disable' to skip.")
            def check_field(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            try:
                msg = await self.bot.wait_for('message', check=check_field, timeout=120)
                if msg.content.lower() != 'disable':
                    if category['type'] == 'url' and not URL_REGEX.match(msg.content):
                        await dm.send("⚠️ Invalid URL, skipping this field.")
                        continue
                    async with self.config.user(member).fields() as fields:
                        fields[identifier] = msg.content
            except TimeoutError:
                await dm.send(f"⌛ Setup timed out for {category['name']}, skipping.")

        await dm.send("✅ Profile setup complete!")

    @cprofileset.command(name="listfields")
    async def list_fields(self, ctx):
        guild_data = await self.config.guild(ctx.guild).all()
        if not guild_data['categories']:
            return await ctx.send("❌ No profile categories available.")
        message = "**Available Profile Categories:**\n"
        for identifier, category in guild_data['categories'].items():
            message += f"`{identifier}`: {category['name']} ({category['type']})\n"
        await ctx.send(message)

    @cprofileset.command(name="setfield")
    async def set_field(self, ctx, identifier: str, *, value: str, member: discord.Member = None):
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        if member == ctx.author and not user_data.get("can_edit", True):
            return await ctx.send("❌ You are not allowed to edit your profile.")
        guild_data = await self.config.guild(ctx.guild).all()
        if identifier not in guild_data['categories']:
            return await ctx.send("❌ That category doesn't exist.")
        category = guild_data['categories'][identifier]
        if category['type'] == 'url' and not URL_REGEX.match(value):
            return await ctx.send("❌ That value must be a valid URL.")
        async with self.config.user(member).fields() as fields:
            fields[identifier] = value
        await ctx.send(f"✅ {member.display_name}'s {category['name']} has been updated.")

    @cprofileset.command(name="adminsetup")
    @checks.is_owner()
    async def admin_setup(self, ctx):
        """Walk an admin through creating categories and managing user permissions."""
        await ctx.send("Starting admin setup. You can add categories and manage user permissions.")
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        while True:
            await ctx.send("Type `addcategory` to add a new category, `allowedit` to toggle user edit permission, `done` to finish.")
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=300)
            except TimeoutError:
                await ctx.send("⌛ Admin setup timed out.")
                break

            content = msg.content.lower()
            if content == 'done':
                await ctx.send("✅ Admin setup complete.")
                break
            elif content.startswith('addcategory'):
                parts = msg.content.split()
                if len(parts) != 4:
                    await ctx.send("❌ Usage: addcategory <identifier> <display_name> <type:text|url>")
                    continue
                _, identifier, display_name, type_ = parts
                async with self.config.guild(ctx.guild).categories() as cats:
                    if identifier in cats:
                        await ctx.send("❌ That identifier already exists.")
                    else:
                        cats[identifier] = {"name": display_name, "type": type_}
                        await ctx.send(f"✅ Added category `{identifier}`.")
            elif content.startswith('allowedit'):
                parts = msg.content.split()
                if len(parts) != 3:
                    await ctx.send("❌ Usage: allowedit <@user> <True|False>")
                    continue
                _, member_mention, allow = parts
                member = await commands.MemberConverter().convert(ctx, member_mention)
                allow_bool = allow.lower() == 'true'
                async with self.config.user(member).all() as user_data:
                    user_data['can_edit'] = allow_bool
                await ctx.send(f"✅ {member.display_name} can now {'edit' if allow_bool else 'not edit'} their profile.")

    # --------------------------
    # Admin category commands
    # --------------------------
    @cprofileset.group(name="category")
    @checks.is_owner()
    async def category_group(self, ctx):
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

    @category_group.command(name="allowedit")
    async def allow_edit(self, ctx, member: discord.Member, allow: bool):
        async with self.config.user(member).all() as user_data:
            user_data['can_edit'] = allow
        await ctx.send(f"✅ {member.display_name} can now {'edit' if allow else 'not edit'} their profile.")

    @category_group.command(name="edituser")
    async def edit_user(self, ctx, member: discord.Member, identifier: str, *, value: str):
        guild_data = await self.config.guild(ctx.guild).all()
        if identifier not in guild_data['categories']:
            return await ctx.send("❌ That category doesn't exist.")
        category = guild_data['categories'][identifier]
        if category['type'] == 'url' and not URL_REGEX.match(value):
            return await ctx.send("❌ That value must be a valid URL.")
        async with self.config.user(member).fields() as fields:
            fields[identifier] = value
        await ctx.send(f"✅ {member.display_name}'s {category['name']} has been updated.")


async def setup(bot):
    await bot.add_cog(Profile(bot))