import { jsx, jsxs } from "react/jsx-runtime";
import { useState, useEffect, useRef } from "react";
import { onGp } from 'data:text/javascript,export const onGp=()=>()=>{}';
const LETTERS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
  ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
  ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
  ["z", "x", "c", "v", "b", "n", "m"],
  ["?123", "SHIFT", "SPACE", "\u232B", "ENTER"]
];
const SYMBOLS = [
  ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],
  ["-", "_", "=", "+", "[", "]", "{", "}", "\xB1", "~"],
  [";", ":", "'", '"', ",", ".", "<", ">", "?", "/"],
  ["\\", "|", "`", "\u20AC", "\xA3", "\xA5", "\xA7", "\xB0", "\xBF", "\xA1"],
  ["abc", "SPACE", "\u232B", "ENTER"]
];
function VirtualKeyboard({ title, password = false, initialValue = "", placeholder, onConfirm, onCancel }) {
  const [value, setValue] = useState(initialValue);
  const [layout, setLayout] = useState("letters");
  const [row, setRow] = useState(1);
  const [col, setCol] = useState(0);
  const [shifted, setShifted] = useState(false);
  const rows = layout === "letters" ? LETTERS : SYMBOLS;
  const stateRef = useRef({ row, col, shifted, value, rows });
  useEffect(() => {
    stateRef.current = { row, col, shifted, value, rows };
  }, [row, col, shifted, value, rows]);
  const onConfirmRef = useRef(onConfirm);
  const onCancelRef = useRef(onCancel);
  useEffect(() => {
    onConfirmRef.current = onConfirm;
  }, [onConfirm]);
  useEffect(() => {
    onCancelRef.current = onCancel;
  }, [onCancel]);
  const toggleLayout = () => {
    setLayout((l) => {
      const next = l === "letters" ? "symbols" : "letters";
      const nextRows = next === "letters" ? LETTERS : SYMBOLS;
      const r = Math.min(stateRef.current.row, nextRows.length - 1);
      setRow(r);
      setCol((c) => Math.min(c, nextRows[r].length - 1));
      return next;
    });
  };
  const pressKey = (key) => {
    const { shifted: shifted2, value: value2 } = stateRef.current;
    switch (key) {
      case "SHIFT":
        setShifted((s) => !s);
        break;
      case "SPACE":
        setValue((v) => v + " ");
        break;
      case "\u232B":
        setValue((v) => v.slice(0, -1));
        break;
      case "ENTER":
        onConfirmRef.current(value2);
        break;
      case "?123":
      case "abc":
        toggleLayout();
        break;
      default: {
        const ch = shifted2 ? key.toUpperCase() : key;
        setValue((v) => v + ch);
        if (shifted2) setShifted(false);
      }
    }
  };
  useEffect(() => {
    const offs = [
      onGp("gp:dpad-up", () => {
        const { row: row2, rows: rows2 } = stateRef.current;
        const newRow = Math.max(0, row2 - 1);
        setRow(newRow);
        setCol((c) => Math.min(c, rows2[newRow].length - 1));
      }),
      onGp("gp:dpad-down", () => {
        const { row: row2, rows: rows2 } = stateRef.current;
        const newRow = Math.min(rows2.length - 1, row2 + 1);
        setRow(newRow);
        setCol((c) => Math.min(c, rows2[newRow].length - 1));
      }),
      onGp("gp:dpad-left", () => {
        const { row: row2, col: col2, rows: rows2 } = stateRef.current;
        setCol(col2 > 0 ? col2 - 1 : rows2[row2].length - 1);
      }),
      onGp("gp:dpad-right", () => {
        const { row: row2, col: col2, rows: rows2 } = stateRef.current;
        setCol(col2 < rows2[row2].length - 1 ? col2 + 1 : 0);
      }),
      onGp("gp:confirm", () => {
        const { row: row2, col: col2, rows: rows2 } = stateRef.current;
        pressKey(rows2[row2][col2]);
      }),
      onGp("gp:back", () => onCancelRef.current()),
      onGp("gp:l1", () => setShifted((s) => !s)),
      onGp("gp:r1", () => toggleLayout())
    ];
    return () => offs.forEach((o) => o());
  }, []);
  const displayValue = password ? "\u25CF".repeat(value.length) : value;
  return /* @__PURE__ */ jsxs("div", { style: { display: "flex", flexDirection: "column", gap: 10 }, children: [
    title && /* @__PURE__ */ jsx("div", { style: { fontSize: 13, color: "var(--gc-accent-soft, #a78bfa)", textAlign: "center", letterSpacing: 1, marginBottom: 2 }, children: title }),
    /* @__PURE__ */ jsx("div", { style: {
      background: "var(--gc-kb-field, rgba(0,0,0,0.45))",
      border: "1px solid color-mix(in srgb, var(--gc-accent, #7c3aed) 50%, transparent)",
      borderRadius: 10,
      padding: "10px 16px",
      minHeight: 44,
      // NOT `--gc-kb-ink-strong`: that one is the lettering on the focused
      // key, which sits on an accent fill and stays light in every theme.
      // This sits on `--gc-kb-field`, which a paper theme makes pale — one
      // token for both put white text on a white field.
      fontSize: 20,
      letterSpacing: 4,
      color: "var(--gc-kb-field-ink, #fff)",
      fontFamily: "monospace",
      display: "flex",
      alignItems: "center",
      justifyContent: displayValue ? "flex-end" : "center",
      overflow: "hidden",
      whiteSpace: "nowrap"
    }, children: displayValue || /* @__PURE__ */ jsx("span", { style: { opacity: 0.25, fontSize: 14, letterSpacing: 1 }, children: placeholder ?? (password ? "enter password" : "start typing\u2026") }) }),
    rows.map((keys, ri) => /* @__PURE__ */ jsx("div", { style: { display: "flex", justifyContent: "center", gap: 4 }, children: keys.map((key, ci) => {
      const focused = ri === row && ci === col;
      const isShift = key === "SHIFT";
      const isSpace = key === "SPACE";
      const isDel = key === "\u232B";
      const isEnter = key === "ENTER";
      const isMode = key === "?123" || key === "abc";
      const isSpecial = isShift || isSpace || isDel || isEnter || isMode;
      const label = isShift ? shifted ? "\u21E7\u25CF" : "\u21E7" : isSpace ? "SPACE" : isEnter ? "\u21B5 OK" : !isSpecial && layout === "letters" && shifted ? key.toUpperCase() : key;
      return /* @__PURE__ */ jsx(
        "button",
        {
          onClick: () => pressKey(key),
          style: {
            minWidth: isSpace ? 100 : isShift || isEnter ? 64 : isDel ? 52 : isMode ? 54 : 34,
            height: 34,
            borderRadius: 7,
            border: focused ? "2px solid var(--gc-accent, #7c3aed)" : "1px solid var(--gc-kb-key-edge, rgba(255,255,255,0.09))",
            background: focused ? "color-mix(in srgb, var(--gc-accent, #7c3aed) 38%, transparent)" : isShift && shifted || isMode ? "color-mix(in srgb, var(--gc-accent, #7c3aed) 20%, transparent)" : isEnter ? "color-mix(in srgb, var(--gc-accent, #7c3aed) 15%, transparent)" : "var(--gc-kb-key, rgba(255,255,255,0.05))",
            color: focused ? "var(--gc-kb-ink-strong, #fff)" : isEnter || isMode ? "var(--gc-accent-bright, #c4b5fd)" : "var(--gc-kb-ink, rgba(255,255,255,0.78))",
            fontSize: isSpecial ? 11 : 13,
            fontWeight: isSpecial ? 600 : 400,
            cursor: "pointer",
            transition: "all 0.08s",
            padding: "0 4px",
            flexShrink: 0
          },
          children: label
        },
        `${layout}-${ri}-${ci}`
      );
    }) }, `${layout}-${ri}`)),
    /* @__PURE__ */ jsx(
      "button",
      {
        onClick: onCancelRef.current,
        style: {
          marginTop: 2,
          padding: "7px",
          borderRadius: 8,
          cursor: "pointer",
          background: "transparent",
          border: "1px solid var(--gc-kb-key-edge, rgba(255,255,255,0.08))",
          color: "var(--gc-kb-ink-dim, rgba(255,255,255,0.3))",
          fontSize: 12
        },
        children: "Cancel"
      }
    ),
    /* @__PURE__ */ jsx("div", { style: { textAlign: "center", fontSize: 10, color: "var(--gc-kb-ink-faint, rgba(255,255,255,0.18))", letterSpacing: 1 }, children: "D-Pad navigate \xB7 \u2715 type \xB7 \u25CB cancel \xB7 L1 shift \xB7 R1 symbols \xB7 \u21B5 OK" })
  ] });
}
export {
  VirtualKeyboard
};
