import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os
from datetime import datetime, timedelta
import re
import threading
from flask import Flask

# Intents setup
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Data files
XP_FILE = "xp_data.json"
CONFIG_FILE = "config.json"

# Data holders
xp_data = {}
config = {}

# Load XP and config data from files
def load_data():
    global xp_data, config
    if os.path.exists(XP_FILE):
        with open(XP_FILE, "r") as f:
            xp_data = json.load(f)
    else:
        xp_data = {}

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    else:
        config = {}

# Save XP and config data to files
def save_data():
    with open(XP_FILE, "w") as f:
        json.dump(xp_data, f, indent=4)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# Get or create default guild config
def get_xp_settings(guild_id):
    guild_id = str(guild_id)
    if guild_id not in config:
        config[guild_id] = {
            "enabled": True,
            "xp_rate": 10,
            "cooldown": 60,
            "level_roles": {},
            "dm_enabled": True,
            "level_channel": None,
            "profile_bg": None,
            # Customization defaults:
            "embed_color": "#00ff99",
            "background_url": None,
            "card_theme": "default",
        }
    return config[guild_id]

# Event: bot ready
@bot.event
async def on_ready():
    load_data()
    await tree.sync()
    print(f"Logged in as {bot.user}.")

# Event: on message to give XP
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    settings = get_xp_settings(message.guild.id)
    if not settings["enabled"]:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)
    now = datetime.utcnow()

    if guild_id not in xp_data:
        xp_data[guild_id] = {}

    if user_id not in xp_data[guild_id]:
        xp_data[guild_id][user_id] = {
            "xp": 0,
            "level": 1,
            "last_message": "2000-01-01T00:00:00"
        }

    user_data = xp_data[guild_id][user_id]
    last_msg_time = datetime.fromisoformat(user_data["last_message"])
    cooldown = timedelta(seconds=settings["cooldown"])

    if now - last_msg_time >= cooldown:
        user_data["xp"] += settings["xp_rate"]
        user_data["last_message"] = now.isoformat()

        new_level = int(user_data["xp"] ** 0.5)
        if new_level > user_data["level"]:
            user_data["level"] = new_level
            await handle_level_up(message.author, new_level, message.guild)

    save_data()
    await bot.process_commands(message)  # important to process commands

# Level up handler
async def handle_level_up(user, level, guild):
    settings = get_xp_settings(guild.id)
    role_id = settings["level_roles"].get(str(level))
    if role_id:
        role = guild.get_role(role_id)
        if role:
            try:
                await user.add_roles(role)
            except discord.Forbidden:
                pass

    channel = guild.get_channel(settings["level_channel"]) if settings["level_channel"] else None
    msg = f"🎉 {user.mention} leveled up to **{level}**!"
    if channel:
        await channel.send(msg)
    elif settings["dm_enabled"]:
        try:
            await user.send(f"🎉 You leveled up to **{level}** in **{guild.name}**!")
        except:
            pass

# Helper: relaxed image URL validation
def is_valid_image_url(url):
    return bool(re.match(r'^https?:\/\/.*', url, re.IGNORECASE)) and \
           bool(re.search(r'\.(png|jpg|jpeg|gif|webp)', url, re.IGNORECASE))

# ---------------------------------
# Slash Commands (Old + New merged)
# ---------------------------------

@tree.command(name="rank", description="Check your rank and XP")
async def rank(interaction: discord.Interaction):
    user = interaction.user
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)

    if guild_id in xp_data and user_id in xp_data[guild_id]:
        xp = xp_data[guild_id][user_id]["xp"]
        level = xp_data[guild_id][user_id]["level"]
        await interaction.response.send_message(f"🔢 {user.mention}, you are level **{level}** with **{xp} XP**.")
    else:
        await interaction.response.send_message("You have no XP yet. Start chatting to earn XP!")

