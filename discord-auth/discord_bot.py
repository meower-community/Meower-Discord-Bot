import nextcord
from nextcord.ext import commands
import os
import json
import time
from uuid import uuid4

intents = nextcord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"Successfully logged into Discord as {bot.user}")
    await bot.change_presence(activity=nextcord.Activity(type=nextcord.ActivityType.watching, name="!help and Verifications"))

@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f"An error occurred, this is what we know:\n\n{error}")

@bot.event
async def on_member_join(user):
    channel = user.guild.get_channel(939748856080511026)
    try:
        verifyID = str(uuid4())
        with open("users/id.json", 'r') as f:
            users_id = json.loads(f.read())
        users_id[verifyID] = {"ID": str(user.id), "username": str(user), "timestamp": int(time.time()) + 600}
        with open("users/id.json", 'w') as f:
            json.dump(users_id, f, indent=4)
    except:
        return await channel.send(f"||{user.mention}||\n\n:warning: Failed generating token, please try again later!")
    try:
        await user.send(f"Welcome to the Meower Discord!\n\nTo be able to access the Discord server you'll need to link your Meower account.\n\nGo to this link to link your Meower account: https://mobile.meower.org/discord-auth?id={verifyID}\nThis link will expire <t:{users_id[verifyID]['timestamp']}:R>")
        return await channel.send(f"||{user.mention}||\n\n:mailbox_with_mail: You have been sent a direct message on how to link your Meower account to be able to access the Discord!")
    except:
        channel = user.guild.get_channel(939748856080511026)
        return await channel.send(f"||{user.mention}||\n\n:warning: You need to have direct messages on to be able to verify!\nAfter enabling direct messages type the command `!verify` into this channel.")

@bot.event
async def on_message(msg):
    if msg.author == bot.user:
        return
    if msg.channel.id == 939748856080511026:
        if msg.content != "!verify":
            await msg.delete()
    if msg.channel.id == 939707540776812605:
        data = msg.content.split(";")
        if len(data) != 3:
            return await msg.reply("Failed to verify user!")
        try:
            if data[0] == "1":
                user = msg.guild.get_member(int(data[1]))
                await user.add_roles(nextcord.utils.get(msg.guild.roles,name="Member"))
                with open("users/meower.json", 'r') as f:
                    meower_users = json.loads(f.read())
                meower_users[str(data[2])] = str(data[1])
                with open("users/meower.json", 'w') as f:
                    json.dump(meower_users, f, indent=4)
                with open(f"users/{str(user.id)}.txt", 'w') as f:
                    f.write(str(data[2]))
                await msg.reply(f"Successfully verified {user.mention}!")
                try:
                    await user.send(f"You have linked the Meower account {data[2]} to your Discord account! Thank you :)\n\nYou have been verified and now have full access to the Discord server.")
                except:
                    pass
            elif data[0] == "0":
                user = msg.guild.get_member(int(data[1]))
                await user.remove_roles(nextcord.utils.get(msg.guild.roles,name="Member"))
                os.remove(f"users/{str(user.id)}.txt")
                await msg.reply(f"Successfully unverified {user.mention}!")
                try:
                    await user.send(f"You have been unverified from the Discord! This is due to you linking your Meower account to a different Discord account.\nTo re-verify run the command `!verify` here.")
                except:
                    pass
            else:
                return await msg.reply("Failed to verify user!")
        except:
            return await msg.reply("Failed to verify user!")
    else:
        await bot.process_commands(msg)

@bot.command()
async def verify(ctx):
    try:
        verifyID = str(uuid4())
        with open("users/id.json", 'r') as f:
            users_id = json.loads(f.read())
        users_id[verifyID] = {"ID": str(ctx.author.id), "username": str(ctx.author), "timestamp": int(time.time()) + 600}
        with open("users/id.json", 'w') as f:
            json.dump(users_id, f, indent=4)
    except:
        return await ctx.reply(":warning: Failed generating token, please try again later!")
    try:
        await ctx.author.send(f"Welcome to the Meower Discord!\n\nTo be able to access the Discord server you'll need to link your Meower account.\n\nGo to this link to link your Meower account: https://mobile.meower.org/discord-auth?id={verifyID}\nThis link will expire <t:{users_id[verifyID]['timestamp']}:R>")
        if ctx.channel.id == 939748856080511026:
            await ctx.message.delete()
    except:
        return await ctx.reply(":warning: You need to have direct messages on to be able to use this command.")

@bot.command()
async def ping(ctx):
    await ctx.reply(f":ping_pong: Bot's ping to Discord API: {round(bot.latency, 1)}")

@bot.command()
async def meower(ctx, user=None):
    if user == None:
        return await ctx.reply("No Meower username was specified!")
    try:
        with open("users/meower.json", 'r') as f:
            meower_users = json.loads(f.read())
            if user in meower_users.keys():
                return await ctx.reply(f"{user}'s Discord account is `{ctx.guild.get_member(int(meower_users[user]))}`")
            else:
                return await ctx.reply(f"{user} hasn't linked their Meower account to a Discord account yet!")
    except:
        return await ctx.reply(f"{user} hasn't linked their Meower account to a Discord account yet!")

@bot.command()
async def info(ctx, user: nextcord.User=None):
    if user == None:
        user = ctx.author
    try:
        with open(f"users/{str(user.id)}.txt", 'r') as f:
            meower_user = f.read()
    except:
        meower_user = "None"
    e = nextcord.Embed(title=user, color=nextcord.Color.orange())
    e.add_field(name="Username", value=str(user.name))
    e.add_field(name="Discriminator", value=str(user.discriminator))
    e.add_field(name="ID", value=str(user.id))
    e.add_field(name="Joined Discord", value=user.created_at.strftime("%b %d, %Y"))
    e.add_field(name="Meower Account", value=meower_user)
    await ctx.reply(embed=e)

bot.run("<TOKEN>")
