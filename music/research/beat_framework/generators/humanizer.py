"""
Humanizer
---------
Applies micro-timing and velocity variation to a RawBeat to make it
feel less mechanical — as if played by a real drummer.

Two modes:
    1. Statistical:  Pure Python. Applies Gaussian timing offsets and
                     velocity curves derived from the GenreProfile.

    2. Magenta:      Passes the beat through GrooVAE for learned humanization.
                     Requires magenta installed. Falls back to statistical if unavailable.

Swing:
    Applies a swing factor to even-numbered 16th note steps (steps 1, 3, 5, ...)
    to create triplet feel. A factor of 0 = straight; 0.33 = full triplet swing.
"""

import random
import logging
from typing import Optional

from .statistical_generator import RawBeat, RawHit
from ..analysis.pattern_analyzer import GenreProfile

logger = logging.getLogger(__name__)

# Genre-typical swing amounts (0 = straight, 0.33 = full triplet swing)
GENRE_SWING: dict[str, float] = {
    "jazz":     0.28,
    "blues":    0.20,
    "hip-hop":  0.15,
    "funk":     0.12,
    "soul":     0.12,
    "rnb":      0.10,
    "reggae":   0.08,
    "rock":     0.03,
    "pop":      0.02,
    "house":    0.00,
    "techno":   0.00,
    "edm":      0.00,
    "drum-and-bass": 0.05,
    "metal":    0.00,
}


