import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import os
import json
from datetime import datetime

TOKEN = os.getenv("DISCORD_TOKEN")
GAMES_FILE = "games.json"
CONFIG_FILE = "config.json"
DATA_URL = "https://raw.githubusercontent.com/threethan/MetaMetadata/main/data/oculus/data.json"
UPDATE_ROLE_ID = 1538938602904485928
FOOTER_TEXT = "made by .cx"


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# =========================================================
# FILE UPLOAD TO CATBOX (permanent host, 200MB limit)
# =========================================================
async def upload_file(file_bytes, filename):
    form = aiohttp.FormData()
    form.add_field("reqtype", "fileupload")
    form.add_field("fileToUpload", file_bytes, filename=filename)
    async with aiohttp.ClientSession() as session:
        async with session.post("https://catbox.moe/user/api.php", data=form) as resp:
            text = await resp.text()
            if text.startswith("http"):
                return text.strip()
            raise Exception(f"upload failed: {text}")


# =========================================================
# /add dump
# =========================================================
@tree.group(name="add", description="Add a game or dump")
@app_commands.default_permissions(administrator=True)
async def add_group(interaction: discord.Interaction):
    pass


@add_group.command(name="dump", description="Add an IL2CPP dump for a game")
@app_commands.describe(
    game="Short name, lowercase, no spaces",
    display_name="Full display name",
    lib="libil2cpp.so file",
    metadata="global-metadata.dat file",
    unity="Unity version",
)
async def add_dump(
    interaction: discord.Interaction,
    game: str,
    display_name: str,
    lib: discord.Attachment,
    metadata: discord.Attachment,
    unity: str = "Unknown",
):
    await interaction.response.defer(ephemeral=True)

    try:
        lib_bytes = await lib.read()
        md_bytes = await metadata.read()

        lib_url = await upload_file(lib_bytes, f"{game}_libil2cpp.so")
        md_url = await upload_file(md_bytes, f"{game}_global-metadata.dat")
    except Exception as e:
        await interaction.followup.send(f"Upload failed: {e}", ephemeral=True)
        return

    games = load_json(GAMES_FILE, {})
    key = game.lower().strip()
    existing = games.get(key, {})

    games[key] = {
        "display_name": display_name,
        "lib": lib_url,
        "metadata": md_url,
        "unity": unity,
        "added": datetime.now().strftime("%Y-%m-%d"),
        "auto_track": existing.get("auto_track", False),
        "current_version": existing.get("current_version", None),
    }
    save_json(GAMES_FILE, games)

    await interaction.followup.send(
        f"Added dump for {display_name}.",
        ephemeral=True,
    )


@add_group.command(name="auto", description="Enable auto-update tracking for a game")
@app_commands.describe(game="Game key from /add dump")
async def add_auto(interaction: discord.Interaction, game: str):
    await interaction.response.defer(ephemeral=True)
    games = load_json(GAMES_FILE, {})
    key = game.lower().strip()

    if key not in games:
        await interaction.followup.send(f"Game {key} not found. Add a dump first.", ephemeral=True)
        return

    games[key]["auto_track"] = True
    save_json(GAMES_FILE, games)
    await interaction.followup.send(f"Auto-update enabled for {games[key]['display_name']}.", ephemeral=True)


# =========================================================
# /auto dump channel
# /auto update channel
# =========================================================
@tree.group(name="auto", description="Auto settings")
@app_commands.default_permissions(administrator=True)
async def auto_group(interaction: discord.Interaction):
    pass


