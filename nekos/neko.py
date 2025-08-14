import aiohttp
from redbot.core import commands

class Neko(commands.Cog):
    """Fetches a random neko image."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def neko(self, ctx):
        """Sends a random neko image."""
        url = "https://api.nekosapi.com/v4/images/random/file"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        await ctx.send(f"Error: received status {response.status}")
                        return
                    data = await response.json()
                    image_url = data.get("url")
                    if image_url:
                        await ctx.send(image_url)
                    else:
                        await ctx.send("No image found.")
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
