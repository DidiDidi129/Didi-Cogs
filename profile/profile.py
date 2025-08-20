import discord
from redbot.core import commands, Config, checks
import re
import shlex
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
        """Profile settings. Only 'setup' and 'adminsetup' remain."""
        if ctx.invoked_subcommand is None:
            await ctx.send("❌ Available subcommands: `setup`, `adminsetup`")

    async def user_can_edit(self, ctx, member):
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

    # --------------------------
    # Admin setup in-channel
    # --------------------------
    @profileset.command(name="adminsetup")
    @checks.is_owner()
    async def admin_setup(self, ctx):
        """Admin setup: categories, user fields, toggle edits, view all categories and users."""
        channel = ctx.channel
        await channel.send(
            "Starting admin setup. Options: add/remove categories, edit/remove user fields, toggle user edits, view all categories and users."
        )

        def check(m):
            return m.author == ctx.author and m.channel == channel

        while True:
            await channel.send(
                "Commands:\n"
                "`addcategory <id> \"<display name>\" <type:text|url>`\n"
                "`removecategory <id>`\n"
                "`toggleedit <True|False>`\n"
                "`edituser <@user> <field_or_color> <value>`\n"
                "`removeuserfield <@user> <field>`\n"
                "`view`\n"
                "`done`"
            )
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=300)
            except TimeoutError:
                await channel.send("⌛ Admin setup timed out.")
                break

            try:
                # Normalize curly quotes to straight quotes before parsing
                normalized = msg.content.replace("“", "\"").replace("”", "\"")
                parts = shlex.split(normalized)
            except ValueError as e:
                await channel.send(f"❌ Parsing error: {e}")
                continue

            if not parts:
                continue
            command = parts[0].lower()

            if command == "done":
                await channel.send("✅ Admin setup complete.")
                break

            elif command == "view":
                guild_data = await self.config.guild(ctx.guild).all()
                categories = guild_data["categories"]
                category_list = "\n".join(f"`{cid}`: {cat['name']} ({cat['type']})" for cid, cat in categories.items()) or "None"

                all_users = await self.config.all_users()
                users_with_profiles = []
                for user_id_str, data in all_users.items():
                    member = ctx.guild.get_member(int(user_id_str))
                    if member is not None:
                        if data.get("color") or data.get("fields"):
                            users_with_profiles.append(f"{member} (`{user_id_str}`)")
                user_list = "\n".join(users_with_profiles) or "None"

                await channel.send(f"**Categories:**\n{category_list}\n\n**Users with profiles:**\n{user_list}")

            elif command == "addcategory":
                if len(parts) != 4:
                    await channel.send("❌ Usage: addcategory <id> \"<display_name>\" <type:text|url>")
                    continue
                _, identifier, display_name, type_ = parts
                async with self.config.guild(ctx.guild).categories() as cats:
                    if identifier in cats:
                        await channel.send("❌ That identifier already exists.")
                    else:
                        cats[identifier] = {"name": display_name, "type": type_}
                        await channel.send(f"✅ Added category `{identifier}`.")

            elif command == "removecategory":
                if len(parts) != 2:
                    await channel.send("❌ Usage: removecategory <id>")
                    continue
                _, identifier = parts
                async with self.config.guild(ctx.guild).categories() as cats:
                    if identifier not in cats:
                        await channel.send("❌ That category does not exist.")
                        continue
                    del cats[identifier]
                all_users = await self.config.all_users()
                for user_id, _ in all_users.items():
                    async with self.config.user_from_id(user_id).fields() as fields:
                        if identifier in fields:
                            del fields[identifier]
                await channel.send(f"✅ Category `{identifier}` removed from guild and all users.")

            elif command == "toggleedit":
                if len(parts) != 2:
                    await channel.send("❌ Usage: toggleedit <True|False>")
                    continue
                allow_bool = parts[1].lower() == "true"
                await self.config.guild(ctx.guild).allow_user_edit.set(allow_bool)
                await channel.send(f"✅ Users can now {'edit' if allow_bool else 'not edit'} profiles globally.")

            elif command == "edituser":
                if len(parts) != 4:
                    await channel.send("❌ Usage: edituser <@user> <field_or_color> <value>")
                    continue
                _, user_mention, field, value = parts
                member = None
                if user_mention.startswith("<@") and user_mention.endswith(">"):
                    user_id = int(user_mention.strip("<@!>"))
                    member = ctx.guild.get_member(user_id)
                if member is None:
                    await channel.send("❌ Could not find that user in this server.")
                    continue
                if field.lower() == "color":
                    try:
                        color = discord.Color(int(value.strip("#"), 16))
                        await self.config.user(member).color.set(color.value)
                        await channel.send(f"✅ {member.display_name}'s color updated.")
                    except ValueError:
                        await channel.send("❌ Invalid color hex value.")
                else:
                    guild_data = await self.config.guild(ctx.guild).all()
                    if field not in guild_data["categories"]:
                        await channel.send("❌ That category does not exist.")
                        continue
                    category = guild_data["categories"][field]
                    if category["type"] == "url" and not URL_REGEX.match(value):
                        await channel.send("❌ That value must be a valid URL.")
                        continue
                    async with self.config.user(member).fields() as fields:
                        fields[field] = value
                    await channel.send(f"✅ {member.display_name}'s {category['name']} updated.")

            elif command == "removeuserfield":
                if len(parts) != 3:
                    await channel.send("❌ Usage: removeuserfield <@user> <field>")
                    continue
                _, user_mention, field = parts
                member = None
                if user_mention.startswith("<@") and user_mention.endswith(">"):
                    user_id = int(user_mention.strip("<@!>"))
                    member = ctx.guild.get_member(user_id)
                if member is None:
                    await channel.send("❌ Could not find that user in this server.")
                    continue
                async with self.config.user(member).fields() as fields:
                    if field in fields:
                        del fields[field]
                        await channel.send(f"✅ Removed `{field}` from {member.display_name}'s profile.")
                    else:
                        await channel.send(f"❌ {member.display_name} does not have a `{field}` field.")

async def setup(bot):
    await bot.add_cog(Profile(bot))
