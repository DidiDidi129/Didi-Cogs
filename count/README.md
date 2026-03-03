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

### Math Expressions

Users can count using basic math expressions instead of plain numbers. For example, if the expected count is **5**, any of these are valid:

- `5`
- `2+3`
- `10/2`
- `2+3=5` (equals sign form, can be disabled by an admin)

Only the four basic operations (`+`, `-`, `*`, `/`) are allowed. Results must be whole numbers. Math expressions and equals signs can each be toggled by an admin.

### Saves

Saves are an optional feature (off by default) that lets a server recover from a broken count. Every N counts (default 1000, configurable), the server earns a save. When someone breaks the count, they are offered the choice to use a save to restore it. The person who broke the count must accept or deny the save to avoid wasting them on small issues.

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
| `[p]countset count <number>` | Set the current count to a specific number. Use this to reset or adjust the count. |
| `[p]countset emoji <emoji>` | Set the reaction emoji for correct counts. Supports built-in and server emojis. |
| `[p]countset edit <member> <amount>` | Edit a user's total count. Use a positive number to increase or negative to decrease. |
| `[p]countset saves` | Toggle the saves feature on or off. Off by default. |
| `[p]countset saveinterval <number>` | Set how many counts are needed to earn a save. Default is 1000. |
| `[p]countset addsave [amount]` | Add one or more saves to the server. Defaults to 1. |
| `[p]countset math` | Toggle whether math expressions can be used for counting. On by default. |
| `[p]countset equals` | Toggle whether equals signs are allowed in math expressions. On by default. |
