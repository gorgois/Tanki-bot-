import discord
from discord.ext import commands
from discord import app_commands
import random, json, asyncio
from flask import Flask
from threading import Thread
import os

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

XP_FILE = "data.json"
user_cooldowns = {}

app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

def load_data():
    try:
        with open(XP_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(XP_FILE, "w") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    data = load_data()
    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    config = data.get(guild_id, {}).get("config", {})

    if not config.get("enabled", False):
        return

    now = asyncio.get_event_loop().time()
    cooldown = config.get("cooldown", 30)
    if user_id in user_cooldowns and now - user_cooldowns[user_id] < cooldown:
        return

    user_cooldowns[user_id] = now

    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}
    if "users" not in data[guild_id]:
        data[guild_id]["users"] = {}
    if user_id not in data[guild_id]["users"]:
        data[guild_id]["users"][user_id] = {"xp": 0, "level": 1}

    xp_min = config.get("xp_min", 5)
    xp_max = config.get("xp_max", 15)
    xp_gain = random.randint(xp_min, xp_max)
    data[guild_id]["users"][user_id]["xp"] += xp_gain

    xp = data[guild_id]["users"][user_id]["xp"]
    level = data[guild_id]["users"][user_id]["level"]
    next_level = level * 100

    if xp >= next_level:
        data[guild_id]["users"][user_id]["level"] += 1
        level_channel_id = config.get("level_channel")
        msg = f"🎉 {message.author.mention} leveled up to **Level {level + 1}**!"

        if level_channel_id:
            channel = bot.get_channel(int(level_channel_id))
            if channel:
                await channel.send(msg)
            else:
                await message.channel.send(msg)
        else:
            await message.channel.send(msg)

        level_roles = config.get("level_roles", {})
        role_id = level_roles.get(str(level + 1))
        if role_id:
            role = message.guild.get_role(int(role_id))
            if role:
                await message.author.add_roles(role)
                await message.channel.send(f"🏅 {message.author.mention} received the role **{role.name}**!")

    save_data(data)

@tree.command(name="rank", description="Show your current level and XP")
async def rank(interaction: discord.Interaction):
    await interaction.response.defer()
    data = load_data()
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)

    user = data.get(guild_id, {}).get("users", {}).get(user_id)
    if not user:
        await interaction.followup.send("You haven't earned any XP yet.")
        return

    level = user["level"]
    xp = user["xp"]
    next_level = level * 100
    percent = int((xp / next_level) * 100)
    bar = "█" * (percent // 10) + "—" * (10 - percent // 10)

    await interaction.followup.send(
        f"📊 **{interaction.user.display_name}'s Rank**\n"
        f"Level: **{level}**\n"
        f"XP: **{xp} / {next_level}**\n"
        f"Progress: `{bar}` ({percent}%)"
    )

@tree.command(name="enable-leveling", description="Enable leveling system in the server")
@app_commands.checks.has_permissions(administrator=True)
async def enable_leveling(interaction: discord.Interaction):
    data = load_data()
    guild_id = str(interaction.guild.id)

    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}

    data[guild_id]["config"]["enabled"] = True
    save_data(data)
    await interaction.response.send_message("✅ Leveling system enabled.")

@tree.command(name="disable-leveling", description="Disable leveling system in the server")
@app_commands.checks.has_permissions(administrator=True)
async def disable_leveling(interaction: discord.Interaction):
    data = load_data()
    guild_id = str(interaction.guild.id)

    if guild_id in data:
        data[guild_id]["config"]["enabled"] = False
        save_data(data)

    await interaction.response.send_message("⛔ Leveling system disabled.")

@tree.command(name="set-level-channel", description="Set channel where level-up messages will be sent")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="The channel to send level-up messages")
async def set_level_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_data()
    guild_id = str(interaction.guild.id)

    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}

    data[guild_id]["config"]["level_channel"] = str(channel.id)
    save_data(data)
    await interaction.response.send_message(f"📢 Level-up messages will be sent in {channel.mention}.")

@tree.command(name="set-level-role", description="Give a role when reaching a certain level")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(level="Level number", role="Role to give")
async def set_level_role(interaction: discord.Interaction, level: int, role: discord.Role):
    data = load_data()
    guild_id = str(interaction.guild.id)

    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}

    if "level_roles" not in data[guild_id]["config"]:
        data[guild_id]["config"]["level_roles"] = {}

    data[guild_id]["config"]["level_roles"][str(level)] = str(role.id)
    save_data(data)
    await interaction.response.send_message(f"🏅 Role {role.mention} will be given at level {level}.")

if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not set.")
        exit(1)
    bot.run(TOKEN)