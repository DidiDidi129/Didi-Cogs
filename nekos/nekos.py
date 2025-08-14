import aiohttp
import discord
from redbot.core import commands

class Nekos(commands.Cog):
    """Get random neko images from Nekos API"""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()  # reuse session for efficiency

    async def cog_unload(self):
        await self.session.close()  # close session when cog unloads

    async def _fetch_neko(self):
        """Fetch a random neko image URL from JSON"""
        url = "https://api.nekosapi.com/v4/images/random"

        async with self.session.get(url) as resp:
            if resp.status != 200:
                return None
            try:
                data = await resp.json()
                return data[0]["attributes"]["file"]  # first item URL
            except (KeyError, IndexError, TypeError):
                return None

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
