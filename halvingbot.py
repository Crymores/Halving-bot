from dateutil import parser, relativedelta
import discord
from discord.ext import tasks, commands
import requests
from datetime import datetime, timedelta
import json
import os
import time

TOKEN_DISCORD = 'token discord'
TOKEN_BLOCKCYPHER = 'token cypher'

BLOCKS_PER_HALVING = 210000
AVERAGE_BLOCK_TIME_MINUTES = 10
DATA_FILE = 'block_data.txt'
FETCH_INTERVAL_SECONDS = 3600 // 100  # Adapté pour la limite de 100 requêtes par heure
RESERVE_API_CALLS = 10
TOTAL_API_CALLS_ALLOWED = 90  # 100 - 10 reserved

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

status_toggle = True  # Commutateur pour alterner l'affichage du statut

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

def fetch_initial_block_data():
    # Fetch initial data for the last 6 blocks
    url = f"https://api.blockcypher.com/v1/btc/main"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        height = data['height']
        blocks = []
        for i in range(6):
            block_url = f"{url}/blocks/{height-i}?token={TOKEN_BLOCKCYPHER}"
            block_response = requests.get(block_url)
            if block_response.status_code == 200:
                block_data = block_response.json()
                blocks.append({'height': block_data['height'], 'time': block_data['time']})
        save_block_data(blocks)
    else:
        print(f"Erreur lors de la récupération de l'info de la blockchain: HTTP {response.status_code}")

@tasks.loop(seconds=FETCH_INTERVAL_SECONDS)
async def periodic_block_fetch():
    # Cette tâche devrait récupérer seulement le dernier bloc
    url = f"https://api.blockcypher.com/v1/btc/main"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        height = data['height']
        block_url = f"{url}/blocks/{height}?token={TOKEN_BLOCKCYPHER}"
        block_response = requests.get(block_url)
        if block_response.status_code == 200:
            block_data = block_response.json()
            save_block_data([{'height': block_data['height'], 'time': block_data['time']}])
        else:
            print(f"Failed to fetch the latest block data: HTTP {block_response.status_code}")
    else:
        print(f"Failed to fetch blockchain info: HTTP {response.status_code}")

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


@bot.event
async def on_ready():
    print(f'Connected as {bot.user.name}')
    fetch_initial_block_data()  # Perform an initial fetch of block data once
    update_status.start()
    periodic_block_fetch.start()
bot.run(TOKEN_DISCORD.strip())
