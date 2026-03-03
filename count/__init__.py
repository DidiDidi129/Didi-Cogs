from .count import Count

async def setup(bot):
    await bot.add_cog(Count(bot))
