import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import {
  DEFAULT_CURRENCIES,
  DEFAULT_INDICES,
  DEFAULT_PREFS,
  moveSection,
  NEWS_COUNTS,
  WATCHLIST_MAX,
  type PanelPrefs,
  type SectionId,
  type Side,
} from "../panelPrefs";
import type { MarketSnapshot } from "../types";
import { SECTION_LABEL } from "./MarketPanels";

interface Props {
  open: boolean;
  prefs: PanelPrefs;
  market: MarketSnapshot | null;
  onChange: (p: PanelPrefs) => void;
  onClose: () => void;
}

/** Multi-select chips; `selected === null` means "defaults". */
function ChipPicker({
  options,
  selected,
  defaults,
  onChange,
  label,
}: {
  options: string[];
  selected: string[] | null;
  defaults: string[];
  onChange: (v: string[]) => void;
  label: string;
}) {
  const current = selected ?? defaults.filter((d) => options.includes(d));
  const toggle = (o: string) =>
    onChange(
      current.includes(o)
        ? current.filter((x) => x !== o)
        : [...current, o].sort((a, b) => options.indexOf(a) - options.indexOf(b)),
    );
  return (
    <div className="chip-picker" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o}
          type="button"
          aria-pressed={current.includes(o)}
          className={current.includes(o) ? "pick on" : "pick"}
          onClick={() => toggle(o)}
        >
          {current.includes(o) && <span aria-hidden>✓ </span>}
          {o}
        </button>
      ))}
    </div>
  );
}

