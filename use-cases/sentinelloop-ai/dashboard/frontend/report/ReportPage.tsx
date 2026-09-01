import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { AppShell, Button, InputField, SelectDropdown } from "@ds/index";

import {
  createManualIncident,
  type ManualIncidentPayload,
  type ManualIncidentResponse,
} from "@/api/client";
import { useDemoMode } from "@/demo/useDemoMode";
import "./report.css";

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

type FieldErrors = Partial<
  Record<
    "description" | "category" | "location" | "people_exposed" | "is_active" | "injury_reported" | "photo" | "form",
    string
  >
>;

type FormState = {
  description: string;
  category: string;
  location: string;
  equipment: string;
  people: string;
  isActive: boolean | null;
  injured: boolean | null;
  reporterName: string;
  photo: { base64: string; filename: string; type: string } | null;
};

const INITIAL: FormState = {
  description: "",
  category: "",
  location: "",
  equipment: "",
  people: "0",
  isActive: null,
  injured: null,
  reporterName: "",
  photo: null,
};

function validate(form: FormState): FieldErrors {
  const errors: FieldErrors = {};
  const description = form.description.trim();
  if (!description) errors.description = "Description is required.";
  else if (description.length < 10) errors.description = "Description must be at least 10 characters.";

  if (!form.category.trim()) errors.category = "Choose a hazard category.";
  else if (!CATEGORIES.some((item) => item.toLowerCase() === form.category.toLowerCase())) {
    errors.category = "Category must be one of the listed hazard types.";
  }

  if (!form.location.trim()) errors.location = "Location is required.";

  const people = Number(form.people);
  if (!Number.isFinite(people) || !Number.isInteger(people)) {
    errors.people_exposed = "People exposed must be a whole number.";
  } else if (people < 0) {
    errors.people_exposed = "People exposed cannot be negative.";
  }

  if (form.isActive === null) errors.is_active = "Select whether the hazard is currently active.";
  if (form.injured === null) errors.injury_reported = "Select whether anyone has been injured.";

  return errors;
}

