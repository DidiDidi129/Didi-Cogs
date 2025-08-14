import aiohttp
import discord
from redbot.core import commands

class Nekos(commands.Cog):
    """Get random neko images from Nekos API"""

    def __init__(self, bot):
        self.bot = bot

    async def _fetch_neko(self):
        """Fetch a random neko image URL (plain text)"""
        url = "https://api.nekosapi.com/v4/images/random/file"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()  # Returns the URL as a string

    @commands.command(name="neko", aliases=["nekos"])
    async def neko_command(self, ctx):
        """Get a random neko image"""
        image_url = await self._fetch_neko()
        if not image_url:
            await ctx.send("❌ Error fetching image.")
            return

        embed = discord.Embed(title="Here’s a random neko 🐱")
        embed.set_image(url=image_url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Nekos(bot))
