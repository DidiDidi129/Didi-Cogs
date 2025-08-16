from .adminrole import AdminRole

async def setup(bot):
    await bot.add_cog(AdminRole(bot))
