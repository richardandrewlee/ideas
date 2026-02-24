"""
Magenta Generator
-----------------
Uses Google Magenta's DrumsRNN model to generate or continue drum sequences
conditioned on a genre/style seed, as a complement to the statistical generator.

This is OPTIONAL — the statistical generator works without Magenta.
Magenta provides more creative, musically interesting variations.

Setup (one-time):
    pip install magenta note-seq
    # Download DrumsRNN checkpoint:
    python -m magenta.models.drums_rnn.drums_rnn_generate \
        --config=drum_kit \
        --bundle_file=/path/to/drum_kit_rnn.mag \
        --output_dir=/tmp/drums_rnn/generated \
        --num_outputs=1 --num_steps=128 --primer_drums=""

    # Or GrooVAE checkpoint (for humanization):
    # https://storage.googleapis.com/magentadata/models/groovae/groovae_4bar.tar.gz
"""

import logging
import os
from pathlib import Path
from typing import Optional

from .statistical_generator import RawBeat
from ..analysis.pattern_analyzer import GenreProfile

logger = logging.getLogger(__name__)

# Default checkpoint locations
CHECKPOINT_DIRS = {
    "drums_rnn":  Path.home() / ".magenta" / "drums_rnn",
    "groovae":    Path.home() / ".magenta" / "groovae",
}


class MagentaGenerator:
    """
    Uses DrumsRNN to generate creative drum variations seeded by a GenreProfile.

    If Magenta is not installed or checkpoints are missing, gracefully degrades
    to returning the input beat unchanged (humanization via Humanizer still applies).
    """

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        temperature: float = 1.0,
    ):
        self.temperature   = temperature
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else CHECKPOINT_DIRS["drums_rnn"]
        self.available     = self._check_availability()

    def _check_availability(self) -> bool:
        try:
            import magenta  # noqa
            import note_seq  # noqa
        except ImportError:
            logger.info(
                "Magenta not installed. Statistical generation only. "
                "To enable: pip install magenta note-seq"
            )
            return False

        if not self.checkpoint_dir.exists():
            logger.info(
                f"Magenta checkpoint not found at {self.checkpoint_dir}. "
                "Statistical generation will be used."
            )
            return False

        return True

    def generate_continuation(
        self,
        seed_beat: RawBeat,
        num_steps: int = 128,
    ) -> Optional[RawBeat]:
        """
        Uses DrumsRNN to generate a drum continuation from a seed beat.

        Args:
            seed_beat:  Initial beat (used as primer sequence).
            num_steps:  How many steps to generate (128 = 8 bars at 16th notes).

        Returns:
            A new RawBeat from Magenta, or None if unavailable.
        """
        if not self.available:
            return None

        try:
            import note_seq
            from magenta.models.drums_rnn import drums_rnn_sequence_generator
            from magenta.models.shared import sequence_generator_bundle

            bundle_path = self.checkpoint_dir / "drum_kit_rnn.mag"
            if not bundle_path.exists():
                logger.warning(f"Bundle not found: {bundle_path}")
                return None

            bundle = sequence_generator_bundle.read_bundle_file(str(bundle_path))
            generator_map = drums_rnn_sequence_generator.get_generator_map()
            generator = generator_map["drum_kit"](checkpoint=None, bundle=bundle)
            generator.initialize()

            # Seed NoteSequence from the statistical beat
            primer_ns = self._beat_to_note_sequence(seed_beat)

            # Generate continuation
            generate_section = note_seq.generator_pb2.GeneratorOptions.GenerateSection()
            generate_section.start_time = seed_beat.duration_ticks / (seed_beat.ticks_per_beat * seed_beat.bpm / 60.0)
            generate_section.end_time   = generate_section.start_time + (num_steps / (4 * seed_beat.steps_per_bar)) * (60.0 / seed_beat.bpm)

            generator_options = note_seq.generator_pb2.GeneratorOptions()
            generator_options.args["temperature"].float_value = self.temperature
            generator_options.generate_sections.extend([generate_section])

            generated_ns = generator.generate(primer_ns, generator_options)

            return self._note_sequence_to_beat(generated_ns, seed_beat)

        except Exception as e:
            logger.error(f"Magenta DrumsRNN generation failed: {e}")
            return None

    def _beat_to_note_sequence(self, beat: RawBeat):
        import note_seq
        ns = note_seq.NoteSequence()
        ns.tempos.add(qpm=beat.bpm)
        ns.ticks_per_quarter = beat.ticks_per_beat

        seconds_per_tick = 60.0 / (beat.bpm * beat.ticks_per_beat)

        for hit in beat.hits:
            tick  = hit.step * beat.ticks_per_step + hit.tick_offset
            start = tick * seconds_per_tick

            note = ns.notes.add()
            note.pitch      = hit.midi_note
            note.velocity   = hit.velocity
            note.start_time = max(0.0, start)
            note.end_time   = max(0.0, start) + 0.05
            note.is_drum    = True
            note.instrument = 9

        ns.total_time = beat.duration_ticks * seconds_per_tick
        return ns

    def _note_sequence_to_beat(self, ns, template: RawBeat) -> RawBeat:
        from .statistical_generator import RawHit, RawBeat
        from ..analysis.drum_extractor import GM_DRUM_MAP, INSTRUMENT_TO_MIDI

        seconds_per_step = (60.0 / template.bpm) / (template.steps_per_bar / 4)

        new_beat = RawBeat(
            genre=template.genre,
            year=template.year,
            bpm=template.bpm,
            steps_per_bar=template.steps_per_bar,
            ticks_per_beat=template.ticks_per_beat,
        )
        new_beat.grid_steps = template.grid_steps

        for note in ns.notes:
            if not note.is_drum:
                continue
            step = int(round(note.start_time / seconds_per_step))
            if step >= new_beat.grid_steps:
                continue
            instrument = GM_DRUM_MAP.get(note.pitch, "snare")
            new_beat.hits.append(RawHit(
                instrument=instrument,
                midi_note=note.pitch,
                step=step,
                velocity=note.velocity,
                tick_offset=0,
            ))

        return new_beat
