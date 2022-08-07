import nextcord
from nextcord import Interaction, utils
from nextcord.ext import commands
from nextcord.ext.application_checks import has_permissions
from MeowerBot import Client as MeowerClient
from threading import Thread
import pymongo
import os
import json
import time
import random
import requests
import secrets

# Environment variables
import dotenv
dotenv.load_dotenv()

# Constants
DB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ["MONGODB_NAME"]
MEOWER_USERNAME = os.environ["MEOWER_USERNAME"]
MEOWER_PASSWORD = os.environ["MEOWER_PASSWORD"]
LINK_SHORTENER_KEY = os.environ["LINK_SHORTENER_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
MEOWER_DISCORD_GUILD = [int(os.environ["DISCORD_GUILD"])]
MEMBER_ROLE = os.environ["MEMBER_ROLE"]
SOMEONE_STORYTIME_CHANNEL = int(os.environ["SOMEONE_STORYTIME_CHANNEL"])
SOMEONE_STORYTIME_WEBHOOK = os.environ["SOMEONE_STORYTIME_WEBHOOK"]
SOMEONE_STORYTIME_ROLE = os.environ["SOMEONE_STORYTIME_ROLE"]
DISCORD_INTENTS = nextcord.Intents(messages=True, message_content=True, guilds=True, members=True, presences=True)

# Database
db = pymongo.MongoClient(DB_URI)[DB_NAME]

# Bot objects
bot = commands.Bot(command_prefix='<@926686033964314645>', intents=DISCORD_INTENTS)
bot.meower = MeowerClient(MEOWER_USERNAME, MEOWER_PASSWORD, debug=True, auto_reconect=True, reconect_time=0)
bot.meower_thread = Thread(target=bot.meower.start)
bot.meower_thread.daemon = True
bot.meower.prev_ulist = []
bot.meower.ulist_time = {}
bot.meower.pending_posts = {}
bot.meower.pending_reactions =[]
bot.meower.cached_pfps = {}

def attempt_webhook(webhook, data):
    resp = requests.post(webhook, json=data)
    if resp.status_code == 404:
        # Delete webhook because Discord says to not spam API requests if it's deleted
        db.bridges.delete_one({"webhook": webhook})
    else:
        print(resp.text)

def reaction_queue():
    # Queue for reactions because they are heavily ratelimited
    while True:
        time.sleep(0.5)
        if len(bot.meower.pending_reactions) > 0:
            requests.put(bot.meower.pending_reactions[0], headers={"Authorization": "Bot {0}".format(DISCORD_TOKEN)})
            del bot.meower.pending_reactions[0]
Thread(target=reaction_queue).start()

def alert_to_discord(post):
    # Send alert to Discord
    for bridge in db.bridges.find({"meower_channel": "home", "verified": True}):
        Thread(target=attempt_webhook, args=(bridge["webhook"], {"username": "Meower", "avatar_url": "https://assets.meower.org/PFP/21.png", "content": post, "allowed_mentions": {"parse": []}},)).start()

def bridge_to_discord(user, post, exempt_channels=[]):
    # Clean markdown
    post = utils.escape_markdown(post)

    # Get pfp data
    if user not in bot.meower.cached_pfps:
        resp = requests.get("https://api.meower.org/users/{0}".format(user)).json()
        if resp["error"] and (resp["type"] == "notFound"):
            # Unlink user if they don't exist anymore
            db.links.delete_one({"meower_username": user})
        elif resp["error"]:
            bot.meower.cached_pfps[user] = 0
        else:
            bot.meower.cached_pfps[user] = (resp["pfp_data"]-1)

            # Unlink user if their UUID has changed
            userdata = db.links.find_one({"meower_username": user})
            if (userdata != None) and (userdata["meower_uuid"] != resp["uuid"]):
                db.links.delete_one({"meower_username": user})

    # Send bridged message to Discord
    for bridge in db.bridges.find({"meower_channel": "home", "verified": True}):
        if str(bridge["discord_channel"]) not in exempt_channels:
            Thread(target=attempt_webhook, args=(bridge["webhook"], {"username": user, "avatar_url": "https://assets.meower.org/PFP/{0}.png".format(bot.meower.cached_pfps[user]), "content": post, "allowed_mentions": {"parse": []}},)).start()

@bot.event
async def on_ready():
    print(f"(Discord) Logged in as {bot.user}")
    await bot.change_presence(status=nextcord.Status.online, activity=nextcord.Activity(type=nextcord.ActivityType.listening, name="Meower Posts"))

@bot.event
async def on_application_command_error(interaction, error):
    try:
        await interaction.response.defer()
    except:
        pass
    e = nextcord.Embed(title="MeOWch!", description="We ran into an error!\n\nThis is all we know: {0}".format(str(error)), color=0xfc0303)
    await interaction.followup.send(embed=e)

@bot.event
async def on_member_join(user):
    if user.guild.id == 910201937352347648:
        userdata = db.links.find_one({"discord": user.id})
        if (userdata is not None) and (userdata["meower_username"] is not None):
            verified_role = nextcord.utils.get(user.guild.roles, id=910203080371494982)
            await user.add_roles(verified_role)
            await user.add_roles(verified_role, reason="Verified with Meower account {0}".format(userdata["meower_username"]))
        else:
            channel = user.guild.get_channel(939748856080511026)
            await channel.send("Hello {0}!\n\nTo be able to access the Meower Discord you need to link your Meower account to your Discord account.\nAll you need to do is run `/link` here to begin the process (this won't take any longer than a minute)!".format(user.mention))

@bot.event
async def on_message(msg):
    # Make sure the message is not from the bot itself or a DM channel
    if (msg.guild is None) or msg.author.bot:
        return

    # Bridge
    bridge_data = db.bridges.find_one({"discord_channel": msg.channel.id, "verified": True})
    if bridge_data is not None:
        # Check if the message can be bridged
        if msg.content.startswith("!!") or (msg.type not in [nextcord.MessageType.default, nextcord.MessageType.reply]):
            return
        
        # Check if the user has a Meower account linked
        link_data = db.links.find_one({"discord": msg.author.id})
        if (link_data is None) or (link_data["meower_username"] is None):
            return await msg.add_reaction("❌")

        # Convert reply to the author name
        if msg.reference is not None:
            replied_to_msg = await msg.channel.fetch_message(msg.reference.message_id)
            if replied_to_msg is not None:
                userdata = db.links.find_one({"discord": replied_to_msg.author.id, "verified": True})
                if userdata is None:
                    msg.content = "@{0} {1}".format(replied_to_msg.author.name, msg.content)
                else:
                    msg.content = "@{0} {1}".format(userdata["meower_username"], msg.content)

        # Convert all files to just the filename
        for file in msg.attachments:
            try:
                shortened_link = requests.post("https://go.meower.org/submit", headers={"Authorization": os.environ["LINK_SHORTENER_KEY"]}, json={"link": file.url}).json()
                msg.content += " [{0}: {1}]".format(file.filename, shortened_link["full_url"])
            except:
                pass

        # Save the message to a pending posts dictionary
        bot.meower.pending_posts[str(msg.id)] = {"channel": str(msg.channel.id), "user": link_data["meower_username"], "content": msg.clean_content}

        # Send post to Meower
        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "post_home", "val": "{0}: {1}".format(link_data["meower_username"], msg.clean_content)}, "listener": str(msg.id)})
    
    # @someone story time
    if (msg.guild.id == MEOWER_DISCORD_GUILD[0]) and ("<@&{0}>".format(SOMEONE_STORYTIME_ROLE) in msg.content) and (msg.channel.id == SOMEONE_STORYTIME_CHANNEL):
        # Check if too many @someone's/pings in the message
        if len(msg.mentions) > len(msg.guild.members):
            return await msg.reply("That's too many @someone/pings! We only have {0} members in this server and you tried using @someone/pings {1} times.".format(len(msg.guild.members), len(msg.mentions)))
        
        # Replace all @someone's with random members
        while "<@&{0}>".format(SOMEONE_STORYTIME_ROLE) in msg.content:
            person = random.choice(msg.guild.members)
            while (str(person) in msg.content) or (person.mention in msg.content):
                person = random.choice(msg.guild.members)
            msg.content = msg.content.replace("<@&{0}>".format(SOMEONE_STORYTIME_ROLE), person.mention, 1)

        # Delete old message and send new message
        request_data = {
            "username": msg.author.name,
            "avatar_url": msg.author.avatar.url,
            "content": str(msg.content),
            "allowed_mentions": {"parse": []}
        }
        await msg.delete()
        requests.post(SOMEONE_STORYTIME_WEBHOOK, json=request_data)

