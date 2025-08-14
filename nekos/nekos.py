import aiohttp
import discord
from redbot.core import commands

class Nekos(commands.Cog):
    """Get random neko images from Nekos API"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def neko(self, ctx):
        """Get a random neko image"""
        url = "https://api.nekosapi.com/v3/images/random"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await ctx.send(f"❌ Error fetching image: {resp.status}")
                    return
                data = await resp.json()

        try:
            image_url = data["data"][0]["attributes"]["file"]
        except (KeyError, IndexError):
            await ctx.send("❌ Could not parse image data.")
            return

        embed = discord.Embed(title="Here’s a random neko 🐱")
        embed.set_image(url=image_url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Nekos(bot))
