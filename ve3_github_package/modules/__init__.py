"""
VE3 Tool - Modules Package
==========================
"""

from modules.utils import (
    setup_logging,
    get_logger,
    load_settings,
    ConfigError,
    get_project_dir,
    ensure_project_structure,
    find_voice_file,
    parse_srt_file,
    group_srt_into_scenes,
    SrtEntry,
)

from modules.excel_manager import (
    PromptWorkbook,
    Character,
    Scene,
    CHARACTERS_COLUMNS,
    SCENES_COLUMNS,
)

from modules.voice_to_srt import (
    VoiceToSrt,
    convert_voice_to_srt,
    WhisperNotFoundError,
)

from modules.prompts_generator import (
    PromptGenerator,
    GeminiClient,
)

# Flows Lab Automation (Selenium - optional)
try:
    from modules.flowslab_automation import (
        FlowsLabClient,
        AccountManager,
        Account,
        DriverFactory,
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    FlowsLabClient = None
    AccountManager = None
    Account = None
    DriverFactory = None
    SELENIUM_AVAILABLE = False

from modules.google_flow_api import (
    GoogleFlowAPI,
    AspectRatio,
    ImageModel,
    GeneratedImage,
    create_flow_client,
    quick_generate,
)

from modules.flow_image_generator import (
    FlowImageGenerator,
    create_generator_from_config,
)

__all__ = [
    # Utils
    "setup_logging",
    "get_logger",
    "load_settings",
    "ConfigError",
    "get_project_dir",
    "ensure_project_structure",
    "find_voice_file",
    "parse_srt_file",
    "group_srt_into_scenes",
    "SrtEntry",
    
    # Excel Manager
    "PromptWorkbook",
    "Character",
    "Scene",
    "CHARACTERS_COLUMNS",
    "SCENES_COLUMNS",
    
    # Voice to SRT
    "VoiceToSrt",
    "convert_voice_to_srt",
    "WhisperNotFoundError",
    
    # Prompts Generator
    "PromptGenerator",
    "GeminiClient",
    
    # Flows Lab Automation (Selenium)
    "FlowsLabClient",
    "AccountManager",
    "Account",
    "DriverFactory",
    
    # Google Flow API (Direct API)
    "GoogleFlowAPI",
    "AspectRatio",
    "ImageModel",
    "GeneratedImage",
    "create_flow_client",
    "quick_generate",
    
    # Flow Image Generator (Pipeline Integration)
    "FlowImageGenerator",
    "create_generator_from_config",
    
    # Chrome Token Extractor
    "ChromeTokenExtractor",
    "ChromeAutoToken",
]

# Chrome Token Extractor (optional - requires selenium)
try:
    from modules.chrome_token_extractor import ChromeTokenExtractor
except ImportError:
    ChromeTokenExtractor = None

try:
    from modules.chrome_auto_token import ChromeAutoToken
except ImportError:
    ChromeAutoToken = None

try:
    from modules.auto_token import ChromeAutoToken as AutoToken
except ImportError:
    AutoToken = None