@bot.slash_command(name="dice", description="Roll a dice", guild_ids=MEOWER_DISCORD_GUILD)
async def dice(interaction: Interaction, sides: int=6):
    await interaction.response.defer()
    number = random.randint(1,sides)
    await interaction.followup.send("The dice landed on **{0}**".format(str(number)))

@bot.slash_command(name="emoji", description="Sends a nitro only emoji.", guild_ids=MEOWER_DISCORD_GUILD)
async def emoji(interaction: Interaction, emoji: str):
    await interaction.response.defer()
    emoji = emoji.replace("meowy_", "")
    emoji = "meowy_" + emoji
    emoji = utils.get(interaction.guild.emojis, name=emoji)
    if emoji is not None:
        await interaction.followup.send(emoji)
    else:
        await interaction.followup.send("That emoji doesn't exist! Try one of these: `spin`, `planet`, `planets`.")

@bot.slash_command(name="restart", description="Restarts the Meower bot.", guild_ids=MEOWER_DISCORD_GUILD)
@has_permissions(administrator=True)
async def restart_meower_bot(interaction: Interaction):
    await interaction.response.send_message("Restarting... The bot should be online again soon.")
    exit()

@bot.slash_command(name="warn", description="Applies a warning to a user.", guild_ids=MEOWER_DISCORD_GUILD)
@has_permissions(administrator=True)
async def add_warning(interaction: Interaction, user: nextcord.Member, reason: str):
    await interaction.response.defer()

    # Get all warnings
    warnings = []
    index = db.warnings.find({"user": user.id})
    for item in index:
        warnings.append(item)

    # Save warning to database
    db.warnings.insert_one({"user": user.id, "issuer": interaction.user.id, "reason": reason, "timestamp": int(time.time())})

    # Send DM to user and respond to moderator
    e = nextcord.Embed(title="You Have Been Warned", description="You have been given a warning in Meower Media Co.!\n\nReason: {0}\n\nIf you continue these actions you may be banned from Meower Media Co. or Meower.".format(reason), color=0xfcba03)
    e.set_footer(text="You have a total of {0} warning(s)".format(len(warnings)))
    try:
        await user.send(embed=e)
        await interaction.followup.send("Successfully applied warning!")
    except:
        await interaction.followup.send("Successfully applied warning! *(but could not DM this user)*")

