import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from keep_alive import keep_alive  # Flask keep-alive server

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Data stores (in-memory; for production use persistent DB or JSON)
level_data = {}        # {guild_id: {user_id: {"xp": int, "level": int}}}
leveling_enabled = {}  # {guild_id: bool}
level_channels = {}    # {guild_id: channel_id}
level_roles = {}       # {guild_id: {level: role_id}}
xp_per_message = {}    # {guild_id: xp_amount_per_msg}
user_cooldowns = {}    # {guild_id: {user_id: last_message_time}}

COOLDOWN_SECONDS = 30  # Cooldown between XP gains per user per server

def calculate_level(xp: int) -> int:
    # Simple leveling formula (can adjust as needed)
    return int(xp ** 0.5 // 10)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await tree.sync()
    print("Slash commands synced.")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    guild_id = message.guild.id
    user_id = message.author.id

    if not leveling_enabled.get(guild_id, False):
        return

    # Handle cooldown per user per guild
    user_cooldowns.setdefault(guild_id, {})
    last_time = user_cooldowns[guild_id].get(user_id, 0)
    now = asyncio.get_event_loop().time()
    if now - last_time < COOLDOWN_SECONDS:
        return
    user_cooldowns[guild_id][user_id] = now

    # Initialize data
    level_data.setdefault(guild_id, {})
    user_stats = level_data[guild_id].setdefault(user_id, {"xp": 0, "level": 0})

    # XP gain per message (default 10)
    xp_gain = xp_per_message.get(guild_id, 10)
    user_stats["xp"] += xp_gain

    new_level = calculate_level(user_stats["xp"])
    if new_level > user_stats["level"]:
        user_stats["level"] = new_level
        # Send level-up message
        channel_id = level_channels.get(guild_id)
        msg = f"🎉 {message.author.mention} leveled up to **level {new_level}**!"
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(msg)
            else:
                await message.channel.send(msg)
        else:
            await message.channel.send(msg)

        # Assign role if configured
        roles_for_guild = level_roles.get(guild_id, {})
        role_id = roles_for_guild.get(new_level)
        if role_id:
            role = message.guild.get_role(role_id)
            if role:
                try:
                    await message.author.add_roles(role)
                    await message.channel.send(f"🏅 {message.author.mention} received the role **{role.name}**!")
                except discord.Forbidden:
                    await message.channel.send("⚠️ I don't have permission to assign roles.")

@tree.command(name="rank", description="Show your level and XP")
async def rank(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    user_id = interaction.user.id
    user_stats = level_data.get(guild_id, {}).get(user_id)
    if not user_stats:
        await interaction.response.send_message("You have no XP yet.")
        return

    level = user_stats["level"]
    xp = user_stats["xp"]
    next_level_xp = ((level + 1) * 10) ** 2  # Reverse from formula for next level threshold
    percent = int((xp / next_level_xp) * 100) if next_level_xp else 100
    bar_length = 10
    filled_length = percent * bar_length // 100
    bar = "█" * filled_length + "—" * (bar_length - filled_length)

    await interaction.response.send_message(
        f"📊 **{interaction.user.display_name}'s Rank**\n"
        f"Level: **{level}**\n"
        f"XP: **{xp} / {next_level_xp}**\n"
        f"Progress: `{bar}` ({percent}%)"
    )

@tree.command(name="enable-leveling", description="Enable leveling system (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def enable_leveling(interaction: discord.Interaction):
    leveling_enabled[interaction.guild_id] = True
    await interaction.response.send_message("✅ Leveling enabled.")

@tree.command(name="disable-leveling", description="Disable leveling system (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def disable_leveling(interaction: discord.Interaction):
    leveling_enabled[interaction.guild_id] = False
    await interaction.response.send_message("⛔ Leveling disabled.")

@tree.command(name="set-level-channel", description="Set channel for level-up messages (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Channel to send level-up messages")
async def set_level_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    level_channels[interaction.guild_id] = channel.id
    await interaction.response.send_message(f"✅ Level-up messages will be sent in {channel.mention}.")

@tree.command(name="set-level-role", description="Assign a role at a specific level (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(level="Level number", role="Role to assign")
async def set_level_role(interaction: discord.Interaction, level: int, role: discord.Role):
    level_roles.setdefault(interaction.guild_id, {})
    level_roles[interaction.guild_id][level] = role.id
    await interaction.response.send_message(f"✅ Role {role.mention} will be given at level {level}.")

@tree.command(name="top", description="Show top 10 users by XP")
async def top(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    guild_data = level_data.get(guild_id, {})
    if not guild_data:
        await interaction.response.send_message("No XP data found.")
        return

    sorted_users = sorted(guild_data.items(), key=lambda item: item[1]["xp"], reverse=True)[:10]
    description = "\n".join(
        f"{i+1}. <@{user_id}> - Level {stats['level']} | XP {stats['xp']}"
        for i, (user_id, stats) in enumerate(sorted_users)
    )
    await interaction.response.send_message(f"🏆 **Top 10 users:**\n{description}")

@tree.command(name="xp", description="Check another user's XP")
@app_commands.describe(user="User to check")
async def xp(interaction: discord.Interaction, user: discord.User):
    guild_id = interaction.guild_id
    user_stats = level_data.get(guild_id, {}).get(user.id)
    if not user_stats:
        await interaction.response.send_message(f"{user.mention} has no XP.")
        return
    await interaction.response.send_message(
        f"{user.mention} is Level {user_stats['level']} with {user_stats['xp']} XP."
    )

@tree.command(name="reset-xp", description="Reset a user's XP (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="User to reset")
async def reset_xp(interaction: discord.Interaction, user: discord.User):
    guild_id = interaction.guild_id
    if user.id in level_data.get(guild_id, {}):
        level_data[guild_id][user.id] = {"xp": 0, "level": 0}
        await interaction.response.send_message(f"{user.mention}'s XP has been reset.")
    else:
        await interaction.response.send_message("That user has no XP.")

@tree.command(name="set-xp", description="Set a user's XP (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="User to set XP", amount="XP amount")
async def set_xp(interaction: discord.Interaction, user: discord.User, amount: int):
    guild_id = interaction.guild_id
    level_data.setdefault(guild_id, {})[user.id] = {"xp": amount, "level": calculate_level(amount)}
    await interaction.response.send_message(f"{user.mention}'s XP set to {amount}.")

@tree.command(name="help", description="Show bot commands list")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Level-Up Bot Commands:**\n"
        "• `/rank` — Show your level and XP\n"
        "• `/top` — Show top 10 users by XP\n"
        "• `/xp @user` — Show XP of another user\n"
        "• `/reset-xp @user` — Reset a user's XP (Admin only)\n"
        "• `/set-xp @user amount` — Set a user's XP (Admin only)\n"
        "• `/enable-leveling` — Enable leveling (Admin only)\n"
        "• `/disable-leveling` — Disable leveling (Admin only)\n"
        "• `/set-level-channel` — Set channel for level-up messages (Admin only)\n"
        "• `/set-level-role level @role` — Assign role at level (Admin only)\n"
        "• `/set-xp-rate amount` — Set XP per message (Admin only)\n"
    )

@tree.command(name="set-xp-rate", description="Set how much XP per message (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(amount="XP per message (default 10)")
async def set_xp_rate(interaction: discord.Interaction, amount: int):
    if amount < 0:
        await interaction.response.send_message("❌ XP amount must be zero or higher.")
        return
    xp_per_message[interaction.guild_id] = amount
    await interaction.response.send_message(f"✅ XP per message set to {amount}.")

if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not set.")
        exit(1)
    bot.run(TOKEN)