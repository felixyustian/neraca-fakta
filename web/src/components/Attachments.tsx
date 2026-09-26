import { useEffect, useMemo, useRef } from "react";
import { useI18n } from "../i18n";

export const MAX_FILES = 3;
const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

/** Keep only acceptable images, up to the limit. Returns [kept, errorKey]. */
export function acceptFiles(current: File[], incoming: File[]): [File[], "attachTooMany" | "attachBadType" | null] {
  const ok = incoming.filter((f) => TYPES.includes(f.type) && f.size <= MAX_BYTES);
  const bad = ok.length < incoming.length;
  const next = [...current, ...ok].slice(0, MAX_FILES);
  const tooMany = current.length + ok.length > MAX_FILES;
  return [next, tooMany ? "attachTooMany" : bad ? "attachBadType" : null];
}

interface Props {
  files: File[];
  onChange: (f: File[]) => void;
  onError: (key: "attachTooMany" | "attachBadType" | null) => void;
  needsAI: boolean;
}

export default function Attachments({ files, onChange, onError, needsAI }: Props) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const urls = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => urls.forEach((u) => URL.revokeObjectURL(u)), [urls]);

  return (
    <div className="attach">
      <div className="attach-row">
        <button
          type="button"
          className="ghost attach-btn"
          onClick={() => input.current?.click()}
          disabled={files.length >= MAX_FILES}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <path
              d="M20 12.5 12.5 20a5 5 0 0 1-7-7L13 5.5a3.3 3.3 0 0 1 4.7 4.7L10.2 17.7a1.7 1.7 0 0 1-2.4-2.4l7-7"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          {t("attach")}
        </button>
        <span className="muted small">{t("attachHint")}</span>
        <input
          ref={input}
          type="file"
          accept={TYPES.join(",")}
          multiple
          hidden
          onChange={(e) => {
            const [next, err] = acceptFiles(files, [...(e.target.files ?? [])]);
            onChange(next);
            onError(err);
            e.target.value = "";
          }}
        />
      </div>
      {files.length > 0 && (
        <>
          <ul className="thumbs">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`}>
                <img src={urls[i]} alt={f.name} />
                <button
                  type="button"
                  className="thumb-x"
                  aria-label={`${t("removeImage")}: ${f.name}`}
                  onClick={() => {
                    onChange(files.filter((_, j) => j !== i));
                    onError(null);
                  }}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
          {needsAI && <p className="hint warn">{t("attachNeedsAI")}</p>}
        </>
      )}
    </div>
  );
}
