from .gemini import Gemini

async def setup(bot):
    await bot.add_cog(Gemini(bot))
