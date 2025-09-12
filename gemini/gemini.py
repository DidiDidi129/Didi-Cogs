import discord
from redbot.core import commands, Config
import aiohttp
import datetime


class Gemini(commands.Cog):
    """Gemini API integration for Red-DiscordBot"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        default_guild = {
            "api_key": None,
            "api_url": "https://generativelanguage.googleapis.com/v1beta/models",  # default
            "model": "gemini-2.0-flash",  # default model
            "respond_to_mentions": True,
        }
        default_channel = {
            "history": [],
            "system_prompt": None,
            "always_respond": False,
            "use_history": True,
            "auto_delete_days": None,
        }
        self.config.register_guild(**default_guild)
        self.config.register_channel(**default_channel)

    async def call_gemini(self, api_key: str, api_url: str, model: str, history: list):
        """
        Call Gemini API with history.
        - If api_url points to Google → append /{model}:generateContent with ?key=
        - If custom API → send directly to base URL with "model" inside JSON
        """
        # Ensure valid scheme
        if not api_url.startswith("http://") and not api_url.startswith("https://"):
            api_url = "https://" + api_url.strip("/")

        if "generativelanguage.googleapis.com" in api_url:
            url = f"{api_url.rstrip('/')}/{model}:generateContent"
            params = {"key": api_key}
        else:
            url = api_url.rstrip("/")
            params = None

        headers = {"Content-Type": "application/json"}

        # Build history
        contents = [{"role": "user", "parts": [{"text": entry["content"]}]} for entry in history]

        payload = {"contents": contents}
        if "generativelanguage.googleapis.com" not in api_url:
            payload["model"] = model

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
            return "⚠️ API returned an unexpected response."

    # ===============================
    # Commands
    # ===============================

    @commands.group(invoke_without_command=True)
    async def gemini(self, ctx):
        """Main Gemini command group.

        Use subcommands to configure or chat with Gemini.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @gemini.command()
    @commands.has_permissions(administrator=True)
    async def apiset(self, ctx, api_key: str):
        """Set the Gemini API key for this server (admin only)."""
        await self.config.guild(ctx.guild).api_key.set(api_key)
        await ctx.reply("✅ Gemini API key has been set.")

    @gemini.command()
    @commands.has_permissions(administrator=True)
    async def apiurl(self, ctx, url: str):
        """Set a custom Gemini API URL for this server (admin only)."""
        await self.config.guild(ctx.guild).api_url.set(url)
        await ctx.reply(f"✅ Gemini API URL set to:\n```{url}```")

    @gemini.command()
    @commands.has_permissions(administrator=True)
    async def model(self, ctx, model_name: str):
        """Set the Gemini model (admin only)."""
        await self.config.guild(ctx.guild).model.set(model_name)
        await ctx.reply(f"✅ Gemini model set to `{model_name}`")

    @gemini.command()
    @commands.has_permissions(manage_channels=True)
    async def system(self, ctx, *, prompt: str = None):
        """Set or clear the system prompt for this channel (requires Manage Channels)."""
        await self.config.channel(ctx.channel).system_prompt.set(prompt)
        if prompt:
            await ctx.reply(f"✅ System prompt set for this channel:\n```{prompt}```")
        else:
            await ctx.reply("🧹 System prompt cleared for this channel.")

    @gemini.command()
    @commands.has_permissions(manage_messages=True)
    async def togglehistory(self, ctx):
        """Toggle chat history for this channel (requires Manage Messages)."""
        current = await self.config.channel(ctx.channel).use_history()
        new_state = not current
        await self.config.channel(ctx.channel).use_history.set(new_state)
        await ctx.reply(f"📜 Chat history is now **{'enabled' if new_state else 'disabled'}** for this channel.")

    @gemini.command()
    @commands.has_permissions(manage_channels=True)
    async def alwaysrespond(self, ctx):
        """Toggle auto-response for this channel (requires Manage Channels)."""
        current = await self.config.channel(ctx.channel).always_respond()
        new_state = not current
        await self.config.channel(ctx.channel).always_respond.set(new_state)
        await ctx.reply(f"💬 Always-respond is now **{'enabled' if new_state else 'disabled'}** for this channel.")

    @gemini.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx):
        """Clear the chat history for this channel (requires Manage Messages)."""
        await self.config.channel(ctx.channel).history.set([])
        await ctx.reply("🧹 Chat history cleared for this channel.")

    @gemini.command()
    async def chat(self, ctx, *, message: str):
        """Send a one-off message to Gemini."""
        await self._handle_message(ctx.channel, ctx.author, message, reply_to=ctx)

    @gemini.command(name="respond")
    @commands.has_permissions(administrator=True)
    async def respond(self, ctx, toggle: bool):
        """Enable or disable responding to mentions for this server (admin only)."""
        await self.config.guild(ctx.guild).respond_to_mentions.set(toggle)
        msg = "✅ Bot will respond to mentions." if toggle else "❌ Bot will ignore mentions."
        await ctx.reply(msg)

    @gemini.command()
    @commands.has_permissions(manage_channels=True)
    async def autodelete(self, ctx, days: int = None):
        """Set auto-delete time (in days) for chat history in this channel (requires Manage Channels).

        Pass no value to disable auto-deletion.
        """
        if days is None:
            await self.config.channel(ctx.channel).auto_delete_days.set(None)
            await ctx.reply("🗑️ Auto-delete disabled for this channel.")
        else:
            await self.config.channel(ctx.channel).auto_delete_days.set(days)
            await ctx.reply(f"🗑️ Auto-delete set: Chat history will be wiped every {days} day(s).")

    # ===============================
    # Listener
    # ===============================

    @commands.Cog.listener("on_message_without_command")
    async def gemini_message_handler(self, message: discord.Message):
        """Listener that processes messages for Gemini in always-respond or mention mode."""
        if message.author.bot or not message.guild:
            return

        # Always respond channel
        if await self.config.channel(message.channel).always_respond():
            await self._handle_message(message.channel, message.author, message.content, reply_to=message)
            return

        # Bot mentioned
        if self.bot.user.mention in message.content:
            respond_enabled = await self.config.guild(message.guild).respond_to_mentions()
            if not respond_enabled:
                return
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
        """Handle a standard Gemini query, with optional history and system prompt."""
        api_key = await self.config.guild(channel.guild).api_key()
        api_url = await self.config.guild(channel.guild).api_url()
        model = await self.config.guild(channel.guild).model()
        system_prompt = await self.config.channel(channel).system_prompt()
        use_history = await self.config.channel(channel).use_history()

        if not api_key:
            await reply_to.reply("⚠️ No API key set. Use `?gemini apiset <API_KEY>` first.")
            return

        # Load history
        history = await self.config.channel(channel).history() if use_history else []

        # Auto-delete old history if enabled
        auto_days = await self.config.channel(channel).auto_delete_days()
        if auto_days:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=auto_days)
            history = [h for h in history if "time" in h and datetime.datetime.fromisoformat(h["time"]) > cutoff]

        # Add user message WITHOUT username
        history.append({
            "role": "user",
            "content": content,
            "time": datetime.datetime.utcnow().isoformat()
        })

        # Prepend system prompt
        if system_prompt and history:
            history[0]["content"] = f"{system_prompt}\n{history[0]['content']}"

        # Call Gemini
        reply_text = await self.call_gemini(api_key, api_url, model, history)

        # Save/update history
        history.append({
            "role": "assistant",
            "content": reply_text,
            "time": datetime.datetime.utcnow().isoformat()
        })
        if use_history:
            await self.config.channel(channel).history.set(history)

        await reply_to.reply(reply_text)

    async def _handle_reply_query(self, channel, author, referenced_message, query, reply_to):
        """Handle an ephemeral Gemini query based on a replied-to message (does not affect history)."""
        api_key = await self.config.guild(channel.guild).api_key()
        api_url = await self.config.guild(channel.guild).api_url()
        model = await self.config.guild(channel.guild).model()
        system_prompt = await self.config.channel(channel).system_prompt()

        if not api_key:
            await reply_to.reply("⚠️ No API key set. Use `?gemini apiset <API_KEY>` first.")
            return

        # Build temporary history for this ephemeral query WITHOUT usernames
        first_message = f"{referenced_message.content}"
        if system_prompt:
            first_message = f"{system_prompt}\n{first_message}"

        temp_history = [
            {"role": "user", "content": first_message},
            {"role": "user", "content": query}
        ]

        reply_text = await self.call_gemini(api_key, api_url, model, temp_history)
        await reply_to.reply(reply_text)