@bot.slash_command(name="removewarning", description="Removes a warning from a user.", guild_ids=MEOWER_DISCORD_GUILD)
@has_permissions(administrator=True)
async def remove_warning(interaction: Interaction, user: nextcord.Member, warning: int):
    await interaction.response.defer()

    # Correct warning index
    warning -= 1

    # Get all warnings
    warnings = []
    index = db.warnings.find({"user": user.id})
    for item in index:
        warnings.append(item)

    # Check if warning exists
    if warning >= len(warnings):
        return await interaction.followup.send("That warning doesn't exist.")

    # Delete warning
    db.warnings.delete_one({"_id": warnings[warning]["_id"]})

    # Respond to moderator
    await interaction.followup.send("Successfully removed warning.")

@bot.slash_command(name="warnings", description="Displays all warnings from a user.", guild_ids=MEOWER_DISCORD_GUILD)
async def view_warnings(interaction: Interaction, user: nextcord.Member):
    await interaction.response.defer()

    # Get all warnings
    warnings = []
    index = db.warnings.find({"user": user.id})
    for item in index:
        warnings.append(item)

    # Create embed
    e = nextcord.Embed(title="Warnings for {0}".format(user.id), color=0xfcba03)
    e.set_footer(text="{0} has a total of {1} warning(s)".format(user.id, len(warnings)))
    index = 1
    for item in warnings:
        e.add_field(name="Warning {0}".format(index), value="Reason: {0}\nIssuer: <@{1}>\nTimestamp: <t:{2}:R>".format(item["reason"], item["issuer"], item["timestamp"]), inline=False)
        index += 1

    # Send embed
    await interaction.followup.send(embed=e)

