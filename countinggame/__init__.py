from .countinggame import CountingGame

async def setup(bot):
    await bot.add_cog(CountingGame(bot))
