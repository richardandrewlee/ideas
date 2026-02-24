"""
Key Detector
-------------
Detects the musical key and mode of a song from MIDI note data
and/or Spotify audio features.

Uses the Krumhansl-Schmuckler key-finding algorithm: builds a pitch-class
histogram from non-drum notes (weighted by duration × velocity), then
correlates against standard major/minor key profiles.
"""

import math
import logging
from typing import Optional

from .midi_parser import ParsedMidi
from .song_dna import SongKey, Mode

logger = logging.getLogger(__name__)


class KeyDetector:
    """Detects key and mode from MIDI or Spotify data."""

    # Krumhansl-Kessler key profiles (empirically derived)
    MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

    def detect(
        self,
        parsed_midi: Optional[ParsedMidi] = None,
        spotify_features: Optional[dict] = None,
    ) -> tuple[Optional[SongKey], Optional[Mode], float]:
        """Best-effort key detection using all available data.

        Returns (key, mode, confidence). Confidence is 0.0-1.0.
        """
        midi_result = None
        spotify_result = None

        if parsed_midi is not None:
            midi_result = self.detect_from_midi(parsed_midi)

        if spotify_features is not None and spotify_features.get("key") is not None:
            spotify_result = self.detect_from_spotify(
                spotify_features["key"],
                spotify_features.get("mode", 0),
            )

        # Decide which to trust
        if midi_result and spotify_result:
            midi_key, midi_mode, midi_conf = midi_result
            sp_key, sp_mode, sp_conf = spotify_result
            # If they agree, boost confidence
            if midi_key == sp_key and midi_mode == sp_mode:
                return midi_key, midi_mode, min(1.0, (midi_conf + sp_conf) / 2 + 0.15)
            # If MIDI confidence is strong, prefer it
            if midi_conf >= 0.6:
                return midi_result
            # Otherwise prefer Spotify (generally reliable)
            return spotify_result
        elif midi_result:
            return midi_result
        elif spotify_result:
            return spotify_result
        else:
            return None, None, 0.0

    def detect_from_midi(self, parsed: ParsedMidi) -> tuple[Optional[SongKey], Optional[Mode], float]:
        """Detect key from MIDI note data using Krumhansl-Schmuckler algorithm."""
        # Check for explicit key signature in MIDI metadata
        if parsed.key_signature is not None:
            pitch_class, mode_int = parsed.key_signature
            key = SongKey(pitch_class % 12)
            mode = Mode.MINOR if mode_int == 1 else Mode.MAJOR
            # Trust MIDI key sig but not 100% — sometimes inaccurate
            return key, mode, 0.75

        # Build pitch-class histogram from non-drum notes
        histogram = self._build_pitch_histogram(parsed)
        if sum(histogram) == 0:
            return None, None, 0.0

        return self._correlate_profiles(histogram)

    def detect_from_spotify(self, key: int, mode: int) -> tuple[SongKey, Mode, float]:
        """Convert Spotify key/mode integers to SongDNA types.

        Spotify: key = 0-11 (C=0, C#=1, ..., B=11), mode = 0 (minor) or 1 (major).
        """
        song_key = SongKey(key % 12)
        song_mode = Mode.MAJOR if mode == 1 else Mode.MINOR
        return song_key, song_mode, 0.85  # Spotify is generally accurate

    def _build_pitch_histogram(self, parsed: ParsedMidi) -> list[float]:
        """Build a duration×velocity weighted pitch-class histogram from non-drum notes."""
        histogram = [0.0] * 12

        for track in parsed.tracks:
            # Skip drum tracks
            if track.channel == 9:
                continue

            for note in track.notes:
                if note.channel == 9:
                    continue
                pitch_class = note.pitch % 12
                # Weight by duration and velocity
                duration = max(note.duration_ticks, 1)  # At least 1 tick
                weight = duration * (note.velocity / 127.0)
                histogram[pitch_class] += weight

        # Normalize
        total = sum(histogram)
        if total > 0:
            histogram = [h / total for h in histogram]

        return histogram

    def _correlate_profiles(self, histogram: list[float]) -> tuple[Optional[SongKey], Optional[Mode], float]:
        """Correlate histogram against all 24 key profiles, return best match."""
        best_key = None
        best_mode = None
        best_corr = -1.0

        for root in range(12):
            # Rotate histogram so 'root' aligns with index 0
            rotated = histogram[root:] + histogram[:root]

            # Correlate with major profile
            major_corr = self._pearson_correlation(rotated, self.MAJOR_PROFILE)
            if major_corr > best_corr:
                best_corr = major_corr
                best_key = SongKey(root)
                best_mode = Mode.MAJOR

            # Correlate with minor profile
            minor_corr = self._pearson_correlation(rotated, self.MINOR_PROFILE)
            if minor_corr > best_corr:
                best_corr = minor_corr
                best_key = SongKey(root)
                best_mode = Mode.MINOR

        # Convert correlation (-1..1) to confidence (0..1)
        confidence = max(0.0, min(1.0, (best_corr + 1.0) / 2.0))

        return best_key, best_mode, confidence

    @staticmethod
    def _pearson_correlation(x: list[float], y: list[float]) -> float:
        """Pearson correlation coefficient between two lists."""
        n = len(x)
        if n == 0:
            return 0.0

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

        if std_x == 0 or std_y == 0:
            return 0.0

        return cov / (std_x * std_y)
