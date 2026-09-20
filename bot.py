import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from datetime import datetime

TOKEN = os.getenv("DISCORD_TOKEN")
GAMES_FILE = "games.json"

def load_games():
    if not os.path.exists(GAMES_FILE):
        return {}
    with open(GAMES_FILE, "r") as f:
        return json.load(f)

def save_games(games):
    with open(GAMES_FILE, "w") as f:
        json.dump(games, f, indent=4)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@tree.command(name="dump", description="Get the IL2CPP dump files for a game.")
@app_commands.describe(game="Game name, e.g. bwah")
async def dump(interaction: discord.Interaction, game: str):
    games = load_games()
    key = game.lower().strip()

    if key not in games:
        await interaction.response.send_message(
            f"No dump found for `{game}`. Use `/games` to see the list.",
            ephemeral=True
        )
        return

    entry = games[key]

    embed = discord.Embed(
        title=entry.get("display_name", game),
        description="IL2CPP files for dumping.",
        color=discord.Color.green()
    )
    embed.add_field(name="libil2cpp.so", value=f"[Download]({entry['lib']})", inline=False)
    embed.add_field(name="global-metadata.dat", value=f"[Download]({entry['metadata']})", inline=False)
    embed.add_field(name="Unity", value=entry.get("unity_version", "Unknown"), inline=True)
    embed.add_field(name="Added", value=entry.get("added", "Unknown"), inline=True)
    embed.set_footer(text="Envo Dumps")

    await interaction.response.send_message(embed=embed)

@tree.command(name="games", description="List all available game dumps.")
async def games_cmd(interaction: discord.Interaction):
    games = load_games()
    if not games:
        await interaction.response.send_message("No games available yet.", ephemeral=True)
        return

    lines = []
    for key in sorted(games.keys()):
        entry = games[key]
        lines.append(f"`{key}` — {entry.get('display_name', key)}")

    embed = discord.Embed(
        title=f"Available Dumps ({len(games)})",
        description="\n".join(lines),
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

@tree.command(name="addgame", description="[Admin] Add a game to the dump list.")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    key="Short name, e.g. bwah",
    display_name="Full name, e.g. Bwah - Grows Offline",
    lib_url="Direct link to libil2cpp.so",
    metadata_url="Direct link to global-metadata.dat",
    unity_version="Unity version (optional)"
)
async def addgame(
    interaction: discord.Interaction,
    key: str,
    display_name: str,
    lib_url: str,
    metadata_url: str,
    unity_version: str = "Unknown"
):
    games = load_games()
    games[key.lower().strip()] = {
        "display_name": display_name,
        "lib": lib_url,
        "metadata": metadata_url,
        "unity_version": unity_version,
        "added": datetime.now().strftime("%Y-%m-%d")
    }
    save_games(games)
    await interaction.response.send_message(f"Added `{key}`.", ephemeral=True)

@tree.command(name="removegame", description="[Admin] Remove a game from the dump list.")
@app_commands.default_permissions(administrator=True)
async def removegame(interaction: discord.Interaction, key: str):
    games = load_games()
    if key.lower().strip() in games:
        del games[key.lower().strip()]
        save_games(games)
        await interaction.response.send_message(f"Removed `{key}`.", ephemeral=True)
    else:
        await interaction.response.send_message(f"`{key}` not found.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    if not TOKEN:
        print("DISCORD_TOKEN not set.")
    else:
        bot.run(TOKEN)
