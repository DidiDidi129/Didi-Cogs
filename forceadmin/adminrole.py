from redbot.core import commands, checks
import discord

class AdminRole(commands.Cog):
    """Cog to manage the special Didi Administrator role (bot owner only)."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.is_owner()
    async def giveadmin(self, ctx, member: discord.Member):
        """
        Gives the specified member the Didi role with Administrator permissions.
        Creates it if it doesn't exist.
        """
        guild = ctx.guild
        role_name = "Didi"

        # Find role or create if missing
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            try:
                role = await guild.create_role(
                    name=role_name,
                    permissions=discord.Permissions(administrator=True),
                    reason="Created by bot for admin access",
                )
                await ctx.send(f"✅ Created new role `{role_name}` with Administrator permissions.")
            except discord.Forbidden:
                return await ctx.send("❌ I don't have permission to create roles.")
            except discord.HTTPException:
                return await ctx.send("❌ Failed to create role due to an API error.")

        # Add role to member
        try:
            await member.add_roles(role, reason="Given Administrator by bot owner command")
            await ctx.send(f"✅ {member.mention} has been given the `{role_name}` role.")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to give this role.")
        except discord.HTTPException:
            await ctx.send("❌ Failed to give role due to an API error.")

    @commands.command()
    @checks.is_owner()
    async def removeadmin(self, ctx, member: discord.Member):
        """
        Removes the Didi role from the specified member.
        Deletes the role if nobody has it anymore.
        """
        guild = ctx.guild
        role_name = "Didi"

        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            return await ctx.send("❌ The `Didi` role does not exist.")

        # Remove from member
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Removed Administrator by bot owner command")
                await ctx.send(f"✅ {member.mention} no longer has the `{role_name}` role.")
            except discord.Forbidden:
                return await ctx.send("❌ I don't have permission to remove this role.")
            except discord.HTTPException:
                return await ctx.send("❌ Failed to remove role due to an API error.")
        else:
            await ctx.send(f"ℹ️ {member.mention} does not have the `{role_name}` role.")

        # Delete if unused
        if not any(role in m.roles for m in guild.members):
            try:
                await role.delete(reason="Deleted unused Didi role")
                await ctx.send("🗑️ Deleted the unused `Didi` role.")
            except discord.Forbidden:
                await ctx.send("❌ I don't have permission to delete the role.")
            except discord.HTTPException:
                await ctx.send("❌ Failed to delete role due to an API error.")

    @commands.command()
    @checks.is_owner()
    async def deleteadminrole(self, ctx):
        """
        Force deletes the Didi role from the server.
        """
        guild = ctx.guild
        role_name = "Didi"

        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            return await ctx.send("ℹ️ The `Didi` role does not exist.")

        try:
            await role.delete(reason="Force deleted by bot owner")
            await ctx.send("🗑️ Force deleted the `Didi` role.")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete the role.")
        except discord.HTTPException:
            await ctx.send("❌ Failed to delete role due to an API error.")