@tree.command(name="add-role-level", description="Set a role reward for reaching a level (admin only)")
@app_commands.describe(level="Level to set the role for", role="Role to give")
async def add_role_level(interaction: discord.Interaction, level: int, role: discord.Role):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return

    settings = get_xp_settings(interaction.guild.id)
    settings["level_roles"][str(level)] = role.id
    save_data()
    await interaction.response.send_message(f"✅ Role {role.mention} will now be given at level {level}.")

@tree.command(name="remove-role-level", description="Remove a level reward (admin only)")
@app_commands.describe(level="Level to remove role from")
async def remove_role_level(interaction: discord.Interaction, level: int):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return

    settings = get_xp_settings(interaction.guild.id)
    if str(level) in settings["level_roles"]:
        del settings["level_roles"][str(level)]
        save_data()
        await interaction.response.send_message(f"❌ Removed role reward for level {level}.")
    else:
        await interaction.response.send_message(f"No reward was set for level {level}.")

@tree.command(name="levels", description="List all level role rewards")
async def list_levels(interaction: discord.Interaction):
    settings = get_xp_settings(interaction.guild.id)
    roles = settings["level_roles"]
    if not roles:
        await interaction.response.send_message("⚠️ No level role rewards set yet.")
        return
    msg = "🎖 **Level Role Rewards:**\n"
    for lvl, role_id in sorted(roles.items(), key=lambda x: int(x[0])):
        role = interaction.guild.get_role(role_id)
        if role:
            msg += f"Level {lvl}: {role.mention}\n"
    await interaction.response.send_message(msg)

@tree.command(name="set-level-channel", description="Set channel for level-up messages (admin only)")
@app_commands.describe(channel="Channel to send level-up messages")
async def set_level_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return

    settings = get_xp_settings(interaction.guild.id)
    settings["level_channel"] = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Level-up messages will be sent in {channel.mention}.")

