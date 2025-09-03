import discord
from redbot.core import commands, Config
import aiohttp

class Gemini(commands.Cog):
    """Gemini API integration for Red-DiscordBot"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {"api_key": None, "model": "gemini-pro"}
        default_channel = {"history": []}
        self.config.register_guild(**default_guild)
        self.config.register_channel(**default_channel)

    async def call_gemini(self, api_key: str, model: str, history: list):
        """
        Calls Gemini API with the current chat history.
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}

        # Format messages for Gemini
        contents = []
        for i, msg in enumerate(history):
            role = "user" if i % 2 == 0 else "model"
            contents.append({"role": role, "parts": [{"text": msg}]})

        payload = {"contents": contents}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, params=params, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return f"❌ Error {resp.status}: {text}"
                data = await resp.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return "⚠️ Gemini API returned an unexpected response."

    @commands.group()
    async def gemini(self, ctx):
        """Talk with Google Gemini AI"""
        pass

    @gemini.command()
    async def apiset(self, ctx, api_key: str):
        """Set the Gemini API key for this server"""
        await self.config.guild(ctx.guild).api_key.set(api_key)
        await ctx.reply("✅ Gemini API key has been set.")

    @gemini.command()
    async def model(self, ctx, model_name: str):
        """Set the Gemini model (default: gemini-pro)"""
        await self.config.guild(ctx.guild).model.set(model_name)
        await ctx.reply(f"✅ Gemini model set to `{model_name}`")

    @gemini.command(name="clear")
    async def clear(self, ctx):
        """Clear the chat history for this channel"""
        await self.config.channel(ctx.channel).history.set([])
        await ctx.reply("🧹 Chat history cleared for this channel.")

    @gemini.command(name="chat")
    async def chat(self, ctx, *, message: str):
        """Send a message to Gemini"""
        api_key = await self.config.guild(ctx.guild).api_key()
        model = await self.config.guild(ctx.guild).model()
        if not api_key:
            await ctx.reply("⚠️ No API key set. Use `?gemini apiset <API_KEY>` first.")
            return

        history = await self.config.channel(ctx.channel).history()
        history.append(message)  # Add user message

        # Call Gemini
        reply_text = await self.call_gemini(api_key, model, history)

        history.append(reply_text)  # Save Gemini's response
        await self.config.channel(ctx.channel).history.set(history)

        await ctx.reply(reply_text)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for bot mentions to chat naturally"""
        if message.author.bot:
            return
        if not message.guild:
            return

        # If bot is mentioned in the message
        if self.bot.user in message.mentions:
            api_key = await self.config.guild(message.guild).api_key()
            model = await self.config.guild(message.guild).model()
            if not api_key:
                await message.reply("⚠️ No API key set. Use `?gemini apiset <API_KEY>` first.")
                return

            # Strip mention from message text
            content = message.clean_content.replace(f"@{self.bot.user.name}", "").strip()
            if not content:
                return

            history = await self.config.channel(message.channel).history()
            history.append(content)

            reply_text = await self.call_gemini(api_key, model, history)
            history.append(reply_text)
            await self.config.channel(message.channel).history.set(history)

            await message.reply(reply_text)
