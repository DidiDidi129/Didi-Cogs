import discord
from redbot.core import commands, Config, checks
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
            "categories": {},  # {identifier: {"name": str, "type": str}}
            "allow_user_edit": True  # global toggle for user edits
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    # --------------------------
    # Profile view command
    # --------------------------
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

    # --------------------------
    # User settings
    # --------------------------
    @commands.group()
    async def cprofileset(self, ctx):
        """Profile settings - only setup and adminsetup remain."""
        if ctx.invoked_subcommand is None:
            await ctx.send("❌ Available subcommands: `setup`, `adminsetup`")

    @cprofileset.command(name="setup")
    async def setup_profile(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        guild_data = await self.config.guild(ctx.guild).all()
        if member == ctx.author and not guild_data.get("allow_user_edit", True):
            return await ctx.send("❌ Users are not allowed to edit profiles.")

        try:
            dm = await member.create_dm()
        except discord.Forbidden:
            return await ctx.send("❌ I cannot send DMs to the user.")

        await dm.send("Let's set up your profile! Type a hex color (e.g., #FF0000) for your embed or 'disable' to skip.")
        def check_color(m):
            return m.author == member and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await self.bot.wait_for('message', check=check_color, timeout=120)
            if msg.content.lower() != 'disable':
                try:
                    color = discord.Color(int(msg.content.strip('#'), 16))
                    await self.config.user(member).color.set(color.value)
                except ValueError:
                    await dm.send("⚠️ Invalid color, skipping.")
        except TimeoutError:
            await dm.send("⌛ Setup timed out, skipping color.")

        guild_data = await self.config.guild(ctx.guild).all()
        for identifier, category in guild_data['categories'].items():
            await dm.send(f"Set your {category['name']} ({category['type']}) or type 'disable' to skip.")
            def check_field(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            try:
                msg = await self.bot.wait_for('message', check=check_field, timeout=120)
                if msg.content.lower() != 'disable':
                    if category['type'] == 'url' and not URL_REGEX.match(msg.content):
                        await dm.send("⚠️ Invalid URL, skipping this field.")
                        continue
                    async with self.config.user(member).fields() as fields:
                        fields[identifier] = msg.content
            except TimeoutError:
                await dm.send(f"⌛ Setup timed out for {category['name']}, skipping.")

        await dm.send("✅ Profile setup complete!")

    @cprofileset.command(name="adminsetup")
    @checks.is_owner()
    async def admin_setup(self, ctx):
        """Walk an admin through categories and global settings in the same channel."""
        channel = ctx.channel
        await channel.send("Starting admin setup. You can add categories and toggle user profile edits globally.")

        def check(m):
            return m.author == ctx.author and m.channel == channel

        while True:
            await channel.send("Type `addcategory` to add a new category, `toggleedit` to enable/disable user edits, `done` to finish.")
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=300)
            except TimeoutError:
                await channel.send("⌛ Admin setup timed out.")
                break

            content = msg.content.lower()
            if content == 'done':
                await channel.send("✅ Admin setup complete.")
                break
            elif content.startswith('addcategory'):
                parts = msg.content.split()
                if len(parts) != 4:
                    await channel.send("❌ Usage: addcategory <identifier> <display_name> <type:text|url>")
                    continue
                _, identifier, display_name, type_ = parts
                async with self.config.guild(ctx.guild).categories() as cats:
                    if identifier in cats:
                        await channel.send("❌ That identifier already exists.")
                    else:
                        cats[identifier] = {"name": display_name, "type": type_}
                        await channel.send(f"✅ Added category `{identifier}`.")
            elif content.startswith('toggleedit'):
                parts = msg.content.split()
                if len(parts) != 2:
                    await channel.send("❌ Usage: toggleedit <True|False>")
                    continue
                allow_bool = parts[1].lower() == 'true'
                await self.config.guild(ctx.guild).allow_user_edit.set(allow_bool)
                await channel.send(f"✅ Users can now {'edit' if allow_bool else 'not edit'} their profiles globally.")


async def setup(bot):
    await bot.add_cog(Profile(bot))
