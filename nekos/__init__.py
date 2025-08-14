from .neko import Neko

async def setup(bot):
    await bot.add_cog(Neko(bot))
