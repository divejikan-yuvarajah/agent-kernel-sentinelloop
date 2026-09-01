import { useState } from "react";

import { Button, InputField, Modal, SelectDropdown } from "@ds/index";

import { createManualIncident, type ManualIncidentResponse } from "../api/client";
import { readOperatorRole } from "../demo/operatorRole";

const CATEGORIES = [
  "Electrical",
  "Fire/Smoke",
  "Chemical",
  "Machine",
  "Slip/Trip",
  "Missing PPE",
  "Structural",
  "Unsafe Behaviour",
  "Other",
];

const ALLOWED = new Set(["image/jpeg", "image/jpg", "image/png", "image/webp"]);

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated?: (result: ManualIncidentResponse) => void;
};

export function LogHazardModal({ open, onClose, onCreated }: Props) {
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("Fire/Smoke");
  const [location, setLocation] = useState("");
  const [people, setPeople] = useState("1");
  const [active, setActive] = useState(true);
  const [injured, setInjured] = useState(false);
  const [photoName, setPhotoName] = useState("");
  const [photo, setPhoto] = useState<{ base64: string; filename: string; type: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function reset() {
    setDescription("");
    setCategory("Fire/Smoke");
    setLocation("");
    setPeople("1");
    setActive(true);
    setInjured(false);
    setPhoto(null);
    setPhotoName("");
    setError(null);
  }

  function close() {
    reset();
    onClose();
  }

  function onFile(file: File | undefined) {
    if (!file) {
      setPhoto(null);
      setPhotoName("");
      return;
    }
    const type = file.type.toLowerCase() || "";
    if (!ALLOWED.has(type) && !/\.(jpe?g|png|webp)$/i.test(file.name)) {
      setError("Image must be jpg, png, or webp");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      const base64 = raw.includes(",") ? raw.split(",")[1] : raw;
      setPhoto({ base64, filename: file.name, type: type || "image/jpeg" });
      setPhotoName(file.name);
      setError(null);
    };
    reader.readAsDataURL(file);
  }

  async function submit() {
    setError(null);
    if (!description.trim()) {
      setError("Description is required before creating incident");
      return;
    }
    if (!location.trim()) {
      setError("Location is required before creating incident");
      return;
    }
    if (!category.trim()) {
      setError("Category is required before creating incident");
      return;
    }
    const peopleExposed = Number(people);
    if (!Number.isFinite(peopleExposed) || peopleExposed < 0) {
      setError("People exposed must be a number");
      return;
    }
    setSubmitting(true);
    try {
      const result = await createManualIncident({
        description: description.trim(),
        category,
        location: location.trim(),
        people_exposed: peopleExposed,
        is_active: active,
        injury_reported: injured,
        photo_base64: photo?.base64,
        photo_filename: photo?.filename,
        photo_content_type: photo?.type,
        created_by: readOperatorRole() === "admin" ? "admin" : "dashboard_officer",
      });
      onCreated?.(result);
      close();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the incident.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} title="Log a Hazard" onClose={close} className="ds-modal--hazard">
      <p className="ds-page-lead" style={{ marginTop: 0 }}>
        Phone-in, verbal, and inspection reports enter the same AI pipeline as Telegram.
      </p>
      <label className="ds-field" htmlFor="hazard-description">
        <span className="ds-field__label">Description</span>
        <textarea
          id="hazard-description"
          className="ds-input"
          rows={4}
          value={description}
          placeholder="Smoke detected near welding machine"
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <SelectDropdown
        label="Category"
        name="category"
        value={category}
        onChange={(event) => setCategory(event.target.value)}
        options={CATEGORIES.map((item) => ({ value: item, label: item }))}
      />
      <InputField
        label="Location"
        name="location"
        value={location}
        placeholder="CNC Area"
        onChange={(event) => setLocation(event.target.value)}
      />
      <InputField
        label="People exposed"
        name="people"
        type="number"
        min={0}
        value={people}
        onChange={(event) => setPeople(event.target.value)}
      />
      <label className="ds-toggle">
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
        <span>Active hazard</span>
      </label>
      <label className="ds-toggle">
        <input type="checkbox" checked={injured} onChange={(event) => setInjured(event.target.checked)} />
        <span>Injury reported</span>
      </label>
      <label className="ds-field" htmlFor="hazard-photo">
        <span className="ds-field__label">Photo (optional)</span>
        <input
          id="hazard-photo"
          className="ds-input"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => onFile(event.target.files?.[0])}
        />
        {photoName ? <span className="ds-mono">{photoName}</span> : null}
      </label>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : null}
      <div className="ds-toolbar" style={{ marginTop: 16 }}>
        <Button disabled={submitting} onClick={() => void submit()}>
          {submitting ? "Submitting…" : "Submit hazard"}
        </Button>
        <Button variant="ghost" onClick={close}>
          Cancel
        </Button>
      </div>
    </Modal>
  );
}
