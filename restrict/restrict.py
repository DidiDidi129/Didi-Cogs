import discord
from discord.ext import commands
from redbot.core import commands as redcommands
from redbot.core import Config
from typing import Union


class Restrict(redcommands.Cog):
    """Restrict and unrestrict users by assigning roles."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8392010293847, force_registration=True)
        default_guild = {
            "restricted_role": None,
            "perms_role": None
        }
        self.config.register_guild(**default_guild)

    async def _can_manage(self, ctx: redcommands.Context):
        """Check if author has the perms role or is admin."""
        perms_role_id = await self.config.guild(ctx.guild).perms_role()
        if perms_role_id is None:
            return ctx.author.guild_permissions.administrator

        perms_role = ctx.guild.get_role(perms_role_id)
        if perms_role in ctx.author.roles or ctx.author.guild_permissions.administrator:
            return True
        return False

    @redcommands.command()
    async def restrict(self, ctx: redcommands.Context, user: Union[discord.Member, int, str]):
        """Restrict a user (by mention, username, or ID)."""
        if not await self._can_manage(ctx):
            return await ctx.send("❌ You don’t have permission to use this command.")

        restricted_role_id = await self.config.guild(ctx.guild).restricted_role()
        if restricted_role_id is None:
            return await ctx.send("❌ No restricted role set. Use `[p]restrictset role @role`.")

        role = ctx.guild.get_role(restricted_role_id)
        if role is None:
            return await ctx.send("❌ The restricted role no longer exists. Reconfigure it.")

        member = None
        if isinstance(user, discord.Member):
            member = user
        else:
            try:
                member = await ctx.guild.fetch_member(int(user))
            except Exception:
                member = discord.utils.find(lambda m: m.name == str(user), ctx.guild.members)

        if member is None:
            return await ctx.send("❌ Could not find that user.")

        if role in member.roles:
            return await ctx.send("⚠️ User is already restricted.")

        await member.add_roles(role, reason=f"Restricted by {ctx.author}")
        await ctx.send(f"✅ {member.mention} has been restricted.")

    @redcommands.command()
    async def unrestrict(self, ctx: redcommands.Context, user: Union[discord.Member, int, str]):
        """Unrestrict a user (by mention, username, or ID)."""
        if not await self._can_manage(ctx):
            return await ctx.send("❌ You don’t have permission to use this command.")

        restricted_role_id = await self.config.guild(ctx.guild).restricted_role()
        if restricted_role_id is None:
            return await ctx.send("❌ No restricted role set. Use `[p]restrictset role @role`.")

        role = ctx.guild.get_role(restricted_role_id)
        if role is None:
            return await ctx.send("❌ The restricted role no longer exists. Reconfigure it.")

        member = None
        if isinstance(user, discord.Member):
            member = user
        else:
            try:
                member = await ctx.guild.fetch_member(int(user))
            except Exception:
                member = discord.utils.find(lambda m: m.name == str(user), ctx.guild.members)

        if member is None:
            return await ctx.send("❌ Could not find that user.")

        if role not in member.roles:
            return await ctx.send("⚠️ User is not restricted.")

        await member.remove_roles(role, reason=f"Unrestricted by {ctx.author}")
        await ctx.send(f"✅ {member.mention} has been unrestricted.")

    @redcommands.group()
    async def restrictset(self, ctx: redcommands.Context):
        """Configure the restrict cog."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @restrictset.command(name="role")
    async def restrictset_role(self, ctx: redcommands.Context, role: discord.Role):
        """Set the restricted role (the one given to restricted users)."""
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only administrators can set this.")

        await self.config.guild(ctx.guild).restricted_role.set(role.id)
        await ctx.send(f"✅ Restricted role set to {role.mention}.")

    @restrictset.command(name="perms")
    async def restrictset_perms(self, ctx: redcommands.Context, role: discord.Role):
        """Set the role that is allowed to restrict/unrestrict users."""
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Only administrators can set this.")

        await self.config.guild(ctx.guild).perms_role.set(role.id)
        await ctx.send(f"✅ Permissions role set to {role.mention}.")
