# Count

A counting game cog for Red-DiscordBot. Users take turns counting in a designated channel — if someone sends the wrong number or counts twice in a row, the count resets!

## Setup

1. Load the cog: `[p]load count`
2. Set a counting channel: `[p]countset channel #your-channel`
3. Start counting from **1** in the designated channel!

## How It Works

- Users must send the next number in sequence (1, 2, 3, …).
- The same user cannot count twice in a row.
- Sending the wrong number, a non-number, or counting twice in a row resets the count back to 0.
- The bot reacts to valid counts with a configurable emoji (default: ✅).
- The server high score is tracked automatically.

## Commands

### General

| Command | Aliases | Description |
| --- | --- | --- |
| `[p]countleaderboard` | `[p]countlb` | Show the counting leaderboard with pagination. |

### Settings (Admin only)

All settings commands confirm success by reacting to your message with the configured emoji.

| Command | Description |
| --- | --- |
| `[p]countset channel <channel>` | Set the counting channel. Only one channel can be active at a time. |
| `[p]countset setcount <number>` | Set the current count to a specific number. Use this to reset or adjust the count. |
| `[p]countset emoji <emoji>` | Set the reaction emoji for correct counts. Supports built-in and server emojis. |
| `[p]countset edit <member> <amount>` | Edit a user's total count. Use a positive number to increase or negative to decrease. |
