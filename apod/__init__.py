from .apod import APOD


async def setup(bot):
    await bot.add_cog(APOD(bot))
