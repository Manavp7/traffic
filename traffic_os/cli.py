"""Traffic-OS command-line entry point.

Subcommands are added as phases land (seed, simulate, history, train, serve, demo).
"""

from __future__ import annotations

import argparse

from traffic_os import __version__
from traffic_os.common.logging import get_logger

log = get_logger("cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="traffic-os", description="National Traffic Intelligence OS"
    )
    parser.add_argument("--version", action="version", version=f"traffic-os {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("info", help="Print environment/storage info")
    p_seed = sub.add_parser("seed", help="Build and persist the road network")
    p_seed.add_argument("--osm", action="store_true", help="Use a real OpenStreetMap network")
    p_seed.add_argument("--place", default=None, help="OSM place name (with --osm)")

    p_sim = sub.add_parser("simulate", help="Run the live simulation for N ticks")
    p_sim.add_argument("--ticks", type=int, default=120)
    p_sim.add_argument("--realtime", action="store_true")

    p_hist = sub.add_parser("history", help="Generate historical metrics")
    p_hist.add_argument("--days", type=int, default=14)
    p_hist.add_argument("--step-min", type=int, default=15)

    sub.add_parser("train", help="Train forecasting + accident-risk models on history")

    p_perc = sub.add_parser("perceive", help="Run YOLO+ByteTrack perception on a video")
    p_perc.add_argument("--video", default="data/samples/traffic.mp4")
    p_perc.add_argument("--source-id", default="cam-1")
    p_perc.add_argument("--max-frames", type=int, default=120)
    p_perc.add_argument("--stride", type=int, default=3)

    p_edge = sub.add_parser("edge", help="Run an Edge AI node (on-device detect + compact uplink)")
    p_edge.add_argument("--video", default="data/samples/highway.mp4")
    p_edge.add_argument("--source-id", default="edge-1")
    p_edge.add_argument("--api", default=None, help="Command Center base URL to uplink to")
    p_edge.add_argument("--max-frames", type=int, default=40)

    args = parser.parse_args(argv)

    if args.command == "info":
        return _cmd_info()
    if args.command == "seed":
        return _cmd_seed(getattr(args, "osm", False), getattr(args, "place", None))
    if args.command == "simulate":
        return _cmd_simulate(args.ticks, args.realtime)
    if args.command == "history":
        return _cmd_history(args.days, args.step_min)
    if args.command == "train":
        return _cmd_train()
    if args.command == "perceive":
        return _cmd_perceive(args.video, args.source_id, args.max_frames, args.stride)
    if args.command == "edge":
        return _cmd_edge(args.video, args.source_id, args.api, args.max_frames)

    parser.print_help()
    return 0


def _cmd_edge(video: str, source_id: str, api: str | None, max_frames: int) -> int:
    from traffic_os.edge import EdgeNode, http_sink

    received: list = []
    sink = http_sink(api) if api else received.append
    node = EdgeNode(source_id=source_id)
    stats = node.run(video, sink, max_frames=max_frames)
    log.info(
        "Edge uplink: %d frames, %.1f KB sent vs %.1f MB raw video (%.1f%% bandwidth saved)",
        stats.frames,
        stats.uplink_bytes / 1024,
        stats.raw_video_bytes / 1e6,
        stats.reduction_pct,
    )
    if api:
        log.info("Uplinked compact metrics to %s/ingest/camera", api)
    return 0


def _cmd_train() -> int:
    from traffic_os.prediction import PredictionService
    from traffic_os.storage import get_storage

    st = get_storage()
    svc = PredictionService(st)
    results = svc.train()
    for h, bt in results["forecast"].items():
        log.info(
            "Forecast %dmin: MAE=%.2f MAPE=%.1f%% skill_vs_persistence=%.3f",
            h,
            bt["mae"],
            bt["mape"],
            bt["skill_vs_persistence"],
        )
    log.info("Accident-risk model AUC=%.3f", results["accident_risk_auc"])
    svc.forecast_all(60)
    svc.accident_risk_all()
    log.info(
        "Forecasts: %d | accident-risk rows: %d",
        st.db.count("forecast"),
        st.db.count("accident_risk"),
    )
    return 0


def _cmd_perceive(video: str, source_id: str, max_frames: int, stride: int) -> int:
    from traffic_os.perception import PerceptionPipeline
    from traffic_os.storage import get_storage

    st = get_storage()
    pipe = PerceptionPipeline(st, source_id=source_id)
    summary = pipe.run(video, max_frames=max_frames, stride=stride)
    log.info(
        "Perception summary: frames=%d unique_tracks=%d classes=%s",
        summary.frames_processed,
        summary.unique_tracks,
        summary.class_totals,
    )
    log.info(
        "Peak occupancy=%.1f%% peak_queue=%.1fm avg_vehicles/frame=%.2f",
        summary.peak_occupancy_pct,
        summary.peak_queue_m,
        summary.avg_vehicles_per_frame,
    )
    if summary.annotated_video_key:
        log.info("Annotated video: %s", st.blob.url(summary.annotated_video_key))
    return 0


def _cmd_info() -> int:
    from traffic_os.storage import get_storage

    st = get_storage()
    log.info("Traffic-OS %s | mode=%s", __version__, st.settings.mode)
    log.info("Graph backend: %s | stats=%s", st.graph.__class__.__name__, st.graph.stats())
    log.info(
        "Network: %d junctions, %d segments", st.db.count("junction"), st.db.count("road_segment")
    )
    log.info(
        "Metrics rows: %d | incidents: %d", st.db.count("segment_metric"), st.db.count("incident")
    )
    return 0


def _cmd_seed(use_osm: bool = False, place: str | None = None) -> int:
    from traffic_os.simulation import build_network_from_settings, save_network
    from traffic_os.storage import get_storage

    st = get_storage()
    if use_osm:
        st.settings.sim_use_osm = True
        if place:
            st.settings.sim_place = place
    net = build_network_from_settings(st.settings)
    save_network(net, st.db)
    log.info(
        "Seeded network: %d junctions, %d segments, %d signals",
        len(net.junctions),
        len(net.segments),
        len(net.signals),
    )
    return 0


def _cmd_simulate(ticks: int, realtime: bool) -> int:
    import asyncio

    from traffic_os.simulation import SimulationEngine
    from traffic_os.storage import get_storage

    st = get_storage()
    eng = SimulationEngine.from_storage(st, st.settings)
    asyncio.run(eng.run(st, max_ticks=ticks, realtime=realtime))
    log.info("Simulation complete. Latest metrics persisted: %d", st.db.count("segment_metric"))
    return 0


def _cmd_history(days: int, step_min: int) -> int:
    from traffic_os.simulation import generate_history
    from traffic_os.simulation.network import build_network_from_settings, load_network
    from traffic_os.storage import get_storage

    st = get_storage()
    net = load_network(st.db)
    if not net.segments:
        net = build_network_from_settings(st.settings)
    stats = generate_history(net, st.db, days=days, step_min=step_min, seed=st.settings.sim_seed)
    log.info("History generated: %s", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
