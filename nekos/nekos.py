import requests
from redbot.core import commands

class Neko(commands.Cog):
    """Fetches a random neko image."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def neko(self, ctx):
        """Sends a random neko image."""
        try:
            response = requests.get("https://api.nekosapi.com/v4/images/random/file")
            response.raise_for_status()
            image_url = response.json().get("url")
            if image_url:
                await ctx.send(image_url)
            else:
                await ctx.send("No image found.")
        except requests.RequestException as e:
            await ctx.send(f"An error occurred: {e}")
