import discord from discord.ext import commands, tasks from discord import app_commands import asyncio import json import os

intents = discord.Intents.default() intents.message_content = True intents.guilds = True intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents) TREE = bot.tree

Global user stats

user_stats = {} RANKS = [ ("Recruit", 0), ("Private", 50), ("Gefreiter", 150), ("Corporal", 300), ("Master Corporal", 600), ("Sergeant", 1000), ("Staff Sergeant", 1600), ("Master Sergeant", 2300), ("First Sergeant", 3100), ("Sergeant Major", 4000), ("Warrant Officer 1", 5000), ("Warrant Officer 2", 6100), ("Warrant Officer 3", 7300), ("Warrant Officer 4", 8600), ("Warrant Officer 5", 10000), ("Third Lieutenant", 11500), ("Second Lieutenant", 13100), ("First Lieutenant", 14800), ("Captain", 16600), ("Major", 18500), ("Lieutenant Colonel", 20500), ("Colonel", 22600), ("Brigadier", 24800), ("Major General", 27100), ("Lieutenant General", 29500), ("General", 32000), ("Marshal", 34600), ("Commander", 37300), ("Commander 2nd rank", 40100), ("Commander 1st rank", 43000) ]

EMOJIS = {}

@bot.event async def on_ready(): print(f"Logged in as {bot.user}") await load_emojis() await TREE.sync()

async def load_emojis(): for guild in bot.guilds: for emoji in guild.emojis: EMOJIS[emoji.name] = str(emoji) print("Emojis loaded:", list(EMOJIS.keys()))

Load stats from file if exists

if os.path.exists("stats.json"): with open("stats.json", "r") as f: user_stats = json.load(f)

Save stats regularly

@tasks.loop(minutes=5) async def save_stats(): with open("stats.json", "w") as f: json.dump(user_stats, f)

save_stats.start()

@TREE.command(name="battle", description="Join a ProTanki battle and earn XP & crystals!") async def battle(interaction: discord.Interaction): user_id = str(interaction.user.id) if user_id not in user_stats: user_stats[user_id] = {"xp": 0, "crystals": 0}

user_stats[user_id]["xp"] += 100
user_stats[user_id]["crystals"] += 25

msg = f"🏆 You joined a battle! You earned 100 XP and 25 crystals."
await interaction.response.send_message(msg, ephemeral=True)

@TREE.command(name="rank", description="See your current rank and progress") async def rank(interaction: discord.Interaction): user_id = str(interaction.user.id) stats = user_stats.get(user_id, {"xp": 0, "crystals": 0}) xp = stats["xp"] current_rank = "Unranked" next_rank = "" for i in range(len(RANKS)): name, required = RANKS[i] if xp >= required: current_rank = name if i + 1 < len(RANKS): next_rank = RANKS[i + 1][0] + f" ({RANKS[i + 1][1] - xp} XP left)" else: break

emoji = EMOJIS.get(current_rank.lower().replace(" ", ""), "")
await interaction.response.send_message(
    f"{emoji} **{interaction.user.display_name}**\nRank: **{current_rank}**\nXP: `{xp}`\nCrystals: `{stats['crystals']}`\nNext Rank: `{next_rank}`",
    ephemeral=True
)

bot.run(os.getenv("TOKEN"))

