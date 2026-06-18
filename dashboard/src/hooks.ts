import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, wsUrl } from "./api";

export function useNetwork() {
  return useQuery({
    queryKey: ["network"],
    queryFn: () => api("/network"),
    staleTime: Infinity,
    refetchInterval: false,
  });
}

export type Live = {
  tick: number;
  active_vehicles: number;
  weather: string;
  congestion: Record<string, number>;
  vehicles: { lat: number; lon: number; speed: number }[];
  incidents: { lat: number; lon: number; type: string; id: string }[];
};

const EMPTY: Live = {
  tick: 0,
  active_vehicles: 0,
  weather: "clear",
  congestion: {},
  vehicles: [],
  incidents: [],
};

export function useLive(): Live {
  const [live, setLive] = useState<Live>(EMPTY);
  const incidents = useRef<Record<string, any>>({});

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stop = false;
    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        const cong: Record<string, number> = {};
        for (const m of msg.metrics || []) cong[m.segment_id] = m.congestion;
        for (const i of msg.incidents || []) {
          if (i.status === "resolved") delete incidents.current[i.id];
          else incidents.current[i.id] = i;
        }
        setLive({
          tick: msg.tick,
          active_vehicles: msg.active_vehicles || 0,
          weather: msg.weather || "clear",
          congestion: cong,
          vehicles: msg.vehicles || [],
          incidents: Object.values(incidents.current),
        });
      };
      ws.onclose = () => {
        if (!stop) setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      stop = true;
      ws?.close();
    };
  }, []);

  return live;
}

export function usePoll<T = any>(path: string, intervalMs = 5000) {
  return useQuery<T>({ queryKey: [path], queryFn: () => api(path), refetchInterval: intervalMs });
}
