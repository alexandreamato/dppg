"""Text templates and layout constants for the VASOSCREEN-style report."""

# Page layout (A4 in points: 595.28 x 841.89)
PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN_LEFT = 50
MARGIN_RIGHT = 50
MARGIN_TOP = 50
MARGIN_BOTTOM = 50
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

# Font sizes
FONT_TITLE = 16
FONT_SUBTITLE = 11
FONT_BODY = 9
FONT_SMALL = 7.5
FONT_TABLE = 8.5

# Colors (RGB 0-1)
COLOR_CYAN = (0, 0.6, 0.8)
COLOR_RED = (0.8, 0, 0)
COLOR_BLACK = (0, 0, 0)
COLOR_GRAY = (0.4, 0.4, 0.4)
COLOR_LIGHT_GRAY = (0.85, 0.85, 0.85)

# Chart dimensions (in points)
CHART_WIDTH = 220
CHART_HEIGHT = 130
CHART_SPACING = 15
DIAGNOSTIC_CHART_WIDTH = 250
DIAGNOSTIC_CHART_HEIGHT = 180

# Method description text (boilerplate)
METHOD_TEXT = (
    "D-PPG (Digital Photoplethysmography) - Fotopletismografia digital para avaliação "
    "da função da bomba muscular venosa dos membros inferiores. "
    "O paciente realiza 8 movimentos de dorsiflexão dos pés em 16 segundos, "
    "seguido de período de repouso para avaliação do reenchimento venoso. "
    "O exame é realizado com e sem garrote (tourniquet) acima do joelho para "
    "diferenciação de insuficiência venosa superficial e profunda."
)

# Parameter descriptions for the report
PARAM_DESCRIPTIONS = {
    "To": "Venous refilling time (s)",
    "Th": "Half-amplitude time (s)",
    "Ti": "Initial inflow time (s)",
    "Vo": "Venous pump power (%)",
    "Fo": "Venous pump capacity (%s)",
    "tau": "Exponential time constant (s)",
}

# Channel display order for the report grid (2x2)
# Top-left: MIE s/Tq, Top-right: MIE c/Tq
# Bottom-left: MID s/Tq, Bottom-right: MID c/Tq
CHANNEL_GRID = [
    [0xDF, 0xE0],  # Top row: MIE s/Tq, MIE c/Tq
    [0xE1, 0xE2],  # Bottom row: MID s/Tq, MID c/Tq
]

# Classification table headers
CLASSIFICATION_HEADERS = ["Membro", "Condição", "Classificação", "Bomba Muscular"]

# Diagnostic chart point info: label_byte -> (point_number, color_name)
# Matches the scatter chart dot numbering/coloring
CHANNEL_POINT_INFO = {
    0xDF: (1, 'blue'),     # MIE s/Tq
    0xE1: (2, 'red'),      # MID s/Tq
    0xE0: (3, 'green'),    # MIE c/Tq
    0xE2: (4, 'orange'),   # MID c/Tq
}
