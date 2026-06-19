"""E2: Real OSM city network — fallback logic + (optional) live download/cache."""

from __future__ import annotations

import os

import pytest

from traffic_os.common.config import Settings
from traffic_os.simulation import network as net_mod
from traffic_os.simulation.network import build_network_from_settings


def test_osm_failure_falls_back_to_grid(monkeypatch):
    def boom(place, cache_dir=None):
        raise RuntimeError("no network")

    monkeypatch.setattr(net_mod, "build_osm_network", boom)
    settings = Settings(mode="dev", sim_use_osm=True, sim_grid_size=4)
    net = build_network_from_settings(settings)
    # falls back to a working synthetic grid
    assert len(net.junctions) == 16
    assert len(net.segments) > 0


def test_grid_default_when_osm_disabled():
    settings = Settings(mode="dev", sim_use_osm=False, sim_grid_size=5)
    net = build_network_from_settings(settings)
    assert len(net.junctions) == 25


@pytest.mark.skipif(os.environ.get("TOS_TEST_OSM") != "1", reason="set TOS_TEST_OSM=1 for live OSM")
def test_osm_real_build_and_cache(tmp_path):
    pytest.importorskip("osmnx")
    from traffic_os.simulation.network import build_osm_network

    place = "Indiranagar, Bengaluru, India"
    net = build_osm_network(place, cache_dir=tmp_path)
    assert len(net.segments) > 100
    cached = list(tmp_path.glob("*.graphml"))
    assert cached, "graphml cache should be written"
    # second build loads from cache (no network)
    net2 = build_osm_network(place, cache_dir=tmp_path)
    assert len(net2.segments) == len(net.segments)
