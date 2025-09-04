import discord
from redbot.core import commands, Config
import aiohttp
from datetime import datetime, timedelta

class Gemini(commands.Cog):
    """Gemini API integration for Red-DiscordBot"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "api_key": None,
            "model": "gemini-pro",
            "respond_to_mentions": True  # New config
        }
        default_channel = {
            "history": [],
            "system_prompt": None,
            "always_respond": False,
            "use_history": True,
            "auto_delete_days": None
        }
        self.config.register_guild(**default_guild)
        self.config.register_channel(**default_channel)

    async def call_gemini(self, api_key: str, model: str, history: list):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}

        contents = [{"role": "user", "parts": [{"text": entry["content"]}]} for entry in history]
        payload = {"contents": contents}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, params=params, json=payload) as resp:
                if resp.status == 503:
                    return "⚠️ Model overloaded, please try again soon"
                if resp.status != 200:
                    text = await resp.text()
                    return f"❌ Error {resp.status}: {text}"
                data = await resp.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return "⚠️ Gemini API returned an unexpected response."

    # ===============================
    # Commands
    # ===============================

    @commands.group()
    async def gemini(self, ctx):
        """Talk with Google Gemini AI"""
        pass

    @gemini.command()
    async def apiset(self, ctx, api_key: str):
        await self.config.guild(ctx.guild).api_key.set(api_key)
        await ctx.reply("✅ Gemini API key has been set.")

    @gemini.command()
    async def model(self, ctx, model_name: str):
        await self.config.guild(ctx.guild).model.set(model_name)
        await ctx.reply(f"✅ Gemini model set to `{model_name}`")

    @gemini.command()
    async def system(self, ctx, *, prompt: str = None):
        await self.config.channel(ctx.channel).system_prompt.set(prompt)
        if prompt:
            await ctx.reply(f"✅ System prompt set for this channel:\n```{prompt}```")
        else:
            await ctx.reply("🧹 System prompt cleared for this channel.")

    @gemini.command()
    async def togglehistory(self, ctx):
        current = await self.config.channel(ctx.channel).use_history()
        new_state = not current
        await self.config.channel(ctx.channel).use_history.set(new_state)
        await ctx.reply(f"📜 Chat history is now **{'enabled' if new_state else 'disabled'}** for this channel.")

    @gemini.command()
    async def alwaysrespond(self, ctx):
        current = await self.config.channel(ctx.channel).always_respond()
        new_state = not current
        await self.config.channel(ctx.channel).always_respond.set(new_state)
        await ctx.reply(f"💬 Always-respond is now **{'enabled' if new_state else 'disabled'}** for this channel.")

    @gemini.command(name="clear")
    async def clear(self, ctx):
        await self.config.channel(ctx.channel).history.set([])
        await ctx.reply("🧹 Chat history cleared for this channel.")

    @gemini.command(name="autodelete")
    @commands.has_permissions(administrator=True)
    async def autodelete(self, ctx, days: int = None):
        if days is not None and days <= 0:
            await ctx.reply("❌ Auto-delete days must be greater than 0.")
            return
        await self.config.channel(ctx.channel).auto_delete_days.set(days)
        msg = f"✅ Auto-delete set to {days} day(s)." if days else "✅ Auto-delete disabled."
        await ctx.reply(msg)

    @gemini.command(name="respond")
    @commands.has_permissions(administrator=True)
    async def respond(self, ctx, toggle: bool):
        """
        Enable or disable responding to mentions for this server.
        Use True to allow, False to disable.
        """
        await self.config.guild(ctx.guild).respond_to_mentions.set(toggle)
        msg = "✅ Bot will respond to mentions." if toggle else "❌ Bot will ignore mentions."
        await ctx.reply(msg)

    @gemini.command(name="chat")
    async def chat(self, ctx, *, message: str):
        await self._handle_message(ctx.channel, ctx.author, message, reply_to=ctx)

    # ===============================
    # Listener
    # ===============================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        prefixes = await self.bot.get_valid_prefixes(message.guild)

        # Always respond channel
        if await self.config.channel(message.channel).always_respond():
            if any(message.content.startswith(prefix) for prefix in prefixes):
                return
            await self._handle_message(message.channel, message.author, message.content, reply_to=message)
            return

        # Bot mentioned
        if self.bot.user.mention in message.content:
            respond_enabled = await self.config.guild(message.guild).respond_to_mentions()
            if not respond_enabled:
                return  # Mentions disabled, skip
            content = message.clean_content.replace(self.bot.user.mention, "").strip()

            if message.reference and (ref := message.reference.resolved) and isinstance(ref, discord.Message):
                await self._handle_reply_query(message.channel, message.author, ref, content, reply_to=message)
                return

            if content:
                await self._handle_message(message.channel, message.author, content, reply_to=message)

    # ===============================
    # Core handlers
    # ===============================

    async def _handle_message(self, channel, author, content, reply_to):
        api_key = await self.config.guild(channel.guild).api_key()
        model = await self.config.guild(channel.guild).model()
        system_prompt = await self.config.channel(channel).system_prompt()
        use_history = await self.config.channel(channel).use_history()
        auto_delete_days = await self.config.channel(channel).auto_delete_days()

        if not api_key:
            await reply_to.reply("⚠️ No API key set. Use `?gemini apiset <API_KEY>` first.")
            return

        # Load history
        history = await self.config.channel(channel).history() if use_history else []

        # Remove old messages if auto_delete_days is set
        if auto_delete_days and history:
            cutoff = datetime.utcnow() - timedelta(days=auto_delete_days)
            history = [h for h in history if h.get("timestamp") is None or datetime.fromisoformat(h["timestamp"]) > cutoff]

        # Add current message
        history.append({
            "role": "user",
            "content": f"{author.display_name}: {content}",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Prepend system prompt to first message
        if system_prompt and history:
            history[0]["content"] = f"{system_prompt}\n{history[0]['content']}"

        # Call Gemini
        reply_text = await self.call_gemini(api_key, model, history)

        # Save/update history
        history.append({
            "role": "user",
            "content": reply_text,
            "timestamp": datetime.utcnow().isoformat()
        })
        if use_history:
            await self.config.channel(channel).history.set(history)

        await reply_to.reply(reply_text)

    async def _handle_reply_query(self, channel, author, referenced_message, query, reply_to):
        api_key = await self.config.guild(channel.guild).api_key()
        model = await self.config.guild(channel.guild).model()
        system_prompt = await self.config.channel(channel).system_prompt()

        if not api_key:
            await reply_to.reply("⚠️ No API key set. Use `?gemini apiset <API_KEY>` first.")
            return

        # Build ephemeral history
        first_message = f"{referenced_message.author.display_name} said: {referenced_message.content}"
        if system_prompt:
            first_message = f"{system_prompt}\n{first_message}"

        temp_history = [
            {"role": "user", "content": first_message},
            {"role": "user", "content": f"{author.display_name} asks: {query}"}
        ]

        reply_text = await self.call_gemini(api_key, model, temp_history)
        await reply_to.reply(reply_text)
