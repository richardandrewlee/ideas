"""
Structure Detector
-------------------
Detects song sections (intro, verse, chorus, bridge, etc.) from
patterns in MIDI data.

Algorithm:
1. Compute per-bar feature vectors (density, velocity, instrument count, drum presence)
2. Build a self-similarity matrix comparing multi-bar blocks
3. Cluster similar blocks and label by energy level
4. Use MIDI markers if present (some MIDIs annotate sections)
"""

import math
import logging
from typing import Optional

from .midi_parser import ParsedMidi
from .song_dna import SongSection, SectionType, ChordEvent

logger = logging.getLogger(__name__)


class StructureDetector:
    """Detects song structure from MIDI data."""

    # Typical block sizes to check (in bars)
    BLOCK_SIZES = [8, 4, 16]

    def detect(
        self,
        parsed: ParsedMidi,
        chords: Optional[list[ChordEvent]] = None,
    ) -> list[SongSection]:
        """Identify song sections from repetition and density analysis.

        Returns a list of SongSection objects covering the full song.
        """
        # If MIDI has markers, use those first
        if parsed.markers:
            marker_sections = self._sections_from_markers(parsed)
            if marker_sections:
                energy = self.compute_energy_curve(parsed)
                self._apply_energy_to_sections(marker_sections, energy)
                return marker_sections

        total_bars = max(1, int(parsed.duration_bars))
        if total_bars < 4:
            return [SongSection(
                section_type=SectionType.VERSE,
                start_bar=0, end_bar=total_bars,
                energy_level=0.5, label="verse_1",
            )]

        # Compute per-bar features
        bar_features = self._compute_bar_features(parsed)
        energy = self.compute_energy_curve(parsed)

        # Try to find repeating blocks
        best_block_size = self._find_best_block_size(bar_features, total_bars)
        blocks = self._segment_into_blocks(bar_features, best_block_size, total_bars)

        # Build similarity matrix and cluster
        clusters = self._cluster_blocks(blocks)

        # Label sections
        sections = self._label_sections(clusters, energy, best_block_size, total_bars)

        return sections

    def compute_energy_curve(self, parsed: ParsedMidi) -> list[float]:
        """Compute per-bar energy level (0.0-1.0).

        Energy is a weighted combination of:
        - Note density (how many notes per bar)
        - Average velocity
        - Number of active channels
        """
        total_bars = max(1, int(parsed.duration_bars))
        ticks_per_bar = parsed.ticks_per_beat * 4  # Assuming 4/4

        if parsed.time_signatures:
            num = parsed.time_signatures[0][1]
            ticks_per_bar = parsed.ticks_per_beat * num

        bar_energy: list[float] = []

        for bar in range(total_bars):
            bar_start = bar * ticks_per_bar
            bar_end = bar_start + ticks_per_bar

            note_count = 0
            velocity_sum = 0
            channels: set[int] = set()

            for track in parsed.tracks:
                for note in track.notes:
                    if bar_start <= note.tick < bar_end:
                        note_count += 1
                        velocity_sum += note.velocity
                        channels.add(note.channel)

            # Normalize components
            density = min(1.0, note_count / 32.0)  # 32 notes/bar = max density
            avg_vel = (velocity_sum / note_count / 127.0) if note_count > 0 else 0.0
            channel_factor = min(1.0, len(channels) / 6.0)  # 6 channels = max

            # Weighted combination
            energy = 0.4 * density + 0.35 * avg_vel + 0.25 * channel_factor
            bar_energy.append(round(energy, 3))

        # Normalize to 0-1 range
        if bar_energy:
            max_e = max(bar_energy) or 1.0
            bar_energy = [e / max_e for e in bar_energy]

        return bar_energy

    def _compute_bar_features(self, parsed: ParsedMidi) -> list[dict]:
        """Compute feature vector per bar for similarity comparison."""
        total_bars = max(1, int(parsed.duration_bars))
        ticks_per_bar = parsed.ticks_per_beat * 4

        if parsed.time_signatures:
            num = parsed.time_signatures[0][1]
            ticks_per_bar = parsed.ticks_per_beat * num

        features: list[dict] = []

        for bar in range(total_bars):
            bar_start = bar * ticks_per_bar
            bar_end = bar_start + ticks_per_bar

            pitches: list[int] = []
            velocities: list[int] = []
            channels: set[int] = set()
            has_drums = False

            for track in parsed.tracks:
                for note in track.notes:
                    if bar_start <= note.tick < bar_end:
                        pitches.append(note.pitch)
                        velocities.append(note.velocity)
                        channels.add(note.channel)
                        if note.channel == 9:
                            has_drums = True

            features.append({
                "note_count": len(pitches),
                "avg_velocity": sum(velocities) / len(velocities) if velocities else 0,
                "pitch_range": (max(pitches) - min(pitches)) if pitches else 0,
                "channel_count": len(channels),
                "has_drums": has_drums,
                "pitch_classes": len(set(p % 12 for p in pitches)) if pitches else 0,
            })

        return features

    def _find_best_block_size(self, bar_features: list[dict], total_bars: int) -> int:
        """Find the block size that produces the most self-similar structure."""
        best_size = 8
        best_score = -1.0

        for size in self.BLOCK_SIZES:
            if total_bars < size * 2:
                continue

            n_blocks = total_bars // size
            if n_blocks < 2:
                continue

            # Compute average self-similarity for this block size
            blocks = []
            for b in range(n_blocks):
                start = b * size
                end = min(start + size, len(bar_features))
                blocks.append(bar_features[start:end])

            total_sim = 0.0
            comparisons = 0
            for i in range(len(blocks)):
                for j in range(i + 1, len(blocks)):
                    total_sim += self._block_similarity(blocks[i], blocks[j])
                    comparisons += 1

            avg_sim = total_sim / comparisons if comparisons > 0 else 0.0

            if avg_sim > best_score:
                best_score = avg_sim
                best_size = size

        return best_size

    def _segment_into_blocks(
        self, bar_features: list[dict], block_size: int, total_bars: int
    ) -> list[list[dict]]:
        """Split bar features into fixed-size blocks."""
        blocks = []
        for i in range(0, total_bars, block_size):
            end = min(i + block_size, len(bar_features))
            blocks.append(bar_features[i:end])
        return blocks

    def _cluster_blocks(self, blocks: list[list[dict]]) -> list[int]:
        """Assign cluster IDs to blocks based on similarity.

        Simple greedy clustering: compare each block to existing clusters,
        assign to most similar if above threshold, else create new cluster.
        """
        if not blocks:
            return []

        threshold = 0.6
        cluster_ids: list[int] = []
        centroids: list[list[dict]] = []

        for block in blocks:
            best_cluster = -1
            best_sim = threshold

            for c_idx, centroid in enumerate(centroids):
                sim = self._block_similarity(block, centroid)
                if sim > best_sim:
                    best_sim = sim
                    best_cluster = c_idx

            if best_cluster >= 0:
                cluster_ids.append(best_cluster)
            else:
                cluster_ids.append(len(centroids))
                centroids.append(block)

        return cluster_ids

    def _label_sections(
        self,
        cluster_ids: list[int],
        energy: list[float],
        block_size: int,
        total_bars: int,
    ) -> list[SongSection]:
        """Label clustered blocks as verse, chorus, bridge, etc."""
        if not cluster_ids:
            return []

        # Compute average energy per cluster
        cluster_energy: dict[int, list[float]] = {}
        for i, cid in enumerate(cluster_ids):
            start = i * block_size
            end = min(start + block_size, len(energy))
            block_energy = energy[start:end]
            avg = sum(block_energy) / len(block_energy) if block_energy else 0.0
            cluster_energy.setdefault(cid, []).append(avg)

        cluster_avg_energy = {
            cid: sum(vals) / len(vals) for cid, vals in cluster_energy.items()
        }

        # Count occurrences per cluster
        cluster_counts: dict[int, int] = {}
        for cid in cluster_ids:
            cluster_counts[cid] = cluster_counts.get(cid, 0) + 1

        # Label assignment rules:
        # - Highest energy recurring cluster = chorus
        # - Lower energy recurring cluster = verse
        # - Single-occurrence clusters = bridge or intro/outro
        # - First block if unique or low energy = intro
        # - Last block if unique or low energy = outro

        recurring = {cid for cid, count in cluster_counts.items() if count >= 2}
        unique = {cid for cid, count in cluster_counts.items() if count == 1}

        # Sort recurring by energy (highest = chorus)
        recurring_sorted = sorted(recurring, key=lambda c: cluster_avg_energy.get(c, 0), reverse=True)

        cluster_labels: dict[int, SectionType] = {}
        if recurring_sorted:
            cluster_labels[recurring_sorted[0]] = SectionType.CHORUS
            for cid in recurring_sorted[1:]:
                cluster_labels[cid] = SectionType.VERSE
        for cid in unique:
            cluster_labels[cid] = SectionType.BRIDGE

        # Build sections
        sections: list[SongSection] = []
        section_type_counts: dict[SectionType, int] = {}

        for i, cid in enumerate(cluster_ids):
            start_bar = i * block_size
            end_bar = min(start_bar + block_size, total_bars)

            section_type = cluster_labels.get(cid, SectionType.VERSE)

            # Override first/last blocks
            if i == 0 and cid in unique:
                section_type = SectionType.INTRO
            elif i == len(cluster_ids) - 1 and cid in unique:
                section_type = SectionType.OUTRO

            # Compute section energy
            block_energy = energy[start_bar:end_bar] if start_bar < len(energy) else [0.5]
            avg_energy = sum(block_energy) / len(block_energy) if block_energy else 0.5

            # Generate label
            section_type_counts[section_type] = section_type_counts.get(section_type, 0) + 1
            label = f"{section_type.value}_{section_type_counts[section_type]}"

            sections.append(SongSection(
                section_type=section_type,
                start_bar=start_bar,
                end_bar=end_bar,
                energy_level=round(avg_energy, 3),
                has_drums=True,
                label=label,
            ))

        return sections

    def _sections_from_markers(self, parsed: ParsedMidi) -> list[SongSection]:
        """Build sections from MIDI marker events."""
        if not parsed.markers:
            return []

        total_bars = max(1, int(parsed.duration_bars))
        marker_map = {
            "intro": SectionType.INTRO,
            "verse": SectionType.VERSE,
            "pre-chorus": SectionType.PRECHORUS,
            "prechorus": SectionType.PRECHORUS,
            "chorus": SectionType.CHORUS,
            "bridge": SectionType.BRIDGE,
            "breakdown": SectionType.BREAKDOWN,
            "drop": SectionType.DROP,
            "outro": SectionType.OUTRO,
        }

        sections: list[SongSection] = []

        for i, (tick, text) in enumerate(parsed.markers):
            text_lower = text.strip().lower()
            section_type = SectionType.VERSE  # default
            for key, st in marker_map.items():
                if key in text_lower:
                    section_type = st
                    break

            start_bar = parsed.tick_to_bar(tick)
            # End is either next marker or end of song
            if i + 1 < len(parsed.markers):
                end_bar = parsed.tick_to_bar(parsed.markers[i + 1][0])
            else:
                end_bar = total_bars

            if end_bar <= start_bar:
                end_bar = start_bar + 1

            sections.append(SongSection(
                section_type=section_type,
                start_bar=start_bar,
                end_bar=end_bar,
                label=text.strip(),
            ))

        return sections

    def _apply_energy_to_sections(self, sections: list[SongSection], energy: list[float]) -> None:
        """Fill in energy levels for marker-based sections."""
        for section in sections:
            start = section.start_bar
            end = min(section.end_bar, len(energy))
            if start < end:
                block = energy[start:end]
                section.energy_level = round(sum(block) / len(block), 3)

    @staticmethod
    def _block_similarity(a: list[dict], b: list[dict]) -> float:
        """Compute similarity between two blocks of bar features (0.0-1.0)."""
        if not a or not b:
            return 0.0

        min_len = min(len(a), len(b))
        total_sim = 0.0

        for i in range(min_len):
            fa, fb = a[i], b[i]
            # Compare normalized features
            max_notes = max(fa["note_count"], fb["note_count"], 1)
            note_sim = 1.0 - abs(fa["note_count"] - fb["note_count"]) / max_notes

            max_vel = max(fa["avg_velocity"], fb["avg_velocity"], 1)
            vel_sim = 1.0 - abs(fa["avg_velocity"] - fb["avg_velocity"]) / max_vel

            max_ch = max(fa["channel_count"], fb["channel_count"], 1)
            ch_sim = 1.0 - abs(fa["channel_count"] - fb["channel_count"]) / max_ch

            drum_sim = 1.0 if fa["has_drums"] == fb["has_drums"] else 0.0

            total_sim += 0.35 * note_sim + 0.25 * vel_sim + 0.2 * ch_sim + 0.2 * drum_sim

        return total_sim / min_len