@bot.slash_command("ping", description="Returns bot's ping to Discord API.", force_global=True)
async def ping(interaction: Interaction):
    await interaction.response.send_message(":ping_pong: Bot's ping to Discord API: {0}ms".format(round(bot.latency * 1000)), ephemeral=True)

@bot.slash_command("status", description="Returns Meower's status.", force_global=True)
async def status(interaction: Interaction):
    await interaction.response.send_message(":robot: Meower's status: {0}".format(status), ephemeral=True)

@bot.slash_command("info", description="Returns info about a Meower account.", force_global=True)
async def info(interaction: Interaction, username: str):
    await interaction.response.defer()

    # Get user info from Meower API
    user_info = requests.get("https://api.meower.org/users/{0}".format(username)).json()
    if user_info["error"]:
        # User not found
        return await interaction.followup.send("Sorry! That user doesn't seem to exist.")

    # Create embed
    e = nextcord.Embed(title=user_info["_id"], color=nextcord.Color.orange())
    e.add_field(name="Username", value=user_info["_id"])
    e.add_field(name="UUID", value=user_info["uuid"])
    e.add_field(name="Permissions", value=(["User", "Moderator", "Moderator", "Moderator", "Administrator"][user_info["lvl"]]))
    e.add_field(name="Banned", value=str(user_info["banned"]))
    e.add_field(name="Quote", value=(user_info["quote"] if (str(user_info["quote"]) != "") else "** **"))
    e.set_thumbnail(url="https://assets.meower.org/PFP/{0}.png".format(user_info["pfp_data"]))

    # Send embed
    await interaction.followup.send(embed=e)

@bot.slash_command("link", description="Links your Meower account to your Discord account.", force_global=True)
async def link_meower(interaction: Interaction):
    # Create new link token
    link_token = secrets.token_urlsafe(32)
    db.links.insert_one({"discord": interaction.user.id, "meower_username": None, "meower_uuid": None, "token": link_token, "verified": False})

    # Send link token to user
    await interaction.response.send_message("To link your Meower account, visit this link: https://meower.org/discord?token={0}\n\nThis link will expire <t:{1}:R>.".format(link_token, int(time.time())+600), ephemeral=True)

@bot.slash_command("bridge", description="Bridges/unbridges Meower home and ulist.", force_global=True)
@has_permissions(manage_channels=True)
async def home_bridge(interaction: Interaction):
    await interaction.response.defer()

    # Delete any current webhooks
    webhooks = await interaction.channel.webhooks()
    for webhook in webhooks:
        if webhook.user == bot.user:
            await webhook.delete()
    
    # Check if the channel is currently bridged
    bridge = db.bridges.find_one({"discord_channel": interaction.channel.id})
    if bridge is not None:
        # Unbridge the channel
        db.bridges.delete_one({"discord_channel": interaction.channel.id})
        await interaction.followup.send("Successfully unbridged this channel from Meower home and ulist.")
    else:
        # Bridge the channel
        webhook = await interaction.channel.create_webhook(name="Meower Bridge")
        db.bridges.insert_one({"discord_channel": interaction.channel.id, "meower_channel": "home", "bridge_owner": interaction.user.id, "webhook": webhook.url, "token": None, "verified": True})
        await interaction.followup.send("Successfully bridged this channel to Meower home and ulist.")

@bot.slash_command("ulist", description="Gets the current online Meower users.", force_global=True)
async def meower_ulist(interaction: Interaction):
    ulist = "**There are currently {0} users online on Meower.**".format(len(bot.meower._wss.statedata["ulist"]["usernames"]))
    for user in bot.meower._wss.statedata["ulist"]["usernames"]:
        try:
            ulist += "\n`{0}`  -  logged in <t:{1}:R>".format(user, bot.meower.ulist_time[user])
        except:
            pass
    await interaction.response.send_message(ulist, ephemeral=True)

