from .profile import Profile

async def setup(bot):
    await bot.add_cog(Profile(bot))
