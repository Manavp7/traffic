import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { congestionColor } from "../api";

type Seg = { id: string; geometry: [number, number][]; name: string };
type Net = { junctions: any[]; segments: Seg[] };

const OSM_STYLE: any = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap",
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#0b1020" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.55, "raster-brightness-max": 0.8 } },
  ],
};

function segFeatures(net: Net, cong: Record<string, number>) {
  return {
    type: "FeatureCollection",
    features: net.segments.map((s) => ({
      type: "Feature",
      properties: { id: s.id, color: congestionColor(cong[s.id] ?? 0) },
      geometry: { type: "LineString", coordinates: s.geometry.map(([la, lo]) => [lo, la]) },
    })),
  } as any;
}

export default function MapView({
  net,
  congestion,
  vehicles,
  incidents,
}: {
  net?: Net;
  congestion: Record<string, number>;
  vehicles: { lat: number; lon: number; speed: number }[];
  incidents: { lat: number; lon: number; type: string }[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map>();
  const ready = useRef(false);

  useEffect(() => {
    if (!ref.current || map.current) return;
    map.current = new maplibregl.Map({
      container: ref.current,
      style: OSM_STYLE,
      center: [77.5946, 12.9716],
      zoom: 13,
    });
    map.current.on("load", () => {
      ready.current = true;
    });
  }, []);

  // build/update segments when network or congestion changes
  useEffect(() => {
    const m = map.current;
    if (!m || !net) return;
    const apply = () => {
      const data = segFeatures(net, congestion);
      if (m.getSource("segments")) {
        (m.getSource("segments") as any).setData(data);
      } else {
        m.addSource("segments", { type: "geojson", data });
        m.addLayer({
          id: "segments",
          type: "line",
          source: "segments",
          paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.9 },
        });
        // fit to network bounds once
        const b = new maplibregl.LngLatBounds();
        net.segments.forEach((s) => s.geometry.forEach(([la, lo]) => b.extend([lo, la])));
        if (!b.isEmpty()) m.fitBounds(b, { padding: 60, duration: 0 });
      }
    };
    if (ready.current) apply();
    else m.once("load", apply);
  }, [net, congestion]);

  // vehicles
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    const data = {
      type: "FeatureCollection",
      features: vehicles.map((v) => ({
        type: "Feature",
        properties: { color: v.speed < 5 ? "#ef4444" : v.speed < 20 ? "#f59e0b" : "#38bdf8" },
        geometry: { type: "Point", coordinates: [v.lon, v.lat] },
      })),
    } as any;
    if (m.getSource("vehicles")) (m.getSource("vehicles") as any).setData(data);
    else {
      m.addSource("vehicles", { type: "geojson", data });
      m.addLayer({
        id: "vehicles",
        type: "circle",
        source: "vehicles",
        paint: { "circle-radius": 3.5, "circle-color": ["get", "color"], "circle-stroke-width": 0.5, "circle-stroke-color": "#0b1020" },
      });
    }
  }, [vehicles]);

  // incidents
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    const data = {
      type: "FeatureCollection",
      features: incidents.map((i) => ({
        type: "Feature",
        properties: { type: i.type },
        geometry: { type: "Point", coordinates: [i.lon, i.lat] },
      })),
    } as any;
    if (m.getSource("incidents")) (m.getSource("incidents") as any).setData(data);
    else {
      m.addSource("incidents", { type: "geojson", data });
      m.addLayer({
        id: "incidents",
        type: "circle",
        source: "incidents",
        paint: { "circle-radius": 7, "circle-color": "#ef4444", "circle-stroke-width": 2, "circle-stroke-color": "#fff", "circle-opacity": 0.85 },
      });
    }
  }, [incidents]);

  return <div className="map" ref={ref} />;
}
