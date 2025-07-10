import discord
from discord.ext import commands
from discord import app_commands
import random, json, os

from rank_data import RANKS
from emojis import EMOJIS
from keep_alive import keep_alive

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DATA_FILE = "database.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

users = load_data()

def get_rank(xp):
    for rank, req_xp, emoji_id in reversed(RANKS):
        if xp >= req_xp:
            return rank, req_xp, emoji_id
    return RANKS[0]

@tree.command(name="register", description="Register to play ProTanki")
async def register(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id in users:
        await interaction.response.send_message("You are already registered.", ephemeral=True)
        return
    users[user_id] = {"xp": 0, "crystals": 0, "goldboxes": 0}
    save_data(users)
    await interaction.response.send_message("✅ Registered! Use `/play` to start battling.", ephemeral=True)

@tree.command(name="play", description="Play a battle and earn XP/crystals")
async def play(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in users:
        await interaction.response.send_message("❌ You need to `/register` first.", ephemeral=True)
        return

    xp_gain = random.randint(100, 300)
    crystal_gain = random.randint(50, 150)
    got_goldbox = random.random() < 0.05

    users[user_id]["xp"] += xp_gain
    users[user_id]["crystals"] += crystal_gain
    if got_goldbox:
        users[user_id]["goldboxes"] += 1

    save_data(users)

    rank, _, emoji_id = get_rank(users[user_id]["xp"])
    embed = discord.Embed(title="🔫 Battle Result", color=0xFFD700)
    embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
    embed.add_field(name="Rank", value=f"<:{rank}:{emoji_id}> `{rank.title()}`", inline=True)
    embed.add_field(name="XP Gained", value=f"`+{xp_gain}`", inline=True)
    embed.add_field(name="Crystals", value=f"{EMOJIS['crystals']} +{crystal_gain}", inline=True)
    if got_goldbox:
        embed.add_field(name="🎉 Jackpot!", value=f"You caught a {EMOJIS['goldbox']} gold box!", inline=False)

    await interaction.response.send_message(embed=embed)

@tree.command(name="profile", description="View your profile")
async def profile(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in users:
        await interaction.response.send_message("❌ You need to `/register` first.", ephemeral=True)
        return

    data = users[user_id]
    rank, req_xp, emoji_id = get_rank(data["xp"])
    next_rank = next((r for r in RANKS if r[1] > data["xp"]), None)

    embed = discord.Embed(title="📜 Your Profile", color=0x00BFFF)
    embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
    embed.add_field(name="Rank", value=f"<:{rank}:{emoji_id}> `{rank.title()}`", inline=True)
    embed.add_field(name="XP", value=f"{data['xp']:,}", inline=True)
    embed.add_field(name="Crystals", value=f"{EMOJIS['crystals']} `{data['crystals']}`", inline=True)
    embed.add_field(name="Gold Boxes", value=f"{EMOJIS['goldbox']} `{data['goldboxes']}`", inline=True)

    if next_rank:
        needed = next_rank[1] - data["xp"]
        embed.set_footer(text=f"Next rank: {next_rank[0].title()} in {needed:,} XP")
    else:
        embed.set_footer(text="Max rank reached!")

    await interaction.response.send_message(embed=embed)

@tree.command(name="leaderboard", description="Top players")
async def leaderboard(interaction: discord.Interaction):
    top = sorted(users.items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    desc = ""
    for i, (uid, data) in enumerate(top, start=1):
        rank, _, emoji_id = get_rank(data["xp"])
        member = await interaction.guild.fetch_member(int(uid))
        desc += f"**{i}.** {member.mention} — <:{rank}:{emoji_id}> `{data['xp']}` XP\n"

    embed = discord.Embed(title="🏆 XP Leaderboard", description=desc or "No players yet.", color=0xFFD700)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")

keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))