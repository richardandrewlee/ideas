"""
WAV Renderer
------------
Renders a MIDI file to WAV audio using FluidSynth and a GM soundfont.

Setup:
    # Install FluidSynth system package:
    brew install fluid-synth          # macOS
    sudo apt install fluidsynth       # Ubuntu/Debian

    # Install Python bindings:
    pip install pyfluidsynth

    # Download a GM soundfont (free):
    # https://musical-artifacts.com/artifacts/728  (GeneralUser GS)
    # https://www.zdoom.org/wiki/FluidSynth         (FluidR3_GM)
    # Set soundfont_path in config.yaml

Fallback:
    If FluidSynth is not available, attempts to use the `midi2audio` package.
    If neither is available, logs a warning and skips WAV rendering.
"""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Common soundfont locations (checked in order if soundfont_path not set)
DEFAULT_SOUNDFONT_PATHS = [
    Path.home() / ".local" / "share" / "sounds" / "sf2" / "GeneralUser_GS.sf2",
    Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
    Path("/usr/share/sounds/sf2/GeneralUser_GS.sf2"),
    Path("/Library/Audio/Sounds/Banks/GeneralUser.sf2"),
    Path.home() / "soundfonts" / "GeneralUser_GS.sf2",
]


class WavRenderer:
    """Renders MIDI to WAV using FluidSynth."""

    def __init__(self, soundfont_path: Optional[str] = None):
        self.soundfont_path = self._find_soundfont(soundfont_path)
        self.fluidsynth_available = shutil.which("fluidsynth") is not None
        self.pyfluidsynth_available = self._check_pyfluidsynth()

        if not self.soundfont_path:
            logger.warning(
                "No soundfont found. WAV rendering disabled. "
                "Download a GM soundfont and set soundfont_path in config.yaml. "
                "Recommended: https://musical-artifacts.com/artifacts/728"
            )
        elif not self.fluidsynth_available and not self.pyfluidsynth_available:
            logger.warning(
                "FluidSynth not found. WAV rendering disabled. "
                "Install with: brew install fluid-synth (macOS) or "
                "sudo apt install fluidsynth (Ubuntu)"
            )

    @property
    def available(self) -> bool:
        return bool(self.soundfont_path) and (
            self.fluidsynth_available or self.pyfluidsynth_available
        )

    def render(
        self,
        midi_path: str,
        output_path: str,
        sample_rate: int = 44100,
        gain: float = 1.0,
    ) -> Optional[str]:
        """
        Render a MIDI file to WAV.

        Args:
            midi_path:   Path to the source .mid file.
            output_path: Destination .wav path.
            sample_rate: Audio sample rate (default 44100 Hz).
            gain:        FluidSynth gain (0.0–5.0, default 1.0).

        Returns:
            output_path if successful, None otherwise.
        """
        if not self.available:
            logger.warning("WAV rendering skipped (FluidSynth/soundfont unavailable)")
            return None

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if self.pyfluidsynth_available:
            return self._render_pyfluidsynth(midi_path, output_path, sample_rate, gain)
        else:
            return self._render_cli(midi_path, output_path, sample_rate, gain)

    def _render_pyfluidsynth(
        self, midi_path: str, output_path: str, sample_rate: int, gain: float
    ) -> Optional[str]:
        try:
            import fluidsynth
            fs = fluidsynth.Synth(gain=gain, samplerate=float(sample_rate))
            sfid = fs.sfload(str(self.soundfont_path))
            fs.program_select(0, sfid, 0, 0)
            fs.midi_player_add(midi_path)
            fs.midi_player_play()

            import wave
            import array
            samples = []
            while fs.midi_player_get_status() == fluidsynth.FLUID_PLAYER_PLAYING:
                block = fs.get_samples(1024)
                samples.extend(block)

            fs.delete()

            with wave.open(output_path, "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(array.array("h", samples).tobytes())

            logger.info(f"WAV rendered (pyfluidsynth) → {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"pyfluidsynth rendering failed: {e}")
            return self._render_cli(midi_path, output_path, sample_rate, gain)

    def _render_cli(
        self, midi_path: str, output_path: str, sample_rate: int, gain: float
    ) -> Optional[str]:
        """Use the fluidsynth CLI tool."""
        cmd = [
            "fluidsynth",
            "-ni",                          # Non-interactive
            "-g", str(gain),                # Gain
            "-r", str(sample_rate),         # Sample rate
            "-F", output_path,              # Output file
            str(self.soundfont_path),       # Soundfont
            midi_path,                      # Input MIDI
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and Path(output_path).exists():
                logger.info(f"WAV rendered (CLI) → {output_path}")
                return output_path
            else:
                logger.error(f"FluidSynth CLI failed: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            logger.error("FluidSynth CLI timed out")
            return None
        except Exception as e:
            logger.error(f"FluidSynth CLI error: {e}")
            return None

    @staticmethod
    def _find_soundfont(provided: Optional[str]) -> Optional[Path]:
        if provided:
            p = Path(provided)
            return p if p.exists() else None
        for candidate in DEFAULT_SOUNDFONT_PATHS:
            if candidate.exists():
                logger.info(f"Found soundfont: {candidate}")
                return candidate
        return None

    @staticmethod
    def _check_pyfluidsynth() -> bool:
        try:
            import fluidsynth  # noqa
            return True
        except ImportError:
            return False
