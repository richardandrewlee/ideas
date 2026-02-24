"""
Beat Framework
==============
Generate genre-authentic drum beats informed by the top 100 songs
of any genre and year, using Spotify, Last.fm, Billboard, and the Lakh MIDI dataset.

Quick start:
    from beat_framework import BeatFramework

    fw = BeatFramework.from_config("config.yaml")
    beats = fw.generate(genre="house", year=2019, count=4)
    fw.export_all(beats, output_dir="./output")
"""

from .framework import BeatFramework

__all__ = ["BeatFramework"]
__version__ = "1.0.0"
