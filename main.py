import nextcord
from nextcord import Interaction, utils, SlashOption
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
import copy


# Environment variables
import dotenv
dotenv.load_dotenv()


# Constants
DB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ["MONGODB_NAME"]
MEOWER_USERNAME = os.environ["MEOWER_USERNAME"]
MEOWER_PASSWORD = os.environ["MEOWER_PASSWORD"]
LINK_SHORTENER_URL = os.environ["LINK_SHORTENER_URL"]
LINK_SHORTENER_KEY = os.environ["LINK_SHORTENER_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
MEOWER_DISCORD_GUILD = [int(os.environ["DISCORD_GUILD"])]
MEMBER_ROLE = os.environ["MEMBER_ROLE"]
SOMEONE_STORYTIME_CHANNEL = int(os.environ["SOMEONE_STORYTIME_CHANNEL"])
SOMEONE_STORYTIME_WEBHOOK = os.environ["SOMEONE_STORYTIME_WEBHOOK"]
SOMEONE_STORYTIME_ROLE = os.environ["SOMEONE_STORYTIME_ROLE"]
DISCORD_INTENTS = nextcord.Intents(messages=True, message_content=True, guilds=True, members=True)


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
bot.meower.meower_last_typed = {}
bot.meower.discord_last_typed = {}


def attempt_webhook(webhook, data):
    resp = requests.post(webhook, json=data)
    if resp.status_code == 404:
        # Delete webhook because Discord says to not spam API requests if it's deleted
        db.bridges.delete_one({"webhook": webhook})


def reaction_queue():
    # Queue for reactions because they are heavily ratelimited
    while True:
        if len(bot.meower.pending_reactions) > 0:
            resp = requests.put(bot.meower.pending_reactions[0], headers={"Authorization": "Bot {0}".format(DISCORD_TOKEN)})
            if resp.status_code != 204:
                time.sleep(3)
                bot.meower.pending_reactions.append(bot.meower.pending_reactions[0])
            del bot.meower.pending_reactions[0]
Thread(target=reaction_queue).start()


def alert_to_discord(channel, post, presence=False, typing=False):
    # Create query to get bridges
    if channel == "ulist":
        query = {"ulist": True}
    else:
        query = {"meower_channel": channel}
        if presence:
            query["presence"] = True
        if typing:
            query["typing"] = True

    # Send alert to Discord
    for bridge in db.bridges.find(query):
        Thread(target=attempt_webhook, args=(bridge["webhook"], {"username": "Meower", "avatar_url": "https://assets.meower.org/PFP/21.png", "content": post, "allowed_mentions": {"parse": []}},)).start()


def bridge_to_discord(channel, user, post, exempt_channels=[]):
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
    for bridge in db.bridges.find({"meower_channel": channel}):
        if str(bridge["discord_channel"]) not in exempt_channels:
            Thread(target=attempt_webhook, args=(bridge["webhook"], {"username": user, "avatar_url": "https://assets.meower.org/PFP/{0}.png".format(bot.meower.cached_pfps[user]), "content": post, "allowed_mentions": {"parse": []}},)).start()


def typing_to_discord(channel, exempt_channels=[]):
    return # disabled for now

    if (channel in bot.meower.meower_last_typed) and (bot.meower.meower_last_typed[channel] > (time.time() + 5)):
        return
    else:
        bot.meower.meower_last_typed[channel] = time.time()

    bridges = list(db.bridges.find({"meower_channel": channel}))
    if len(bridges) == 0:
        return

    for bridge_data in bridges:
        if bridge_data["discord_channel"] not in exempt_channels:
            Thread(target=requests.post, args=(f"https://discord.com/api/v9/channels/{bridge_data['discord_channel']}/typing",), kwargs={"headers": {"Authorization": "Bot {0}".format(DISCORD_TOKEN)}}).start()


def typing_to_meower(channel):
    return # disabled for now

    if (channel in bot.meower.discord_last_typed) and (bot.meower.discord_last_typed[channel] > (time.time() + 3)):
        return
    else:
        bot.meower.discord_last_typed[channel] = time.time()

    bridge = db.bridges.find_one({"discord_channel": channel})
    if bridge is None:
        return

    if bridge["meower_channel"] == "home":
        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "set_chat_state", "val": {"chatid": "livechat", "state": 101}}})
    else:
        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "set_chat_state", "val": {"chatid": bridge["meower_channel"], "state": 100}}})


