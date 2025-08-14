import aiohttp
import random
import discord
from redbot.core import commands

class Neko(commands.Cog):
    """Fetches random neko images with optional rating."""

    VALID_RATINGS = ["safe", "nsfw", "explicit"]

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def neko(self, ctx, rating: str = "safe"):
        """
        Sends a random neko image with a specific rating.

        Valid ratings: safe, nsfw, explicit
        Example: ?neko safe
        """
        rating = rating.lower()
        if rating not in self.VALID_RATINGS:
            await ctx.send(f"Invalid rating! Choose from: {', '.join(self.VALID_RATINGS)}")
            return

        await self.send_neko(ctx, rating)

    @commands.command()
    async def nekorandom(self, ctx):
        """Sends a random neko image from a completely random category."""
        rating = random.choice(self.VALID_RATINGS)
        await self.send_neko(ctx, rating)

    async def send_neko(self, ctx, rating: str):
        api_url = f"https://api.nekosapi.com/v4/images/random/file?rating={rating}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url) as response:
                    if "application/json" in response.headers.get("Content-Type", ""):
                        data = await response.json()
                        image_url = data.get("url")
                    else:
                        image_url = str(response.url)

                    if image_url:
                        embed = discord.Embed(
                            title=f"Neko Image ({rating})",
                            color=discord.Color.random()
                        )
                        embed.set_image(url=image_url)
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send("No image found.")
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
