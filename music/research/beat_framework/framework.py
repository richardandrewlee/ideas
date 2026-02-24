"""
BeatFramework — Main Orchestrator
----------------------------------
Ties together all components: data collection → analysis → generation → export.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import yaml

from .collectors import (
    SpotifyCollector, LastFMCollector, BillboardCollector,
    BillboardStaticCollector, LakhCollector, SongAggregator,
)
from .analysis   import MidiParser, DrumExtractor, PatternAnalyzer, SongAnalyzer, SongDNA
from .generators import (
    StatisticalGenerator, Humanizer, MagentaGenerator,
    ArrangementEngine, SongGenerator,
    BassGenerator, HarmonyGenerator, MultiInstrumentGenerator, FullArrangement,
)
from .exporters  import MidiExporter, WavRenderer, JsonExporter
from .analysis.pattern_analyzer import GenreProfile
from .generators.statistical_generator import RawBeat

logger = logging.getLogger(__name__)


class BeatFramework:
    """
    High-level API for the beat generation framework.

    Usage:
        fw = BeatFramework.from_config("config.yaml")
        beats = fw.generate(genre="house", year=2019, count=4)
        fw.export_all(beats, output_dir="./output/house_2019")
    """

    def __init__(
        self,
        # Collector credentials (all optional)
        spotify_client_id:     Optional[str] = None,
        spotify_client_secret: Optional[str] = None,
        lastfm_api_key:        Optional[str] = None,
        lastfm_api_secret:     Optional[str] = None,
        lakh_path:             Optional[str] = None,
        genre_annotations_path: Optional[str] = None,
        soundfont_path:        Optional[str] = None,
        # Generation settings
        use_magenta:           bool = True,
        seed:                  Optional[int] = None,
        # Profile cache directory
        profile_cache_dir:     str = "./profiles",
        verbose:               bool = False,
    ):
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(level=log_level, format="%(levelname)s | %(name)s | %(message)s")

        # ── Collectors ──────────────────────────────────────────────────────
        spotify = None
        if spotify_client_id and spotify_client_secret:
            spotify = SpotifyCollector(spotify_client_id, spotify_client_secret)

        lastfm = None
        if lastfm_api_key:
            lastfm = LastFMCollector(lastfm_api_key, lastfm_api_secret or "")

        billboard = BillboardCollector()
        billboard_static = BillboardStaticCollector()

        lakh = None
        if lakh_path:
            lakh = LakhCollector(lakh_path, genre_annotations_path)

        self.aggregator = SongAggregator(
            spotify=spotify,
            lastfm=lastfm,
            billboard=billboard,
            billboard_static=billboard_static,
            lakh=lakh,
        )

        # ── Analysis ────────────────────────────────────────────────────────
        self.parser        = MidiParser()
        self.extractor     = DrumExtractor()
        self.analyzer      = PatternAnalyzer()
        self.song_analyzer = SongAnalyzer()

        # ── Generation ──────────────────────────────────────────────────────
        self.stat_gen           = StatisticalGenerator(seed=seed)
        self.humanizer          = Humanizer(seed=seed, use_magenta=use_magenta)
        self.magenta            = MagentaGenerator() if use_magenta else None
        self.arrangement_engine = ArrangementEngine()
        self.song_generator     = SongGenerator(seed=seed)
        self.multi_gen          = MultiInstrumentGenerator(seed=seed)

        # ── Export ──────────────────────────────────────────────────────────
        self.midi_exporter = MidiExporter()
        self.wav_renderer  = WavRenderer(soundfont_path=soundfont_path)
        self.json_exporter = JsonExporter()

        # ── Cache ────────────────────────────────────────────────────────────
        self.profile_cache_dir = Path(profile_cache_dir)
        self.profile_cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_config(cls, config_path: str = "config.yaml") -> "BeatFramework":
        """Load configuration from a YAML file."""
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        spotify = cfg.get("spotify", {})
        lastfm  = cfg.get("lastfm",  {})
        lakh    = cfg.get("lakh",    {})
        gen     = cfg.get("generation", {})
        paths   = cfg.get("paths",  {})

        return cls(
            spotify_client_id=     spotify.get("client_id"),
            spotify_client_secret= spotify.get("client_secret"),
            lastfm_api_key=        lastfm.get("api_key"),
            lastfm_api_secret=     lastfm.get("api_secret"),
            lakh_path=             lakh.get("path"),
            genre_annotations_path=lakh.get("genre_annotations"),
            soundfont_path=        paths.get("soundfont"),
            use_magenta=           gen.get("use_magenta", True),
            seed=                  gen.get("seed"),
            profile_cache_dir=     paths.get("profile_cache", "./profiles"),
            verbose=               cfg.get("verbose", False),
        )

    # -----------------------------------------------------------------------
    # Core API
    # -----------------------------------------------------------------------

    def build_profile(
        self,
        genre: str,
        year: int,
        force_rebuild: bool = False,
        use_builtin_fallback: bool = True,
    ) -> GenreProfile:
        """
        Build (or load from cache) a GenreProfile for the given genre/year.

        Process:
            1. Check cache for existing profile
            2. Collect top-100 songs from all sources
            3. Find and parse MIDI files (from Lakh or matched paths)
            4. Extract drum patterns
            5. Analyze patterns into a statistical profile
            6. Save to cache

        Args:
            genre:                 Genre name (e.g. "house", "techno", "reggae").
            year:                  Year (e.g. 2019).
            force_rebuild:         Ignore cache and rebuild.
            use_builtin_fallback:  Use built-in genre data if MIDI analysis is sparse.

        Returns:
            A GenreProfile ready for generation.
        """
        cache_path = self.profile_cache_dir / f"{genre}_{year}.json"

        if not force_rebuild and cache_path.exists():
            logger.info(f"Loading cached profile: {cache_path}")
            return GenreProfile.load(str(cache_path))

        logger.info(f"Building profile for {genre}/{year}...")

        # Step 1: Collect songs
        songs = self.aggregator.get_songs(genre=genre, year=year, limit=100)
        logger.info(f"Collected {len(songs)} songs")

        bpm_stats = self.aggregator.get_bpm_distribution(songs)
        if bpm_stats:
            logger.info(f"BPM distribution: {bpm_stats}")

        # Step 2: Find MIDI files (from Lakh-matched songs or songs with midi_path)
        midi_paths = [s["midi_path"] for s in songs if s.get("midi_path")]

        # Step 3: Parse and extract drum patterns
        all_patterns = []
        for midi_path in midi_paths[:200]:  # Cap for performance
            try:
                parsed = self.parser.parse(midi_path)
                if parsed:
                    patterns = self.extractor.extract(parsed, genre=genre, source=midi_path)
                    all_patterns.extend(patterns)
            except Exception as e:
                logger.debug(f"Failed to parse {midi_path}: {e}")

        logger.info(f"Extracted {len(all_patterns)} drum patterns from {len(midi_paths)} MIDIs")

        # Step 4: Build profile (blends with built-in if data is sparse)
        profile = self.analyzer.analyze(
            patterns=all_patterns,
            genre=genre,
            year=year,
        )

        # Override BPM stats if we have Spotify data
        if bpm_stats.get("mean"):
            profile.bpm_mean = bpm_stats["mean"]
            profile.bpm_std  = (bpm_stats["p75"] - bpm_stats["p25"]) / 2.0

        # Step 5: Cache
        profile.save(str(cache_path))
        return profile

    def generate(
        self,
        genre: str,
        year: int,
        count: int = 4,
        num_bars: int = 4,
        variation_factor: float = 0.15,
        swing: Optional[float] = None,
        use_magenta_continuation: bool = False,
        profile: Optional[GenreProfile] = None,
    ) -> list[RawBeat]:
        """
        Generate `count` unique beats for the given genre and year.

        Args:
            genre:                     Genre name.
            year:                      Year.
            count:                     Number of beat variations to generate.
            num_bars:                  Bars per beat (4 or 8 recommended).
            variation_factor:          How much variation between beats (0–1).
            swing:                     Swing amount (None = use genre default).
            use_magenta_continuation:  Enrich one beat with Magenta DrumsRNN.
            profile:                   Pre-built profile (skips build_profile).

        Returns:
            List of humanized RawBeat objects.
        """
        if profile is None:
            profile = self.build_profile(genre, year)

        beats = self.stat_gen.generate_variations(
            profile=profile,
            count=count,
            num_bars=num_bars,
        )

        # Humanize each beat
        humanized = []
        for beat in beats:
            h = self.humanizer.humanize(beat, profile, swing=swing)
            humanized.append(h)

        # Optionally enrich first beat with Magenta continuation
        if use_magenta_continuation and self.magenta and self.magenta.available:
            try:
                magenta_beat = self.magenta.generate_continuation(humanized[0])
                if magenta_beat:
                    magenta_h = self.humanizer.humanize(magenta_beat, profile, swing=swing)
                    humanized.append(magenta_h)
                    logger.info("Magenta continuation added as bonus beat")
            except Exception as e:
                logger.warning(f"Magenta continuation failed: {e}")

        return humanized

    def export_all(
        self,
        beats: list[RawBeat],
        output_dir: str,
        prefix: str = "",
        loop_count: int = 2,
        export_midi: bool = True,
        export_wav:  bool = True,
        export_json: bool = True,
        export_collection: bool = True,
    ) -> dict[str, list[str]]:
        """
        Export all beats to MIDI, WAV, and JSON files.

        Returns:
            Dict mapping format → list of output file paths.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, list[str]] = {"midi": [], "wav": [], "json": []}

        for i, beat in enumerate(beats):
            name = f"{prefix}{beat.genre}_{beat.year}_{beat.bpm:.0f}bpm_v{i+1:02d}"

            if export_midi:
                midi_path = str(out / f"{name}.mid")
                self.midi_exporter.export(beat, midi_path, multi_track=True, loop_count=loop_count)
                outputs["midi"].append(midi_path)

                if export_wav and self.wav_renderer.available:
                    wav_path = str(out / f"{name}.wav")
                    result = self.wav_renderer.render(midi_path, wav_path)
                    if result:
                        outputs["wav"].append(result)

            if export_json:
                json_path = str(out / f"{name}.json")
                self.json_exporter.export_beat(beat, json_path)
                outputs["json"].append(json_path)

        # Export combined collection JSON
        if export_collection and export_json and beats:
            collection_path = str(out / f"{prefix}collection.json")
            self.json_exporter.export_collection(beats, [], collection_path)
            outputs["json"].append(collection_path)

        total = sum(len(v) for v in outputs.values())
        logger.info(f"Exported {total} files to {output_dir}")
        return outputs

    def quick_generate(
        self,
        genre: str,
        year: int,
        output_dir: str,
        count: int = 4,
        num_bars: int = 4,
    ) -> dict[str, list[str]]:
        """
        One-shot: build profile, generate beats, export everything.

        Usage:
            fw.quick_generate("house", 2019, "./output/house_2019")
        """
        beats = self.generate(genre=genre, year=year, count=count, num_bars=num_bars)
        return self.export_all(beats, output_dir, prefix=f"{genre}_{year}_")

    # -----------------------------------------------------------------------
    # Song Analysis (Phase 1)
    # -----------------------------------------------------------------------

    def analyze_song(
        self,
        midi_path: str,
        spotify_features: Optional[dict] = None,
        genre: str = "",
        title: str = "",
        artist: str = "",
    ) -> "SongDNA":
        """Produce a full SongDNA from a MIDI file and optional Spotify data.

        Returns a SongDNA with key, chords, structure, instruments,
        energy curve, and drum patterns.
        """
        if spotify_features:
            return self.song_analyzer.analyze_hybrid(midi_path, spotify_features)
        return self.song_analyzer.analyze_midi(midi_path, genre=genre, title=title, artist=artist)

    def analyze_batch(
        self,
        genre: str,
        year: int,
        limit: int = 100,
    ) -> list["SongDNA"]:
        """Analyze all available songs for a genre/year from collectors.

        Returns a list of SongDNA objects — one per song with MIDI data,
        plus partial SongDNA (Spotify-only) for songs without MIDI.
        """
        songs = self.aggregator.get_songs(genre=genre, year=year, limit=limit)
        results: list[SongDNA] = []

        for song in songs:
            try:
                midi_path = song.get("midi_path")
                if midi_path:
                    dna = self.song_analyzer.analyze_hybrid(midi_path, song)
                else:
                    dna = self.song_analyzer.analyze_spotify(song)
                results.append(dna)
            except Exception as e:
                logger.debug(f"Analysis failed for {song.get('title', '?')}: {e}")

        logger.info(f"Analyzed {len(results)} songs for {genre}/{year}")
        return results

    # -----------------------------------------------------------------------
    # Full Song Generation (Phase 2)
    # -----------------------------------------------------------------------

    def generate_song(
        self,
        genre: str,
        year: int,
        template_name: Optional[str] = None,
        swing: Optional[float] = None,
        profile: Optional[GenreProfile] = None,
    ):
        """Generate a full-song percussion track with sections.

        Returns a SongBeat with section-aware percussion,
        transitions, fills, builds, and energy dynamics.
        """
        if profile is None:
            profile = self.build_profile(genre, year)

        arrangement = self.arrangement_engine.get_template(genre, template_name)

        song_beat = self.song_generator.generate_song(
            profile=profile,
            arrangement=arrangement,
        )

        # Humanize with section awareness
        self.humanizer.humanize_song(song_beat, profile, swing=swing)

        logger.info(
            f"Full song generated: {genre}/{year}, {arrangement.total_bars} bars, "
            f"{len(song_beat.sections)} sections"
        )
        return song_beat

    # -----------------------------------------------------------------------
    # Full Production (Phase 3)
    # -----------------------------------------------------------------------

    def generate_full_production(
        self,
        genre: str,
        year: int,
        template_name: Optional[str] = None,
        swing: Optional[float] = None,
        profile: Optional[GenreProfile] = None,
        include_bass: bool = True,
        include_harmony: bool = True,
    ) -> "FullArrangement":
        """Generate a full multi-instrument song (drums + bass + harmony).

        Returns a FullArrangement with section-aware drums, bass line
        following chord progression, and genre-appropriate harmony.
        """
        if profile is None:
            profile = self.build_profile(genre, year)

        arrangement = self.arrangement_engine.get_template(genre, template_name)

        full = self.multi_gen.generate(
            profile=profile,
            genre=genre,
            year=year,
            arrangement=arrangement,
            include_bass=include_bass,
            include_harmony=include_harmony,
        )

        # Humanize the drum tracks
        if full.drums:
            self.humanizer.humanize_song(full.drums, profile, swing=swing)

        logger.info(
            f"Full production generated: {genre}/{year}, {full.total_bars} bars, "
            f"bass={'yes' if full.bass else 'no'}, harmony={'yes' if full.harmony else 'no'}"
        )
        return full

    def export_full_arrangement(
        self,
        full_arrangement: "FullArrangement",
        output_dir: str,
        prefix: str = "",
        export_midi: bool = True,
        export_wav: bool = True,
        export_json: bool = True,
    ) -> dict[str, list[str]]:
        """Export a FullArrangement to multi-track MIDI, WAV, and JSON."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, list[str]] = {"midi": [], "wav": [], "json": []}
        name = (
            f"{prefix}{full_arrangement.genre}_{full_arrangement.year}_"
            f"{full_arrangement.bpm:.0f}bpm_production"
        )

        if export_midi:
            midi_path = str(out / f"{name}.mid")
            self.midi_exporter.export_full_arrangement(full_arrangement, midi_path)
            outputs["midi"].append(midi_path)

            if export_wav and self.wav_renderer.available:
                wav_path = str(out / f"{name}.wav")
                result = self.wav_renderer.render(midi_path, wav_path)
                if result:
                    outputs["wav"].append(result)

        if export_json:
            json_path = str(out / f"{name}.json")
            self.json_exporter.export_full_arrangement(full_arrangement, json_path)
            outputs["json"].append(json_path)

        total = sum(len(v) for v in outputs.values())
        logger.info(f"Exported {total} full production files to {output_dir}")
        return outputs

    def export_song(
        self,
        song_beat,
        output_dir: str,
        prefix: str = "",
        export_midi: bool = True,
        export_wav: bool = True,
        export_json: bool = True,
    ) -> dict[str, list[str]]:
        """Export a SongBeat to MIDI, WAV, and JSON."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        outputs: dict[str, list[str]] = {"midi": [], "wav": [], "json": []}
        name = f"{prefix}{song_beat.genre}_{song_beat.year}_{song_beat.bpm:.0f}bpm_full"

        if export_midi:
            midi_path = str(out / f"{name}.mid")
            self.midi_exporter.export_song(song_beat, midi_path)
            outputs["midi"].append(midi_path)

            if export_wav and self.wav_renderer.available:
                wav_path = str(out / f"{name}.wav")
                result = self.wav_renderer.render(midi_path, wav_path)
                if result:
                    outputs["wav"].append(result)

        if export_json:
            json_path = str(out / f"{name}.json")
            self.json_exporter.export_song_beat(song_beat, json_path)
            outputs["json"].append(json_path)

        total = sum(len(v) for v in outputs.values())
        logger.info(f"Exported {total} song files to {output_dir}")
        return outputs
