from .nekos import Nekos

async def setup(bot):
    await bot.add_cog(Nekos(bot))
