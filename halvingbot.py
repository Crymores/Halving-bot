import os
import json
from datetime import datetime, timedelta
from dateutil import parser, relativedelta
import discord
from discord.ext import tasks, commands
import aiohttp


TOKEN_DISCORD = 'ton token discord'
TOKEN_BLOCKCYPHER = 'votre token'

BLOCKS_PER_HALVING = 210000
AVERAGE_BLOCK_TIME_MINUTES = 10
DATA_FILE = 'block_data.txt'
FETCH_INTERVAL_SECONDS = 3600 // 100
RESERVE_API_CALLS = 10
TOTAL_API_CALLS_ALLOWED = 90

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

status_toggle = True

async def fetch(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

def load_or_initialize_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as file:
            json.dump([], file)
    try:
        with open(DATA_FILE, 'r') as file:
            return json.load(file)
    except json.JSONDecodeError:
        return []

def save_block_data(blocks):
    with open(DATA_FILE, 'w') as file:
        json.dump(blocks, file)

async def fetch_initial_block_data():
    url = f"https://api.blockcypher.com/v1/btc/main"
    data = await fetch(url)
    if 'height' in data:
        height = data['height']
        blocks = []
        for i in range(6):
            block_url = f"{url}/blocks/{height-i}?token={TOKEN_BLOCKCYPHER}"
            block_data = await fetch(block_url)
            if 'height' in block_data:
                blocks.append({'height': block_data['height'], 'time': block_data['time']})
        save_block_data(blocks)
    else:
        print("Erreur lors de la récupération de l'info de la blockchain.")

@tasks.loop(seconds=FETCH_INTERVAL_SECONDS)
async def periodic_block_fetch():
    url = f"https://api.blockcypher.com/v1/btc/main"
    data = await fetch(url)
    if 'height' in data:
        height = data['height']
        block_url = f"{url}/blocks/{height}?token={TOKEN_BLOCKCYPHER}"
        block_data = await fetch(block_url)
        if 'height' in block_data:
            save_block_data([{'height': block_data['height'], 'time': block_data['time']}])
        else:
            print("Failed to fetch the latest block data.")
    else:
        print("Failed to fetch blockchain info.")

def calculate_halving_estimate():
    data = load_or_initialize_data()
    if data:
        latest_block = data[-1]  # Prendre le dernier bloc enregistré
        current_block_height = latest_block['height']
        blocks_remaining = BLOCKS_PER_HALVING - (current_block_height % BLOCKS_PER_HALVING)
        
        # Suppose un temps moyen de génération des blocs de 10 minutes
        average_block_time_minutes = AVERAGE_BLOCK_TIME_MINUTES
        
        seconds_until_halving = blocks_remaining * average_block_time_minutes * 60
        halving_estimate = datetime.utcnow() + timedelta(seconds=seconds_until_halving)
        
        return halving_estimate
    return None


@tasks.loop(seconds=45)
async def update_status():
    global status_toggle
    data = load_or_initialize_data()
    if data:
        latest_block = data[-1]  # Prendre le dernier bloc enregistré
        current_block_height = latest_block['height']
        blocks_remaining = BLOCKS_PER_HALVING - (current_block_height % BLOCKS_PER_HALVING)
        
        # Calcule le temps moyen de génération des blocs à partir des données enregistrées
        if len(data) >= 2:
            timestamps = [parser.parse(block['time']) for block in data[-2:]]
            average_block_time_seconds = (timestamps[-1] - timestamps[-2]).total_seconds()
        else:
            average_block_time_seconds = AVERAGE_BLOCK_TIME_MINUTES * 60  # Utilisez 10 minutes par défaut
        
        seconds_until_halving = blocks_remaining * average_block_time_seconds
        halving_estimate = datetime.utcnow() + timedelta(seconds=seconds_until_halving)
        
        if status_toggle:
            # Affichage de la date du halving
            status_message = f"📅{halving_estimate.strftime('%d-%m-%Y')} 📆"
        else:
            # Affichage du compte à rebours
            now = datetime.utcnow()
            rdelta = relativedelta.relativedelta(halving_estimate, now)
            status_message = f"⏳{rdelta.years * 365 + rdelta.months * 30 + rdelta.days} days, {rdelta.hours} hours, {rdelta.minutes} minutes ⌛"
        
        await bot.change_presence(activity=discord.Game(name=status_message))
        print(f"Statut mis à jour : {status_message}")
        status_toggle = not status_toggle
    else:
        print("Aucune donnée de bloc disponible pour calculer l'estimation du halving.")

alert_sent = False  # Ajoutez cette variable globale pour suivre si l'alerte a été envoyée

async def send_halving_alert():
    global alert_sent
    if not alert_sent:
        for guild in bot.guilds:  # Parcourir chaque serveur où le bot est membre
            for channel in guild.text_channels:  # Parcourir chaque salon texte du serveur
                if channel.permissions_for(guild.me).send_messages and channel.permissions_for(guild.me).attach_files:
                    # Si le bot a les permissions nécessaires, envoyer l'alerte
                    message = "@everyone L alerte halving Bitcoin ! Moins de 24 heures restantes !"
                    file = discord.File('https://github.com/Crymores/Halving-bot/blob/main/halvinggg.jpg?raw=true', filename='image.jpg')
                    await channel.send(message, file=file)
                    alert_sent = True  # Marquer que l'alerte a été envoyée
                    return  # Arrêter après avoir envoyé l'alerte pour éviter les doublons
        print("Aucun salon trouvé avec les permissions nécessaires.")

@tasks.loop(seconds=3600)  # Vous pouvez ajuster cette fréquence selon vos besoins
async def halving_alert_check():
    halving_estimate = calculate_halving_estimate()
    if halving_estimate:
        now = datetime.utcnow()
        time_until_halving = halving_estimate - now
        if time_until_halving.total_seconds() <= 86400:  # 86400 secondes = 24 heures
            await send_halving_alert()

@bot.event
async def on_ready():
    print(f'Connected as {bot.user.name}')
    fetch_initial_block_data()  # Perform an initial fetch of block data once
    update_status.start()
    periodic_block_fetch.start()
    halving_alert_check.start()
bot.run(TOKEN_DISCORD.strip())