def check_for_ban(meower_username):
    # Get user IP
    bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "get_user_ip", "val": meower_username}})


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
    bridge_data = db.bridges.find_one({"discord_channel": msg.channel.id})
    if bridge_data is not None:
        # Check if the message can be bridged
        if msg.content.startswith("!!") or (msg.type not in [nextcord.MessageType.default, nextcord.MessageType.reply]):
            return
        
        # Check if the user has a Meower account linked
        link_data = db.links.find_one({"discord": msg.author.id, "verified": True})
        if (link_data is None) or (link_data["meower_username"] is None):
            if db.bans.find_one({"discord": {"$all": [msg.author.id]}}) is None:
                link_data = {"meower_username": f"(Discord) {msg.author.name}#{msg.author.discriminator}"}
            else:
                return

        # Convert reply to the author name
        if msg.reference is not None:
            replied_to_msg = await msg.channel.fetch_message(msg.reference.message_id)
            if replied_to_msg is not None:
                userdata = db.links.find_one({"discord": replied_to_msg.author.id, "verified": True})
                if userdata is None:
                    msg.content = "@{0} {1}".format(f"(Discord) {replied_to_msg.author.name}#{replied_to_msg.author.discriminator}", msg.content)
                else:
                    msg.content = "@{0} {1}".format(userdata["meower_username"], msg.content)

        # Convert all files to just the filename
        for file in msg.attachments:
            try:
                shortened_link = requests.post(f"{LINK_SHORTENER_URL}/submit", headers={"Authorization": LINK_SHORTENER_KEY}, json={"link": file.url}).json()
                msg.content += " [{0}: {1}]".format(file.filename, shortened_link["full_url"])
            except:
                pass

        # Save the message to a pending posts dictionary
        bot.meower.pending_posts[str(msg.id)] = {"action": "post", "discord_channel": str(bridge_data["discord_channel"]), "meower_channel": bridge_data["meower_channel"], "user": link_data["meower_username"], "content": msg.clean_content, "add_reaction": bridge_data["reactions"]}

        # Send post to Meower
        if bridge_data["meower_channel"] == "home":
            bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "post_home", "val": "{0}: {1}".format(link_data["meower_username"], msg.clean_content)}, "listener": str(msg.id)})
        else:
            bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "post_chat", "val": {"chatid": bridge_data["meower_channel"], "p": "{0}: {1}".format(link_data["meower_username"], msg.clean_content)}}, "listener": str(msg.id)})
    
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


@bot.event
async def on_typing(channel, user, when):
    print("typing detected")
    if db.bans.find_one({"discord": {"$all": [user.id]}}) is None:
        typing_to_meower(channel.id)


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
    await interaction.send("Restarting... The bot should be online again soon.")
    os.system("kill -KILL {0}".format(os.getpid()))


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
    except:
        await interaction.followup.send("Successfully applied warning! *(but could not DM this user)*")
    else:
        await interaction.followup.send("Successfully applied warning!")


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


@bot.slash_command(name="ping", description="Returns bot's ping to Discord API.", force_global=True)
async def ping(interaction: Interaction):
    await interaction.send(":ping_pong: Bot's ping to Discord API: {0}ms".format(round(bot.latency * 1000)), ephemeral=True)


@bot.slash_command(name="status", description="Returns Meower's status.", force_global=True)
async def status(interaction: Interaction):
    await interaction.send(":robot: Meower's status: {0}".format(status), ephemeral=True)


@bot.slash_command(name="info", description="Returns info about a Meower account.", force_global=True)
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


@bot.slash_command(name="link", description="Links your Meower account to your Discord account.", force_global=True)
async def link_meower(interaction: Interaction):
    # Check for ban
    ban_entry = db.bans.find_one({"discord": {"$all": [interaction.user.id]}})
    if ban_entry is not None:
        await interaction.send(":x: You are currently banned from linking your account to Meower Robot!\n\nReason: {0}".format(ban_entry.get("reason")), ephemeral=True)
        return

    # Create new link token
    link_token = secrets.token_urlsafe(32)
    db.links.insert_one({"discord": interaction.user.id, "meower_username": None, "meower_uuid": None, "token": link_token, "verified": False})

    # Send link token to user
    await interaction.send("To link your Meower account, visit this link: https://meower.org/discord?token={0}\n\nThis link will expire <t:{1}:R>.".format(link_token, int(time.time())+600), ephemeral=True)


