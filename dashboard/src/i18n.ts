export type Lang = "en" | "hi";

const DICT: Record<string, { en: string; hi: string }> = {
  tagline: { en: "Detect · Predict · Recommend · Simulate · Optimize", hi: "पहचानें · भविष्यवाणी · सुझाव · सिमुलेट · अनुकूलन" },
  command: { en: "Command Center", hi: "कमांड सेंटर" },
  commissioner: { en: "Commissioner", hi: "आयुक्त" },
  national: { en: "National", hi: "राष्ट्रीय" },
  analytics: { en: "Analytics", hi: "विश्लेषण" },
  twin: { en: "3D Twin", hi: "3D ट्विन" },
  mobility: { en: "Mobility", hi: "गतिशीलता" },
  citizen: { en: "Citizen", hi: "नागरिक" },
  copilot_title: { en: "AI Copilot", hi: "एआई सहायक" },
  copilot_placeholder: { en: "Ask the Copilot…", hi: "सहायक से पूछें…" },
  ask: { en: "Ask", hi: "पूछें" },
  listen: { en: "🎤 Speak", hi: "🎤 बोलें" },
};

export function t(key: string, lang: Lang): string {
  const e = DICT[key];
  return e ? e[lang] : key;
}