@tree.command(name="enable-leveling", description="Enable leveling (admin only)")
async def enable_leveling(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["enabled"] = True
    save_data()
    await interaction.response.send_message("✅ Leveling enabled.")

@tree.command(name="disable-leveling", description="Disable leveling (admin only)")
async def disable_leveling(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["enabled"] = False
    save_data()
    await interaction.response.send_message("⛔ Leveling disabled.")

@tree.command(name="set-xp-rate", description="Set XP per message (admin only)")
@app_commands.describe(amount="XP amount per message")
async def set_xp_rate(interaction: discord.Interaction, amount: int):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    if amount < 0:
        await interaction.response.send_message("❌ XP amount must be zero or higher.")
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["xp_rate"] = amount
    save_data()
    await interaction.response.send_message(f"✅ XP per message set to {amount}.")

@tree.command(name="set-xp-cooldown", description="Set XP gain cooldown in seconds (admin only)")
@app_commands.describe(seconds="Cooldown in seconds")
async def set_xp_cooldown(interaction: discord.Interaction, seconds: int):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    if seconds < 1:
        await interaction.response.send_message("❌ Cooldown must be at least 1 second.")
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["cooldown"] = seconds
    save_data()
    await interaction.response.send_message(f"✅ XP cooldown set to {seconds} seconds.")

@tree.command(name="set-xp", description="Set a user's XP (admin only)")
@app_commands.describe(user="User to set XP", amount="XP amount")
async def set_xp(interaction: discord.Interaction, user: discord.User, amount: int):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in xp_data:
        xp_data[guild_id] = {}
    xp_data[guild_id][user_id] = {
        "xp": amount,
        "level": int(amount ** 0.5),
        "last_message": "2000-01-01T00:00:00"
    }
    save_data()
    await interaction.response.send_message(f"✅ Set {user.mention}'s XP to {amount}.")

@tree.command(name="reset-xp", description="Reset a user's XP (admin only)")
@app_commands.describe(user="User to reset XP")
async def reset_xp(interaction: discord.Interaction, user: discord.User):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id in xp_data and user_id in xp_data[guild_id]:
        xp_data[guild_id][user_id]["xp"] = 0
        xp_data[guild_id][user_id]["level"] = 1
        save_data()
        await interaction.response.send_message(f"✅ Reset {user.mention}'s XP.")
    else:
        await interaction.response.send_message(f"{user.mention} has no XP data.")

@tree.command(name="daily", description="Claim daily XP bonus")
async def daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    guild_id = str(interaction.guild.id)
    now = datetime.utcnow()

    cooldown_hours = 24
    cooldown = timedelta(hours=cooldown_hours)

    if guild_id not in xp_data:
        xp_data[guild_id] = {}
    if user_id not in xp_data[guild_id]:
        xp_data[guild_id][user_id] = {
            "xp": 0,
            "level": 1,
            "last_message": "2000-01-01T00:00:00",
            "last_daily": "2000-01-01T00:00:00"
        }

    user_data = xp_data[guild_id][user_id]
    last_daily = datetime.fromisoformat(user_data.get("last_daily", "2000-01-01T00:00:00"))
    if now - last_daily < cooldown:
        remaining = cooldown - (now - last_daily)
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes = remainder // 60
        await interaction.response.send_message(f"⏳ You already claimed your daily XP. Come back in {hours}h {minutes}m.", ephemeral=True)
        return

    bonus_xp = 50
    user_data["xp"] += bonus_xp
    user_data["last_daily"] = now.isoformat()
    new_level = int(user_data["xp"] ** 0.5)
    if new_level > user_data["level"]:
        user_data["level"] = new_level
        await handle_level_up(interaction.user, new_level, interaction.guild)
    save_data()
    await interaction.response.send_message(f"🎉 You claimed your daily {bonus_xp} XP!")

@tree.command(name="bonus-xp", description="Grant bonus XP to a user (admin only)")
@app_commands.describe(user="User to grant XP", amount="XP amount")
async def bonus_xp(interaction: discord.Interaction, user: discord.User, amount: int):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    if amount < 1:
        await interaction.response.send_message("❌ Amount must be 1 or higher.")
        return

    guild_id = str(interaction.guild.id)
    user_id = str(user.id)

    if guild_id not in xp_data:
        xp_data[guild_id] = {}
    if user_id not in xp_data[guild_id]:
        xp_data[guild_id][user_id] = {
            "xp": 0,
            "level": 1,
            "last_message": "2000-01-01T00:00:00"
        }

    user_data = xp_data[guild_id][user_id]
    user_data["xp"] += amount
    new_level = int(user_data["xp"] ** 0.5)
    if new_level > user_data["level"]:
        user_data["level"] = new_level
        await handle_level_up(user, new_level, interaction.guild)
    save_data()
    await interaction.response.send_message(f"✅ Granted {amount} XP to {user.mention}.")

@tree.command(name="profile", description="Show your profile card with XP and level")
async def profile(interaction: discord.Interaction):
    user = interaction.user
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)

    if guild_id not in xp_data or user_id not in xp_data[guild_id]:
        await interaction.response.send_message("You have no XP data yet.")
        return

    user_data = xp_data[guild_id][user_id]
    xp = user_data["xp"]
    level = user_data["level"]
    bg_url = get_xp_settings(interaction.guild.id).get("profile_bg") or "https://i.imgur.com/TP3E2Ch.png"

    embed = discord.Embed(title=f"{user.display_name}'s Profile", color=discord.Color.blue())
    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)
    embed.set_image(url=bg_url)
    embed.add_field(name="Level", value=str(level), inline=True)
    embed.add_field(name="XP", value=str(xp), inline=True)

    await interaction.response.send_message(embed=embed)

@tree.command(name="bg-list", description="List available profile backgrounds")
async def bg_list(interaction: discord.Interaction):
    backgrounds = {
        "Default": "https://i.imgur.com/TP3E2Ch.png",
        "Dark": "https://i.imgur.com/8f7Q9nr.png",
        "Sunset": "https://i.imgur.com/r3fLMKt.png"
    }
    msg = "Available backgrounds:\n"
    for name, url in backgrounds.items():
        msg += f"**{name}**: {url}\n"
    await interaction.response.send_message(msg)