export default function PanelSettings({ open, prefs, market, onChange, onClose }: Props) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const [ticker, setTicker] = useState("");
  const [tickerError, setTickerError] = useState<string | null>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      setTicker("");
      setTickerError(null);
      d.showModal();
    } else if (!open && d.open) d.close();
  }, [open]);

  const set = (patch: Partial<PanelPrefs>) => onChange({ ...prefs, ...patch });
  const setSection = (id: SectionId, patch: { side?: Side; visible?: boolean }) =>
    set({ layout: prefs.layout.map((s) => (s.id === id ? { ...s, ...patch } : s)) });

  function addTicker() {
    const sym = ticker.trim().toUpperCase().replace(/^\$/, "").replace(/\.JK$/, "");
    if (!/^[A-Z]{4}$/.test(sym)) return setTickerError(t("watchInvalid"));
    if (prefs.watchlist.includes(sym)) return setTicker("");
    if (prefs.watchlist.length >= WATCHLIST_MAX) return setTickerError(t("watchFull", { n: WATCHLIST_MAX }));
    set({ watchlist: [...prefs.watchlist, sym] });
    setTicker("");
    setTickerError(null);
  }

  const sides: Side[] = ["left", "right"];
  return (
    <dialog ref={ref} className="dialog wide" onClose={onClose} aria-labelledby="panels-title">
      <div className="dialog-body">
        <div className="dialog-head">
          <h2 id="panels-title">{t("customizePanels")}</h2>
          <button type="button" className="icon-btn" aria-label={t("closeLabel")} onClick={onClose}>
            ✕
          </button>
        </div>
        <p className="muted small">{t("customizeIntro")}</p>

        <h3 className="dlg-section">{t("sectionsTitle")}</h3>
        {sides.map((side) => {
          const rows = prefs.layout.filter((s) => s.side === side);
          return (
            <div key={side} className="layout-group">
              <span className="layout-side">{t(side === "left" ? "sideLeft" : "sideRight")}</span>
              {rows.length === 0 && <p className="panel-empty">{t("sideEmpty")}</p>}
              <ul className="layout-list">
                {rows.map((s, i) => (
                  <li key={s.id} className={s.visible ? "" : "hidden-row"}>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={s.visible}
                        onChange={(e) => setSection(s.id, { visible: e.target.checked })}
                      />
                      {t(SECTION_LABEL[s.id])}
                    </label>
                    <span className="layout-actions">
                      <button
                        type="button"
                        className="icon-btn sm"
                        disabled={i === 0}
                        aria-label={t("moveUp")}
                        title={t("moveUp")}
                        onClick={() => onChange(moveSection(prefs, s.id, -1))}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="icon-btn sm"
                        disabled={i === rows.length - 1}
                        aria-label={t("moveDown")}
                        title={t("moveDown")}
                        onClick={() => onChange(moveSection(prefs, s.id, 1))}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="ghost xs"
                        onClick={() => setSection(s.id, { side: side === "left" ? "right" : "left" })}
                      >
                        {side === "left" ? t("toRight") : t("toLeft")}
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
        <label className="check">
          <input type="checkbox" checked={prefs.ticker} onChange={(e) => set({ ticker: e.target.checked })} />
          {t("showTicker")}
        </label>

        <h3 className="dlg-section">{t("watchlistTitle")}</h3>
        <p className="muted small">{t("watchlistHelp", { n: WATCHLIST_MAX })}</p>
        <form
          className="key-row"
          onSubmit={(e) => {
            e.preventDefault();
            addTicker();
          }}
        >
          <input
            type="text"
            value={ticker}
            maxLength={8}
            placeholder="BBCA"
            aria-label={t("watchlistAdd")}
            onChange={(e) => setTicker(e.target.value)}
          />
          <button type="submit" className="ghost">
            {t("add")}
          </button>
        </form>
        {tickerError && <p className="hint warn">{tickerError}</p>}
        {prefs.watchlist.length > 0 && (
          <div className="chip-picker">
            {prefs.watchlist.map((s) => (
              <button
                key={s}
                type="button"
                className="pick on"
                aria-label={t("removeX", { x: s })}
                onClick={() => set({ watchlist: prefs.watchlist.filter((x) => x !== s) })}
              >
                {s} <span aria-hidden>✕</span>
              </button>
            ))}
          </div>
        )}

        {market && market.indices.length > 0 && (
          <>
            <h3 className="dlg-section">{t("indicesTitle")}</h3>
            <ChipPicker
              label={t("indicesTitle")}
              options={market.indices.map((q) => q.code)}
              selected={prefs.indices}
              defaults={DEFAULT_INDICES}
              onChange={(v) => set({ indices: v })}
            />
          </>
        )}
        {market && market.forex.length > 0 && (
          <>
            <h3 className="dlg-section">{t("forexTitle")}</h3>
            <ChipPicker
              label={t("forexTitle")}
              options={market.forex.map((f) => f.currency)}
              selected={prefs.currencies}
              defaults={DEFAULT_CURRENCIES}
              onChange={(v) => set({ currencies: v })}
            />
          </>
        )}
        {market && market.commodities.length > 0 && (
          <>
            <h3 className="dlg-section">{t("commoditiesTitle")}</h3>
            <ChipPicker
              label={t("commoditiesTitle")}
              options={market.commodities.map((c) => c.name)}
              selected={prefs.commodities}
              defaults={market.commodities.map((c) => c.name)}
              onChange={(v) => set({ commodities: v })}
            />
          </>
        )}

        <h3 className="dlg-section">{t("newsTitle")}</h3>
        <div className="seg-toggle" role="group" aria-label={t("newsCount")}>
          {NEWS_COUNTS.map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={prefs.newsCount === n}
              className={prefs.newsCount === n ? "on" : ""}
              onClick={() => set({ newsCount: n })}
            >
              {n}
            </button>
          ))}
        </div>

        <div className="dialog-actions">
          <button
            type="button"
            className="ghost"
            onClick={() => onChange({ ...DEFAULT_PREFS, watchlist: prefs.watchlist })}
          >
            {t("resetLayout")}
          </button>
          <span className="spacer" />
          <button type="button" className="primary" onClick={onClose}>
            {t("done")}
          </button>
        </div>
      </div>
    </dialog>
  );
}
