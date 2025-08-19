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
            "fields": {}
        }
        default_guild = {
            "categories": {},
            "allow_user_edit": False,
            "roles_allowed": []
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

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

    @commands.group()
    async def cprofileset(self, ctx):
        pass

    @cprofileset.command(name="setup")
    async def setup_profile(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        guild_data = await self.config.guild(ctx.guild).all()
        member_roles = [role.id for role in ctx.author.roles]
        if member == ctx.author and not guild_data.get("allow_user_edit", False) and not any(r in guild_data['roles_allowed'] for r in member_roles):
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

    @cprofileset.command(name="adminsetup")
    @checks.is_owner()
    async def admin_setup(self, ctx):
        """Admin DM menu to manage categories, roles, global edit permission, remove profiles, and edit any user's profile."""
        try:
            dm = await ctx.author.create_dm()
        except discord.Forbidden:
            return await ctx.send("❌ Cannot send DMs to the bot owner.")

        await dm.send("Starting admin setup. You can manage categories, toggle user edits, roles, remove profiles, or edit any user's profile.")
        def check(m):
            return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)

        while True:
            await dm.send("Type `addcategory`, `removecategory`, `toggleedit`, `setroles`, `removeprofile`, `editprofile`, or `done` to finish.")
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=300)
            except TimeoutError:
                await dm.send("⌛ Admin setup timed out.")
                break

            content = msg.content.lower()

            if content == 'done':
                await dm.send("✅ Admin setup complete.")
                break

            elif content.startswith('addcategory'):
                parts = msg.content.split()
                if len(parts) != 4:
                    await dm.send("❌ Usage: addcategory <identifier> <display_name> <type:text|url>")
                    continue
                _, identifier, display_name, type_ = parts
                async with self.config.guild(ctx.guild).categories() as cats:
                    if identifier in cats:
                        await dm.send("❌ That identifier already exists.")
                    else:
                        cats[identifier] = {"name": display_name, "type": type_}
                        await dm.send(f"✅ Added category `{identifier}`.")

            elif content.startswith('removecategory'):
                parts = msg.content.split()
                if len(parts) != 2:
                    await dm.send("❌ Usage: removecategory <identifier>")
                    continue
                _, identifier = parts
                async with self.config.guild(ctx.guild).categories() as cats:
                    if identifier not in cats:
                        await dm.send("❌ That category doesn't exist.")
                        continue
                    del cats[identifier]
                async with self.config.all_users() as users:
                    for user_id, user_data in users.items():
                        if 'fields' in user_data and identifier in user_data['fields']:
                            del user_data['fields'][identifier]
                await dm.send(f"✅ Category `{identifier}` removed from guild and all user profiles.")

            elif content.startswith('toggleedit'):
                parts = msg.content.split()
                if len(parts) != 2:
                    await dm.send("❌ Usage: toggleedit <True|False>")
                    continue
                allow_bool = parts[1].lower() == 'true'
                await self.config.guild(ctx.guild).allow_user_edit.set(allow_bool)
                await dm.send(f"✅ Users can now {'edit' if allow_bool else 'not edit'} their profiles globally.")

            elif content.startswith('setroles'):
                await dm.send("Type role IDs to allow users to edit their profiles, separated by spaces, or 'none' to clear.")
                try:
                    role_msg = await self.bot.wait_for('message', check=check, timeout=120)
                    if role_msg.content.lower() == 'none':
                        await self.config.guild(ctx.guild).roles_allowed.set([])
                    else:
                        role_ids = [int(r) for r in role_msg.content.split() if r.isdigit()]
                        await self.config.guild(ctx.guild).roles_allowed.set(role_ids)
                    await dm.send("✅ Roles allowed for user edits have been updated.")
                except TimeoutError:
                    await dm.send("⌛ Timed out setting roles.")

            elif content.startswith('removeprofile') or content.startswith('editprofile'):
                action = content
                await dm.send("Type the username#discriminator or user ID of the member.")
                try:
                    user_msg = await self.bot.wait_for('message', check=check, timeout=120)
                    guild = ctx.guild
                    user_input = user_msg.content.strip()

                    user = None
                    if user_input.isdigit():
                        user = guild.get_member(int(user_input))
                    elif '#' in user_input:
                        name, discrim = user_input.split('#')
                        user = discord.utils.get(guild.members, name=name, discriminator=discrim)

                    if not user:
                        await dm.send("❌ User not found.")
                        continue

                    if action == 'removeprofile':
                        await self.config.user(user).clear()
                        await dm.send(f"✅ Removed profile for {user.display_name}.")
                    else:
                        user_data = await self.config.user(user).all()
                        guild_data = await self.config.guild(ctx.guild).all()
                        for identifier, category in guild_data['categories'].items():
                            await dm.send(f"Set value for {category['name']} ({category['type']}) or type 'disable' to skip.")
                            try:
                                value_msg = await self.bot.wait_for('message', check=check, timeout=120)
                                if value_msg.content.lower() != 'disable':
                                    if category['type'] == 'url' and not URL_REGEX.match(value_msg.content):
                                        await dm.send("⚠️ Invalid URL, skipping this field.")
                                        continue
                                    async with self.config.user(user).fields() as fields:
                                        fields[identifier] = value_msg.content
                            except TimeoutError:
                                await dm.send(f"⌛ Timed out for {category['name']}, skipping.")
                        await dm.send(f"✅ Edited profile for {user.display_name}.")
                except TimeoutError:
                    await dm.send("⌛ Timed out waiting for user input.")

async def setup(bot):
    await bot.add_cog(Profile(bot))
