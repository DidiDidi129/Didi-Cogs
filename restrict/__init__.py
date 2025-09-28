from .restrict import Restrict

async def setup(bot):
    await bot.add_cog(Restrict(bot))
