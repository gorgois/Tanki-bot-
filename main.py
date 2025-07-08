import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import os
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

XP_FILE = "xp_data.json"
CONFIG_FILE = "config.json"

xp_data = {}
config = {}

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

def save_data():
    with open(XP_FILE, "w") as f:
        json.dump(xp_data, f)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

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
            "profile_bg": None
        }
    return config[guild_id]

@bot.event
async def on_ready():
    load_data()
    await tree.sync()
    print(f"Logged in as {bot.user}.")
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
    # Example list - you can add URLs here
    backgrounds = {
        "Default": "https://i.imgur.com/TP3E2Ch.png",
        "Dark": "https://i.imgur.com/8f7Q9nr.png",
        "Sunset": "https://i.imgur.com/r3fLMKt.png"
    }
    msg = "Available backgrounds:\n"
    for name, url in backgrounds.items():
        msg += f"**{name}**: {url}\n"
    await interaction.response.send_message(msg)

@tree.command(name="set-profile-bg", description="Set profile background URL")
@app_commands.describe(url="Image URL for profile background")
async def set_profile_bg(interaction: discord.Interaction, url: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
        return
    settings = get_xp_settings(interaction.guild.id)
    settings["profile_bg"] = url
    save_data()
    await interaction.response.send_message("✅ Profile background set!")

@tree.command(name="toggle-dms", description="Toggle DM level-up messages")
@app_commands.describe(enabled="True to enable, False to disable")
async def toggle_dms(interaction: discord.Interaction, enabled: bool):
    settings = get_xp_settings(interaction.guild.id)
    settings["dm_enabled"] = enabled
    save_data()
    await interaction.response.send_message(f"✅ DM level-up messages {'enabled' if enabled else 'disabled'}.")

@tree.command(name="top", description="Show top 10 users by XP")
async def top(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id not in xp_data or not xp_data[guild_id]:
        await interaction.response.send_message("No XP data available.")
        return
    sorted_users = sorted(xp_data[guild_id].items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    description = ""
    for i, (user_id, data) in enumerate(sorted_users, 1):
        user = interaction.guild.get_member(int(user_id))
        name = user.display_name if user else f"User ID {user_id}"
        description += f"{i}. {name} — Level {data['level']} ({data['xp']} XP)\n"
    embed = discord.Embed(title="Top 10 XP Leaders", description=description, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@tree.command(name="help", description="Show list of bot commands")
async def help_command(interaction: discord.Interaction):
    help_text = (
        "**Level-Up Bot Commands:**\n"
        "• `/rank` — Show your level and XP\n"
        "• `/xp @user` — Show XP of another user\n"
        "• `/top` — Show top 10 users by XP\n"
        "• `/leaderboard-range start end` — Show leaderboard slice\n"
        "• `/next-level` — XP needed for next level\n"
        "• `/add-role-level level @role` — Assign role at level (Admin)\n"
        "• `/remove-role-level level` — Remove role reward (Admin)\n"
        "• `/levels` — List level-role rewards\n"
        "• `/set-level-channel #channel` — Set level-up messages channel (Admin)\n"
        "• `/enable-leveling` — Enable leveling (Admin)\n"
        "• `/disable-leveling` — Disable leveling (Admin)\n"
        "• `/set-xp-rate amount` — XP per message (Admin)\n"
        "• `/set-xp-cooldown seconds` — XP cooldown in seconds (Admin)\n"
        "• `/set-xp @user amount` — Set user XP (Admin)\n"
        "• `/reset-xp @user` — Reset user XP (Admin)\n"
        "• `/daily` — Claim daily XP bonus\n"
        "• `/bonus-xp @user amount` — Grant bonus XP (Admin)\n"
        "• `/profile` — Show your profile card\n"
        "• `/bg-list` — List profile backgrounds\n"
        "• `/set-profile-bg url` — Set profile background (Admin)\n"
        "• `/toggle-dms true/false` — Enable/disable DM level-up msgs\n"
        "• `/help` — Show this help message\n"
    )
    await interaction.response.send_message(help_text)

# Run bot
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("Error: DISCORD_BOT_TOKEN env variable not set.")
        exit(1)
    bot.run(TOKEN)