class Humanizer:
    """Adds human feel to a RawBeat."""

    def __init__(
        self,
        seed: Optional[int] = None,
        use_magenta: bool = True,
    ):
        self.rng = random.Random(seed)
        self.use_magenta = use_magenta
        self._magenta_available = self._check_magenta()

    @staticmethod
    def _check_magenta() -> bool:
        try:
            import magenta  # noqa
            return True
        except ImportError:
            return False

    def humanize(
        self,
        beat: RawBeat,
        profile: GenreProfile,
        swing: Optional[float] = None,
        timing_strength: float = 1.0,
        velocity_strength: float = 1.0,
    ) -> RawBeat:
        """
        Applies humanization to all hits in-place and returns the beat.

        Args:
            beat:              The beat to humanize.
            profile:           Source GenreProfile for timing/velocity stats.
            swing:             Swing amount (0–0.33). If None, uses genre default.
            timing_strength:   Multiplier for timing variation (1.0 = normal).
            velocity_strength: Multiplier for velocity variation (1.0 = normal).

        Returns:
            The same RawBeat with tick_offset and velocity modified.
        """
        if self.use_magenta and self._magenta_available:
            try:
                return self._humanize_magenta(beat, profile, swing, timing_strength, velocity_strength)
            except Exception as e:
                logger.warning(f"Magenta humanization failed ({e}), falling back to statistical")

        return self._humanize_statistical(beat, profile, swing, timing_strength, velocity_strength)

    # -----------------------------------------------------------------------
    # Statistical humanization
    # -----------------------------------------------------------------------

    def _humanize_statistical(
        self,
        beat: RawBeat,
        profile: GenreProfile,
        swing: Optional[float],
        timing_strength: float,
        velocity_strength: float,
    ) -> RawBeat:
        swing_amount = swing if swing is not None else GENRE_SWING.get(profile.genre, 0.02)

        for hit in beat.hits:
            inst = hit.instrument

            # 1. Swing: delay odd 16th-note steps
            swing_offset = 0
            if swing_amount > 0:
                step_in_bar = hit.step % beat.steps_per_bar
                if step_in_bar % 2 == 1:  # odd 16th note steps
                    swing_offset = int(swing_amount * beat.ticks_per_step)

            # 2. Micro-timing: Gaussian offset per instrument
            timing_std = profile.timing_std.get(inst, 3.0) * timing_strength
            micro_offset = int(self.rng.gauss(0, timing_std))

            # 3. Clamp total offset to ±25% of step width
            max_offset = int(0.25 * beat.ticks_per_step)
            hit.tick_offset = max(-max_offset, min(max_offset, swing_offset + micro_offset))

            # 4. Velocity accent: beat-position aware
            vel_variation = self._velocity_accent(
                hit, beat, profile, velocity_strength
            )
            hit.velocity = max(1, min(127, hit.velocity + vel_variation))

        logger.debug(f"Statistical humanization applied to {len(beat.hits)} hits")
        return beat

    def _velocity_accent(
        self,
        hit: RawHit,
        beat: RawBeat,
        profile: GenreProfile,
        strength: float,
    ) -> int:
        """
        Returns a velocity delta based on metrical position.
        Beat 1 is strongest, beat 3 is second, off-beats are weaker.
        """
        step_in_bar = hit.step % beat.steps_per_bar
        vel_std = profile.velocity_std.get(hit.instrument, 8.0) * strength

        # Accent grid (relative strength by 16th note position in a 16-step bar)
        ACCENT = [
            1.00, 0.60, 0.70, 0.60,   # Beat 1
            0.75, 0.55, 0.65, 0.55,   # Beat 2
            0.90, 0.60, 0.70, 0.60,   # Beat 3
            0.75, 0.55, 0.65, 0.55,   # Beat 4
        ]
        accent_mul = ACCENT[step_in_bar % 16]
        natural_variation = self.rng.gauss(0, vel_std)
        accent_boost = (accent_mul - 0.7) * 20  # Center around 0

        return int(accent_boost + natural_variation * 0.5)

    # -----------------------------------------------------------------------
    # Full song humanization
    # -----------------------------------------------------------------------

    def humanize_song(
        self,
        song_beat,
        profile: GenreProfile,
        swing: Optional[float] = None,
    ):
        """Humanize a full SongBeat with section-aware dynamics.

        Scales timing tightness and velocity strength per section energy.
        Returns the same SongBeat with modified hits.
        """
        for section in song_beat.sections:
            # Scale humanization by section energy
            timing_strength = 0.5 + section.energy * 0.5
            velocity_strength = 0.7 + section.energy * 0.3

            # Build a temporary RawBeat for the section
            temp_beat = RawBeat(
                genre=song_beat.genre, year=song_beat.year,
                bpm=song_beat.bpm, hits=section.hits,
                grid_steps=section.bars * song_beat.steps_per_bar,
                steps_per_bar=song_beat.steps_per_bar,
            )
            self._humanize_statistical(temp_beat, profile, swing, timing_strength, velocity_strength)
            section.hits = temp_beat.hits

            # Also humanize transition hits
            if section.transition_hits:
                trans_beat = RawBeat(
                    genre=song_beat.genre, year=song_beat.year,
                    bpm=song_beat.bpm, hits=section.transition_hits,
                    grid_steps=song_beat.steps_per_bar * 2,
                    steps_per_bar=song_beat.steps_per_bar,
                )
                self._humanize_statistical(trans_beat, profile, swing, 1.0, 1.0)
                section.transition_hits = trans_beat.hits

        return song_beat

    # -----------------------------------------------------------------------
    # Magenta humanization
    # -----------------------------------------------------------------------

    def _humanize_magenta(
        self,
        beat: RawBeat,
        profile: GenreProfile,
        swing: Optional[float],
        timing_strength: float,
        velocity_strength: float,
    ) -> RawBeat:
        """
        Uses Magenta's GrooVAE to humanize the beat.

        GrooVAE encodes a quantized drum sequence and decodes it with
        learned timing and velocity variations from real drummers.
        """
        try:
            import note_seq
            from magenta.models.groovae import groove_vae
        except ImportError:
            raise ImportError("magenta / note_seq not installed")

        # Convert RawBeat → NoteSequence
        ns = self._beat_to_note_sequence(beat)

        # Run through GrooVAE (encode → sample → decode)
        # NOTE: Requires pre-downloaded checkpoint at ~/.magenta/groovae/
        try:
            model = groove_vae.GrooVAEModel(
                config=groove_vae.CONFIG_MAP["groovae_4bar"],
            )
            humanized_ns = model.humanize(ns, temperature=0.5 * timing_strength)
        except Exception as e:
            raise RuntimeError(f"GrooVAE inference failed: {e}")

        # Convert back to RawBeat
        return self._note_sequence_to_beat(humanized_ns, beat)

    def _beat_to_note_sequence(self, beat: RawBeat):
        """Converts RawBeat to a magenta NoteSequence."""
        try:
            import note_seq
        except ImportError:
            raise

        ns = note_seq.NoteSequence()
        ns.tempos.add(qpm=beat.bpm)
        ns.ticks_per_quarter = beat.ticks_per_beat

        seconds_per_tick = 60.0 / (beat.bpm * beat.ticks_per_beat)

        for hit in beat.hits:
            tick = hit.step * beat.ticks_per_step
            start = tick * seconds_per_tick
            end   = start + 0.05  # Drums are percussive; short duration

            note = ns.notes.add()
            note.pitch         = hit.midi_note
            note.velocity      = hit.velocity
            note.start_time    = start
            note.end_time      = end
            note.is_drum       = True
            note.instrument    = 9

        ns.total_time = beat.duration_ticks * seconds_per_tick
        return ns

    def _note_sequence_to_beat(self, ns, original_beat: RawBeat) -> RawBeat:
        """Converts a NoteSequence back to a RawBeat."""
        from .statistical_generator import RawHit, RawBeat, INSTRUMENT_TO_MIDI
        from ..analysis.drum_extractor import GM_DRUM_MAP

        seconds_per_tick = 60.0 / (original_beat.bpm * original_beat.ticks_per_beat)

        new_beat = RawBeat(
            genre=original_beat.genre,
            year=original_beat.year,
            bpm=original_beat.bpm,
            grid_steps=original_beat.grid_steps,
            steps_per_bar=original_beat.steps_per_bar,
            ticks_per_beat=original_beat.ticks_per_beat,
        )

        for note in ns.notes:
            if not note.is_drum:
                continue
            tick = note.start_time / seconds_per_tick
            step = int(round(tick / original_beat.ticks_per_step))
            tick_offset = int(tick - step * original_beat.ticks_per_step)
            instrument = GM_DRUM_MAP.get(note.pitch, "snare")

            new_beat.hits.append(RawHit(
                instrument=instrument,
                midi_note=note.pitch,
                step=step % original_beat.grid_steps,
                velocity=note.velocity,
                tick_offset=tick_offset,
            ))

        return new_beat
