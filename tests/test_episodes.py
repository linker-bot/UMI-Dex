"""Tests for umi_dex.episodes."""

from pathlib import Path

from umi_dex.episodes import (
    EpisodeInterval,
    episode_id_for_timestamp,
    extract_episodes,
    filter_rows_by_episode,
    kept_episodes,
    write_episodes_csv,
)


def test_episode_interval_duration():
    ep = EpisodeInterval(episode_id=1, start_ns=1_000_000_000, end_ns=3_000_000_000, status="kept")
    assert ep.duration_s == 2.0


def test_episode_interval_duration_no_end():
    ep = EpisodeInterval(episode_id=1, start_ns=1_000_000_000)
    assert ep.duration_s is None


def test_kept_episodes():
    episodes = [
        EpisodeInterval(1, 100, 200, "kept"),
        EpisodeInterval(2, 300, 400, "discarded"),
        EpisodeInterval(3, 500, 600, "kept"),
        EpisodeInterval(4, 700, status="recording"),
    ]
    result = kept_episodes(episodes)
    assert len(result) == 2
    assert result[0].episode_id == 1
    assert result[1].episode_id == 3


def test_filter_rows_by_episode():
    ep = EpisodeInterval(1, start_ns=100, end_ns=300, status="kept")
    timestamps = [50, 100, 150, 200, 300, 350]
    indices = filter_rows_by_episode(timestamps, ep)
    assert indices == [1, 2, 3, 4]


def test_filter_rows_by_episode_no_end():
    ep = EpisodeInterval(1, start_ns=200, status="recording")
    timestamps = [50, 100, 200, 300, 400]
    indices = filter_rows_by_episode(timestamps, ep)
    assert indices == [2, 3, 4]


def test_episode_id_for_timestamp():
    episodes = [
        EpisodeInterval(1, 100, 200, "kept"),
        EpisodeInterval(2, 300, 400, "discarded"),
        EpisodeInterval(3, 500, 600, "kept"),
    ]
    assert episode_id_for_timestamp(150, episodes) == 1
    assert episode_id_for_timestamp(350, episodes) == -1  # discarded
    assert episode_id_for_timestamp(550, episodes) == 3
    assert episode_id_for_timestamp(50, episodes) == -1   # before any
    assert episode_id_for_timestamp(700, episodes) == -1   # after all


def test_write_episodes_csv(tmp_path: Path):
    episodes = [
        EpisodeInterval(1, 1_000_000_000, 2_000_000_000, "kept"),
        EpisodeInterval(2, 3_000_000_000, 4_000_000_000, "discarded"),
    ]
    csv_path = write_episodes_csv(episodes, tmp_path)
    assert csv_path.exists()
    lines = csv_path.read_text().strip().splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert "episode_id" in lines[0]
    assert "kept" in lines[1]
    assert "discarded" in lines[2]
