"""Constants for the Liquipedia integration."""

DOMAIN = "liquipedia"

# Configuration
CONF_GAME = "game"
CONF_TOURNAMENT = "tournament"

# Defaults
DEFAULT_GAME = "leagueoflegends"
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes
MATCH_RUNNING_WINDOW = 4 * 60 * 60  # Matches are considered active for up to four hours.

# Supported games
SUPPORTED_GAMES = [
    "leagueoflegends",
    "counterstrike",
    "dota2",
    "valorant",
    "overwatch",
    "hearthstone",
    "starcraft",
    "starcraft2",
]

# API endpoints
LIQUIPEDIA_BASE_URL = "https://liquipedia.net"
LIQUIPEDIA_API_URL = "https://liquipedia.net/{game}/api.php"

# Headers
USER_AGENT = (
    "HomeAssistant-Liquipedia/0.2 "
    "(https://github.com/KevinBacas/hacs-liquipedia-integration)"
)
