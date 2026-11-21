"""Constants for the Liquipedia integration."""

DOMAIN = "liquipedia"

# Configuration
CONF_GAME = "game"
CONF_MODE = "mode"
CONF_TEAM_FILTER = "team_filter"
CONF_TEAM_NAME = "team_name"
CONF_TEAM_PAGES = "team_pages"
CONF_TOURNAMENT = "tournament"
MODE_TEAM = "team"
MODE_TOURNAMENT = "tournament"

# Defaults
DEFAULT_GAME = "leagueoflegends"
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes

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

# Games with a supported organization match feed
TEAM_GAMES = {
    "leagueoflegends": "League of Legends",
    "counterstrike": "Counter-Strike",
}

# API endpoints
LIQUIPEDIA_BASE_URL = "https://liquipedia.net"
LIQUIPEDIA_API_URL = "https://liquipedia.net/{game}/api.php"

# Headers
USER_AGENT = (
    "HomeAssistant-Liquipedia/1 "
    "(https://github.com/KevinBacas/hacs-liquipedia-integration/issues)"
)
