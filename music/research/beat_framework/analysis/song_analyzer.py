"""
Song Analyzer
--------------
Orchestrates all Phase 1 analysis modules to produce a SongDNA
from MIDI files, Spotify audio features, or both.

This is the single entry point for full song analysis.
"""

import logging
from typing import Optional

from .midi_parser import MidiParser, ParsedMidi
from .key_detector import KeyDetector
from .instrument_identifier import InstrumentIdentifier
from .chord_extractor import ChordExtractor
from .structure_detector import StructureDetector
from .song_dna import SongDNA, SongKey, Mode

logger = logging.getLogger(__name__)


class SongAnalyzer:
    """Produces a SongDNA from MIDI, Spotify features, or both."""

    def __init__(self):
        self.midi_parser = MidiParser()
        self.key_detector = KeyDetector()
        self.instrument_identifier = InstrumentIdentifier()
        self.chord_extractor = ChordExtractor()
        self.structure_detector = StructureDetector()

        # Lazy import — drum_extractor may not be needed
        self._drum_extractor = None

    @property
    def drum_extractor(self):
        if self._drum_extractor is None:
            try:
                from .drum_extractor import DrumExtractor
                self._drum_extractor = DrumExtractor()
            except ImportError:
                logger.warning("DrumExtractor not available")
        return self._drum_extractor

    def analyze_midi(self, midi_path: str, genre: str = "", title: str = "", artist: str = "") -> SongDNA:
        """Full analysis from a MIDI file.

        Returns a SongDNA with key, chords, structure, instruments,
        energy curve, and drum patterns.
        """
        parsed = self.midi_parser.parse(midi_path)
        if parsed is None:
            raise ValueError(f"Could not parse MIDI file: {midi_path}")

        dna = SongDNA(source="midi", title=title, artist=artist, genre=genre)

        # Tempo
        dna.bpm = parsed.bpm
        dna.total_ticks = parsed.duration_ticks
        dna.total_bars = max(1, int(parsed.duration_bars))

        # Tempo map
        if parsed.tempo_map:
            dna.tempo_changes = [(tick, round(60_000_000 / us, 2)) for tick, us in parsed.tempo_map]

        # Time signature
        if parsed.time_signatures:
            _, num, denom = parsed.time_signatures[0]
            dna.time_signature_numerator = num
            dna.time_signature_denominator = denom

        # Key detection
        key, mode, conf = self.key_detector.detect_from_midi(parsed)
        dna.key = key
        dna.mode = mode
        dna.key_confidence = conf

        # Instrument identification
        dna.instruments = self.instrument_identifier.identify(parsed)
        dna.has_bass = any(i.name == "bass" for i in dna.instruments)
        dna.has_melody = any(
            i.name in ("melody", "synth_lead", "pipe", "reed")
            for i in dna.instruments
        )
        dna.has_chords = any(
            i.name in ("chords", "piano", "organ", "guitar", "synth_pad", "strings")
            for i in dna.instruments
        )
        dna.has_drums = any(i.is_drum for i in dna.instruments)

        # Chord extraction
        dna.chord_progression = self.chord_extractor.extract(
            parsed, parsed.ticks_per_beat, dna.instruments
        )

        # Structure detection
        dna.sections = self.structure_detector.detect(parsed, dna.chord_progression)

        # Energy curve
        dna.energy_curve = self.structure_detector.compute_energy_curve(parsed)

        # Drum patterns (if extractor available)
        if self.drum_extractor:
            try:
                dna.drum_patterns = self.drum_extractor.extract(parsed, genre=genre)
            except Exception as e:
                logger.debug(f"Drum extraction failed: {e}")

        return dna

    def analyze_spotify(self, track_features: dict) -> SongDNA:
        """Partial SongDNA from Spotify audio features alone.

        Useful when no MIDI is available — captures key, mode, BPM,
        and all audio features but no structure or chord detail.
        """
        dna = SongDNA(source="spotify")
        dna.title = track_features.get("title", "")
        dna.artist = track_features.get("artist", "")
        dna.year = track_features.get("year", 0)
        dna.genre = track_features.get("genre", "")
        dna.bpm = track_features.get("bpm", 120.0)

        # Time signature
        time_sig = track_features.get("time_sig", 4)
        dna.time_signature_numerator = time_sig if isinstance(time_sig, int) else 4

        # Key detection from Spotify
        if track_features.get("key") is not None:
            key, mode, conf = self.key_detector.detect_from_spotify(
                track_features["key"],
                track_features.get("mode", 0),
            )
            dna.key = key
            dna.mode = mode
            dna.key_confidence = conf

        # Audio features
        dna.danceability = track_features.get("danceability")
        dna.energy = track_features.get("energy")
        dna.valence = track_features.get("valence")
        dna.loudness = track_features.get("loudness")
        dna.acousticness = track_features.get("acousticness")
        dna.instrumentalness = track_features.get("instrumentalness")
        dna.speechiness = track_features.get("speechiness")
        dna.liveness = track_features.get("liveness")

        return dna

    def analyze_hybrid(self, midi_path: str, track_features: dict) -> SongDNA:
        """Full analysis combining MIDI structure + Spotify audio features.

        Best results: uses MIDI for structure, chords, instruments,
        and Spotify for audio features and key tiebreaking.
        """
        dna = self.analyze_midi(
            midi_path,
            genre=track_features.get("genre", ""),
            title=track_features.get("title", ""),
            artist=track_features.get("artist", ""),
        )
        dna.source = "hybrid"
        dna.year = track_features.get("year", dna.year)

        # Overlay Spotify audio features
        dna.danceability = track_features.get("danceability")
        dna.energy = track_features.get("energy")
        dna.valence = track_features.get("valence")
        dna.loudness = track_features.get("loudness")
        dna.acousticness = track_features.get("acousticness")
        dna.instrumentalness = track_features.get("instrumentalness")
        dna.speechiness = track_features.get("speechiness")
        dna.liveness = track_features.get("liveness")

        # Use Spotify key if MIDI detection was uncertain
        if dna.key_confidence < 0.5 and track_features.get("key") is not None:
            key, mode, conf = self.key_detector.detect_from_spotify(
                track_features["key"],
                track_features.get("mode", 0),
            )
            dna.key = key
            dna.mode = mode
            dna.key_confidence = conf

        # Use Spotify BPM if it seems more reliable
        spotify_bpm = track_features.get("bpm")
        if spotify_bpm and abs(spotify_bpm - dna.bpm) > 10:
            # Large discrepancy — Spotify is usually more reliable
            dna.bpm = spotify_bpm

        return dna
