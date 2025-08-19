import discord
from redbot.core import commands, Config, checks
from typing import Literal
import re

URL_REGEX = re.compile(r"^(https?://[\w.-]+(?:\.[\w\.-]+)+[/\w\-._~:/?#[\]@!$&'()*+,;=.]+)?$")

class Profile(commands.Cog):
    """User profiles with customizable fields."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=13572468)
        default_user = {
            "color": None,
            "fields": {}
        }
        default_guild = {
            "categories": {},
            "allow_user_edit": False,
            "roles_allowed": []
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    @commands.command()
    async def cprofile(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_data = await self.config.user(member).all()
        guild_data = await self.config.guild(ctx.guild).all()

        color = discord.Color(user_data['color']) if user_data['color'] else member.color
        embed = discord.Embed(
            title=f"{member.display_name}'s Profile",
            color=color,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Username", value=str(member), inline=True)

        for identifier, category in guild_data["categories"].items():
            if identifier in user_data["fields"]:
                embed.add_field(name=category["name"], value=user_data["fields"][identifier], inline=False)

        await ctx.send(embed=embed)

    @commands.group()
    async def cprofileset(self, ctx):
        pass

    @cprofileset.command(name="setup")
    async def setup_profile(self, ctx, member: discord.Member = None):
        # existing setup_profile code here...
        pass

    @cprofileset.command(name="adminsetup")
    @checks.is_owner()
    async def admin_setup(self, ctx):
        try:
            dm = await ctx.author.create_dm()
        except discord.Forbidden:
            return await ctx.send("❌ Cannot send DMs to the bot owner.")

        await dm.send("Starting admin setup. You can manage categories, toggle user edits, roles, remove profiles, or edit any user's profile.")
        def check(m):
            return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)

        while True:
            await dm.send("Type `addcategory`, `removecategory`, `toggleedit`, `setroles`, `removeprofile`, `editprofile`, or `done` to finish.")
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=300)
            except TimeoutError:
                await dm.send("⌛ Admin setup timed out.")
                break

            content = msg.content.lower()
            if content == 'done':
                await dm.send("✅ Admin setup complete.")
                break

            elif content.startswith('editprofile'):
                await dm.send("Enter the user ID or exact username#discriminator of the user to edit.")
                try:
                    user_msg = await self.bot.wait_for('message', check=check, timeout=120)
                    target = None
                    if user_msg.content.isdigit():
                        target = ctx.guild.get_member(int(user_msg.content))
                    else:
                        name_disc = user_msg.content.split('#')
                        if len(name_disc) == 2:
                            target = discord.utils.get(ctx.guild.members, name=name_disc[0], discriminator=name_disc[1])
                    if not target:
                        await dm.send("❌ User not found.")
                        continue

                    guild_data = await self.config.guild(ctx.guild).all()
                    for identifier, category in guild_data['categories'].items():
                        await dm.send(f"Set value for {category['name']} ({category['type']}) or type 'disable' to skip.")
                        try:
                            value_msg = await self.bot.wait_for('message', check=check, timeout=120)
                            if value_msg.content.lower() != 'disable':
                                if category['type'] == 'url' and not URL_REGEX.match(value_msg.content):
                                    await dm.send("⚠️ Invalid URL, skipping this field.")
                                    continue
                                async with self.config.user(target).fields() as fields:
                                    fields[identifier] = value_msg.content
                        except TimeoutError:
                            await dm.send(f"⌛ Timed out for {category['name']}, skipping.")
                    await dm.send(f"✅ Edited profile for {target.display_name}.")
                except TimeoutError:
                    await dm.send("⌛ Timed out editing profile.")

async def setup(bot):
    await bot.add_cog(Profile(bot))
