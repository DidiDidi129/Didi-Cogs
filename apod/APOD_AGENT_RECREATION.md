# APOD Cog Recreation Guide (Bug-Free Target)

Use this guide to recreate the `apod` cog with the same feature set while avoiding current reliability gaps.

## Source of truth
- `apod/__init__.py`
- `apod/apod.py`
- `apod/info.json`

## Goal
Create a Red Discord Bot cog that fetches NASA APOD content, posts it manually by command, and supports scheduled daily posting per guild.

## Required behavior
1. **Cog setup**
   - `setup(bot)` loads `APOD` cog.
   - Register per-guild config keys:
     - `channel_id` (int or null)
     - `post_time` (string `HH:MM` in UTC)
     - `include_info` (bool)
     - `api_key` (str or null)
     - `ping_roles` (list[int])

2. **NASA API fetch**
   - Endpoint: `https://api.nasa.gov/planetary/apod`
   - Use guild API key when present, otherwise `DEMO_KEY`.
   - Optional API date parameter in `YYYY-MM-DD`.
   - Handle network and API errors safely; do not crash command/task loop.

3. **Message output (`send_apod`)**
   - Build one embed with title, date footer, optional explanation field.
   - Trim explanation to Discord field limit.
   - If `media_type` is `video`, include a clear APOD page link in embed description.
   - If `media_type` is `image`, send the image URL or file in a second message.
   - Ping configured roles only for scheduled posts, never for manual command usage.

4. **Commands**
   - `[p]apod [DD/MM/YYYY]` (day/month/year, e.g. `31/12/2022`): manual APOD fetch; convert valid input to `YYYY-MM-DD` before API request.
   - `[p]apodset` group (admin/manage_guild):
     - `channel <#channel>`
     - `time <HH:MM>`
     - `includeinfo <true|false>`
     - `apikey <key>`
     - `pingroles <@role...>`
   - Base `apodset` command prints current settings.

5. **Scheduler**
   - Per-guild daily loop at configured UTC time.
   - Restart/replace the guild loop after config changes.
   - Initialize tasks on `on_ready` and `on_guild_join`.
   - Cancel loops cleanly on cog unload and close HTTP session.

## Bug-free requirements (must implement)
1. **No DM crash**
   - Manual command must gracefully reject DM usage (no `channel.guild` access in DMs).

2. **HTTP exception safety**
   - Wrap outbound HTTP calls with exception handling (`aiohttp.ClientError`, timeout, invalid payload).
   - On failure, send user-safe error text and keep scheduler alive.

3. **Robust APOD date handling**
   - Do not assume `data['date']` always exists or is valid for split/unpack.
   - Fallback to safe defaults before composing APOD page links.

4. **Task lifecycle safety**
   - Avoid duplicate task loops per guild.
   - Cancel old loop before replacing.
   - Ensure unload does not leave background loops or open HTTP clients.

5. **Role ping safety**
   - Only mention roles that still exist in guild.
   - Use `AllowedMentions(roles=True)` only for scheduled posts, never for manual command invocations.

## Data/storage contract
- Stored values are guild-level configuration only.
- No personal user profile data is required.
- Keep `info.json` metadata aligned with functionality and requirements.

## Validation checklist for code
- Manual command works in guild and fails safely in DM.
- Invalid date format returns clear message.
- Scheduled posting works with and without ping roles.
- Video APOD and image APOD both render correctly.
- Cog unload leaves no running loops and no unclosed session warnings.
