import warnings

# Suppress specific SyntaxWarnings from third-party packages
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pydub.*")
warnings.filterwarnings("ignore", category=SyntaxWarning, module="syrics.*")

from .karaoke_gen import KaraokePrep