export function ReportPage() {
  const [demo] = useDemoMode();
  const [form, setForm] = useState<FormState>(INITIAL);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<ManualIncidentResponse | null>(null);

  const errors = useMemo(() => validate(form), [form]);
  const valid = Object.keys(errors).length === 0;

  function mark(field: string) {
    setTouched((current) => ({ ...current, [field]: true }));
  }

  function showError(field: keyof FieldErrors) {
    return touched[field] || submitting ? errors[field] : undefined;
  }

  function onFile(file: File | undefined) {
    mark("photo");
    if (!file) {
      setForm((current) => ({ ...current, photo: null }));
      return;
    }
    const type = file.type.toLowerCase() || "";
    if (!ALLOWED.has(type) && !/\.(jpe?g|png|webp)$/i.test(file.name)) {
      setSubmitError("Image must be jpg, png, or webp");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      const base64 = raw.includes(",") ? raw.split(",")[1] : raw;
      setForm((current) => ({
        ...current,
        photo: { base64, filename: file.name, type: type || "image/jpeg" },
      }));
      setSubmitError(null);
    };
    reader.readAsDataURL(file);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched({
      description: true,
      category: true,
      location: true,
      people_exposed: true,
      is_active: true,
      injury_reported: true,
    });
    if (!valid) return;
    setSubmitting(true);
    setSubmitError(null);
    const payload: ManualIncidentPayload = {
      description: form.description.trim(),
      category: form.category,
      location: form.location.trim(),
      equipment_involved: form.equipment.trim() || undefined,
      people_exposed: Number(form.people),
      is_active: Boolean(form.isActive),
      injury_reported: Boolean(form.injured),
      reporter_name: form.reporterName.trim() || undefined,
      photo_base64: form.photo?.base64,
      photo_filename: form.photo?.filename,
      photo_content_type: form.photo?.type,
    };
    try {
      const created = await createManualIncident(payload);
      setResult(created);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not create the incident.");
    } finally {
      setSubmitting(false);
    }
  }

  function resetForm() {
    setForm(INITIAL);
    setTouched({});
    setSubmitError(null);
    setResult(null);
  }

  return (
    <AppShell title="Log a hazard" operationalStatus="OPEN">
      <p className="ds-page-lead">
        Phoned-in or in-person reports enter the same intake → incident → risk → guidance → coordination pipeline as
        Telegram{demo ? " (demo mode uses the deterministic matrix)" : ""}. Risk is never chosen from a dropdown.
      </p>

      {result ? (
        <section className="sl-report-confirm" aria-live="polite">
          <p className="sl-kicker">Confirmation</p>
          <h2 className="sl-report-confirm__title">Hazard logged</h2>
          <dl className="sl-report-confirm__grid">
            <div>
              <dt>Incident ID</dt>
              <dd className="ds-mono">{result.incident_id || "—"}</dd>
            </div>
            <div>
              <dt>Risk level</dt>
              <dd>
                <strong>{result.risk_level || "—"}</strong>
                {result.risk_score != null ? <span className="ds-mono"> · score {result.risk_score}</span> : null}
              </dd>
            </div>
            <div>
              <dt>Risk explanation</dt>
              <dd>{result.risk_explanation || "Deterministic matrix applied through risk_agent."}</dd>
            </div>
            <div>
              <dt>Guidance</dt>
              <dd>{result.guidance_text || "Guidance was generated through guidance_agent."}</dd>
            </div>
            <div>
              <dt>Channel</dt>
              <dd className="ds-mono">{result.input_channel}</dd>
            </div>
          </dl>
          <div className="ds-toolbar">
            {result.incident_id ? (
              <Link className="ds-btn" to={`/incidents/${encodeURIComponent(result.incident_id)}`}>
                Open incident detail
              </Link>
            ) : null}
            <Button variant="ghost" onClick={resetForm}>
              Log another hazard
            </Button>
          </div>
        </section>
      ) : (
        <form className="sl-report-form" onSubmit={(event) => void onSubmit(event)} noValidate>
          <label className="ds-field" htmlFor="report-description">
            <span className="ds-field__label">Description</span>
            <textarea
              id="report-description"
              className={`ds-input${showError("description") ? " is-invalid" : ""}`}
              rows={5}
              value={form.description}
              placeholder="Describe what happened, where, and who is nearby"
              onBlur={() => mark("description")}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            />
            {showError("description") ? <span className="sl-field-error">{showError("description")}</span> : null}
          </label>

          <SelectDropdown
            label="Category"
            name="category"
            value={form.category}
            onChange={(event) => {
              mark("category");
              setForm((current) => ({ ...current, category: event.target.value }));
            }}
            options={[{ value: "", label: "Select category" }, ...CATEGORIES.map((item) => ({ value: item, label: item }))]}
          />
          {showError("category") ? <span className="sl-field-error">{showError("category")}</span> : null}

          <InputField
            label="Location"
            name="location"
            value={form.location}
            placeholder="CNC Area / Electrical Room"
            onBlur={() => mark("location")}
            onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))}
          />
          {showError("location") ? <span className="sl-field-error">{showError("location")}</span> : null}

          <InputField
            label="Equipment involved (optional)"
            name="equipment"
            value={form.equipment}
            placeholder="Machine 4 isolator"
            onChange={(event) => setForm((current) => ({ ...current, equipment: event.target.value }))}
          />

          <InputField
            label="People exposed"
            name="people"
            type="number"
            min={0}
            value={form.people}
            onBlur={() => mark("people_exposed")}
            onChange={(event) => setForm((current) => ({ ...current, people: event.target.value }))}
          />
          {showError("people_exposed") ? <span className="sl-field-error">{showError("people_exposed")}</span> : null}

          <fieldset className="sl-report-toggle">
            <legend>Is the hazard currently active?</legend>
            <label>
              <input
                type="radio"
                name="is_active"
                checked={form.isActive === true}
                onChange={() => {
                  mark("is_active");
                  setForm((current) => ({ ...current, isActive: true }));
                }}
              />
              Yes
            </label>
            <label>
              <input
                type="radio"
                name="is_active"
                checked={form.isActive === false}
                onChange={() => {
                  mark("is_active");
                  setForm((current) => ({ ...current, isActive: false }));
                }}
              />
              No
            </label>
            {showError("is_active") ? <span className="sl-field-error">{showError("is_active")}</span> : null}
          </fieldset>

          <fieldset className="sl-report-toggle">
            <legend>Has anyone already been injured?</legend>
            <label>
              <input
                type="radio"
                name="injury"
                checked={form.injured === true}
                onChange={() => {
                  mark("injury_reported");
                  setForm((current) => ({ ...current, injured: true }));
                }}
              />
              Yes
            </label>
            <label>
              <input
                type="radio"
                name="injury"
                checked={form.injured === false}
                onChange={() => {
                  mark("injury_reported");
                  setForm((current) => ({ ...current, injured: false }));
                }}
              />
              No
            </label>
            {showError("injury_reported") ? (
              <span className="sl-field-error">{showError("injury_reported")}</span>
            ) : null}
          </fieldset>

          <InputField
            label="Reporter name (optional — leave blank for anonymous)"
            name="reporter"
            value={form.reporterName}
            placeholder="Duty officer / leave blank"
            onChange={(event) => setForm((current) => ({ ...current, reporterName: event.target.value }))}
          />

          <label className="ds-field" htmlFor="report-photo">
            <span className="ds-field__label">Photo (optional)</span>
            <input
              id="report-photo"
              className="ds-input"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => onFile(event.target.files?.[0])}
            />
            {form.photo ? <span className="ds-mono">{form.photo.filename}</span> : null}
          </label>

          {submitError ? (
            <p className="sl-field-error" role="alert">
              {submitError}
            </p>
          ) : null}

          <div className="ds-toolbar">
            <Button type="submit" disabled={!valid || submitting}>
              {submitting ? "Submitting…" : "Submit hazard"}
            </Button>
            <Link className="ds-btn ds-btn--ghost" to="/dashboard">
              Cancel
            </Link>
          </div>
        </form>
      )}
    </AppShell>
  );
}

export default ReportPage;
