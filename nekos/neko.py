import aiohttp
from redbot.core import commands

class Neko(commands.Cog):
    """Fetches a random neko image with optional rating."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def neko(self, ctx, rating: str = "safe"):
        """
        Sends a random neko image.
        
        Rating options: safe, nsfw, etc.
        Example: ?neko safe
        """
        rating = rating.lower()
        api_url = f"https://api.nekosapi.com/v4/images/random/file?rating={rating}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url) as response:
                    # If the response is JSON
                    if "application/json" in response.headers.get("Content-Type", ""):
                        data = await response.json()
                        image_url = data.get("url")
                        if image_url:
                            await ctx.send(image_url)
                        else:
                            await ctx.send("No image found for that rating.")
                    else:
                        # If the API returned an image directly
                        await ctx.send(str(response.url))
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
