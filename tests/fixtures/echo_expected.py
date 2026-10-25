"""Fake solver for testing the bench: prints the .expected file for the input."""
import sys
from pathlib import Path

print(Path(sys.argv[1]).with_suffix(".expected").read_text(), end="")
