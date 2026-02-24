#!/usr/bin/env python3
"""
Beat Framework — CLI Entry Point
=================================
Generate genre-authentic drum beats based on the top 100 songs
of any genre and year.

Usage examples:
    # Generate 4 house beats from 2019 (uses built-in profiles, no API keys needed)
    python generate.py --genre house --year 2019

    # Generate with config file (Spotify/Last.fm/Billboard/Lakh enabled)
    python generate.py --genre techno --year 2022 --config config.yaml

    # Generate 8-bar reggae beats, 6 variations
    python generate.py --genre reggae --year 2015 --bars 8 --count 6

    # Multiple genres at once
    python generate.py --genre house --genre rock --genre hip-hop --year 2020

    # With specific swing and BPM override
    python generate.py --genre jazz --year 2010 --swing 0.25 --bpm 140

    # Force rebuild cached profile
    python generate.py --genre pop --year 2023 --rebuild-profile

Available genres:
    house, techno, reggae, rock, hip-hop, jazz, pop, metal, soul,
    funk, rnb, country, blues, edm, drum-and-bass
"""

import argparse
import logging
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Generate genre-authentic drum beats.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Required
    parser.add_argument(
        "--genre", "-g",
        action="append",
        dest="genres",
        required=True,
        metavar="GENRE",
        help="Genre(s) to generate (can specify multiple times)",
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        required=True,
        help="Year for top-100 song data (e.g. 2019)",
    )

    # Optional generation settings
    parser.add_argument("--count",  "-n", type=int, default=4,   help="Number of beat variations (default: 4)")
    parser.add_argument("--bars",   "-b", type=int, default=4,   help="Bars per beat (default: 4)")
    parser.add_argument("--swing",  "-s", type=float, default=None, help="Swing amount 0.0–0.33 (default: genre-specific)")
    parser.add_argument("--bpm",          type=float, default=None, help="Override BPM (default: sampled from genre profile)")
    parser.add_argument("--loop",         type=int,   default=2,    help="MIDI loop count (default: 2)")
    parser.add_argument("--seed",         type=int,   default=None, help="Random seed for reproducibility")
    parser.add_argument("--variation",    type=float, default=0.15, help="Variation factor 0–1 (default: 0.15)")
    parser.add_argument("--no-magenta",   action="store_true",      help="Disable Magenta (faster, pure statistical)")
    parser.add_argument("--magenta-continuation", action="store_true", help="Add a Magenta DrumsRNN continuation beat")

    # Export settings
    parser.add_argument("--output",  "-o", default="./output", help="Output directory (default: ./output)")
    parser.add_argument("--no-wav",        action="store_true",  help="Skip WAV rendering")
    parser.add_argument("--no-json",       action="store_true",  help="Skip JSON export")
    parser.add_argument("--multi-track",   action="store_true",  default=True,  help="Write Format 1 MIDI (per-instrument tracks)")

    # Config / profile
    parser.add_argument("--config",        default=None,         help="Path to config.yaml")
    parser.add_argument("--rebuild-profile", action="store_true", help="Ignore profile cache and rebuild")
    parser.add_argument("--profile-cache",  default="./profiles", help="Profile cache directory")
    parser.add_argument("--soundfont",      default=None,         help="Path to GM soundfont (.sf2)")

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # ── Setup logging ────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s | %(message)s",
    )
    logger = logging.getLogger(__name__)

    # ── Import framework ─────────────────────────────────────────────────
    try:
        from beat_framework import BeatFramework
    except ImportError:
        # Allow running from the beat_framework directory itself
        sys.path.insert(0, str(Path(__file__).parent.parent))
        try:
            from beat_framework import BeatFramework
        except ImportError as e:
            logger.error(f"Could not import beat_framework: {e}")
            logger.error("Make sure you're running from the project root directory.")
            sys.exit(1)

    # ── Build framework ──────────────────────────────────────────────────
    if args.config and Path(args.config).exists():
        logger.info(f"Loading config: {args.config}")
        fw = BeatFramework.from_config(args.config)
    else:
        logger.info("No config file found; using built-in profiles (no API keys needed)")
        fw = BeatFramework(
            soundfont_path=args.soundfont,
            use_magenta=not args.no_magenta,
            seed=args.seed,
            profile_cache_dir=args.profile_cache,
            verbose=args.verbose,
        )

    # ── Generate for each genre ──────────────────────────────────────────
    all_outputs: dict[str, list[str]] = {"midi": [], "wav": [], "json": []}

    for genre in args.genres:
        logger.info(f"\n{'='*50}")
        logger.info(f"  Genre: {genre.upper()}  |  Year: {args.year}")
        logger.info(f"{'='*50}")

        # Build or load profile
        profile = fw.build_profile(
            genre=genre,
            year=args.year,
            force_rebuild=args.rebuild_profile,
        )

        # BPM override
        if args.bpm:
            profile.bpm_mean = args.bpm
            profile.bpm_std  = 0.0
            logger.info(f"BPM overridden to {args.bpm}")

        logger.info(
            f"Profile: {profile.num_patterns} patterns, "
            f"BPM {profile.bpm_mean:.1f} ± {profile.bpm_std:.1f}"
        )

        # Generate beats
        beats = fw.generate(
            genre=genre,
            year=args.year,
            count=args.count,
            num_bars=args.bars,
            variation_factor=args.variation,
            swing=args.swing,
            use_magenta_continuation=args.magenta_continuation,
            profile=profile,
        )

        logger.info(f"Generated {len(beats)} beats")

        # Export
        output_dir = str(Path(args.output) / f"{genre}_{args.year}")
        outputs = fw.export_all(
            beats=beats,
            output_dir=output_dir,
            prefix=f"{genre}_{args.year}_",
            loop_count=args.loop,
            export_midi=True,
            export_wav=not args.no_wav,
            export_json=not args.no_json,
        )

        for fmt, paths in outputs.items():
            all_outputs[fmt].extend(paths)

    # ── Summary ──────────────────────────────────────────────────────────
    logger.info(f"\n{'='*50}")
    logger.info("  DONE")
    logger.info(f"{'='*50}")
    for fmt, paths in all_outputs.items():
        if paths:
            logger.info(f"  {fmt.upper():5s}: {len(paths)} files")
            for p in paths[:5]:
                logger.info(f"         {p}")
            if len(paths) > 5:
                logger.info(f"         ... and {len(paths) - 5} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