def on_packet(data):
    data = json.loads(data)

    # Successful login
    if ("mode" in data["val"]) and (data["val"]["mode"] == "auth"):
        print("(Meower) Logged in as {0}".format(data["val"]["payload"]["username"]))

    # Ulist check
    if data["cmd"] == "ulist":
        # Get ulist
        ulist = bot.meower._wss.getUsernames()
        if len(bot.meower.prev_ulist) == 0:
            bot.meower.prev_ulist = ulist
            for user in ulist:
                bot.meower.ulist_time[user] = int(time.time())

        # Online checker
        for user in ulist:
            if not user in bot.meower.prev_ulist:
                bot.meower.ulist_time[user] = int(time.time())
                alert_to_discord(":green_circle: {0} is now online!".format(user))
        
        # Offline checker
        for user in bot.meower.prev_ulist:
            if not user in ulist:
                # Calculate time online
                time_online = (int(time.time()) - bot.meower.ulist_time[user])
                del bot.meower.ulist_time[user]
                if time_online == 1:
                    time_online = "1 second"
                elif time_online < 60:
                    time_online = "{0} seconds".format(time_online)
                elif time_online < 120:
                    time_online = "1 minute"
                elif time_online < 3600:
                    time_online = "{0} minutes".format(str(int(time_online/60)))
                elif time_online < 7200:
                    time_online = "1 hour"
                else:
                    time_online = "{0} hours".format(str(int(time_online/3600)))
                
                # Alert to discord
                alert_to_discord(":red_circle: {0} is now offline! {0} was online for {1}.".format(user, time_online))
        
        # Update previous ulist
        bot.meower.prev_ulist = ulist

    # Bridge status
    elif (data["cmd"] == "statuscode") and ("listener" in data) and (data["listener"] in bot.meower.pending_posts):
        post_data = bot.meower.pending_posts[data["listener"]]
        del bot.meower.pending_posts[data["listener"]]
        if data["val"] == "I:100 | OK":
            bridge_to_discord(post_data["user"], post_data["content"], exempt_channels=[str(post_data["channel"])])
            reaction = "%E2%9C%85"
        else:
            reaction = "%E2%9D%8C"
        bot.meower.pending_reactions.append("https://discord.com/api/v9/channels/{0}/messages/{1}/reactions/{2}/%40me?location=Message".format(post_data["channel"], data["listener"], reaction))

    # User sent pvar
    elif data["cmd"] == "pvar":
        if type(data["val"]) == str:
            return bot.meower._wss.sendPacket({"cmd": "pvar", "id": data["origin"], "name": data["name"], "val": handle_pvar(data["origin"], data["name"], data["val"])})
        else:
            return bot.meower._wss.sendPacket({"cmd": "pvar", "id": data["origin"], "name": data["name"], "val": "E:102 | Datatype"})

    # Bridge posts
    elif ("post_origin" in data["val"]) and (data["val"]["post_origin"] == "home") and (data["val"]["u"] != MEOWER_USERNAME):
        bridge_to_discord(data["val"]["u"], data["val"]["p"])

def handle_pvar(origin, name, val):
    if name == "discord":
        userdata = db.links.find_one({"token": val})
        if userdata is None:
            return "E:103 | IDNotFound"
        
        requests.put("https://discord.com/api/v9/guilds/{0}/members/{1}/roles/{2}".format(MEOWER_DISCORD_GUILD[0], userdata["discord"], MEMBER_ROLE), headers={"Authorization": "Bot {0}".format(DISCORD_TOKEN)})
        try:
            db.links.update_one({"token": val}, {"$set": {"meower_username": origin, "meower_uuid": requests.get("https://api.meower.org/users/{0}".format(origin)).json()["uuid"], "verified": True}})
            return "I:100 | OK"
        except:
            return "E:104 | InternalServerError"
    elif name == "custom_id_check":
        with open("custom_ids.json", 'r') as f:
            custom_ids = json.loads(f.read())
        if origin in custom_ids:
            return custom_ids[origin]
        else:
            return None
    elif name == "set_custom_id":
        with open("custom_ids.json", 'r') as f:
            custom_ids = json.loads(f.read())
        if (len(val) < 1) or (val) > 20:
            return "ID must be between 1 and 20 characters."
        for char in val:
            if char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-":
                return "ID must only contain letters, numbers, underscores and dashes."
        for taken_name in custom_ids.values():
            if taken_name == val:
                return "ID is already taken."
        custom_ids[origin] = val
        with open("custom_ids.json", 'w') as f:
            json.dump(custom_ids, f, indent=4)
        return "I:100 | OK"

if __name__ == '__main__':
    # Start Meower bot
    bot.meower._wss.callback("on_packet", on_packet)
    bot.meower_thread.start()

    # Start Discord bot
    bot.run(os.environ["DISCORD_TOKEN"])