@auto_group.command(name="dump", description="Set the channel where dumps get announced")
async def auto_dump(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = load_json(CONFIG_FILE, {})
    cfg["dump_channel"] = channel.id
    save_json(CONFIG_FILE, cfg)
    await interaction.response.send_message(f"Dump channel set to {channel.mention}.", ephemeral=True)


@auto_group.command(name="update", description="Set the channel where game updates get posted")
async def auto_update(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = load_json(CONFIG_FILE, {})
    cfg["update_channel"] = channel.id
    save_json(CONFIG_FILE, cfg)
    await interaction.response.send_message(f"Update channel set to {channel.mention}.", ephemeral=True)


# =========================================================
# /dump
# =========================================================
@tree.command(name="dump", description="Get the IL2CPP dump files for a game")
@app_commands.describe(game="Game key, e.g. bwah")
async def dump_cmd(interaction: discord.Interaction, game: str):
    games = load_json(GAMES_FILE, {})
    key = game.lower().strip()

    if key not in games:
        await interaction.response.send_message(
            f"No dump found for {game}. Use /games to see available games.",
            ephemeral=True,
        )
        return

    entry = games[key]

    embed = discord.Embed(
        title=entry.get("display_name", key),
        color=discord.Color.from_rgb(74, 74, 224),
    )
    embed.add_field(name="lib", value=f"[download]({entry['lib']})", inline=False)
    embed.add_field(name="globalmetadata", value=f"[download]({entry['metadata']})", inline=False)
    embed.add_field(name="unity", value=entry.get("unity", "Unknown"), inline=True)
    embed.add_field(name="added", value=entry.get("added", "Unknown"), inline=True)
    embed.set_footer(text=FOOTER_TEXT)

    await interaction.response.send_message(embed=embed)


# =========================================================
# /games
# =========================================================
@tree.command(name="games", description="List all available dumps")
async def games_cmd(interaction: discord.Interaction):
    games = load_json(GAMES_FILE, {})
    if not games:
        await interaction.response.send_message("No games available yet.", ephemeral=True)
        return

    lines = [f"{k} - {v.get('display_name', k)}" for k, v in sorted(games.items())]

    embed = discord.Embed(
        title=f"Available Dumps ({len(games)})",
        description="\n".join(lines),
        color=discord.Color.from_rgb(74, 74, 224),
    )
    embed.set_footer(text=FOOTER_TEXT)
    await interaction.response.send_message(embed=embed)


# =========================================================
# UPDATE TRACKER
# =========================================================
all_apps = []


async def fetch_apps():
    global all_apps
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(DATA_URL) as resp:
                if resp.status == 200:
                    all_apps = await resp.json()
                    print(f"Fetched {len(all_apps)} apps.")
                else:
                    print(f"Fetch failed: {resp.status}")
    except Exception as e:
        print(f"Fetch error: {e}")


@tasks.loop(minutes=30)
async def update_checker():
    print("Checking for updates...")
    await fetch_apps()

    cfg = load_json(CONFIG_FILE, {})
    update_channel_id = cfg.get("update_channel")
    if not update_channel_id:
        print("No update channel set.")
        return

    channel = bot.get_channel(update_channel_id)
    if not channel:
        print("Update channel not found.")
        return

    games = load_json(GAMES_FILE, {})
    apps_iter = all_apps.values() if isinstance(all_apps, dict) else all_apps

    changed = False

    for key, entry in games.items():
        if not entry.get("auto_track"):
            continue

        display_name = entry.get("display_name", key)
        stored_version = entry.get("current_version")

        for app in apps_iter:
            app_name = app.get("name", "")
            if app_name.lower() != display_name.lower():
                continue

            new_version = app.get("version")
            if not new_version:
                continue

            if stored_version is None:
                games[key]["current_version"] = new_version
                changed = True
                print(f"Baseline set for {display_name}: {new_version}")
                break

            if new_version != stored_version:
                embed = discord.Embed(
                    title="Update Tracker",
                    description="Update Detected",
                    color=discord.Color.from_rgb(74, 74, 224),
                )
                embed.add_field(name="Status", value="LIVE Build", inline=False)
                embed.add_field(name="Updated Version", value=f"`{new_version}`", inline=False)
                embed.add_field(name="Last Logged", value=f"`{stored_version}`", inline=False)
                embed.add_field(
                    name="Time of Release",
                    value=f"<t:{int(datetime.now().timestamp())}:F>",
                    inline=False,
                )

                if app.get("square"):
                    embed.set_thumbnail(url=app["square"])
                if app.get("landscape"):
                    embed.set_image(url=app["landscape"])

                embed.set_footer(text=FOOTER_TEXT)

                try:
                    await channel.send(
                        content=f"<@&{UPDATE_ROLE_ID}>",
                        embed=embed,
                    )
                    games[key]["current_version"] = new_version
                    changed = True
                    print(f"Update posted for {display_name}: {stored_version} -> {new_version}")
                except Exception as e:
                    print(f"Send failed: {e}")

            break

    if changed:
        save_json(GAMES_FILE, games)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync failed: {e}")
    update_checker.start()


if __name__ == "__main__":
    if not TOKEN:
        print("DISCORD_TOKEN not set.")
    else:
        bot.run(TOKEN)
