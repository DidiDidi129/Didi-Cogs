import aiohttp
import random
from redbot.core import commands

class Neko(commands.Cog):
    """Fetches a random neko image with optional or random rating."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def neko(self, ctx, rating: str = "safe"):
        """
        Sends a random neko image.
        
        Rating options: safe, borderline, explicit, questionable.
        Example: ?neko safe
        """
        await self.fetch_and_send(ctx, rating.lower())

    @commands.command()
    async def aniroulette(self, ctx):
        """
        Sends a random neko image from a random rating.
        
        Each rating has an equal 1/4 chance.
        """
        ratings = ["safe", "borderline", "explicit", "suggestive"]
        rating = random.choice(ratings)
        await ctx.send(f"🎲 Rolled rating: **{rating}**")
        await self.fetch_and_send(ctx, rating)

    async def fetch_and_send(self, ctx, rating: str):
        """Helper function to fetch and send image based on rating."""
        api_url = f"https://api.nekosapi.com/v4/images/random/file?rating={rating}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url) as response:
                    if "application/json" in response.headers.get("Content-Type", ""):
                        data = await response.json()
                        image_url = data.get("url")
                        if image_url:
                            await ctx.send(image_url)
                        else:
                            await ctx.send("No image found for that rating.")
                    else:
                        await ctx.send(str(response.url))
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