@tree.command(name="set-profile-bg", description="Set profile background URL (admin only)")
@app_commands.describe(url="Image URL for profile background")
async def set_profile_bg(interaction: discord.Interaction, url: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return

    if not is_valid_image_url(url):
        await interaction.response.send_message("❌ Please provide a valid image URL containing .png, .jpg, .jpeg, .gif, or .webp")
        return

    settings = get_xp_settings(interaction.guild.id)
    settings["profile_bg"] = url
    save_data()
    await interaction.response.send_message("✅ Profile background set!")

@tree.command(name="toggle-dms", description="Toggle DM level-up messages (admin only)")
@app_commands.describe(enabled="True to enable, False to disable")
async def toggle_dms(interaction: discord.Interaction, enabled: bool):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["dm_enabled"] = enabled
    save_data()
    status = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"✅ Level-up DM messages {status}.")

@tree.command(name="set-embed-color", description="Set embed color (admin only)")
@app_commands.describe(color="Hex color code, e.g. #00ff99")
async def set_embed_color(interaction: discord.Interaction, color: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    # Simple hex color validation
    if not re.match(r"^#([A-Fa-f0-9]{6})$", color):
        await interaction.response.send_message("❌ Please provide a valid hex color code like #00ff99.", ephemeral=True)
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["embed_color"] = color
    save_data()
    await interaction.response.send_message(f"✅ Embed color set to {color}.")

@tree.command(name="set-background-url", description="Set background image URL for profile cards (admin only)")
@app_commands.describe(url="Image URL (must end with .png, .jpg, etc.)")
async def set_background_url(interaction: discord.Interaction, url: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    if not is_valid_image_url(url):
        await interaction.response.send_message("❌ Please provide a valid image URL ending with .png, .jpg, .jpeg, .gif, or .webp", ephemeral=True)
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["background_url"] = url
    save_data()
    await interaction.response.send_message("✅ Background image URL set.")

@tree.command(name="set-card-theme", description="Set card theme for profile cards (admin only)")
@app_commands.describe(theme="Theme name, e.g. default, dark, sunset")
async def set_card_theme(interaction: discord.Interaction, theme: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    allowed_themes = ["default", "dark", "sunset"]
    if theme.lower() not in allowed_themes:
        await interaction.response.send_message(f"❌ Invalid theme. Allowed: {', '.join(allowed_themes)}", ephemeral=True)
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["card_theme"] = theme.lower()
    save_data()
    await interaction.response.send_message(f"✅ Card theme set to {theme}.")

@tree.command(name="resetleveling", description="Completely reset leveling data for this server (admin only)")
async def resetleveling(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    if guild_id in xp_data:
        del xp_data[guild_id]
    if guild_id in config:
        # Reset config to default by removing
        del config[guild_id]
    save_data()
    await interaction.response.send_message("✅ Leveling data and config have been fully reset for this server.")

@tree.command(name="top", description="Show the top XP users in the server")
@app_commands.checks.has_permissions(manage_guild=True)
async def top(interaction: discord.Interaction):
    await interaction.response.defer()
    guild_id = str(interaction.guild.id)
    xp_data = load_xp_data()
    if guild_id not in xp_data:
        await interaction.followup.send("No XP data available for this server.")
        return

    members = xp_data[guild_id]
    sorted_members = sorted(members.items(), key=lambda x: x[1]["xp"], reverse=True)
    top_list = ""
    for i, (user_id, data) in enumerate(sorted_members[:10], start=1):
        user = interaction.guild.get_member(int(user_id))
        if user:
            top_list += f"**{i}. {user.display_name}** – XP: {data['xp']}, Level: {data['level']}\n"

    if not top_list:
        top_list = "No users with XP yet."

    embed = discord.Embed(
        title=f"🏆 Top 10 XP Users in {interaction.guild.name}",
        description=top_list,
        color=discord.Color.gold()
    )
    await interaction.followup.send(embed=embed)
# Flask keep_alive server for Render
app = Flask("")

@app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set.")
    else:
        bot.run(TOKEN)