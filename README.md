# DiscordAuth
Source code for the DiscordAuth Meower and Discord bot.

## Credentials
Before using this you have to change the following things:
1. Add your Webhook URL in the 'webhook' variable in main.py (Flask server)
2. Add your Discord bot token to the 'bot.run()' function at the very bottom in discord-auth/discord_bot.py
3. Add your Meower bot username and password in the auth command in discord-auth/meower_bot.js
4. Change the channel IDs set under 'on_message' bot event in discord-auth/discord_bot.py to your channel IDs  -  939748856080511026 is for Meower's 'another-verify' channel (where verification alerts show and where a user can ask for a new verification link), 939707540776812605 is for Meower's 'verify' channel (where the webhook is setup and where the Discord bot is watching for verification requests)

## How to run
Python Pip Dependencies (Ones that aren't pre-installed with Pip): nextcord, flask, requests

All Node dependencies are already installed in the discord-auth/node_modules folder.

1. Start main.py with Python 3.10
2. Start discord-auth/discord_bot.py with Python 3.10
3. Start discord-auth/meower_bot.js with Node 16.13.2 (No other versions have been tested - but I do know Node 10 doesn't work if that's helpful to anyone)