@bot.slash_command(name="bridge", description="Bridge Meower home or a group chat.", force_global=True)
@has_permissions(manage_channels=True)
async def create_bridge(
    interaction: Interaction, 
    channel: str = SlashOption(name="channel", choices=["home", "livechat", "group chat"])
):
    await interaction.response.defer()
    
    # Check if the channel is currently bridged
    if db.bridges.find_one({"discord_channel": interaction.channel.id}) is not None:
        return await interaction.followup.send("There is already a bridge setup, please delete it first by doing `/unbridge`.")

    # Bridge the channel
    webhook = await interaction.channel.create_webhook(name="Meower Bridge")
    if channel == "home":
        db.bridges.insert_one({"discord_channel": interaction.channel.id, "meower_channel": "home", "bridge_owner": interaction.user.id, "webhook": webhook.url, "ulist": True, "presence": False, "typing": True, "reactions": True})
        await interaction.followup.send("Successfully bridged this channel to Meower home.")
    elif channel == "livechat":
        db.bridges.insert_one({"discord_channel": interaction.channel.id, "meower_channel": "livechat", "bridge_owner": interaction.user.id, "webhook": webhook.url, "ulist": False, "presence": True, "typing": True, "reactions": True})
        await interaction.followup.send("Successfully bridged this channel to Meower livechat.")
    else:
        token = secrets.token_hex(4)
        db.pending_chats.insert_one({"_id": token, "expires": (int(time.time()) + 900), "data": {"discord_channel": interaction.channel.id, "meower_channel": "livechat", "bridge_owner": interaction.user.id, "webhook": webhook.url, "ulist": False, "presence": True, "typing": True, "reactions": True}})
        await interaction.followup.send(f"To link this channel to your Meower group chat, please add me to the group chat then send `@discord bridge {token}`.\n\nThe code will expire <t:{(int(time.time()) + 900)}:R>.")


@bot.slash_command(name="unbridge", description="Unbridge channel from Meower.", force_global=True)
@has_permissions(manage_channels=True)
async def delete_bridge(interaction: Interaction):
    await interaction.response.defer()

    # Delete any current webhooks
    webhooks = await interaction.channel.webhooks()
    for webhook in webhooks:
        if webhook.user == bot.user:
            await webhook.delete()
    
    # Delete bridges
    db.bridges.delete_many({"discord_channel": interaction.channel.id})

    await interaction.followup.send("Successfully unbridged this channel from Meower.")


@bot.slash_command(name="settings", description="View/edit settings for Meower bridge.", force_global=True)
@has_permissions(manage_channels=True)
async def edit_settings(
    interaction: Interaction,
    setting: str = SlashOption(name="toggle", choices=["ulist", "presence", "reactions"], required=False)
):
    # Get bridge information
    bridge_data = db.bridges.find_one({"discord_channel": interaction.channel.id})
    if bridge_data is None:
        return await interaction.send("There is no bridge setup for this channel! Set one up by running `/bridge`.")

    if setting is None:
        # View config
        await interaction.send(embed=nextcord.Embed(title="Bridge Settings", description=f"""
            Bridged to: `{bridge_data['meower_channel']}`


            {':white_check_mark:' if bridge_data['ulist'] else ':x:'} **Ulist**: Alerts whenever someone logs in/out of Meower.

            {':white_check_mark:' if bridge_data['presence'] else ':x:'} **Presence**: Alerts whenever someone joins/leaves the bridged group chat. (only for livechat and group chats)

            {':white_check_mark:' if bridge_data['reactions'] else ':x:'} **Reactions**: Adds a reaction to sent messages to indicate whether they successfully sent or there was an error sending.
        """, color=0x34a1eb), ephemeral=True)
    else:
        # Save setting
        db.bridges.update_one({"_id": bridge_data["_id"]}, {"$set": {setting: (not bridge_data[setting])}})

        await interaction.send(f":white_check_mark: Successfully updated **{setting}** to **{str(not bridge_data[setting]).lower()}**!", ephemeral=True)


