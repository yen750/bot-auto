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
STATE_FILE = "state.json"

# CHANGE THIS: replace YOUR_USERNAME with your github username
VERSIONS_URL = "https://raw.githubusercontent.com/yen750/bot-auto/main/versions.json"

UPDATE_ROLE_ID = 1538938602904485928
FOOTER_TEXT = "made by .cx"

ALLOWED_USERS = {1537176834708602889, 1399841773555023893}

GUILD_ID = 1536788735616876698


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


async def only_allowed(interaction: discord.Interaction) -> bool:
    if interaction.user.id not in ALLOWED_USERS:
        try:
            if interaction.response.is_done():
                await interaction.followup.send("You are not allowed to use this bot.", ephemeral=True)
            else:
                await interaction.response.send_message("You are not allowed to use this bot.", ephemeral=True)
        except Exception:
            pass
        return False
    return True


tree.interaction_check = only_allowed


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


add_group = app_commands.Group(name="add", description="Add a game or dump")
auto_group = app_commands.Group(name="auto", description="Auto settings")


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
    }
    save_json(GAMES_FILE, games)
    await interaction.followup.send(f"Added dump for {display_name}.", ephemeral=True)


@add_group.command(name="auto", description="Enable auto-update tracking for a game")
@app_commands.describe(game="Game key matching a key in versions.json")
async def add_auto(interaction: discord.Interaction, game: str):
    await interaction.response.defer(ephemeral=True)
    games = load_json(GAMES_FILE, {})
    key = game.lower().strip()

    if key not in games:
        await interaction.followup.send(f"Game {key} not found. Add a dump first.", ephemeral=True)
        return

    games[key]["auto_track"] = True
    save_json(GAMES_FILE, games)
    await interaction.followup.send(
        f"Auto-update enabled for {games[key]['display_name']}. Make sure '{key}' exists in versions.json.",
        ephemeral=True,
    )


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


tree.add_command(add_group)
tree.add_command(auto_group)


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


async def fetch_versions():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(VERSIONS_URL) as resp:
                if resp.status == 200:
                    return await resp.json()
                print(f"Versions fetch failed: {resp.status}")
    except Exception as e:
        print(f"Versions fetch error: {e}")
    return {}


@tasks.loop(minutes=30)
async def update_checker():
    print("Checking for updates...")

    cfg = load_json(CONFIG_FILE, {})
    update_channel_id = cfg.get("update_channel")
    if not update_channel_id:
        print("No update channel set.")
        return

    channel = bot.get_channel(update_channel_id)
    if not channel:
        print("Update channel not found.")
        return

    versions = await fetch_versions()
    if not versions:
        print("No versions returned.")
        return

    state = load_json(STATE_FILE, {})
    games = load_json(GAMES_FILE, {})
    changed = False

    for key, entry in games.items():
        if not entry.get("auto_track"):
            continue

        remote = versions.get(key)
        if not remote:
            continue

        new_version = remote.get("version")
        if not new_version:
            continue

        last = state.get(key)

        if last is None:
            state[key] = new_version
            changed = True
            print(f"Baseline set for {key}: {new_version}")
            continue

        if new_version != last:
            embed = discord.Embed(
                title="Update Tracker",
                description="Update Detected",
                color=discord.Color.from_rgb(74, 74, 224),
            )
            embed.add_field(name="Status", value="LIVE Build", inline=False)
            embed.add_field(name="Updated Version", value=f"`{new_version}`", inline=False)
            embed.add_field(name="Last Logged", value=f"`{last}`", inline=False)
            embed.add_field(
                name="Time of Release",
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=False,
            )

            square = remote.get("square", "")
            landscape = remote.get("landscape", "")
            if square:
                embed.set_thumbnail(url=square)
            if landscape:
                embed.set_image(url=landscape)

            embed.set_footer(text=FOOTER_TEXT)

            try:
                await channel.send(
                    content=f"<@&{UPDATE_ROLE_ID}>",
                    embed=embed,
                )
                state[key] = new_version
                changed = True
                print(f"Update posted for {key}: {last} -> {new_version}")
            except Exception as e:
                print(f"Send failed: {e}")

    if changed:
        save_json(STATE_FILE, state)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    guild_obj = discord.Object(id=GUILD_ID)
    try:
        synced = await tree.sync(guild=guild_obj)
        print(f"Synced {len(synced)} commands to guild {GUILD_ID}.")
    except Exception as e:
        print(f"Sync failed: {e}")
    update_checker.start()


if __name__ == "__main__":
    if not TOKEN:
        print("DISCORD_TOKEN not set.")
    else:
        bot.run(TOKEN)
