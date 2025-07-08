import discord
from discord.ext import commands
from discord import app_commands
import random, json, asyncio
from flask import Flask
from threading import Thread

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

XP_FILE = "data.json"
user_cooldowns = {}

# Flask app for uptime check
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Load XP and config data
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

    # Check if leveling enabled
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

        # Role reward
        level_roles = config.get("level_roles", {})
        role_id = level_roles.get(str(level + 1))
        if role_id:
            role = message.guild.get_role(int(role_id))
            if role:
                await message.author.add_roles(role)
                await message.channel.send(f"🏅 {message.author.mention} received the role **{role.name}**!")

    save_data(data)

# ------------------ SLASH COMMANDS ------------------

@tree.command(name="rank", description="Show your current level and XP")
async def rank(interaction: discord.Interaction):
    user = interaction.user
    data = load_data()
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)

    if guild_id not in data or "users" not in data[guild_id] or user_id not in data[guild_id]["users"]:
        await interaction.response.send_message("You haven't earned any XP yet!", ephemeral=True)
        return

    stats = data[guild_id]["users"][user_id]
    xp = stats["xp"]
    level = stats["level"]
    next_level = level * 100
    percent = int((xp / next_level) * 100)

    bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
    await interaction.response.send_message(
        f"📊 **{user.display_name}'s Rank**\n"
        f"Level: **{level}**\n"
        f"XP: **{xp} / {next_level}**\n"
        f"Progress: `{bar}` ({percent}%)"
    )

