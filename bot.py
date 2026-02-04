import discord
from discord.ext import commands, tasks
import feedparser
import requests
import json
import os
import re
import random
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==================== BOT CONFIGURATION ====================
TOKEN = os.getenv("DISCORD_TOKEN")
ALERTS_CHANNEL_ID = int(os.getenv("ALERTS_CHANNEL_ID", 0))
PRICE_CHANNEL_ID = int(os.getenv("PRICE_CHANNEL_ID", 0))
NEWS_CHANNEL_ID = int(os.getenv("NEWS_CHANNEL_ID", 0))
CHAT_CHANNEL_ID = int(os.getenv("CHAT_CHANNEL_ID", 0))

# Validate required token
if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env")

# Bot setup - DISABLE BUILT-IN HELP COMMAND
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ==================== FILES & CONSTANTS ====================
ALERTS_FILE = 'crypto_alerts.json'
COIN_LIST_FILE = 'coingecko_coins.json'
COIN_LIST_REFRESH_HOURS = int(os.getenv("COIN_LIST_REFRESH_HOURS", 24))
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 60))
TOP_N = int(os.getenv("TOP_N", 20))

# ==================== GLOBAL VARIABLES ====================
coin_cache = {'by_id': {}, 'by_symbol': {}, 'by_name': {}, 'all_coins': []}
coin_list_last_updated = None
posted_news = set()
auto_price_message = None

# ==================== COIN SUPPORT ====================
COINS = {
    "btc": "bitcoin",
    "eth": "ethereum", 
    "xrp": "ripple",
    "sol": "solana",
    "bnb": "binancecoin",
    "doge": "dogecoin",
    "shib": "shiba-inu",
    "ada": "cardano",
    "link": "chainlink"
}

# Coin names for display
COIN_NAMES = {
    "btc": "Bitcoin",
    "eth": "Ethereum", 
    "xrp": "Ripple",
    "sol": "Solana",
    "bnb": "Binance Coin",
    "doge": "Dogecoin",
    "shib": "Shiba Inu",
    "ada": "Cardano",
    "link": "Chainlink"
}

# ==================== ENHANCED CHAT RESPONSES ====================
CHAT_REPLIES = [
    # ENTHUSIASTIC RESPONSES
    "TO THE MOON! Lets goooo!",
    "LFG! Crypto is pumping!",
    "DIAMOND HANDS! HODL strong!",
    "THIS IS THE WAY! Crypto never sleeps!",
    "BULLISH AF! Markets looking good!",
    
    # COOL RESPONSES
    "Smooth moves! Whats your next play?",
    "King/Queen of crypto! I see you!",
    "Based! You know whats up!",
    "Alpha detected! Share your wisdom!",
    "Big brain energy! Love the discussion!",
    
    # TRADING TALK
    "BUY THE DIP! Opportunity knocks!",
    "NOT FINANCIAL ADVICE but... I like the stock!",
    "PROFITS ARE COMING! Stay patient!",
    "RISK MANAGEMENT! Protect your capital!",
    "CRYPTO ROLLERCOASTER! Enjoy the ride!",
    
    # TECH TALK
    "SECURITY FIRST! Keep those keys safe!",
    "LIGHTNING FAST! Crypto moving at lightspeed!",
    "WEB3 IS HERE! Future is decentralized!",
    "SMART CONTRACTS! Code is law!",
    "GM! Good morning, degenerates!",
    
    # FUN RESPONSES
    "WEN LAMB0? Soon my friend, soon!",
    "APES TOGETHER STRONG!",
    "PAMP IT! Colors are green!",
    "GAME ON! Time to make moves!",
    "PARTY TIME! Crypto party never ends!",
    
    # SUPPORTIVE
    "YOU GOT THIS! Believe in yourself!",
    "COMMUNITY STRONG! Were in this together!",
    "SHINE BRIGHT! Your portfolio will thank you!",
    "MAGIC HAPPENING! Crypto miracles every day!",
    "CELEBRATE WINS! Big or small!"
]

# Crypto keywords that trigger responses (expanded)
CRYPTO_KEYWORDS = {
    # Bitcoin related
    'bitcoin': ['🚀', '💎', '👑', '⚡'],
    'btc': ['💰', '🎯', '🔥', '👑'],
    
    # Ethereum related  
    'ethereum': ['🌐', '🤖', '💻', '⚡'],
    'eth': ['🔵', '🌙', '🚀', '💎'],
    
    # Solana related
    'solana': ['⚡', '🚀', '🔥', '💨'],
    'sol': ['🔥', '⚡', '🚀', '🎯'],
    
    # General trading
    'pump': ['🚀', '📈', '🎉', '🔥'],
    'dump': ['📉', '😢', '💎', '🛡️'],
    'moon': ['🌙', '🚀', '🪐', '✨'],
    'hodl': ['💎', '🤲', '🛡️', '🎯'],
    'bullish': ['📈', '🐂', '🚀', '💪'],
    'bearish': ['📉', '🐻', '🛡️', '💎'],
    
    # Emotions
    'lfg': ['🔥', '🚀', '🎉', '💪'],
    'gm': ['🌅', '☕', '👋', '✨'],
    'gn': ['🌙', '😴', '✨', '💤'],
    
    # Actions
    'buy': ['🛒', '💰', '🎯', '📈'],
    'sell': ['💸', '📉', '🎯', '⚡'],
    'trade': ['⚡', '📊', '🎮', '💎']
}

# ==================== FUNNY PRICE REACTIONS ====================
PRICE_REACTIONS = {
    'big_pump': [
        "ROCKET LAUNCH DETECTED! To the moon we go!",
        "PUMP IT! Someones getting rich today!",
        "DIAMOND HANDS PAYING OFF! Congrats!",
        "PARTY TIME! Green candles everywhere!",
        "STONKS ONLY GO UP! This is the way!"
    ],
    'big_dump': [
        "RUG PULL? Just kidding... maybe?",
        "DIAMOND HANDS TEST! Stay strong!",
        "DEFENSE MODE! Protect your capital!",
        "PAIN IS TEMPORARY! HODL through it!",
        "ROLLERCOASTER RIDE! Crypto things!"
    ],
    'stable': [
        "CHILLING! Market taking a breather!",
        "SLEEPY MARKETS! Waiting for action!",
        "ACCUMULATION PHASE! Smart money loading!",
        "CALM BEFORE STORM! Somethings brewing!",
        "ZEN MODE! Everything balanced!"
    ]
}

# ==================== DATA FUNCTIONS ====================
def get_top_coins(n=TOP_N):
    """Fetch top N coins by 24h quote volume from MEXC."""
    try:
        url = "https://api.mexc.com/api/v3/ticker/24hr"
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list):
            return {}
        sorted_data = sorted(data, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)[:n]
        top_coins = {item["symbol"].replace("USDT", ""): item["symbol"] 
                    for item in sorted_data if "USDT" in item["symbol"]}
        return top_coins
    except Exception as e:
        logging.error(f"Error fetching top coins from MEXC: {e}")
        return {}

