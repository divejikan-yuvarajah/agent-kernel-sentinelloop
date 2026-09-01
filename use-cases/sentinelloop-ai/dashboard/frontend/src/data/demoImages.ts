/** Central Horizon Engineering Workshop demo image catalog. Frontend-only. */

export type DemoImageType = "before" | "after" | "analysis" | "worker" | "location" | "avatar" | "dashboard";

export type DemoImageRecord = {
  image_id: string;
  src: string;
  alt: string;
  incident_id?: string;
  source?: string;
  uploaded_by?: string;
  timestamp?: string;
  type?: DemoImageType;
  category?: string;
  location?: string;
  verification_status?: string;
};

export type DemoVisionAnalysis = {
  label: string;
  objects: string[];
  hazard: string;
  confidence: number;
};

const img = (file: string) => `/images/${file}`;

export const FALLBACK_IMAGE = {
  image_id: "img-none",
  src: "",
  alt: "No Evidence Available",
};

const CATEGORY_IMAGE: Record<string, string> = {
  electrical: img("electrical_panel_damage.jpg"),
  "fire/smoke": img("machine_smoke.jpg"),
  fire: img("machine_smoke.jpg"),
  chemical: img("chemical_spill.jpg"),
  machine: img("machine_guard_missing.jpg"),
  "slip/trip": img("oil_spill_floor.jpg"),
  "missing ppe": img("missing_ppe.jpg"),
  ppe: img("missing_ppe.jpg"),
  structural: img("structural_damage.jpg"),
  "unsafe behaviour": img("missing_ppe.jpg"),
};

