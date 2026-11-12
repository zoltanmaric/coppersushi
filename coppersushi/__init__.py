"""Copper Sushi product paths; shared workspace tooling stays at repository root."""
from pathlib import Path
PRODUCT = Path(__file__).parent
PACKAGE = PRODUCT / 'pipelines'
REPO = PRODUCT.parent
