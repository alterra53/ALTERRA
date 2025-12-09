# alterra_bot.py
# Requirements:
#   pip install discord.py python-dotenv

import os
import json
import logging
from pathlib import Path
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# -----------------------
# CONFIG / LOGGING
# -----------------------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN nincs beállítva az env-ben.")

CONFIG_PATH = Path("guild_config.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("alterra_bot")

# -----------------------
# Helper: load / save config
# -----------------------
def load_config():
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.exception("Hiba a config betöltésénél:")
    return {}

def save_config(cfg: dict):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        log.exception("Hiba a config mentésénél:")

config = load_config()  # structure: { "<guild_id>": {"channel_id": 123, "role_id": 456} }

# -----------------------
# Bot + intents
# -----------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # szükséges lesz role assignhoz később
# message_content nem szükséges slash parancsokhoz

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# -----------------------
# Utility guards
# -----------------------
def is_guild_admin(interaction: discord.Interaction) -> bool:
    try:
        return interaction.user.guild_permissions.administrator
    except Exception:
        return False

# -----------------------
# Views / Buttons
# -----------------------
class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.primary, custom_id="alterra_verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # jelenleg csak ephemer üzenet — később ide jön a link / logika
            await interaction.response.send_message("Well done.", ephemeral=True)
            log.info(f"User {interaction.user} clicked verify in guild {interaction.guild_id}")
        except Exception as e:
            log.exception("Hiba a verify gomb callbackben:")
            try:
                await interaction.response.send_message("Hiba történt. Ellenőrizd a logot.", ephemeral=True)
            except Exception:
                pass

# -----------------------
# Slash commands
# -----------------------
@tree.command(name="setup-channel", description="Beállítja a jelenlegi csatornát a verification üzenethez (admin only).")
async def setup_channel(interaction: discord.Interaction):
    if not is_guild_admin(interaction):
        await interaction.response.send_message("Ehhez nincs jogosultságod (Admin required).", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    channel_id = interaction.channel.id

    cfg = config.get(guild_id, {})
    cfg["channel_id"] = channel_id
    config[guild_id] = cfg
    save_config(config)

    await interaction.response.send_message(f"Setup: verification channel beállítva erre a csatornára (ID: {channel_id}).", ephemeral=True)
    log.info(f"Guild {guild_id}: channel set to {channel_id} by {interaction.user}")

@tree.command(name="setup-role", description="Beállítja a szerepet, amit a felhasználó kap verifikáció után (admin only).")
@app_commands.describe(role="Válaszd ki a szerepet, amit kiosztunk verifikáció után.")
async def setup_role(interaction: discord.Interaction, role: discord.Role):
    if not is_guild_admin(interaction):
        await interaction.response.send_message("Ehhez nincs jogosultságod (Admin required).", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    cfg = config.get(guild_id, {})
    cfg["role_id"] = role.id
    config[guild_id] = cfg
    save_config(config)

    await interaction.response.send_message(f"Setup: verified role beállítva erre: {role.name} (ID: {role.id}).", ephemeral=True)
    log.info(f"Guild {guild_id}: role set to {role.id} by {interaction.user}")

@tree.command(name="setup-verify", description="Létrehozza a verification embedet és a Verify gombot az előre beállított csatornában. (admin only)")
async def setup_verify(interaction: discord.Interaction):
    if not is_guild_admin(interaction):
        await interaction.response.send_message("Ehhez nincs jogosultságod (Admin required).", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    cfg = config.get(guild_id, {})

    channel_id = cfg.get("channel_id")
    if not channel_id:
        await interaction.response.send_message("Nincs beállítva verification channel. Használd előbb a /setup-channel parancsot.", ephemeral=True)
        return

    channel = interaction.guild.get_channel(channel_id)
    if channel is None:
        await interaction.response.send_message("A beállított csatorna nem található. Ellenőrizd a /setup-channel használatát.", ephemeral=True)
        return

    # Embed stílus — Alterra stílus: hivatalos, narancs
    orange = 0xFFA500
    embed = discord.Embed(
        title="Alterra Verification",
        description="Please complete this verification in order to be a member of the server.",
        color=orange
    )
    embed.set_footer(text="Alterra • Be safe. Be verified.")

    view = VerificationView()
    try:
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Verification message sikeresen elküldve: {channel.mention}", ephemeral=True)
        log.info(f"Guild {guild_id}: verification embed sent to channel {channel_id} by {interaction.user}")
    except Exception:
        log.exception("Hiba az embed küldésekor:")
        await interaction.response.send_message("Hiba történt az üzenet küldésekor. Ellenőrizd a bot jogosultságait és a logot.", ephemeral=True)

# -----------------------
# Admin helper: show config
# -----------------------
@tree.command(name="setup-show", description="Megmutatja a jelenlegi setup beállításokat (admin only).")
async def setup_show(interaction: discord.Interaction):
    if not is_guild_admin(interaction):
        await interaction.response.send_message("Ehhez nincs jogosultságod (Admin required).", ephemeral=True)
        return
    guild_id = str(interaction.guild_id)
    cfg = config.get(guild_id)
    if not cfg:
        await interaction.response.send_message("Nincsenek beállítások ennél a guildnél.", ephemeral=True)
        return
    channel = f"<#{cfg.get('channel_id')}>" if cfg.get('channel_id') else "nincs"
    role = f"<@&{cfg.get('role_id')}>" if cfg.get('role_id') else "nincs"
    await interaction.response.send_message(f"Channel: {channel}\nRole: {role}", ephemeral=True)

# -----------------------
# Events: ready + sync commands to guilds where present
# -----------------------
@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    # sync commands to each guild (immediate availability)
    try:
        for guild in bot.guilds:
            try:
                await tree.sync(guild=guild)
                log.info(f"Slash commands synced for guild {guild.id}")
            except Exception:
                log.exception(f"Sync hiba guild {guild.id}")
        # also sync globally as fallback (may be slow)
        try:
            await tree.sync()
            log.info("Global slash commands synced")
        except Exception:
            log.exception("Global sync failure")
    except Exception:
        log.exception("HIBA on_ready sync közben")

# -----------------------
# Optional: detect when bot added to new guild — sync there immediately
# -----------------------
@bot.event
async def on_guild_join(guild):
    log.info(f"Joined guild {guild.id}. Syncing commands...")
    try:
        await tree.sync(guild=guild)
        log.info(f"Synced for guild {guild.id}")
    except Exception:
        log.exception(f"Failed to sync for guild {guild.id}")

# -----------------------
# Error handling for app commands
# -----------------------
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    log.exception(f"App command error for {interaction.command_name if interaction else 'unknown'}: {error}")
    try:
        await interaction.response.send_message("Hiba a parancs futtatása közben. Ellenőrizd a logot.", ephemeral=True)
    except Exception:
        pass

# -----------------------
# Keepalive: optional import if present (keeps container alive on Render)
# place a keepalive.py in repo or rely on Render's web service settings
# -----------------------
try:
    import keepalive  # type: ignore
    try:
        keepalive.keep_alive()  # if keepalive.py exposes keep_alive()
        log.info("keepalive module invoked")
    except Exception:
        log.info("keepalive module found but failed to run keep_alive()")
except Exception:
    log.info("No keepalive module found — ok on Render web service")

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception:
        log.exception("Bot leállt kivétellel:")