export const demoImages = {
  locations: {
    "Main Workshop Floor": {
      src: img("main_workshop_floor.jpg"),
      description: "Open fabrication floor with marked walkways and workbenches.",
      hazards: ["missing PPE", "slip/trip", "machine"],
    },
    "CNC Area": {
      src: img("factory_machine_area.jpg"),
      description: "Industrial machining area containing CNC equipment.",
      hazards: ["electrical", "fire/smoke", "machine"],
    },
    "CNC Production Area": {
      src: img("factory_machine_area.jpg"),
      description: "Industrial machining area containing CNC equipment.",
      hazards: ["electrical", "machine"],
    },
    "Electrical Room": {
      src: img("electrical_room.jpg"),
      description: "Switchgear and cable trays serving the workshop.",
      hazards: ["electrical"],
    },
    "Chemical Storage Room": {
      src: img("chemical_storage.jpg"),
      description: "Drum store for solvents and cutting fluids.",
      hazards: ["chemical"],
    },
    "Welding Section": {
      src: img("welding_section.jpg"),
      description: "Welding bays with extraction and gas cylinders.",
      hazards: ["fire/smoke", "chemical"],
    },
    "Loading Bay": {
      src: img("loading_bay.jpg"),
      description: "Goods-in dock with pallet traffic.",
      hazards: ["slip/trip", "structural"],
    },
  },
  hazards: {
    electrical: [img("electrical_panel_damage.jpg"), img("electrical_spark.jpg"), img("damaged_cable.jpg")],
    fire: [img("machine_smoke.jpg"), img("overheating_equipment.jpg")],
    chemical: [img("chemical_spill.jpg"), img("chemical_storage.jpg")],
    machine: [img("machine_guard_missing.jpg"), img("rotating_equipment.jpg")],
    slip: [img("oil_spill_floor.jpg"), img("wet_floor.jpg"), img("blocked_walkway.jpg")],
    ppe: [img("missing_ppe.jpg"), img("missing_gloves.jpg")],
    structural: [img("structural_damage.jpg")],
  },
  after: {
    electrical: img("electrical_panel_repaired.jpg"),
    cable: img("cable_repaired.jpg"),
    chemical: img("chemical_area_cleaned.jpg"),
    slip: img("loading_bay_cleaned.jpg"),
    machine: img("machine_guard_fixed.jpg"),
  },
  dashboards: {
    critical: img("electrical_panel_damage.jpg"),
    report: img("monthly_report_preview.jpg"),
    shield: img("guardrail_shield.jpg"),
    warning: img("guardrail_warning.jpg"),
  },
  reports: {
    august: img("monthly_report_preview.jpg"),
  },
  workers: {
    "Kasun Perera": img("avatar-kasun.svg"),
    "Arun Kumar": img("avatar-arun.svg"),
    "R. Silva": img("avatar-rsilva.svg"),
    "Kamal": img("avatar-kamal.svg"),
    "Nimal Perera": img("avatar-nimal.svg"),
    "Kavitha Rajan": img("avatar-kavitha.svg"),
    "Anonymous reporter": img("avatar-anonymous.svg"),
    "Anonymous Worker": img("avatar-anonymous.svg"),
  },
  incidents: {
    "INC-2026-00421": { before: img("electrical_panel_damage.jpg"), after: img("electrical_panel_repaired.jpg") },
    "INC-2026-00422": { before: img("machine_smoke.jpg"), after: img("machine_guard_fixed.jpg") },
    "INC-2026-00420": { before: img("chemical_spill.jpg"), after: img("chemical_area_cleaned.jpg") },
    "INC-2026-00419": { before: img("welding_section.jpg"), after: img("machine_guard_fixed.jpg") },
    "INC-2026-00418": { before: img("missing_ppe.jpg"), after: img("missing_ppe.jpg") },
    "INC-2026-00417": { before: img("oil_spill_floor.jpg"), after: img("loading_bay_cleaned.jpg") },
    "INC-2026-00416": { before: img("missing_ppe.jpg"), after: img("missing_ppe.jpg") },
    "INC-2026-00415": { before: img("structural_damage.jpg"), after: img("loading_bay_cleaned.jpg") },
    "INC-2026-00414": { before: img("electrical_spark.jpg"), after: img("electrical_panel_repaired.jpg") },
    "INC-2026-00413": { before: img("machine_guard_missing.jpg"), after: img("machine_guard_fixed.jpg") },
    "INC-2026-00412": { before: img("structural_damage.jpg"), after: img("loading_bay.jpg") },
    "INC-2026-00411": { before: img("overheating_equipment.jpg"), after: img("welding_section.jpg") },
    "INC-2026-00410": { before: img("chemical_spill.jpg"), after: img("chemical_area_cleaned.jpg") },
    "INC-2026-00409": { before: img("wet_floor.jpg"), after: img("loading_bay_cleaned.jpg") },
    "INC-2026-00408": { before: img("missing_gloves.jpg"), after: img("missing_ppe.jpg") },
    "INC-2026-00407": { before: img("rotating_equipment.jpg"), after: img("machine_guard_fixed.jpg") },
    "INC-2026-00406": { before: img("blocked_walkway.jpg"), after: img("loading_bay_cleaned.jpg") },
    "INC-2026-00405": { before: img("machine_smoke.jpg"), after: img("welding_section.jpg") },
    "INC-2026-00404": { before: img("chemical_spill.jpg"), after: img("chemical_area_cleaned.jpg") },
    "INC-2026-00403": { before: img("damaged_cable.jpg"), after: img("cable_repaired.jpg") },
    "INC-2026-00402": { before: img("machine_guard_missing.jpg"), after: img("machine_guard_fixed.jpg") },
    "INC-2026-00401": { before: img("chemical_storage.jpg"), after: img("chemical_area_cleaned.jpg") },
    "INC-2026-00400": { before: img("electrical_room.jpg"), after: img("electrical_panel_repaired.jpg") },
    "DEMO-HORIZON-004": { before: img("electrical_spark.jpg"), after: img("electrical_panel_repaired.jpg") },
    "DEMO-HORIZON-001": { before: img("electrical_panel_damage.jpg"), after: img("electrical_panel_repaired.jpg") },
  } as Record<string, { before: string; after: string }>,
  evidence: {
    "EV-421-B": {
      image_id: "EV-421-B",
      src: img("damaged_cable.jpg"),
      alt: "Damaged electrical cable at CNC-04",
      incident_id: "INC-2026-00421",
      source: "Telegram",
      uploaded_by: "Worker",
      timestamp: "2026-08-10",
      type: "before" as const,
      category: "electrical",
      location: "CNC Area",
      verification_status: "reported",
    },
    "EV-421-A": {
      image_id: "EV-421-A",
      src: img("cable_repaired.jpg"),
      alt: "Repaired cable at CNC-04",
      incident_id: "INC-2026-00421",
      source: "Officer",
      uploaded_by: "Safety Officer",
      timestamp: "2026-08-11",
      type: "after" as const,
      category: "electrical",
      location: "CNC Area",
      verification_status: "verified",
    },
    "EV-417-B": {
      image_id: "EV-417-B",
      src: img("oil_spill_floor.jpg"),
      alt: "Oil spill on Loading Bay floor",
      incident_id: "INC-2026-00417",
      source: "Telegram",
      uploaded_by: "Worker",
      timestamp: "2026-08-20",
      type: "before" as const,
      category: "slip/trip",
      location: "Loading Bay",
      verification_status: "reported",
    },
    "EV-417-A": {
      image_id: "EV-417-A",
      src: img("loading_bay_cleaned.jpg"),
      alt: "Loading bay cleaned and dry",
      incident_id: "INC-2026-00417",
      source: "Officer",
      uploaded_by: "Safety Officer",
      timestamp: "2026-08-20",
      type: "after" as const,
      category: "slip/trip",
      location: "Loading Bay",
      verification_status: "verified",
    },
    "EV-422-T": {
      image_id: "EV-422-T",
      src: img("machine_smoke.jpg"),
      alt: "Telegram image of machine-area smoke",
      incident_id: "INC-2026-00422",
      source: "Telegram",
      uploaded_by: "Kamal",
      timestamp: "2026-08-31T10:32:00+00:00",
      type: "worker" as const,
      category: "fire/smoke",
      location: "CNC Area",
      verification_status: "reported",
    },
  } as Record<string, DemoImageRecord>,
  storage: {
    totalImages: 452,
    beforeEvidence: 210,
    afterEvidence: 180,
    pendingReview: 62,
  },
};