@bot.slash_command(name="ulist", description="Gets the current online Meower users.", force_global=True)
async def meower_ulist(interaction: Interaction):
    ulist = "**There are currently {0} users online on Meower.**".format(len(bot.meower._wss.statedata["ulist"]["usernames"]))
    for user in bot.meower._wss.statedata["ulist"]["usernames"]:
        try:
            ulist += "\n`{0}`  -  logged in <t:{1}:R>".format(user, bot.meower.ulist_time[user])
        except:
            pass
    await interaction.send(ulist, ephemeral=True)


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
            if user not in bot.meower.prev_ulist:
                bot.meower.ulist_time[user] = int(time.time())
                alert_to_discord("ulist", ":green_circle: {0} is now online!".format(user))
        
        # Offline checker
        for user in bot.meower.prev_ulist:
            if user not in ulist:
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
                alert_to_discord("ulist", ":red_circle: {0} is now offline! {0} was online for {1}.".format(user, time_online))
        
        # Update previous ulist
        bot.meower.prev_ulist = copy.copy(ulist)

    # Bridge status
    elif (data["cmd"] == "statuscode") and ("listener" in data) and (data["listener"] in bot.meower.pending_posts):
        post_data = bot.meower.pending_posts[data["listener"]]
        del bot.meower.pending_posts[data["listener"]]
        if data["val"] == "I:100 | OK":
            bridge_to_discord(post_data["meower_channel"], post_data["user"], post_data["content"], exempt_channels=[str(post_data["discord_channel"])])
            reaction = "%E2%9C%85"
        else:
            reaction = "%E2%9D%8C"
        
        if post_data["add_reaction"]:
            bot.meower.pending_reactions.append("https://discord.com/api/v9/channels/{0}/messages/{1}/reactions/{2}/%40me?location=Message".format(post_data["discord_channel"], data["listener"], reaction))

    # User sent pvar
    elif data["cmd"] == "pvar":
        if type(data["val"]) == str:
            return bot.meower._wss.sendPacket({"cmd": "pvar", "id": data["origin"], "name": data["name"], "val": handle_pvar(data["origin"], data["name"], data["val"])})
        else:
            return bot.meower._wss.sendPacket({"cmd": "pvar", "id": data["origin"], "name": data["name"], "val": "E:102 | Datatype"})

    # Commands and bridge
    elif "post_origin" in data["val"]:
        data = data["val"]
        original_u = data["u"]
        original_p = data["p"]

        if data["u"] == MEOWER_USERNAME:
            data["u"] = data["p"].split(":")[0]
            data["p"] = data["p"].replace("{0}: ".format(data["u"]), "", 1)

        # Bridge commands
        if data["p"].lower().startswith("@discord "):
            args = data["p"].lower().split(" ")
            del args[0]
            
            if data["post_origin"] != "home":
                if args[0] == "bridge":
                    bridge_data = db.pending_chats.find_one({"_id": args[1]})
                    db.pending_chats.delete_one({"_id": args[1]})

                    if bridge_data is None:
                        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "post_chat", "val": {"chatid": data["post_origin"], "p": "Unable to find bridge with that code!"}}})
                    elif bridge_data["expires"] < int(time.time()):
                        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "post_chat", "val": {"chatid": data["post_origin"], "p": "This code has expired! Please generate a new one by running '/bridge' in Discord."}}})
                    else:
                        bridge_data["data"]["meower_channel"] = data["post_origin"]
                        db.bridges.delete_many({"discord_channel": bridge_data["data"]["discord_channel"]})
                        db.bridges.insert_one(bridge_data["data"])
                        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "post_chat", "val": {"chatid": data["post_origin"], "p": "Successfully created bridge!"}}})
                """ disabled due to getting chat owner is annoying to do right now
                elif args[0] == "unbridge":
                    if data["post_origin"] == "livechat":
                        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "post_chat", "val": {"chatid": data["post_origin"], "p": "You cannot unbridge livechat!"}}})
                    else:
                        alert_to_discord(data["post_origin"], ":link::x: Meower bridge to `{0}` has been destroyed by request of the chat owner!".format(data["post_origin"]))
                        db.bridges.delete_many({"meower_channel": data["post_origin"]})
                        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "post_chat", "val": {"chatid": data["post_origin"], "p": "Successfully deleted all bridges to this group chat!"}}})
                """


        # Moderator commands
        if data["p"].lower().startswith("@mod "):
            user_info = requests.get("https://api.meower.org/users/{0}".format(data["u"])).json()
            if user_info["lvl"] >= 1:
                args = data["p"].lower().split(" ")
                del args[0]

                if args[0] == "alert":
                    alert_msg = data["p"].replace((args[0] + " "), "", 1)
                    alert_msg = alert_msg.replace((args[1] + " "), "", 1)
                    bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "alert", "val": {"username": args[1], "p": alert_msg}}})
                elif args[0] == "kick":
                    bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "kick", "val": args[1]}})
                elif args[0] == "ban":
                    bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "ban", "val": args[1]}})
                elif args[0] == "pardon":
                    bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "pardon", "val": args[1]}})

        # Bridge
        if (original_u != MEOWER_USERNAME) and (not original_p.startswith("@discord")) and (not original_p.startswith("@mod")):
            bridge_to_discord(data["post_origin"], original_u, original_p)

    # Chat state
    elif ("state" in data["val"]) and (data["val"]["u"] != MEOWER_USERNAME):
        if data["val"]["state"] == 0:
            alert_to_discord(data["val"]["chatid"], ":outbox_tray: {0} left the chat!".format(data["val"]["u"]), presence=True)
        elif data["val"]["state"] == 1:
            alert_to_discord(data["val"]["chatid"], ":inbox_tray: {0} joined the chat!".format(data["val"]["u"]), presence=True)
        elif data["val"]["state"] == 100:
            typing_to_discord(data["val"]["chatid"])
        elif (data["val"]["state"] == 101) and (data["val"]["chatid"] == "livechat"):
            typing_to_discord("home")

    # Get IP for ban checking
    elif ("mode" in data["val"]) and (data["val"]["mode"] == "user_ip"):
        bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "get_ip_data", "val": data["val"]["payload"]["ip"]}})
    
    # Get IP data for ban checking
    elif ("mode" in data["val"]) and (data["val"]["mode"] == "ip_data"):
        ban_entry = db.bans.find_one({"meower": {"$in": data["val"]["payload"]["users"]}})
        if ban_entry is not None:
            for user in ban_entry["meower"]:
                if db.links.find_one({"meower_username": user}) is not None:
                    bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "alert", "val": {"username": user, "p": "Your account has been unlinked from your Discord account on Meower Robot due to one or more accounts on your IP address being banned. Reason: {0}".format(ban_entry["reason"])}}})
            db.links.delete_many({"meower_username": {"$im": [origin]}})