@tree.command(name="leaderboard", description="Show top XP users")
async def leaderboard(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    data = load_data()

    if guild_id not in data or "users" not in data[guild_id]:
        await interaction.response.send_message("No leaderboard data yet.")
        return

    leaderboard = sorted(data[guild_id]["users"].items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    embed = discord.Embed(title="🏆 Top 10 Users", color=0x00ff00)

    for i, (user_id, stats) in enumerate(leaderboard, start=1):
        member = interaction.guild.get_member(int(user_id))
        name = member.display_name if member else f"User ID {user_id}"
        embed.add_field(
            name=f"{i}. {name}",
            value=f"Level {stats['level']} – {stats['xp']} XP",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@tree.command(name="enable-leveling", description="Turn ON the XP/leveling system")
@app_commands.checks.has_permissions(administrator=True)
async def enable_leveling(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    data = load_data()
    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}
    data[guild_id]["config"]["enabled"] = True
    save_data(data)
    await interaction.response.send_message("✅ Leveling system is now **ENABLED**.")

@tree.command(name="disable-leveling", description="Turn OFF the XP/leveling system")
@app_commands.checks.has_permissions(administrator=True)
async def disable_leveling(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    data = load_data()
    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}
    data[guild_id]["config"]["enabled"] = False
    save_data(data)
    await interaction.response.send_message("⛔ Leveling system is now **DISABLED**.")

@tree.command(name="set-level-channel", description="Set the channel for level-up messages")
@app_commands.checks.has_permissions(administrator=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    data = load_data()
    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}
    data[guild_id]["config"]["level_channel"] = str(channel.id)
    save_data(data)
    await interaction.response.send_message(f"✅ Level-up messages will go to {channel.mention}")

@tree.command(name="set-xp-rate", description="Set the XP gain range (min and max)")
@app_commands.checks.has_permissions(administrator=True)
async def set_xp_rate(interaction: discord.Interaction, min_xp: int, max_xp: int):
    if min_xp < 1 or max_xp < min_xp:
        await interaction.response.send_message("Invalid XP range.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    data = load_data()
    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}
    data[guild_id]["config"]["xp_min"] = min_xp
    data[guild_id]["config"]["xp_max"] = max_xp
    save_data(data)
    await interaction.response.send_message(f"✅ XP gain range set to {min_xp}-{max_xp} XP")

@tree.command(name="set-cooldown", description="Set the XP cooldown in seconds")
@app_commands.checks.has_permissions(administrator=True)
async def set_cooldown(interaction: discord.Interaction, seconds: int):
    if seconds < 1:
        await interaction.response.send_message("Cooldown must be at least 1 second.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    data = load_data()
    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}
    data[guild_id]["config"]["cooldown"] = seconds
    save_data(data)
    await interaction.response.send_message(f"✅ XP cooldown set to {seconds} seconds")

@tree.command(name="reset-user", description="Reset a user’s XP and level")
@app_commands.checks.has_permissions(administrator=True)
async def reset_user(interaction: discord.Interaction, user: discord.Member):
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    data = load_data()
    if guild_id in data and "users" in data[guild_id] and user_id in data[guild_id]["users"]:
        del data[guild_id]["users"][user_id]
        save_data(data)
        await interaction.response.send_message(f"🔁 Reset {user.mention}'s XP and level.")
    else:
        await interaction.response.send_message(f"User has no XP data yet.")

@tree.command(name="reset-all", description="Reset all XP and levels in this server")
@app_commands.checks.has_permissions(administrator=True)
async def reset_all(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    data = load_data()
    if guild_id in data and "users" in data[guild_id]:
        data[guild_id]["users"] = {}
        save_data(data)
        await interaction.response.send_message("🔁 All users' XP and levels have been reset.")
    else:
        await interaction.response.send_message("This server has no XP data yet.")

@tree.command(name="set-role-for-level", description="Assign a role when a user reaches a level")
@app_commands.checks.has_permissions(administrator=True)
async def set_role_for_level(interaction: discord.Interaction, level: int, role: discord.Role):
    if level < 1:
        await interaction.response.send_message("Level must be at least 1.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    data = load_data()
    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}
    level_roles = data[guild_id]["config"].get("level_roles", {})
    level_roles[str(level)] = str(role.id)
    data[guild_id]["config"]["level_roles"] = level_roles
    save_data(data)
    await interaction.response.send_message(f"✅ Users who reach level {level} will be given the role {role.name}.")

@tree.command(name="boost", description="Give bonus XP to a user")
@app_commands.checks.has_permissions(administrator=True)
async def boost(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount < 1:
        await interaction.response.send_message("Amount must be positive.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    data = load_data()
    if guild_id not in data:
        data[guild_id] = {"config": {}, "users": {}}
    if "users" not in data[guild_id]:
        data[guild_id]["users"] = {}
    if user_id not in data[guild_id]["users"]:
        data[guild_id]["users"][user_id] = {"xp": 0, "level": 1}
    data[guild_id]["users"][user_id]["xp"] += amount
    save_data(data)
    await interaction.response.send_message(f"🚀 {user.mention} has been boosted by **{amount} XP**!")

@tree.command(name="status", description="View current leveling bot settings")
@app_commands.checks.has_permissions(administrator=True)
async def status(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    data = load_data()
    config = data.get(guild_id, {}).get("config", {})

    enabled = config.get("enabled", False)
    xp_min = config.get("xp_min", 5)
    xp_max = config.get("xp_max", 15)
    cooldown = config.get("cooldown", 30)
    level_channel_id = config.get("level_channel")
    level_channel = interaction.guild.get_channel(int(level_channel_id)) if level_channel_id else None

    level_roles = config.get("level_roles", {})
    role_text = ""
    for level, role_id in sorted(level_roles.items(), key=lambda x: int(x[0])):
        role = interaction.guild.get_role(int(role_id))
        if role:
            role_text += f"Level {level}: {role.name}\n"

    embed = discord.Embed(title="📋 Leveling System Status", color=0x3498db)
    embed.add_field(name="Enabled", value=str(enabled), inline=True)
    embed.add_field(name="XP Range", value=f"{xp_min}–{xp_max}", inline=True)
    embed.add_field(name="Cooldown", value=f"{cooldown}s", inline=True)
    embed.add_field(name="Level-Up Channel", value=level_channel.mention if level_channel else "Not Set", inline=False)
    embed.add_field(name="Level Roles", value=role_text or "None", inline=False)

    await interaction.response.send_message(embed=embed)

# --------------------------------------------------------

if __name__ == "__main__":
    keep_alive()
    bot.run("YOUR_BOT_TOKEN")