const VISION: Record<string, DemoVisionAnalysis> = {
  "INC-2026-00421": {
    label: "Demo AI Analysis Result",
    objects: ["exposed wire visible", "damaged cable insulation", "worker near electrical panel"],
    hazard: "electrical",
    confidence: 88,
  },
  "INC-2026-00420": {
    label: "Demo AI Analysis Result",
    objects: ["liquid spill visible", "chemical container nearby"],
    hazard: "chemical",
    confidence: 81,
  },
  "INC-2026-00417": {
    label: "Demo AI Analysis Result",
    objects: ["liquid on floor", "walkway unmarked"],
    hazard: "slip/trip",
    confidence: 79,
  },
  "INC-2026-00422": {
    label: "Demo AI Analysis Result",
    objects: ["CNC machine", "Smoke plume", "Aisle marking"],
    hazard: "fire/smoke",
    confidence: 91,
  },
};

function categoryKey(category?: string | null) {
  return (category || "").toLowerCase().trim();
}

export function categoryImage(category?: string | null): string {
  return CATEGORY_IMAGE[categoryKey(category)] || img("factory_machine_area.jpg");
}

export function locationImage(location?: string | null): string {
  if (!location) return img("main_workshop_floor.jpg");
  const hit = demoImages.locations[location as keyof typeof demoImages.locations];
  if (hit) return hit.src;
  const key = Object.keys(demoImages.locations).find((name) => name.toLowerCase() === location.toLowerCase());
  return key ? demoImages.locations[key as keyof typeof demoImages.locations].src : img("main_workshop_floor.jpg");
}

export function avatarFor(name?: string | null, anonymous?: boolean): string {
  if (anonymous || !name) return demoImages.workers["Anonymous Worker"];
  return demoImages.workers[name as keyof typeof demoImages.workers] || demoImages.workers["Anonymous Worker"];
}

export function incidentPair(incidentId?: string | null, category?: string | null) {
  if (incidentId && demoImages.incidents[incidentId]) return demoImages.incidents[incidentId];
  return { before: categoryImage(category), after: demoImages.after.electrical };
}

export function incidentThumbnail(incidentId?: string | null, category?: string | null, location?: string | null): string {
  if (incidentId && demoImages.incidents[incidentId]) return demoImages.incidents[incidentId].before;
  if (category) return categoryImage(category);
  return locationImage(location);
}

export function visionAnalysis(incidentId?: string | null, category?: string | null): DemoVisionAnalysis {
  if (incidentId && VISION[incidentId]) return VISION[incidentId];
  const key = categoryKey(category);
  if (key.includes("fire")) return VISION["INC-2026-00422"];
  if (key.includes("chemical")) return VISION["INC-2026-00420"];
  if (key.includes("slip")) return VISION["INC-2026-00417"];
  return VISION["INC-2026-00421"];
}

export function evidenceRecord(id?: string | null): DemoImageRecord | null {
  if (!id) return null;
  return demoImages.evidence[id] ?? null;
}

export const locationRiskDemo = [
  { location: "Electrical Room", risk: "CRITICAL", src: locationImage("Electrical Room"), active: 4 },
  { location: "Chemical Storage Room", risk: "HIGH", src: locationImage("Chemical Storage Room"), active: 3 },
  { location: "CNC Area", risk: "HIGH", src: locationImage("CNC Area"), active: 3 },
  { location: "Welding Section", risk: "HIGH", src: locationImage("Welding Section"), active: 2 },
  { location: "Loading Bay", risk: "MEDIUM", src: locationImage("Loading Bay"), active: 2 },
  { location: "Main Workshop Floor", risk: "LOW", src: locationImage("Main Workshop Floor"), active: 1 },
];

export const recentEvidenceFeed = [
  {
    title: "Worker uploaded new evidence",
    src: img("chemical_spill.jpg"),
    location: "Chemical Storage Room",
    when: "5 minutes ago",
    channel: "telegram",
    incident_id: "INC-2026-00420",
  },
  {
    title: "Telegram image received",
    src: img("machine_smoke.jpg"),
    location: "CNC Area",
    when: "12 minutes ago",
    channel: "telegram",
    incident_id: "INC-2026-00422",
  },
  {
    title: "Telegram photo attached",
    src: img("electrical_panel_damage.jpg"),
    location: "CNC Area",
    when: "18 minutes ago",
    channel: "telegram",
    incident_id: "INC-2026-00421",
  },
];