def handle_pvar(origin, name, val):
    if name == "discord":
        userdata = db.links.find_one({"token": val})
        if userdata is None:
            return "E:103 | IDNotFound"
        
        requests.put("https://discord.com/api/v9/guilds/{0}/members/{1}/roles/{2}".format(MEOWER_DISCORD_GUILD[0], userdata["discord"], MEMBER_ROLE), headers={"Authorization": "Bot {0}".format(DISCORD_TOKEN)})
        try:
            userdata["meower_username"] = origin
            userdata["meower_uuid"] = requests.get("https://api.meower.org/users/{0}".format(origin)).json()["uuid"]
            userdata["verified"] = True
            del userdata["token"]

            db.links.delete_many({"$or": [{"discord": userdata["discord"]}, {"meower_username": origin}, {"meower_uuid": userdata["meower_uuid"]}]})

            Thread(target=bot.meower._wss.sendPacket, args=({"cmd": "direct", "val": {"cmd": "get_user_ip", "val": origin}},))
            ban_entry = db.bans.find_one({"meower": {"$all": [origin]}})
            if ban_entry is not None:
                bot.meower._wss.sendPacket({"cmd": "direct", "val": {"cmd": "alert", "val": {"username": origin, "p": "Your account has been unlinked from your Discord account on Meower Robot due to one or more accounts on your IP address being banned. Reason: {0}".format(ban_entry["reason"])}}})
            else:
                db.links.insert_one(userdata)

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
        if (len(val) < 1) or (len(val)) > 20:
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
    bot.run(DISCORD_TOKEN)