def load_alerts():
    """Load existing alerts from file."""
    try:
        with open(ALERTS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_alerts(alerts):
    """Save alerts to file."""
    with open(ALERTS_FILE, 'w') as f:
        json.dump(alerts, f, indent=4)

def get_all_coingecko_coins(force_refresh=False):
    """Fetch and cache all coins from CoinGecko."""
    global coin_cache, coin_list_last_updated
    
    if not force_refresh and os.path.exists(COIN_LIST_FILE):
        file_age = datetime.now().timestamp() - os.path.getmtime(COIN_LIST_FILE)
        if file_age < COIN_LIST_REFRESH_HOURS * 3600:
            with open(COIN_LIST_FILE, 'r') as f:
                coin_cache = json.load(f)
            coin_list_last_updated = datetime.fromtimestamp(os.path.getmtime(COIN_LIST_FILE))
            return coin_cache
    
    try:
        logging.info("Fetching fresh coin list from CoinGecko...")
        url = "https://api.coingecko.com/api/v3/coins/list"
        params = {'include_platform': 'false'}
        
        headers = {}
        api_key = os.getenv('COINGECKO_API_KEY')
        if api_key:
            headers['x-cg-demo-api-key'] = api_key
        
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        if response.status_code == 200:
            coins = response.json()
            coin_cache = {
                'by_id': {},
                'by_symbol': {},
                'by_name': {},
                'all_coins': coins
            }
            
            for coin in coins:
                coin_id = coin['id'].lower()
                symbol = coin['symbol'].lower()
                name = coin['name'].lower()
                
                coin_cache['by_id'][coin_id] = coin
                coin_cache['by_symbol'][symbol] = coin
                coin_cache['by_name'][name] = coin
            
            with open(COIN_LIST_FILE, 'w') as f:
                json.dump(coin_cache, f, indent=4)
            
            coin_list_last_updated = datetime.now()
            logging.info(f"Loaded {len(coins)} coins from CoinGecko")
            return coin_cache
        else:
            logging.error(f"Error fetching coin list: {response.status_code}")
            return load_cached_coins()
            
    except Exception as e:
        logging.error(f"Error fetching coin list: {e}")
        return load_cached_coins()

def load_cached_coins():
    """Load coins from cache file if API fails."""
    if os.path.exists(COIN_LIST_FILE):
        try:
            with open(COIN_LIST_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'by_id': {}, 'by_symbol': {}, 'by_name': {}, 'all_coins': []}

def find_coin(identifier):
    """Find coin by symbol, name, or CoinGecko ID."""
    identifier = identifier.lower().strip()
    
    if identifier in coin_cache['by_id']:
        return coin_cache['by_id'][identifier]
    elif identifier in coin_cache['by_symbol']:
        return coin_cache['by_symbol'][identifier]
    elif identifier in coin_cache['by_name']:
        return coin_cache['by_name'][identifier]
    
    for coin in coin_cache['all_coins']:
        if identifier in coin['id'].lower() or \
           identifier in coin['symbol'].lower() or \
           identifier in coin['name'].lower():
            return coin
    
    return None

def get_crypto_price(coin_id, vs_currency='usd'):
    """Get current price for any coin from CoinGecko."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': vs_currency,
            'include_market_cap': 'false',
            'include_24hr_vol': 'false',
            'include_24hr_change': 'false',
            'include_last_updated_at': 'false'
        }
        
        headers = {}
        api_key = os.getenv('COINGECKO_API_KEY')
        if api_key:
            headers['x-cg-demo-api-key'] = api_key
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if coin_id in data and vs_currency in data[coin_id]:
            return data[coin_id][vs_currency]
        return None
    except Exception as e:
        logging.error(f"Error fetching price for {coin_id}: {e}")
        return None

def get_mexc_price(symbol):
    """Get price from MEXC exchange."""
    try:
        url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={symbol}"
        response = requests.get(url, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        logging.error(f"Error fetching MEXC price for {symbol}: {e}")
        return None

def get_mexc_volume(symbol):
    """Get volume data from MEXC exchange."""
    try:
        url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={symbol}"
        response = requests.get(url, timeout=10)
        data = response.json()
        if data and 'quoteVolume' in data:
            return float(data['quoteVolume'])
        return None
    except Exception as e:
        logging.error(f"Error fetching MEXC volume for {symbol}: {e}")
        return None

def parse_alert_input(input_str):
    """Parse various input formats for alerts."""
    parts = re.split(r'[\s\-]+', input_str.lower())
    price = None
    coin_parts = []
    
    for part in parts:
        clean_part = part.replace(',', '').replace('$', '')
        if clean_part.replace('.', '').isdigit() and '.' in clean_part:
            price = float(clean_part)
        elif clean_part.isdigit() and len(clean_part) > 3:
            price = float(clean_part)
        else:
            coin_parts.append(part)
    
    coin_identifier = ' '.join(coin_parts).strip()
    return coin_identifier, price

def fmt(p):
    """Format price with 4 decimal places."""
    try:
        return f"${float(p):,.4f}"
    except:
        return "$0.0000"

def fmt_volume(v):
    """Format volume in a readable way."""
    try:
        v = float(v)
        if v >= 1_000_000_000:
            return f"${v/1_000_000_000:.2f}B"
        elif v >= 1_000_000:
            return f"${v/1_000_000:.2f}M"
        elif v >= 1_000:
            return f"${v/1_000:.2f}K"
        else:
            return f"${v:,.0f}"
    except:
        return "$0"

def get_support_resistance_levels(coin_symbol):
    """
    Calculate simple support and resistance levels.
    """
    try:
        # Get current price to base levels on
        data = get_mexc_price(f"{coin_symbol.upper()}USDT")
        if not data:
            return None, None
        
        current_price = float(data.get('lastPrice', 0))
        high = float(data.get('highPrice', current_price * 1.1))
        low = float(data.get('lowPrice', current_price * 0.9))
        
        # Calculate levels based on recent range
        price_range = high - low
        support_levels = [
            low + (price_range * 0.25),
            low + (price_range * 0.15),
            low + (price_range * 0.05)
        ]
        
        resistance_levels = [
            low + (price_range * 0.75),
            low + (price_range * 0.85),
            low + (price_range * 0.95)
        ]
        
        return support_levels, resistance_levels
        
    except Exception as e:
        logging.error(f"Error calculating support/resistance: {e}")
        return None, None

# ==================== FUN FUNCTIONS ====================
def get_funny_price_reaction(change):
    """Get funny reaction based on price change."""
    if change > 10:
        return random.choice(PRICE_REACTIONS['big_pump'])
    elif change < -10:
        return random.choice(PRICE_REACTIONS['big_dump'])
    elif abs(change) < 2:
        return random.choice(PRICE_REACTIONS['stable'])
    else:
        emoji = "🚀" if change > 0 else "📉"
        return f"{emoji} Normal crypto things! Price is doing its dance!"

def get_random_emoji_combo():
    """Get random emoji combination."""
    combos = [
        "🚀🔥💎", "⚡🎯💪", "🌙✨🪐", "💰📈🎉", "🤖🌐💻",
        "🎮🔥⚡", "💎🤲🛡️", "📊🎯⚡", "🚀🌙🪐", "🔥💪🎯"
    ]
    return random.choice(combos)

# ==================== NEWS FUNCTIONS ====================
RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://cryptopotato.com/feed/",
    "https://beincrypto.com/feed/"
]

def get_crypto_news():
    """Fetch latest news from RSS feeds."""
    news_items = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                source = "CoinDesk" if "coindesk" in feed_url else \
                         "CoinTelegraph" if "cointelegraph" in feed_url else \
                         "CryptoPotato" if "cryptopotato" in feed_url else "BeInCrypto"
                
                news_items.append({
                    "title": entry.title[:200] + "..." if len(entry.title) > 200 else entry.title,
                    "link": entry.link,
                    "source": source,
                    "published": entry.get('published', '')
                })
        except Exception as e:
            logging.error(f"Error parsing feed {feed_url}: {e}")
    
    # Sort by publication date if available
    news_items.sort(key=lambda x: x.get('published', ''), reverse=True)
    return news_items

# ==================== ENHANCED HELPER FUNCTIONS ====================
async def type_and_send(channel, message, delay=0.3):
    """Simulate typing before sending message."""
    async with channel.typing():
        await asyncio.sleep(delay)
        await channel.send(message)

async def send_with_reactions(channel, message, reactions=None):
    """Send message with reactions."""
    msg = await channel.send(message)
    if reactions:
        for reaction in reactions[:3]:
            try:
                await msg.add_reaction(reaction)
            except:
                pass
    return msg

async def send_to_alerts_channel(content):
    """Send message to alerts channel."""
    if ALERTS_CHANNEL_ID:
        try:
            channel = bot.get_channel(ALERTS_CHANNEL_ID)
            if channel:
                await channel.send(content)
        except Exception as e:
            logging.error(f"Error sending to alerts channel: {e}")

async def send_to_chat_channel(content):
    """Send message to chat channel."""
    if CHAT_CHANNEL_ID:
        try:
            channel = bot.get_channel(CHAT_CHANNEL_ID)
            if channel:
                await channel.send(content)
        except Exception as e:
            logging.error(f"Error sending to chat channel: {e}")

# ==================== ENHANCED TASKS ====================
@tasks.loop(minutes=5)
async def check_alerts():
    """Background task to check alerts every 5 minutes."""
    alerts = load_alerts()
    if not alerts:
        return
    
    total_alerts = sum(len(v) for v in alerts.values())
    logging.info(f"Checking {total_alerts} alerts...")
    
    triggered_count = 0
    for user_id, user_alerts in alerts.items():
        for alert in user_alerts:
            if alert['triggered']:
                continue
            
            current_price = get_crypto_price(alert['coin_id'])
            if current_price is None:
                continue
            
            alert['current_price'] = current_price
            previous_price = alert.get('last_checked_price', current_price)
            target_price = alert['target_price']
            
            price_crossed_up = (previous_price < target_price <= current_price)
            price_crossed_down = (previous_price > target_price >= current_price)
            
            if price_crossed_up or price_crossed_down:
                alert['triggered'] = True
                alert['triggered_at'] = datetime.now().isoformat()
                alert['triggered_price'] = current_price
                alert['direction'] = 'above' if price_crossed_up else 'below'
                triggered_count += 1
                
                # Send alert notification
                try:
                    channel = bot.get_channel(alert['channel_id'])
                    if channel:
                        embed = discord.Embed(
                            title="PRICE ALERT TRIGGERED!",
                            color=discord.Color.green() if price_crossed_up else discord.Color.red(),
                            timestamp=datetime.now()
                        )
                        
                        price_change = ((current_price - target_price) / target_price * 100)
                        reaction = "🚀📈🎉" if price_crossed_up else "📉🛡️💎"
                        
                        embed.add_field(
                            name=f"{reaction} {alert['name']} ({alert['symbol']}) {reaction}",
                            value=(
                                f"Target: ${target_price:,.4f}\n"
                                f"Current: ${current_price:,.4f}\n"
                                f"Change: {price_change:+.2f}%\n"
                                f"Direction: {'ABOVE' if price_crossed_up else 'BELOW'}"
                            ),
                            inline=False
                        )
                        
                        embed.set_footer(text=f"Congrats {alert['user_name']}! Time to make moves!")
                        
                        # Send to original channel and alerts channel
                        message = await channel.send(f"<@{user_id}>", embed=embed)
                        await message.add_reaction("🚨")
                        await message.add_reaction("💰")
                        await message.add_reaction("🎯")
                        
                        if ALERTS_CHANNEL_ID and ALERTS_CHANNEL_ID != alert['channel_id']:
                            alerts_channel = bot.get_channel(ALERTS_CHANNEL_ID)
                            if alerts_channel:
                                await alerts_channel.send(f"<@{user_id}>", embed=embed)
                                
                except Exception as e:
                    logging.error(f"Error sending alert notification: {e}")
            
            alert['last_checked_price'] = current_price
    
    if triggered_count > 0:
        save_alerts(alerts)
        logging.info(f"Triggered {triggered_count} alerts")

@tasks.loop(hours=24)
async def refresh_coin_list():
    """Refresh coin list every 24 hours."""
    logging.info("Auto-refreshing coin list...")
    get_all_coingecko_coins(force_refresh=True)
    logging.info(f"Coin list refreshed. Now tracking {len(coin_cache['all_coins'])} coins")

@tasks.loop(seconds=UPDATE_INTERVAL)
async def auto_price_update():
    """Auto-update MEXC prices in price channel."""
    global auto_price_message
    
    if not PRICE_CHANNEL_ID:
        return
    
    await bot.wait_until_ready()
    channel = bot.get_channel(PRICE_CHANNEL_ID)
    
    if not channel:
        return
    
    try:
        PAIRS = get_top_coins(TOP_N)
        if not PAIRS:
            logging.warning("No MEXC data available")
            return
        
        embed = discord.Embed(
            title=f"MEXC TOP 20 LIVE PRICES {get_random_emoji_combo()}",
            description=f"Auto-update every {UPDATE_INTERVAL}s • {datetime.utcnow().strftime('%H:%M:%S')} UTC",
            color=0x00ff99
        )

        for name, symbol in list(PAIRS.items())[:TOP_N]:
            data = get_mexc_price(symbol)
            if data:
                last_price = float(data.get("lastPrice", 0))
                change = float(data.get("priceChangePercent", 0))
                high = float(data.get("highPrice", 0))
                low = float(data.get("lowPrice", 0))
                volume = float(data.get("quoteVolume", 0))
                
                arrow = "🟢 ▲" if change >= 0 else "🔴 ▼"
                price_emoji = "🚀" if change > 10 else "📈" if change > 5 else "⚡" if change > 0 else "📉" if change < -10 else "🛡️" if change < -5 else "⚖️"
                
                embed.add_field(
                    name=f"{price_emoji} {name}USDT",
                    value=(
                        f"Price: {fmt(last_price)}\n"
                        f"Change: {change:+.2f}% {arrow}\n"
                        f"H/L: {fmt(high)} / {fmt(low)}\n"
                        f"Vol: ${volume:,.0f}"
                    ),
                    inline=True
                )

        if auto_price_message is None:
            auto_price_message = await channel.send(embed=embed)
            await auto_price_message.add_reaction("📈")
            await auto_price_message.add_reaction("📊")
            await auto_price_message.add_reaction("⚡")
        else:
            await auto_price_message.edit(embed=embed)
            
    except Exception as e:
        logging.error(f"Error in auto_price_update: {e}")

@tasks.loop(minutes=5)
async def auto_news_update():
    """Auto-post news updates in news channel."""
    global posted_news
    
    if not NEWS_CHANNEL_ID:
        return
    
    await bot.wait_until_ready()
    channel = bot.get_channel(NEWS_CHANNEL_ID)
    
    if not channel:
        return
    
    try:
        news = get_crypto_news()
        new_posts = 0

        for item in news[:3]:
            news_id = item["link"]
            if news_id not in posted_news:
                # Create a news embed
                source_emoji = "📰" if "CoinDesk" in item['source'] else "📖" if "CoinTelegraph" in item['source'] else "🥔" if "CryptoPotato" in item['source'] else "🔐"
                
                embed = discord.Embed(
                    title=f"{source_emoji} {item['source']} UPDATE {source_emoji}",
                    description=f"{item['title']}",
                    color=discord.Color.blue(),
                    url=item["link"],
                    timestamp=datetime.now()
                )
                
                embed.set_footer(text=f"Stay informed! • Source: {item['source']}")
                
                # Add reactions for engagement
                message = await channel.send(embed=embed)
                await message.add_reaction("📰")
                await message.add_reaction("🔥")
                await message.add_reaction("💎")
                await message.add_reaction("🚀")
                
                posted_news.add(news_id)
                new_posts += 1
                
                # Small delay between news posts
                await asyncio.sleep(1)

        if new_posts > 0:
            logging.info(f"Posted {new_posts} new news item(s) to channel {NEWS_CHANNEL_ID}")
            
    except Exception as e:
        logging.error(f"Error in auto_news_update: {e}")

@tasks.loop(hours=1)
async def cleanup_posted_news():
    """Clean up old news entries to prevent memory issues."""
    global posted_news
    
    if len(posted_news) > 1000:
        # Keep only the last 500 news items
        posted_news = set(list(posted_news)[-500:])
        logging.info("Cleaned up old news entries")

# ==================== ENHANCED EVENT HANDLERS ====================
@bot.event
async def on_ready():
    """Bot startup event."""
    global coin_cache
    
    print(f"\n{'='*60}")
    print(f"{'UNIFIED CRYPTO BOT ONLINE':^60}")
    print(f"{'='*60}")
    print(f"Logged in as: {bot.user.name}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Servers: {len(bot.guilds)}")
    print(f"{'-'*60}")
    print(f"Coin Database: {len(coin_cache.get('all_coins', [])):,} coins")
    print(f"Alerts Channel: {'✅ Enabled' if ALERTS_CHANNEL_ID else '❌ Disabled'}")
    print(f"Price Channel: {'✅ Enabled' if PRICE_CHANNEL_ID else '❌ Disabled'}")
    print(f"News Channel: {'✅ Enabled' if NEWS_CHANNEL_ID else '❌ Disabled'}")
    print(f"Chat Channel: {'✅ Enabled' if CHAT_CHANNEL_ID else '❌ Disabled'}")
    print(f"{'='*60}\n")
    
    # Initialize coin list
    get_all_coingecko_coins()
    
    # Start all background tasks
    tasks_to_start = [
        (check_alerts, "Alert Checker"),
        (refresh_coin_list, "Coin List Refresher"),
        (auto_price_update, "Price Auto-Updater"),
        (auto_news_update, "News Auto-Poster"),
        (cleanup_posted_news, "News Cleanup")
    ]
    
    for task, name in tasks_to_start:
        if not task.is_running():
            task.start()
            print(f"✅ Started: {name}")
    
    # Set bot status
    activity = discord.Activity(
        type=discord.ActivityType.playing,
        name=f"with {len(coin_cache.get('all_coins', [])):,} coins | !commands"
    )
    await bot.change_presence(activity=activity, status=discord.Status.online)
    
    # Send startup message to channels
    startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if ALERTS_CHANNEL_ID:
        try:
            channel = bot.get_channel(ALERTS_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="ALERTS SYSTEM ONLINE",
                    description="Crypto price alerts are now active! Set alerts and get notified!",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Quick Start", value="Use `!set_alert btc 50000` to set your first alert!", inline=False)
                embed.add_field(name="Make Money", value="Stay ahead of the market with instant notifications!", inline=False)
                embed.set_footer(text=f"Bot started at {startup_time} • Lets get this bread!")
                await channel.send(embed=embed)
        except:
            pass
    
    if CHAT_CHANNEL_ID:
        try:
            channel = bot.get_channel(CHAT_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="CRYPTO BOT IS ONLINE!",
                    description="Ready to chat about crypto, give prices, news, and more!",
                    color=discord.Color.gold(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Try These Commands", value="`!commands` - See all commands\n`!btc` - Bitcoin info\n`!news` - Latest crypto news", inline=False)
                embed.add_field(name="Chat With Me", value="Mention me or talk about crypto in this channel!", inline=False)
                embed.set_footer(text="GM Degens! Lets make some money!")
                await channel.send(embed=embed)
        except:
            pass

@bot.event
async def on_message(message):
    """Handle all incoming messages with ENHANCED responses."""
    if message.author.bot:
        return
    
    content = message.content.lower()
    
    # Enhanced chat responses in chat channel
    if CHAT_CHANNEL_ID and message.channel.id == CHAT_CHANNEL_ID:
        # Direct mention with high priority
        if bot.user.mentioned_in(message):
            if 'gm' in content:
                reply = f"GM {message.author.mention}! Ready to make some money today?"
                await type_and_send(message.channel, reply, delay=0.1)
                await message.add_reaction("☕")
                await message.add_reaction("💰")
            elif 'gn' in content:
                reply = f"GN {message.author.mention}! Sweet crypto dreams!"
                await type_and_send(message.channel, reply, delay=0.1)
                await message.add_reaction("😴")
                await message.add_reaction("🌙")
            else:
                reply = random.choice(CHAT_REPLIES)
                await type_and_send(message.channel, f"{message.author.mention} {reply}", delay=0.1)
                # Add relevant reactions
                for keyword, emojis in CRYPTO_KEYWORDS.items():
                    if keyword in content:
                        for emoji in emojis[:2]:
                            try:
                                await message.add_reaction(emoji)
                            except:
                                pass
                        break
        
        # Crypto-related keywords that trigger responses (higher chance)
        else:
            for keyword, emojis in CRYPTO_KEYWORDS.items():
                if keyword in content and random.random() < 0.4:
                    reply = random.choice(CHAT_REPLIES)
                    await type_and_send(message.channel, f"{message.author.mention} {reply}", delay=0.2)
                    # Add relevant emojis
                    for emoji in emojis[:2]:
                        try:
                            await message.add_reaction(emoji)
                        except:
                            pass
                    break
    
    # Process commands
    await bot.process_commands(message)

# ==================== ENHANCED COMMANDS ====================

# ----- FUN COMMANDS -----
@bot.command(name='moon', help='Moon mission countdown!')
async def moon(ctx):
    """Moon mission!"""
    messages = [
        "MISSION CONTROL: Preparing for launch!",
        "T-10 seconds: Engines firing up!",
        "T-5 seconds: Main engines GO!",
        "T-2 seconds: Liftoff!",
        "LIFTOFF! We have liftoff!",
        "ENTERING ORBIT: Next stop...",
        "THE MOON! We made it!",
        "MISSION SUCCESS! TO THE MOON!"
    ]
    
    for msg in messages:
        await ctx.send(msg)
        await asyncio.sleep(1)

@bot.command(name='gm', help='Good morning crypto!')
async def gm_command(ctx):
    """Good morning!"""
    gm_messages = [
        f"GM {ctx.author.mention}! Ready to make some money today?",
        f"GOOD MORNING! Coffee + Crypto = Perfect day! {ctx.author.mention}",
        f"RISE AND SHINE! Charts dont sleep! Lets go {ctx.author.mention}!",
        f"GM SENT! Time to meditate on those gains {ctx.author.mention}!",
        f"MORNING APE! Lets get this bread {ctx.author.mention}!"
    ]
    await ctx.send(random.choice(gm_messages))
    await ctx.message.add_reaction("☕")
    await ctx.message.add_reaction("💰")

@bot.command(name='gn', help='Good night crypto!')
async def gn_command(ctx):
    """Good night!"""
    gn_messages = [
        f"GN {ctx.author.mention}! Sweet crypto dreams!",
        f"SLEEP WELL! Markets will be here tomorrow {ctx.author.mention}!",
        f"NIGHT NIGHT! Dont let the bears bite {ctx.author.mention}!",
        f"REST UP! Big trading day tomorrow {ctx.author.mention}!",
        f"GN DEGEN! See you on the charts tomorrow {ctx.author.mention}!"
    ]
    await ctx.send(random.choice(gn_messages))
    await ctx.message.add_reaction("😴")
    await ctx.message.add_reaction("🌙")

@bot.command(name='lfg', help='LFG! (Lets Go!)')
async def lfg_command(ctx):
    """LFG!"""
    lfg_messages = [
        "LFG! TO THE MOON!",
        "LETS GO! PUMP IT!",
        "DIAMOND HANDS! LFG!",
        "PARTY TIME! LFG DEGENS!",
        "SPEED RUN! LFG TO PROFITS!"
    ]
    await ctx.send(random.choice(lfg_messages))
    await ctx.message.add_reaction("🚀")
    await ctx.message.add_reaction("🔥")
    await ctx.message.add_reaction("💎")

# ----- MISSING ALERT COMMANDS -----
@bot.command(name='alerts_detailed', help='View detailed alerts list')
async def alerts_detailed(ctx):
    """Show detailed alerts list."""
    user_id = str(ctx.author.id)
    alerts = load_alerts()
    
    if user_id not in alerts or not alerts[user_id]:
        await ctx.send("No alerts yet! Set one with `!set_alert SYMBOL PRICE`")
        return
    
    active_alerts = [a for a in alerts[user_id] if not a['triggered']]
    
    if not active_alerts:
        await ctx.send("No active alerts. All your alerts have been triggered or deleted.")
        return
    
    embed = discord.Embed(
        title=f"DETAILED ALERTS FOR {ctx.author.name}",
        description=f"Total Active Alerts: {len(active_alerts)}",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    for i, alert in enumerate(active_alerts, 1):
        current_price = get_crypto_price(alert['coin_id']) or alert['current_price']
        target_price = alert['target_price']
        price_diff = ((target_price - current_price) / current_price * 100)
        days_ago = (datetime.now() - datetime.fromisoformat(alert['timestamp'])).days
        
        status = "WAITING" if not alert['triggered'] else "TRIGGERED"
        emoji = "⏳" if not alert['triggered'] else "✅"
        
        embed.add_field(
            name=f"{emoji} Alert #{i}: {alert['name']}",
            value=(
                f"**Symbol**: {alert['symbol']}\n"
                f"**Target**: ${target_price:,.2f}\n"
                f"**Current**: ${current_price:,.2f}\n"
                f"**Difference**: {price_diff:+.2f}%\n"
                f"**Status**: {status}\n"
                f"**Set**: {days_ago} days ago\n"
                f"**ID**: `{alert['coin_id']}`"
            ),
            inline=False
        )
    
    embed.set_footer(text="Use !delete_alert [number] to remove an alert")
    await ctx.send(embed=embed)

@bot.command(name='delete_alert', help='Delete a specific alert')
async def delete_alert(ctx, alert_number: int):
    """Delete a specific alert by number."""
    user_id = str(ctx.author.id)
    alerts = load_alerts()
    
    if user_id not in alerts or not alerts[user_id]:
        await ctx.send("You don't have any alerts to delete!")
        return
    
    # Get only active alerts
    active_alerts = [a for a in alerts[user_id] if not a['triggered']]
    
    if alert_number < 1 or alert_number > len(active_alerts):
        await ctx.send(f"Invalid alert number! You have {len(active_alerts)} active alerts. Use `!my_alerts` to see them.")
        return
    
    # Find and remove the alert
    alert_to_delete = active_alerts[alert_number - 1]
    
    # Remove from original list (including triggered ones)
    alerts[user_id] = [a for a in alerts[user_id] if a.get('unique_id') != alert_to_delete.get('unique_id') or a['triggered']]
    
    # If all alerts are removed, remove the user entry
    if not alerts[user_id]:
        del alerts[user_id]
    
    save_alerts(alerts)
    
    await ctx.send(f"✅ Alert #{alert_number} for **{alert_to_delete['name']}** at **${alert_to_delete['target_price']:,.2f}** has been deleted!")

@bot.command(name='clear_alerts', help='Clear all your alerts')
async def clear_alerts(ctx):
    """Clear all alerts for the user."""
    user_id = str(ctx.author.id)
    alerts = load_alerts()
    
    if user_id not in alerts or not alerts[user_id]:
        await ctx.send("You don't have any alerts to clear!")
        return
    
    alert_count = len(alerts[user_id])
    del alerts[user_id]
    save_alerts(alerts)
    
    await ctx.send(f"✅ Cleared {alert_count} alerts! All your alerts have been removed.")

# ----- ALERT COMMANDS (Enhanced) -----
@bot.command(name='set_alert', help='Set a crypto price alert')
async def set_alert(ctx, *, input_str: str):
    """Set a price alert for any cryptocurrency."""
    coin_identifier, target_price = parse_alert_input(input_str)
    
    if not coin_identifier:
        await ctx.send("Oops! Please specify a cryptocurrency (e.g., `!set_alert bitcoin 50000`)")
        return
    
    if target_price is None:
        await ctx.send("Missing price! Please specify a target price (e.g., `!set_alert bitcoin 50000`)")
        return
    
    coin = find_coin(coin_identifier)
    if not coin:
        await ctx.send(f"Coin not found! Couldnt find '{coin_identifier}'. Try `!search {coin_identifier}`")
        return
    
    user_id = str(ctx.author.id)
    alerts = load_alerts()
    
    if user_id not in alerts:
        alerts[user_id] = []
    
    # Check for duplicate alert
    for alert in alerts[user_id]:
        if alert['coin_id'] == coin['id'] and alert['target_price'] == target_price and not alert['triggered']:
            await ctx.send(f"Already watching! You already have an active alert for **{coin['name']}** at **${target_price:,.2f}**")
            return
    
    current_price = get_crypto_price(coin['id'])
    if current_price is None:
        await ctx.send(f"Price fetch failed! Could not get current price for {coin['name']}. Try again later!")
        return
    
    # Create new alert
    new_alert = {
        'coin_id': coin['id'],
        'symbol': coin['symbol'].upper(),
        'name': coin['name'],
        'target_price': target_price,
        'current_price': current_price,
        'timestamp': datetime.now().isoformat(),
        'channel_id': ctx.channel.id,
        'user_id': user_id,
        'user_name': ctx.author.name,
        'triggered': False,
        'vs_currency': 'usd'
    }
    
    alerts[user_id].append(new_alert)
    save_alerts(alerts)
    
    # Send ENHANCED confirmation
    price_diff = ((target_price - current_price) / current_price * 100)
    direction = "above" if target_price > current_price else "below"
    emoji_combo = "🚀📈🎯" if target_price > current_price else "🛡️📉🎯"
    
    embed = discord.Embed(
        title=f"ALERT SET SUCCESSFULLY! {emoji_combo}",
        color=discord.Color.green() if target_price > current_price else discord.Color.orange(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Cryptocurrency", value=f"**{coin['name']}** ({coin['symbol'].upper()})", inline=True)
    embed.add_field(name="Target Price", value=f"**${target_price:,.2f}**", inline=True)
    embed.add_field(name="Current Price", value=f"${current_price:,.2f}", inline=True)
    embed.add_field(name="Difference", value=f"{price_diff:+.2f}%", inline=True)
    embed.add_field(name="Direction", value=f"Will trigger when price goes **{direction}** target", inline=True)
    embed.add_field(name="Status", value="ACTIVE & WATCHING!", inline=True)
    
    embed.set_footer(text=f"Alert ID: {len(alerts[user_id])} • Good luck!")
    
    message = await ctx.send(embed=embed)
    await message.add_reaction("🎯")
    await message.add_reaction("💰")
    await message.add_reaction("👀")
    
    # Also send to alerts channel if different
    if ALERTS_CHANNEL_ID and ALERTS_CHANNEL_ID != ctx.channel.id:
        await send_to_alerts_channel(f"New alert set by {ctx.author.mention}: **{coin['name']}** at ${target_price:,.2f}")

@bot.command(name='my_alerts', help='Show all your active alerts')
async def my_alerts(ctx):
    """Display all alerts for the user."""
    user_id = str(ctx.author.id)
    alerts = load_alerts()
    
    if user_id not in alerts or not alerts[user_id]:
        await ctx.send("No alerts yet! Set one with `!set_alert SYMBOL PRICE` and start tracking!")
        return
    
    active_alerts = [a for a in alerts[user_id] if not a['triggered']]
    triggered_alerts = [a for a in alerts[user_id] if a['triggered']]
    
    embed = discord.Embed(
        title=f"{ctx.author.name}'s ALERT DASHBOARD",
        description=f"Active: {len(active_alerts)} | Triggered: {len(triggered_alerts)}",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    if active_alerts:
        for i, alert in enumerate(active_alerts[:6], 1):
            current_price = get_crypto_price(alert['coin_id']) or alert['current_price']
            price_diff = ((alert['target_price'] - current_price) / current_price * 100)
            days_ago = (datetime.now() - datetime.fromisoformat(alert['timestamp'])).days
            
            status_emoji = "🚀" if price_diff < -5 else "📈" if price_diff < 0 else "⚡" if price_diff < 5 else "🛡️"
            
            embed.add_field(
                name=f"{status_emoji} {i}. {alert['name']} ({alert['symbol']})",
                value=(
                    f"Target: ${alert['target_price']:,.2f}\n"
                    f"Current: ${current_price:,.2f}\n"
                    f"Diff: {price_diff:+.2f}%\n"
                    f"Set: {days_ago}d ago"
                ),
                inline=True
            )
    
    if triggered_alerts:
        triggered_list = "\n".join([f"• {a['name']} at ${a['target_price']:,.2f}" for a in triggered_alerts[:3]])
        if len(triggered_alerts) > 3:
            triggered_list += f"\n• ...and {len(triggered_alerts) - 3} more"
        
        embed.add_field(name="TRIGGERED ALERTS", value=triggered_list or "None yet!", inline=False)
    
    embed.set_footer(text=f"Use !delete_alert [number] to remove alerts • Stay vigilant!")
    
    message = await ctx.send(embed=embed)
    await message.add_reaction("📊")
    await message.add_reaction("👀")

# ----- ENHANCED PRICE COMMANDS -----
@bot.command(name='price', help='Get all top coin prices')
async def all_prices(ctx):
    """Get all top coin prices."""
    embed = discord.Embed(
        title="TOP CRYPTO PRICES",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    
    prices_data = []
    for symbol, coin_id in COINS.items():
        price = get_crypto_price(coin_id)
        if price:
            change = get_price_change(coin_id) or 0
            emoji = "🚀" if change > 5 else "📈" if change > 0 else "📉" if change < -5 else "⚡"
            prices_data.append((symbol.upper(), price, change, emoji))
    
    # Sort by market cap/importance
    order = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'SHIB', 'LINK']
    prices_data.sort(key=lambda x: order.index(x[0]) if x[0] in order else 999)
    
    for symbol, price, change, emoji in prices_data:
        embed.add_field(
            name=f"{emoji} {symbol}",
            value=f"${price:,.2f}\n{change:+.2f}%",
            inline=True
        )
    
    embed.set_footer(text=f"Use !btc, !eth, !sol for detailed info • {get_random_emoji_combo()}")
    
    message = await ctx.send(embed=embed)
    await message.add_reaction("💰")
    await message.add_reaction("📊")

@bot.command(name='btc', help='Get Bitcoin price and info')
async def btc_info(ctx, subcommand: str = None):
    """Get Bitcoin info."""
    await handle_coin_command(ctx, 'btc', subcommand)

@bot.command(name='eth', help='Get Ethereum price and info')
async def eth_info(ctx, subcommand: str = None):
    """Get Ethereum info."""
    await handle_coin_command(ctx, 'eth', subcommand)

@bot.command(name='sol', help='Get Solana price and info')
async def sol_info(ctx, subcommand: str = None):
    """Get Solana info."""
    await handle_coin_command(ctx, 'sol', subcommand)

@bot.command(name='xrp', help='Get Ripple price and info')
async def xrp_info(ctx, subcommand: str = None):
    """Get Ripple info."""
    await handle_coin_command(ctx, 'xrp', subcommand)

@bot.command(name='bnb', help='Get Binance Coin price and info')
async def bnb_info(ctx, subcommand: str = None):
    """Get Binance Coin info."""
    await handle_coin_command(ctx, 'bnb', subcommand)

@bot.command(name='doge', help='Get Dogecoin price and info')
async def doge_info(ctx, subcommand: str = None):
    """Get Dogecoin info."""
    await handle_coin_command(ctx, 'doge', subcommand)

@bot.command(name='ada', help='Get Cardano price and info')
async def ada_info(ctx, subcommand: str = None):
    """Get Cardano info."""
    await handle_coin_command(ctx, 'ada', subcommand)

@bot.command(name='volume', help='Get volume for all top coins')
async def all_volumes(ctx):
    """Get volume for all top coins."""
    PAIRS = get_top_coins(TOP_N)
    
    if not PAIRS:
        await ctx.send("Could not fetch volume data.")
        return
    
    embed = discord.Embed(
        title="TOP CRYPTO VOLUMES",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    for name, symbol in list(PAIRS.items())[:10]:
        data = get_mexc_price(symbol)
        if data:
            volume = float(data.get("quoteVolume", 0))
            
            # Determine volume level emoji
            if volume > 1000000000:
                emoji = "🔥"
                level = "HIGH VOLUME"
            elif volume > 100000000:
                emoji = "⚡"
                level = "ACTIVE"
            else:
                emoji = "💎"
                level = "LOW"
            
            embed.add_field(
                name=f"{emoji} {name}",
                value=f"{fmt_volume(volume)}\n{level}",
                inline=True
            )
    
    embed.set_footer(text="24h trading volume on MEXC")
    await ctx.send(embed=embed)

async def handle_coin_command(ctx, coin_symbol: str, subcommand: str = None):
    """Handle individual coin commands with ENHANCED responses."""
    coin_symbol = coin_symbol.lower()
    
    if coin_symbol not in COINS:
        await ctx.send(f"Oops! {coin_symbol.upper()} is not in my watchlist!\nSupported coins: {', '.join(COINS.keys()).upper()}")
        return
    
    coin_id = COINS[coin_symbol]
    coin_name = COIN_NAMES[coin_symbol]
    
    # Get MEXC data
    PAIRS = get_top_coins(TOP_N)
    if not PAIRS or coin_symbol.upper() not in PAIRS:
        await ctx.send(f"Data fetch failed! Could not get data for {coin_name}. Try again!")
        return
    
    data = get_mexc_price(PAIRS[coin_symbol.upper()])
    if not data:
        await ctx.send(f"Market data missing! Could not fetch data for {coin_name}.")
        return
    
    # Handle subcommands
    if subcommand is None:
        # Default: Show price with FUN info
        await show_enhanced_coin_price(ctx, coin_symbol, coin_name, data)
    
    elif subcommand.lower() in ['price', 'p']:
        # Show only price with FUN
        last_price = float(data.get("lastPrice", 0))
        change = float(data.get("priceChangePercent", 0))
        
        embed = discord.Embed(
            title=f"{coin_name} ({coin_symbol.upper()}) PRICE",
            description=f"**${last_price:,.4f}**",
            color=discord.Color.green() if change >= 0 else discord.Color.red(),
            timestamp=datetime.now()
        )
        
        if change != 0:
            arrow = "📈🚀" if change >= 0 else "📉🛡️"
            embed.add_field(name="24h Change", value=f"{arrow} **{change:+.2f}%**", inline=True)
            embed.add_field(name="Mood", value=get_funny_price_reaction(change), inline=False)
        
        embed.set_footer(text=f"MEXC Exchange • {get_random_emoji_combo()}")
        
        message = await ctx.send(embed=embed)
        reactions = ["💰", "📈", "🎯"] if change >= 0 else ["💰", "📉", "🛡️"]
        for reaction in reactions:
            await message.add_reaction(reaction)
    
    elif subcommand.lower() in ['volume', 'vol', 'v']:
        # Show volume with FUN
        volume = float(data.get("quoteVolume", 0))
        
        embed = discord.Embed(
            title=f"{coin_name} ({coin_symbol.upper()}) VOLUME",
            description=f"24h Trading Volume",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Volume", value=f"**{fmt_volume(volume)}**", inline=False)
        embed.add_field(name="Exchange", value="MEXC ⚡", inline=True)
        embed.add_field(name="Pair", value=f"{coin_symbol.upper()}USDT", inline=True)
        
        # Enhanced volume analysis
        if volume > 1000000000:
            volume_emoji = "🔥🔥"
            activity = "VERY HIGH VOLUME"
        elif volume > 500000000:
            volume_emoji = "🔥"
            activity = "HIGH VOLUME"
        elif volume > 100000000:
            volume_emoji = "⚡"
            activity = "ACTIVE"
        elif volume > 50000000:
            volume_emoji = "📊"
            activity = "MODERATE"
        else:
            volume_emoji = "💎"
            activity = "LOW VOLUME"
        
        embed.add_field(name="Activity Level", value=f"{volume_emoji} {activity}", inline=True)
        embed.add_field(name="Market Attention", value="LOTS" if volume > 500000000 else "NORMAL" if volume > 100000000 else "LOW", inline=True)
        
        embed.set_footer(text="24h trading volume • Money moves!")
        
        message = await ctx.send(embed=embed)
        reactions = ["📊", "💎", "🔥"] if volume > 500000000 else ["📊", "💎", "⚡"]
        for reaction in reactions:
            await message.add_reaction(reaction)
    
    elif subcommand.lower() in ['h/l', 'hl', 'highlow']:
        # Show high/low
        high = float(data.get("highPrice", 0))
        low = float(data.get("lowPrice", 0))
        last_price = float(data.get("lastPrice", 0))
        
        embed = discord.Embed(
            title=f"{coin_name} ({coin_symbol.upper()}) High/Low",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="24h High", value=fmt(high), inline=True)
        embed.add_field(name="24h Low", value=fmt(low), inline=True)
        embed.add_field(name="Current Price", value=fmt(last_price), inline=True)
        
        # Calculate range
        price_range = high - low
        if price_range > 0:
            current_position = ((last_price - low) / price_range) * 100
            embed.add_field(name="Current Position", value=f"{current_position:.1f}% of range", inline=False)
        
        embed.set_footer(text="24h price range on MEXC")
        await ctx.send(embed=embed)
    
    elif subcommand.lower() in ['s/r', 'sr', 'supportresistance']:
        # Show support and resistance
        support_levels, resistance_levels = get_support_resistance_levels(coin_symbol.upper())
        last_price = float(data.get("lastPrice", 0))
        
        embed = discord.Embed(
            title=f"{coin_name} ({coin_symbol.upper()}) Support & Resistance",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Current Price", value=fmt(last_price), inline=False)
        
        if support_levels:
            support_text = "\n".join([f"• {fmt(level)}" for level in support_levels[:3]])
            embed.add_field(name="Support Levels", value=support_text, inline=True)
        else:
            embed.add_field(name="Support Levels", value="Calculating...", inline=True)
        
        if resistance_levels:
            resistance_text = "\n".join([f"• {fmt(level)}" for level in resistance_levels[:3]])
            embed.add_field(name="Resistance Levels", value=resistance_text, inline=True)
        else:
            embed.add_field(name="Resistance Levels", value="Calculating...", inline=True)
        
        embed.set_footer(text="These are estimated levels for educational purposes")
        await ctx.send(embed=embed)
    
    elif subcommand.lower() in ['support']:
        # Show only support levels
        support_levels, _ = get_support_resistance_levels(coin_symbol.upper())
        last_price = float(data.get("lastPrice", 0))
        
        embed = discord.Embed(
            title=f"{coin_name} ({coin_symbol.upper()}) SUPPORT LEVELS",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Current Price", value=fmt(last_price), inline=False)
        
        if support_levels:
            support_text = "\n".join([f"• **{fmt(level)}** - {'🟢 STRONG' if i == 0 else '🟡 MEDIUM' if i == 1 else '🔴 WEAK'}" 
                                    for i, level in enumerate(support_levels[:3])])
            embed.add_field(name="Key Support Levels", value=support_text, inline=False)
            
            # Distance to nearest support
            nearest_support = min(support_levels, key=lambda x: abs(x - last_price))
            distance_pct = ((last_price - nearest_support) / last_price * 100)
            
            if distance_pct > 0:
                embed.add_field(name="Distance to Support", value=f"{distance_pct:.2f}% ABOVE nearest support", inline=True)
            else:
                embed.add_field(name="Distance to Support", value=f"{-distance_pct:.2f}% BELOW nearest support", inline=True)
        else:
            embed.add_field(name="Support Levels", value="Calculating support levels...", inline=False)
        
        embed.set_footer(text="Support = Price tends to bounce UP from these levels")
        await ctx.send(embed=embed)
    
    elif subcommand.lower() in ['resistance']:
        # Show only resistance levels
        _, resistance_levels = get_support_resistance_levels(coin_symbol.upper())
        last_price = float(data.get("lastPrice", 0))
        
        embed = discord.Embed(
            title=f"{coin_name} ({coin_symbol.upper()}) RESISTANCE LEVELS",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Current Price", value=fmt(last_price), inline=False)
        
        if resistance_levels:
            resistance_text = "\n".join([f"• **{fmt(level)}** - {'🔴 STRONG' if i == 0 else '🟡 MEDIUM' if i == 1 else '🟢 WEAK'}" 
                                       for i, level in enumerate(resistance_levels[:3])])
            embed.add_field(name="Key Resistance Levels", value=resistance_text, inline=False)
            
            # Distance to nearest resistance
            nearest_resistance = min(resistance_levels, key=lambda x: abs(x - last_price))
            distance_pct = ((nearest_resistance - last_price) / last_price * 100)
            
            embed.add_field(name="Distance to Resistance", value=f"{distance_pct:.2f}% to nearest resistance", inline=True)
        else:
            embed.add_field(name="Resistance Levels", value="Calculating resistance levels...", inline=False)
        
        embed.set_footer(text="Resistance = Price tends to bounce DOWN from these levels")
        await ctx.send(embed=embed)
    
    else:
        # Unknown subcommand
        await ctx.send(f"Unknown subcommand for {coin_name}. Try: `!{coin_symbol} price`, `!{coin_symbol} volume`, `!{coin_symbol} h/l`, `!{coin_symbol} s/r`, `!{coin_symbol} support`, `!{coin_symbol} resistance`")

async def show_enhanced_coin_price(ctx, coin_symbol: str, coin_name: str, data: dict):
    """Show comprehensive coin information with FUN."""
    last_price = float(data.get("lastPrice", 0))
    change = float(data.get("priceChangePercent", 0))
    high = float(data.get("highPrice", 0))
    low = float(data.get("lowPrice", 0))
    volume = float(data.get("quoteVolume", 0))
    
    # Determine mood
    if change > 10:
        mood = "PUMPING HARD!"
        color = discord.Color.green()
    elif change > 5:
        mood = "LOOKING GOOD!"
        color = discord.Color.green()
    elif change > 0:
        mood = "SLOW & STEADY!"
        color = discord.Color.green()
    elif change > -5:
        mood = "HOLDING STRONG!"
        color = discord.Color.orange()
    else:
        mood = "BEAR ATTACK!"
        color = discord.Color.red()
    
    embed = discord.Embed(
        title=f"{coin_name} ({coin_symbol.upper()}) {get_random_emoji_combo()}",
        color=color,
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Price", value=f"**${last_price:,.4f}**", inline=True)
    embed.add_field(name="24h Change", value=f"**{change:+.2f}%** {'🟢' if change >= 0 else '🔴'}", inline=True)
    embed.add_field(name="Market Mood", value=mood, inline=True)
    embed.add_field(name="24h High", value=fmt(high), inline=True)
    embed.add_field(name="24h Low", value=fmt(low), inline=True)
    embed.add_field(name="24h Volume", value=fmt_volume(volume), inline=True)
    
    # Quick action buttons suggestion with emojis
    quick_actions = (
        f"• `!{coin_symbol} price` - Just price\n"
        f"• `!{coin_symbol} volume` - Volume only\n"
        f"• `!{coin_symbol} h/l` - High/Low\n"
        f"• `!{coin_symbol} s/r` - Support/Resistance\n"
        f"• `!{coin_symbol} support` - Support levels\n"
        f"• `!{coin_symbol} resistance` - Resistance levels\n"
        f"• `!set_alert {coin_symbol} [price]` - Set alert"
    )
    
    embed.add_field(name="Quick Actions", value=quick_actions, inline=False)
    
    embed.set_footer(text=f"Use !commands for more options • Good luck trading!")
    
    message = await ctx.send(embed=embed)
    
    # Add relevant reactions
    reactions = []
    if change > 5:
        reactions = ["🚀", "📈", "🎉", "💰"]
    elif change > 0:
        reactions = ["📈", "⚡", "💰", "🎯"]
    elif change > -5:
        reactions = ["🛡️", "💎", "📉", "🎯"]
    else:
        reactions = ["📉", "🛡️", "💎", "🎯"]
    
    for reaction in reactions[:3]:
        await message.add_reaction(reaction)

# ----- ADVANCED PRICE COMMANDS -----
@bot.command(name='price_gecko', help='Get price from CoinGecko for any coin')
async def price_gecko(ctx, *, coin_identifier: str):
    """Get price from CoinGecko for any coin."""
    coin = find_coin(coin_identifier)
    
    if not coin:
        await ctx.send(f"Couldnt find '{coin_identifier}'. Try `!search {coin_identifier}`")
        return
    
    price = get_crypto_price(coin['id'])
    change = get_price_change(coin['id'])
    
    if price:
        embed = discord.Embed(
            title=f"{coin['name']} ({coin['symbol'].upper()})",
            color=discord.Color.green() if change and change >= 0 else discord.Color.red() if change else discord.Color.blue(),
            timestamp=datetime.now(),
            url=f"https://www.coingecko.com/en/coins/{coin['id']}"
        )
        
        embed.add_field(name="Current Price", value=f"**${price:,.4f}**", inline=True)
        
        if change is not None:
            arrow = "📈" if change >= 0 else "📉"
            embed.add_field(name="24h Change", value=f"{arrow} {change:+.2f}%", inline=True)
        
        embed.add_field(name="CoinGecko ID", value=f"`{coin['id']}`", inline=True)
        embed.set_footer(text="Data from CoinGecko")
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Could not fetch price for {coin['name']}.")

def get_price_change(coin_id):
    """Get 24h price change for a coin."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        
        headers = {}
        api_key = os.getenv('COINGECKO_API_KEY')
        if api_key:
            headers['x-cg-demo-api-key'] = api_key
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if coin_id in data and 'usd_24h_change' in data[coin_id]:
            return data[coin_id]['usd_24h_change']
    except:
        pass
    return None

# ----- MEXC COMMANDS -----
@bot.command(name='mexc', help='Get MEXC exchange price')
async def mexc_price(ctx, coin: str = None):
    """Get MEXC exchange price."""
    if coin is None:
        PAIRS = get_top_coins(10)
        
        embed = discord.Embed(
            title="MEXC PRICE CHECK",
            description="Get real-time prices from MEXC exchange",
            color=0x00ff99
        )
        
        embed.add_field(
            name="Usage",
            value="`!mexc btc` - Get BTC/USDT price\n`!mexc_all` - Top 20 prices\n`!mexc sol` - Get SOL price",
            inline=False
        )
        
        if PAIRS:
            top_coins = "\n".join([f"• {c}" for c in list(PAIRS.keys())[:10]])
            embed.add_field(name="Top 10 Coins", value=top_coins, inline=False)
        
        embed.set_footer(text="Real-time data from MEXC")
        await ctx.send(embed=embed)
        return
    
    coin = coin.upper()
    PAIRS = get_top_coins(TOP_N)
    
    if coin not in PAIRS:
        await ctx.send(f"{coin} not in top {TOP_N} coins on MEXC.")
        return
    
    data = get_mexc_price(PAIRS[coin])
    
    if not data:
        await ctx.send(f"Could not fetch data for {coin}.")
        return
    
    change = float(data.get("priceChangePercent", 0))
    last_price = float(data.get("lastPrice", 0))
    high = float(data.get("highPrice", 0))
    low = float(data.get("lowPrice", 0))
    volume = float(data.get("quoteVolume", 0))
    
    embed = discord.Embed(
        title=f"{coin}USDT - MEXC",
        color=0x00ff99 if change >= 0 else 0xff3333,
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Last Price", value=f"**{fmt(last_price)}**", inline=True)
    embed.add_field(name="24h Change", value=f"**{change:+.2f}%** {'🟢' if change >= 0 else '🔴'}", inline=True)
    embed.add_field(name="24h High", value=fmt(high), inline=True)
    embed.add_field(name="24h Low", value=fmt(low), inline=True)
    embed.add_field(name="24h Volume", value=f"${volume:,.0f}", inline=True)
    
    # Add price chart emoji visualization
    price_range = high - low
    if price_range > 0:
        current_position = (last_price - low) / price_range
        chart_bar = "─" * 20
        chart = chart_bar[:int(current_position * 20)] + "🔘" + chart_bar[int(current_position * 20):]
        embed.add_field(name="Price Position", value=f"`{chart}`", inline=False)
    
    embed.set_footer(text="MEXC Exchange • Updated real-time")
    await ctx.send(embed=embed)

@bot.command(name='mexc_all', help='Show all MEXC top 20 prices')
async def mexc_all(ctx):
    """Show all MEXC top 20 prices."""
    PAIRS = get_top_coins(TOP_N)
    
    if not PAIRS:
        await ctx.send("Could not fetch MEXC data.")
        return
    
    embed = discord.Embed(
        title="MEXC TOP 20 LIVE PRICES",
        color=0x00ff99,
        timestamp=datetime.now()
    )
    
    for name, symbol in list(PAIRS.items())[:20]:
        data = get_mexc_price(symbol)
        if data:
            price = fmt(data.get("lastPrice", 0))
            change = float(data.get("priceChangePercent", 0))
            arrow = "🟢 ▲" if change >= 0 else "🔴 ▼"
            
            embed.add_field(
                name=f"{name}USDT",
                value=f"{price}\n{arrow} {change:+.2f}%",
                inline=True
            )
    
    embed.set_footer(text="Real-time data • Updates every 60s in price channel")
    await ctx.send(embed=embed)

# ----- NEWS COMMANDS -----
@bot.command(name='news', help='Get latest crypto news')
async def news_command(ctx, count: int = 5):
    """Get latest crypto news."""
    news = get_crypto_news()
    
    if not news:
        await ctx.send("Could not fetch news at the moment.")
        return
    
    count = min(max(count, 1), 10)
    
    embed = discord.Embed(
        title="LATEST CRYPTO NEWS",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    for i, item in enumerate(news[:count], 1):
        source_emoji = "📰" if "CoinDesk" in item['source'] else "📖" if "CoinTelegraph" in item['source'] else "🥔" if "CryptoPotato" in item['source'] else "🔐"
        
        embed.add_field(
            name=f"{source_emoji} {item['source']}",
            value=f"[{item['title']}]({item['link']})",
            inline=False
        )
    
    embed.set_footer(text=f"Showing {min(len(news), count)} news items • Auto-news in news channel")
    await ctx.send(embed=embed)

# ----- SEARCH & INFO COMMANDS -----
@bot.command(name='search', help='Search for cryptocurrencies')
async def search_coin(ctx, *, query: str):
    """Search for cryptocurrencies."""
    query = query.lower().strip()
    
    if len(query) < 2:
        await ctx.send("Please enter at least 2 characters to search.")
        return
    
    results = []
    for coin in coin_cache['all_coins']:
        if (query in coin['id'].lower() or 
            query in coin['symbol'].lower() or 
            query in coin['name'].lower()):
            results.append(coin)
    
    if not results:
        await ctx.send(f"No cryptocurrencies found for '{query}'")
        return
    
    results.sort(key=lambda x: (
        not (x['symbol'].lower() == query),
        not (x['id'].lower() == query),
        not (x['name'].lower() == query)
    ))
    
    embed = discord.Embed(
        title=f"SEARCH RESULTS: '{query}'",
        description=f"Found {len(results)} cryptocurrencies",
        color=discord.Color.blue()
    )
    
    for i, coin in enumerate(results[:8]):
        embed.add_field(
            name=f"{i+1}. {coin['name']} ({coin['symbol'].upper()})",
            value=f"ID: `{coin['id']}`",
            inline=False
        )
    
    if len(results) > 8:
        embed.set_footer(text=f"Showing 8 of {len(results)} results • Be more specific for better results")
    
    await ctx.send(embed=embed)

@bot.command(name='coin_info', help='Get detailed info about a cryptocurrency')
async def coin_info(ctx, *, coin_identifier: str):
    """Get detailed information about a coin."""
    coin = find_coin(coin_identifier)
    
    if not coin:
        await ctx.send(f"Couldnt find '{coin_identifier}'.")
        return
    
    price = get_crypto_price(coin['id'])
    
    embed = discord.Embed(
        title=f"{coin['name']} ({coin['symbol'].upper()})",
        description=f"CoinGecko ID: `{coin['id']}`",
        color=discord.Color.blue(),
        url=f"https://www.coingecko.com/en/coins/{coin['id']}"
    )
    
    if price:
        embed.add_field(name="Current Price", value=f"**${price:,.4f}**", inline=True)
    
    embed.add_field(name="Symbol", value=coin['symbol'].upper(), inline=True)
    
    # Try to get market data
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin['id']}"
        headers = {}
        api_key = os.getenv('COINGECKO_API_KEY')
        if api_key:
            headers['x-cg-demo-api-key'] = api_key
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            market_data = data.get('market_data', {})
            
            if 'market_cap' in market_data and 'usd' in market_data['market_cap']:
                market_cap = market_data['market_cap']['usd']
                embed.add_field(name="Market Cap", value=f"${market_cap:,.0f}", inline=True)
            
            if 'total_volume' in market_data and 'usd' in market_data['total_volume']:
                volume = market_data['total_volume']['usd']
                embed.add_field(name="24h Volume", value=f"${volume:,.0f}", inline=True)
            
            if 'price_change_percentage_24h' in market_data:
                change_24h = market_data['price_change_percentage_24h']
                change_emoji = "📈" if change_24h > 0 else "📉"
                embed.add_field(name="24h Change", value=f"{change_emoji} {change_24h:+.2f}%", inline=True)
            
            if 'description' in data and 'en' in data['description']:
                description = data['description']['en']
                if len(description) > 300:
                    description = description[:300] + "..."
                embed.add_field(name="Description", value=description, inline=False)
    except:
        pass
    
    embed.set_footer(text="Use !set_alert to create price alerts")
    await ctx.send(embed=embed)

# ----- UTILITY COMMANDS -----
@bot.command(name='stats', help='Show bot statistics')
async def bot_stats(ctx):
    """Show bot statistics."""
    alerts = load_alerts()
    
    total_alerts = 0
    active_alerts = 0
    triggered_alerts = 0
    unique_users = 0
    unique_coins = set()
    
    for user_id, user_alerts in alerts.items():
        unique_users += 1
        total_alerts += len(user_alerts)
        active_alerts += len([a for a in user_alerts if not a['triggered']])
        triggered_alerts += len([a for a in user_alerts if a['triggered']])
        unique_coins.update([a['coin_id'] for a in user_alerts])
    
    embed = discord.Embed(
        title="BOT STATISTICS",
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Bot Status", value="Online", inline=True)
    embed.add_field(name="Total Users", value=str(unique_users), inline=True)
    embed.add_field(name="Total Alerts", value=str(total_alerts), inline=True)
    embed.add_field(name="Active Alerts", value=str(active_alerts), inline=True)
    embed.add_field(name="Triggered Alerts", value=str(triggered_alerts), inline=True)
    embed.add_field(name="Tracked Coins", value=str(len(unique_coins)), inline=True)
    embed.add_field(name="Coin Database", value=f"{len(coin_cache.get('all_coins', [])):,}", inline=True)
    embed.add_field(name="Posted News", value=str(len(posted_news)), inline=True)
    embed.add_field(name="Update Interval", value=f"{UPDATE_INTERVAL}s", inline=True)
    
    if coin_list_last_updated:
        hours_ago = (datetime.now() - coin_list_last_updated).seconds // 3600
        embed.add_field(
            name="Coin List Updated", 
            value=f"{hours_ago}h ago",
            inline=True
        )
    
    embed.set_footer(text=f"Server: {ctx.guild.name if ctx.guild else 'DM'}")
    await ctx.send(embed=embed)

@bot.command(name='refresh_coins', help='Force refresh the coin list (Admin only)')
@commands.has_permissions(administrator=True)
async def refresh_coins(ctx):
    """Force refresh coin list."""
    await ctx.send("Refreshing coin list from CoinGecko...")
    get_all_coingecko_coins(force_refresh=True)
    await ctx.send(f"Coin list refreshed! Now tracking {len(coin_cache['all_coins'])} cryptocurrencies.")

@bot.command(name='commands', aliases=['cmds', 'help'], help='Show all available commands')
async def show_commands(ctx):
    """Show help menu with FUN."""
    embed = discord.Embed(
        title="CRYPTO BOT COMMAND GUIDE",
        description="One bot with all features: Alerts, Prices, News & More! Get ready to make money!",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    categories = [
        ("FUN COMMANDS", [
            ("!gm", "Good morning!"),
            ("!gn", "Good night!"),
            ("!lfg", "LFG!"),
            ("!moon", "Moon mission!")
        ]),
        ("ALERT COMMANDS", [
            ("!set_alert [coin] [price]", "Set price alert"),
            ("!my_alerts", "View your alerts"),
            ("!alerts_detailed", "Detailed alerts list"),
            ("!delete_alert [number]", "Delete specific alert"),
            ("!clear_alerts", "Clear all your alerts")
        ]),
        ("PRICE COMMANDS", [
            ("!price", "All top coin prices"),
            ("!volume", "All top coin volumes"),
            ("!btc, !eth, !sol, etc.", "Individual coin info"),
            ("!btc price / !sol volume", "Specific coin data"),
            ("!btc h/l", "High/Low for BTC"),
            ("!sol s/r", "Support/Resistance for SOL"),
            ("!sol support", "Support levels for SOL"),
            ("!sol resistance", "Resistance levels for SOL"),
            ("!mexc [coin]", "MEXC exchange price"),
            ("!mexc_all", "Top 20 MEXC prices"),
            ("!price_gecko [coin]", "Any CoinGecko coin")
        ]),
        ("NEWS COMMANDS", [
            ("!news [count]", "Latest crypto news")
        ]),
        ("INFO COMMANDS", [
            ("!search [query]", "Search cryptocurrencies"),
            ("!coin_info [coin]", "Detailed coin info")
        ]),
        ("BOT COMMANDS", [
            ("!stats", "Bot statistics"),
            ("!commands / !help", "This help menu"),
            ("!refresh_coins", "Refresh coin list (Admin)")
        ])
    ]
    
    for category_name, commands_list in categories:
        commands_text = "\n".join([f"• `{cmd}` - {desc}" for cmd, desc in commands_list])
        embed.add_field(name=category_name, value=commands_text, inline=False)
    
    examples = (
        "QUICK START EXAMPLES:\n"
        "• `!gm` - Start your day right!\n"
        "• `!price` - All top coins\n"
        "• `!btc` or `!btc price` - Bitcoin price\n"
        "• `!btc volume` - Bitcoin volume\n"
        "• `!sol h/l` - Solana high/low\n"
        "• `!sol s/r` - Solana support/resistance\n"
        "• `!sol support` - Solana support levels\n"
        "• `!sol resistance` - Solana resistance levels\n"
        "• `!set_alert bitcoin 100000` - Set alert\n"
        "• `!mexc sol` or `!mexc_all` - MEXC prices\n"
        "• `!news 3` - Latest news\n"
        "• `!lfg` - Get hyped!"
    )
    
    embed.add_field(name="GET STARTED", value=examples, inline=False)
    
    # Channel info
    channel_info = []
    if ALERTS_CHANNEL_ID:
        channel_info.append(f"Alerts: <#{ALERTS_CHANNEL_ID}>")
    if PRICE_CHANNEL_ID:
        channel_info.append(f"Prices: <#{PRICE_CHANNEL_ID}>")
    if NEWS_CHANNEL_ID:
        channel_info.append(f"News: <#{NEWS_CHANNEL_ID}>")
    if CHAT_CHANNEL_ID:
        channel_info.append(f"Chat: <#{CHAT_CHANNEL_ID}>")
    
    if channel_info:
        embed.add_field(name="CHANNELS", value="\n".join(channel_info), inline=False)
    
    embed.set_footer(text=f"Tracking {len(coin_cache.get('all_coins', [])):,} cryptocurrencies • Lets make money!")
    
    message = await ctx.send(embed=embed)
    await message.add_reaction("🎮")
    await message.add_reaction("🚀")
    await message.add_reaction("💰")

# ==================== ERROR HANDLING ====================
@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"Command not found. Use `!commands` to see all commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument. Check usage with `!commands`")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You dont have permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Please check your input.")
    else:
        logging.error(f"Command error: {error}")
        await ctx.send(f"An error occurred: `{str(error)[:100]}`")

# ==================== RUN BOT ====================
if __name__ == "__main__":

    print("Starting ENHANCED Crypto Bot...")
    print(f"Token: {'✅ Loaded' if TOKEN else '❌ Missing'}")
    print(
        f"Channels configured: "
        f"{sum(1 for x in [ALERTS_CHANNEL_ID, PRICE_CHANNEL_ID, NEWS_CHANNEL_ID, CHAT_CHANNEL_ID] if x)}/4"
    )

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Failed to login. Check your DISCORD_TOKEN environment variable")
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
