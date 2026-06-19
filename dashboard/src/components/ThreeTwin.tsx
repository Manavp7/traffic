import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Live } from "../hooks";

const M_PER_DEG_LAT = 111320;

function congColorHex(score: number): number {
  if (score < 25) return 0x22c55e;
  if (score < 50) return 0xeab308;
  if (score < 75) return 0xf97316;
  return 0xef4444;
}

export default function ThreeTwin({ net, live }: { net?: any; live: Live }) {
  const ref = useRef<HTMLDivElement>(null);
  const scene = useRef<THREE.Scene>();
  const renderer = useRef<THREE.WebGLRenderer>();
  const roadLines = useRef<Record<string, THREE.Line>>({});
  const vehicleGroup = useRef<THREE.Group>();
  const proj = useRef<{ clat: number; clon: number; scale: number }>();

  // init scene
  useEffect(() => {
    if (!ref.current || renderer.current) return;
    const el = ref.current;
    const w = el.clientWidth, h = el.clientHeight || 600;
    const sc = new THREE.Scene();
    sc.background = new THREE.Color(0x0b1020);
    const cam = new THREE.PerspectiveCamera(55, w / h, 0.1, 5000);
    cam.position.set(0, 600, 700);
    const rnd = new THREE.WebGLRenderer({ antialias: true });
    rnd.setSize(w, h);
    el.appendChild(rnd.domElement);
    const controls = new OrbitControls(cam, rnd.domElement);
    controls.target.set(0, 0, 0);
    sc.add(new THREE.AmbientLight(0xffffff, 0.7));
    const dir = new THREE.DirectionalLight(0xffffff, 0.6);
    dir.position.set(300, 800, 200);
    sc.add(dir);
    // ground
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(4000, 4000),
      new THREE.MeshStandardMaterial({ color: 0x141a2e })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -1;
    sc.add(ground);
    const vg = new THREE.Group();
    sc.add(vg);
    vehicleGroup.current = vg;
    scene.current = sc;
    renderer.current = rnd;

    let raf = 0;
    const loop = () => {
      controls.update();
      rnd.render(sc, cam);
      raf = requestAnimationFrame(loop);
    };
    loop();
    const onResize = () => {
      const nw = el.clientWidth, nh = el.clientHeight || 600;
      cam.aspect = nw / nh; cam.updateProjectionMatrix(); rnd.setSize(nw, nh);
    };
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      rnd.dispose();
      el.removeChild(rnd.domElement);
      renderer.current = undefined;
    };
  }, []);

  // build roads when network arrives
  useEffect(() => {
    const sc = scene.current;
    if (!sc || !net?.segments?.length) return;
    const lats = net.junctions.map((j: any) => j.lat);
    const lons = net.junctions.map((j: any) => j.lon);
    const clat = lats.reduce((a: number, b: number) => a + b, 0) / lats.length;
    const clon = lons.reduce((a: number, b: number) => a + b, 0) / lons.length;
    const scale = 0.25; // metres -> world units
    proj.current = { clat, clon, scale };
    const toXZ = (lat: number, lon: number): [number, number] => [
      (lon - clon) * (M_PER_DEG_LAT * Math.cos((clat * Math.PI) / 180)) * scale,
      -(lat - clat) * M_PER_DEG_LAT * scale,
    ];
    Object.values(roadLines.current).forEach((l) => sc.remove(l));
    roadLines.current = {};
    for (const s of net.segments) {
      const pts = s.geometry.map(([la, lo]: [number, number]) => {
        const [x, z] = toXZ(la, lo);
        return new THREE.Vector3(x, 2, z);
      });
      const geo = new THREE.BufferGeometry().setFromPoints(pts);
      const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0x22c55e }));
      sc.add(line);
      roadLines.current[s.id] = line;
    }
  }, [net]);

  // update colors + vehicles on live updates
  useEffect(() => {
    for (const [id, line] of Object.entries(roadLines.current)) {
      const c = live.congestion[id] ?? 0;
      (line.material as THREE.LineBasicMaterial).color.setHex(congColorHex(c));
    }
    const vg = vehicleGroup.current;
    const p = proj.current;
    if (!vg || !p) return;
    while (vg.children.length) vg.remove(vg.children[0]);
    const geo = new THREE.BoxGeometry(6, 4, 10);
    for (const v of live.vehicles.slice(0, 400)) {
      const x = (v.lon - p.clon) * (M_PER_DEG_LAT * Math.cos((p.clat * Math.PI) / 180)) * p.scale;
      const z = -(v.lat - p.clat) * M_PER_DEG_LAT * p.scale;
      const color = v.speed < 5 ? 0xef4444 : v.speed < 20 ? 0xf59e0b : 0x38bdf8;
      const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color }));
      m.position.set(x, 4, z);
      vg.add(m);
    }
  }, [live, net]);

  return <div className="map" ref={ref} style={{ position: "relative", height: "100%" }} />;
}
