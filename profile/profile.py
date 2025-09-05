import discord
from redbot.core import commands, Config, checks
import re
from typing import Literal

URL_REGEX = re.compile(r"^(https?://[\w.-]+(?:\.[\w\.-]+)+[/\w\-._~:/?#[\]@!$&'()*+,;=.]+)?$")

class Profile(commands.Cog):
    """User profiles with customizable fields."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=13572468)
        default_user = {
            "color": None,
            "fields": {}
        }
        default_guild = {
            "categories": {},  # {identifier: {"name": str, "type": str}}
            "allow_user_edit": True,  # global toggle for user edits
            "role_bypass": []  # roles that bypass global toggle
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    # --------------------------
    # Profile view
    # --------------------------
    @commands.command(name="profile")
    async def profile(self, ctx, member: discord.Member = None):
        """View your own or another member's profile."""
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        guild_data = await self.config.guild(ctx.guild).all()

        color = discord.Color(user_data['color']) if user_data['color'] else member.color
        embed = discord.Embed(
            title=f"{member.display_name}'s Profile",
            color=color
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Username", value=str(member), inline=True)

        for identifier, category in guild_data["categories"].items():
            if identifier in user_data["fields"]:
                embed.add_field(name=category["name"], value=user_data["fields"][identifier], inline=False)

        await ctx.send(embed=embed)

    # --------------------------
    # Profile settings
    # --------------------------
    @commands.group(name="profileset")
    async def profileset(self, ctx):
        """Profile settings group (contains setup and admin tools)."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    async def user_can_edit(self, ctx, member):
        """Check whether the invoking user is allowed to edit a profile."""
        guild_data = await self.config.guild(ctx.guild).all()
        if member != ctx.author:
            return True
        if guild_data.get("allow_user_edit", True):
            return True
        # role bypass
        bypass_roles = guild_data.get("role_bypass", [])
        return any(r.id in bypass_roles for r in ctx.author.roles)

    @profileset.command(name="setup")
    async def setup_profile(self, ctx, member: discord.Member = None):
        """Interactive DM-based setup for a user profile."""
        member = member or ctx.author
        if not await self.user_can_edit(ctx, member):
            return await ctx.send("❌ You are not allowed to edit your profile.")

        try:
            dm = await member.create_dm()
        except discord.Forbidden:
            return await ctx.send("❌ Cannot DM the user.")

        await dm.send("Type a hex color (e.g., #FF0000) or 'disable' to skip.")
        def check_color(m):
            return m.author == member and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await self.bot.wait_for('message', check=check_color, timeout=120)
            if msg.content.lower() != 'disable':
                try:
                    color = discord.Color(int(msg.content.strip('#'), 16))
                    await self.config.user(member).color.set(color.value)
                except ValueError:
                    await dm.send("⚠️ Invalid color. Skipping.")
        except TimeoutError:
            await dm.send("⌛ Color setup timed out. Skipping.")

        guild_data = await self.config.guild(ctx.guild).all()
        for identifier, category in guild_data['categories'].items():
            await dm.send(f"Set your {category['name']} ({category['type']}) or 'disable' to skip.")
            def check_field(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            try:
                msg = await self.bot.wait_for('message', check=check_field, timeout=120)
                if msg.content.lower() != 'disable':
                    if category['type'] == 'url' and not URL_REGEX.match(msg.content):
                        await dm.send("⚠️ Invalid URL. Skipping this field.")
                        continue
                    async with self.config.user(member).fields() as fields:
                        fields[identifier] = msg.content
            except TimeoutError:
                await dm.send(f"⌛ Setup timed out for {category['name']}. Skipping.")

        await dm.send("✅ Profile setup complete!")

    # -----------
    # Admin tools
    # -----------
    @profileset.group(name="admin")
    @commands.admin_or_permissions(administrator=True)
    async def profileset_admin(self, ctx):
        """Admin tools for managing categories and user profiles."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @profileset_admin.command(name="addcategory")
    async def admin_add_category(self, ctx, identifier: str, display_name: str, type_: Literal["text", "url"]):
        """Add a new profile category."""
        async with self.config.guild(ctx.guild).categories() as cats:
            if identifier in cats:
                await ctx.send("❌ That identifier already exists.")
            else:
                cats[identifier] = {"name": display_name, "type": type_}
                await ctx.send(f"✅ Added category `{identifier}`.")

    @profileset_admin.command(name="removecategory")
    async def admin_remove_category(self, ctx, identifier: str):
        """Remove a profile category from the guild and all users."""
        async with self.config.guild(ctx.guild).categories() as cats:
            if identifier not in cats:
                return await ctx.send("❌ That category does not exist.")
            del cats[identifier]

        all_users = await self.config.all_users()
        for user_id, _ in all_users.items():
            async with self.config.user_from_id(user_id).fields() as fields:
                if identifier in fields:
                    del fields[identifier]
        await ctx.send(f"✅ Category `{identifier}` removed.")

    @profileset_admin.command(name="toggleedit")
    async def admin_toggle_edit(self, ctx, allow: bool):
        """Toggle whether users can edit their profiles."""
        await self.config.guild(ctx.guild).allow_user_edit.set(allow)
        await ctx.send(f"✅ Users can now {'edit' if allow else 'not edit'} their profiles.")

    @profileset_admin.command(name="edituser")
    async def admin_edit_user(self, ctx, member: discord.Member, field: str, value: str):
        """Edit a user's profile field or color."""
        if field.lower() == "color":
            try:
                color = discord.Color(int(value.strip("#"), 16))
                await self.config.user(member).color.set(color.value)
                return await ctx.send(f"✅ {member.display_name}'s color updated.")
            except ValueError:
                return await ctx.send("❌ Invalid color hex value.")

        guild_data = await self.config.guild(ctx.guild).all()
        if field not in guild_data["categories"]:
            return await ctx.send("❌ That category does not exist.")

        category = guild_data["categories"][field]
        if category["type"] == "url" and not URL_REGEX.match(value):
            return await ctx.send("❌ That value must be a valid URL.")

        async with self.config.user(member).fields() as fields:
            fields[field] = value
        await ctx.send(f"✅ {member.display_name}'s {category['name']} updated.")

    @profileset_admin.command(name="removeuserfield")
    async def admin_remove_user_field(self, ctx, member: discord.Member, field: str):
        """Remove a specific field from a user's profile."""
        async with self.config.user(member).fields() as fields:
            if field in fields:
                del fields[field]
                await ctx.send(f"✅ Removed `{field}` from {member.display_name}'s profile.")
            else:
                await ctx.send(f"❌ {member.display_name} does not have a `{field}` field.")

    @profileset_admin.command(name="view")
    async def admin_view(self, ctx):
        """View all categories and users with profiles."""
        guild_data = await self.config.guild(ctx.guild).all()
        categories = guild_data["categories"]
        category_list = "\n".join(
            f"`{cid}`: {cat['name']} ({cat['type']})"
            for cid, cat in categories.items()
        ) or "None"

        all_users = await self.config.all_users()
        users_with_profiles = []
        for user_id_str, data in all_users.items():
            member = ctx.guild.get_member(int(user_id_str))
            if member is not None and (data.get("color") or data.get("fields")):
                users_with_profiles.append(f"{member} (`{user_id_str}`)")
        user_list = "\n".join(users_with_profiles) or "None"

        await ctx.send(f"**Categories:**\n{category_list}\n\n**Users with profiles:**\n{user_list}")
