/* Hand-drawn 16px stroke icons — one weight, round caps, currentColor.
   Replaces the emoji glyphs used by the Tk UI so every glyph shares a stroke. */

const Icon = ({ name, size = 15, stroke = 1.6, className = "" }) => {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: stroke,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className,
    "aria-hidden": "true"
  };
  const paths = {
    monitor: (
      <>
        <rect x="3" y="4.5" width="18" height="12.5" rx="2.2" />
        <path d="M8.5 20.5h7M12 17v3.5" />
      </>
    ),
    sliders: (
      <>
        <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
        <circle cx="15" cy="7" r="2.1" />
        <circle cx="9" cy="17" r="2.1" />
      </>
    ),
    user: (
      <>
        <circle cx="12" cy="8" r="3.4" />
        <path d="M4.8 20c.7-3.6 3.6-5.6 7.2-5.6s6.5 2 7.2 5.6" />
      </>
    ),
    folder: (
      <>
        <path d="M3.5 7.2c0-1 .8-1.8 1.8-1.8h3.4l1.8 2.2h8.2c1 0 1.8.8 1.8 1.8v8c0 1-.8 1.8-1.8 1.8H5.3c-1 0-1.8-.8-1.8-1.8V7.2Z" />
      </>
    ),
    check: <path d="M4.5 12.4 9.4 17l10.1-10" />,
    refresh: (
      <>
        <path d="M20 11.4a8 8 0 1 0-2.1 6.2" />
        <path d="M20 4.8v6.6h-6.6" />
      </>
    ),
    pause: (
      <>
        <rect x="6.6" y="5" width="3.6" height="14" rx="1.1" />
        <rect x="13.8" y="5" width="3.6" height="14" rx="1.1" />
      </>
    ),
    play: <path d="M7.4 5.2v13.6L19 12 7.4 5.2Z" />,
    reconnect: (
      <>
        <path d="M4.3 10.2A7.9 7.9 0 0 1 18 8.4" />
        <path d="M19.7 13.8A7.9 7.9 0 0 1 6 15.6" />
        <path d="M18.4 4.6v4h-4M5.6 19.4v-4h4" />
      </>
    ),
    external: (
      <>
        <path d="M13.8 4.5H19.5V10" />
        <path d="M19.5 4.5 11 13" />
        <path d="M19.5 14.6v3.6c0 1-.8 1.8-1.8 1.8H5.3c-1 0-1.8-.8-1.8-1.8V6.3c0-1 .8-1.8 1.8-1.8h3.6" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    alert: (
      <>
        <path d="M12 4.6 21 19.4H3L12 4.6Z" />
        <path d="M12 10v4.2M12 17.2v.1" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="8.4" />
        <path d="M12 11v5.2M12 7.9v.1" />
      </>
    ),
    shield: (
      <>
        <path d="M12 3.6 19 6v5.4c0 4-2.8 7-7 8.9-4.2-1.9-7-4.9-7-8.9V6l7-2.4Z" />
        <path d="M9 12.2 11.3 14.5 15.3 10" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="8.4" />
        <path d="M12 7.4V12l3.2 1.9" />
      </>
    ),
    qr: (
      <>
        <rect x="4" y="4" width="6" height="6" rx="1.2" />
        <rect x="14" y="4" width="6" height="6" rx="1.2" />
        <rect x="4" y="14" width="6" height="6" rx="1.2" />
        <path d="M14 14h2.6v2.6H14zM18.4 18.4H20V20h-1.6z" />
      </>
    ),
    bell: (
      <>
        <path d="M6.4 10.2a5.6 5.6 0 0 1 11.2 0c0 4 1.4 5.4 1.4 5.4H5s1.4-1.4 1.4-5.4Z" />
        <path d="M10 19a2.2 2.2 0 0 0 4 0" />
      </>
    ),
    power: (
      <>
        <path d="M12 4.6v7" />
        <path d="M7.6 7.2a7 7 0 1 0 8.8 0" />
      </>
    ),
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    medal: <><circle cx="12" cy="9" r="5.5" /><path d="M8 13.5 6.5 21l5.5-3 5.5 3-1.5-7.5" /></>
  };
  return <svg {...common}>{paths[name] || paths.info}</svg>;
};

const Pulse = ({ size = 16, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.9"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    <path d="M2.6 12h4.2l2.3-6.2 3.5 12.4 2.6-8.6 1.7 2.4h4.5" />
  </svg>
);

Object.assign(window, { Icon, Pulse });
