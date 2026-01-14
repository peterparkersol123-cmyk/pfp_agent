"""
Pump.fun API client for fetching real-time ecosystem data.
Enables Pepe to talk about actual trending coins, rugs, and live data.
Uses DexScreener API as primary source (more reliable than Pump.fun direct API).
"""

import requests
import time
import random
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.helpers import calculate_exponential_backoff

logger = get_logger(__name__)


class PumpFunClient:
    """Client for fetching Pump.fun ecosystem data via DexScreener."""

    def __init__(self):
        """Initialize Pump.fun data client."""
        # DexScreener is more reliable for Solana/Pump.fun data
        self.dexscreener_url = "https://api.dexscreener.com/latest/dex"

        # Search for Raydium pairs (where Pump.fun tokens graduate to)
        self.solana_dex = "raydium"

        # $PFP token pair address
        self.pfp_pair_address = "GdfCd7L8X1GiUdFZ1WthNHEB352K3Ni37rswtjgmGLPt"

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })

        # Cache for reducing API calls
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes

        logger.info("Initialized PumpFunClient (using DexScreener)")

    def get_trending_tokens(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get trending tokens (using Solana/Raydium as proxy for Pump.fun ecosystem).

        Args:
            limit: Number of trending tokens to fetch

        Returns:
            List of trending token data
        """
        cache_key = f"trending_{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            logger.debug(f"Fetching trending Solana tokens via DexScreener")

            # Get trending pairs on Solana (many Pump.fun tokens graduate here)
            url = f"{self.dexscreener_url}/search/?q=SOL"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                pairs = data.get('pairs', [])

                # Filter for Solana pairs with good volume
                solana_pairs = [
                    p for p in pairs
                    if p.get('chainId') == 'solana' and
                    p.get('volume', {}).get('h24', 0) > 1000
                ]

                # Sort by 24h volume
                solana_pairs.sort(
                    key=lambda x: float(x.get('volume', {}).get('h24', 0) or 0),
                    reverse=True
                )

                # Format tokens
                tokens = []
                for pair in solana_pairs[:limit]:
                    token = {
                        'name': pair.get('baseToken', {}).get('name', 'Unknown'),
                        'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                        'price_usd': pair.get('priceUsd', 0),
                        'volume_24h': pair.get('volume', {}).get('h24', 0),
                        'price_change_24h': pair.get('priceChange', {}).get('h24', 0),
                        'liquidity': pair.get('liquidity', {}).get('usd', 0),
                        'address': pair.get('baseToken', {}).get('address', ''),
                    }
                    tokens.append(token)

                self._set_cache(cache_key, tokens)
                logger.info(f"Fetched {len(tokens)} trending Solana tokens")
                return tokens
            else:
                logger.warning(f"DexScreener API returned {response.status_code}")
                return self._get_fallback_trending(limit)

        except Exception as e:
            logger.error(f"Error fetching trending tokens: {e}")
            return self._get_fallback_trending(limit)

    def get_recent_launches(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recently launched tokens (simulated from trending + randomness).

        Args:
            limit: Number of recent launches to fetch

        Returns:
            List of recent token launches
        """
        cache_key = f"recent_{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            logger.debug(f"Fetching recent Solana launches")

            # Get trending as base (newer tokens tend to be trending)
            trending = self.get_trending_tokens(limit=limit * 2)

            # Filter for tokens with recent activity (proxy for new launches)
            recent = [
                t for t in trending
                if t.get('volume_24h', 0) > 500  # Has some activity
            ]

            # Add some randomization to simulate "recent launches"
            random.shuffle(recent)
            recent = recent[:limit]

            self._set_cache(cache_key, recent)
            logger.info(f"Generated {len(recent)} recent launches")
            return recent

        except Exception as e:
            logger.error(f"Error fetching recent launches: {e}")
            return self._get_fallback_trending(limit)

    def get_token_info(self, token_address: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed info about a specific token.

        Args:
            token_address: Token contract address

        Returns:
            Token data or None
        """
        cache_key = f"token_{token_address}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            logger.debug(f"Fetching token info for {token_address[:8]}...")

            url = f"{self.dexscreener_url}/tokens/{token_address}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                pairs = data.get('pairs', [])

                if pairs:
                    pair = pairs[0]  # Use first pair
                    token_data = {
                        'name': pair.get('baseToken', {}).get('name', 'Unknown'),
                        'symbol': pair.get('baseToken', {}).get('symbol', '???'),
                        'price_usd': pair.get('priceUsd', 0),
                        'volume_24h': pair.get('volume', {}).get('h24', 0),
                        'price_change_24h': pair.get('priceChange', {}).get('h24', 0),
                        'liquidity': pair.get('liquidity', {}).get('usd', 0),
                        'market_cap': pair.get('fdv', 0),
                    }
                    self._set_cache(cache_key, token_data, ttl=60)
                    return token_data

            logger.warning(f"Token info API returned {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Error fetching token info: {e}")
            return None

    def get_pump_fun_stats(self) -> Dict[str, Any]:
        """
        Get overall Pump.fun platform statistics (estimated from ecosystem).

        Returns:
            Platform stats dictionary
        """
        cache_key = "platform_stats"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            logger.debug("Generating platform stats from ecosystem data")

            trending = self.get_trending_tokens(limit=20)

            # Calculate stats from trending tokens
            total_volume = sum(t.get('volume_24h', 0) for t in trending)
            avg_volume = total_volume / len(trending) if trending else 0

            stats = {
                'total_tokens': '50,000+',  # Estimated
                'volume_24h': f'${total_volume:,.0f}' if total_volume > 0 else '$1M+',
                'trades_24h': '10,000+',  # Estimated
                'avg_token_volume': f'${avg_volume:,.0f}' if avg_volume > 0 else 'N/A',
            }

            self._set_cache(cache_key, stats, ttl=600)
            logger.info("Generated platform stats")
            return stats

        except Exception as e:
            logger.error(f"Error fetching platform stats: {e}")
            return self._get_fallback_stats()

    def detect_rugs(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Detect potential rug pulls (tokens with suspicious activity).

        Args:
            hours: Look back period in hours

        Returns:
            List of suspicious tokens
        """
        cache_key = f"rugs_{hours}h"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            logger.debug(f"Detecting rugs from trending tokens")

            # Get trending tokens and analyze
            trending = self.get_trending_tokens(limit=50)

            rugs = []
            for token in trending:
                # Heuristics for rug detection
                price_change = token.get('price_change_24h', 0)
                liquidity = token.get('liquidity', 0)

                suspicious = False

                # Big price dump
                if price_change < -70:
                    suspicious = True

                # Very low liquidity
                if liquidity < 1000:
                    suspicious = True

                if suspicious:
                    rugs.append(token)

            self._set_cache(cache_key, rugs, ttl=300)
            logger.info(f"Detected {len(rugs)} suspicious tokens")
            return rugs

        except Exception as e:
            logger.error(f"Error detecting rugs: {e}")
            return []

    def get_solana_dex_data(self, token_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Get DEX data from DexScreener for Solana tokens.

        Args:
            token_address: Specific token to query (optional)

        Returns:
            DEX trading data
        """
        try:
            if token_address:
                url = f"{self.dexscreener_url}/tokens/{token_address}"
            else:
                url = f"{self.dexscreener_url}/search/?q=SOL"

            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                return {}

        except Exception as e:
            logger.error(f"Error fetching DEX data: {e}")
            return {}

    def get_trending_narrative(self) -> str:
        """
        Analyze trending tokens to identify current narrative/meta.

        Returns:
            String describing current narrative
        """
        cache_key = "narrative"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            trending = self.get_trending_tokens(limit=20)

            if not trending:
                return "degen chaos mode"

            # Analyze token names/symbols for patterns
            names = [t.get('name', '').lower() for t in trending if t.get('name')]
            symbols = [t.get('symbol', '').lower() for t in trending if t.get('symbol')]

            all_text = ' '.join(names + symbols)

            # Common themes
            themes = {
                'dog': ['dog', 'doge', 'shib', 'puppy', 'woof', 'inu'],
                'cat': ['cat', 'kitty', 'meow', 'neko'],
                'frog': ['frog', 'pepe', 'toad', 'ribbit'],
                'meme': ['meme', 'chad', 'wojak', 'based'],
                'ai': ['ai', 'gpt', 'bot', 'agent', 'agi'],
                'trump': ['trump', 'maga', 'donald'],
            }

            theme_counts = {}
            for theme, keywords in themes.items():
                count = sum(1 for keyword in keywords if keyword in all_text)
                if count > 0:
                    theme_counts[theme] = count

            if theme_counts:
                top_theme = max(theme_counts, key=theme_counts.get)
                narrative = f"{top_theme} season"
                self._set_cache(cache_key, narrative, ttl=600)
                return narrative

            return "general memecoin season"

        except Exception as e:
            logger.error(f"Error detecting narrative: {e}")
            return "degen chaos mode"

    def get_pfp_data(self) -> Optional[Dict[str, Any]]:
        """
        Get $PFP token data from DexScreener.

        Returns:
            $PFP token data with price, volume, change, etc.
        """
        cache_key = "pfp_data"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            logger.debug("Fetching $PFP token data from DexScreener")

            url = f"{self.dexscreener_url}/pairs/solana/{self.pfp_pair_address}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                pair = data.get('pair')

                if pair:
                    pfp_data = {
                        'name': 'Pump.fun Pepe',
                        'symbol': 'PFP',
                        'price_usd': float(pair.get('priceUsd', 0)),
                        'price_change_5m': float(pair.get('priceChange', {}).get('m5', 0)),
                        'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0)),
                        'price_change_6h': float(pair.get('priceChange', {}).get('h6', 0)),
                        'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0)),
                        'volume_5m': float(pair.get('volume', {}).get('m5', 0)),
                        'volume_1h': float(pair.get('volume', {}).get('h1', 0)),
                        'volume_6h': float(pair.get('volume', {}).get('h6', 0)),
                        'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
                        'liquidity': float(pair.get('liquidity', {}).get('usd', 0)),
                        'market_cap': float(pair.get('fdv', 0)),
                        'pair_address': self.pfp_pair_address,
                        'dexscreener_url': f'https://dexscreener.com/solana/{self.pfp_pair_address}',
                    }

                    self._set_cache(cache_key, pfp_data, ttl=60)  # 1 minute cache
                    logger.info(f"Fetched $PFP data: ${pfp_data['price_usd']:.8f} ({pfp_data['price_change_24h']:+.2f}%)")
                    return pfp_data

            logger.warning(f"$PFP data API returned {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Error fetching $PFP data: {e}")
            return None

    def get_context_for_content(self) -> Dict[str, Any]:
        """
        Get comprehensive context for content generation.

        Returns:
            Dictionary with ecosystem data for Pepe to reference
        """
        context = {
            'trending_tokens': [],
            'recent_launches': [],
            'platform_stats': {},
            'narrative': 'memecoin season',
            'suspicious_activity': [],
            'pfp_data': None,  # NEW: $PFP token data
            'timestamp': datetime.now().isoformat()
        }

        try:
            # Gather data (with timeouts)
            context['trending_tokens'] = self.get_trending_tokens(limit=5)
            context['recent_launches'] = self.get_recent_launches(limit=10)
            context['platform_stats'] = self.get_pump_fun_stats()
            context['narrative'] = self.get_trending_narrative()
            context['suspicious_activity'] = self.detect_rugs(hours=24)
            context['pfp_data'] = self.get_pfp_data()  # NEW: Fetch $PFP data

            logger.info("Built context for content generation")
            return context

        except Exception as e:
            logger.error(f"Error building context: {e}")
            return context

    def _get_cache(self, key: str) -> Optional[Any]:
        """Get cached data if not expired."""
        if key in self.cache:
            data, expiry = self.cache[key]
            if time.time() < expiry:
                logger.debug(f"Cache hit: {key}")
                return data
            else:
                del self.cache[key]
        return None

    def _set_cache(self, key: str, data: Any, ttl: Optional[int] = None):
        """Set cache with expiry."""
        ttl = ttl or self.cache_ttl
        expiry = time.time() + ttl
        self.cache[key] = (data, expiry)
        logger.debug(f"Cached: {key} (TTL: {ttl}s)")

    def _get_fallback_trending(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fallback data when API is unavailable (realistic Solana memecoins)."""
        fallback_tokens = [
            {'name': 'Bonk', 'symbol': 'BONK', 'price_change_24h': 5.2, 'volume_24h': 2500000},
            {'name': 'Dogwifhat', 'symbol': 'WIF', 'price_change_24h': -2.1, 'volume_24h': 1800000},
            {'name': 'Popcat', 'symbol': 'POPCAT', 'price_change_24h': 8.7, 'volume_24h': 950000},
            {'name': 'Myro', 'symbol': 'MYRO', 'price_change_24h': -5.3, 'volume_24h': 720000},
            {'name': 'Pepe Fork', 'symbol': 'PEPE2', 'price_change_24h': 15.4, 'volume_24h': 650000},
            {'name': 'Samo', 'symbol': 'SAMO', 'price_change_24h': 3.1, 'volume_24h': 580000},
            {'name': 'Retardio', 'symbol': 'RETARDIO', 'price_change_24h': -8.9, 'volume_24h': 420000},
            {'name': 'Silly Dragon', 'symbol': 'SILLY', 'price_change_24h': 22.1, 'volume_24h': 380000},
            {'name': 'Fartcoin', 'symbol': 'FARTCOIN', 'price_change_24h': -12.3, 'volume_24h': 310000},
            {'name': 'Ponke', 'symbol': 'PONKE', 'price_change_24h': 6.8, 'volume_24h': 290000},
        ]
        return fallback_tokens[:limit]

    def _get_fallback_stats(self) -> Dict[str, Any]:
        """Fallback stats when API is unavailable."""
        return {
            'total_tokens': '50,000+',
            'volume_24h': '$1.5M+',
            'trades_24h': '10,000+',
        }
