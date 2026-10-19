/* LiveSupport JSX {"code_sha256":"ef10fc3937792f81a75b6f0301dd197a7c68c8cca122cd2a3a25bbbcb3084382","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"e774ed3dcaf52bf175bb1ead66127d902fc59b7457073a7dec6ceea54b6806f9","schema":1,"source":"icons.jsx","source_sha256":"4b31e2652c0eaf8d4276b254891822597121e40cd0f9649bb14d01649179ba84"} */
(function () {
"use strict";
/* Hand-drawn 16px stroke icons — one weight, round caps, currentColor.
   Replaces the emoji glyphs used by the Tk UI so every glyph shares a stroke. */

const Icon = ({
  name,
  size = 15,
  stroke = 1.6,
  className = ""
}) => {
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
    monitor: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "3",
      y: "4.5",
      width: "18",
      height: "12.5",
      rx: "2.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M8.5 20.5h7M12 17v3.5"
    })),
    sliders: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M4 7h9M17 7h3M4 17h3M11 17h9"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "15",
      cy: "7",
      r: "2.1"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "9",
      cy: "17",
      r: "2.1"
    })),
    user: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "8",
      r: "3.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M4.8 20c.7-3.6 3.6-5.6 7.2-5.6s6.5 2 7.2 5.6"
    })),
    folder: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M3.5 7.2c0-1 .8-1.8 1.8-1.8h3.4l1.8 2.2h8.2c1 0 1.8.8 1.8 1.8v8c0 1-.8 1.8-1.8 1.8H5.3c-1 0-1.8-.8-1.8-1.8V7.2Z"
    })),
    check: /*#__PURE__*/React.createElement("path", {
      d: "M4.5 12.4 9.4 17l10.1-10"
    }),
    refresh: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M20 11.4a8 8 0 1 0-2.1 6.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M20 4.8v6.6h-6.6"
    })),
    pause: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "6.6",
      y: "5",
      width: "3.6",
      height: "14",
      rx: "1.1"
    }), /*#__PURE__*/React.createElement("rect", {
      x: "13.8",
      y: "5",
      width: "3.6",
      height: "14",
      rx: "1.1"
    })),
    play: /*#__PURE__*/React.createElement("path", {
      d: "M7.4 5.2v13.6L19 12 7.4 5.2Z"
    }),
    reconnect: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M4.3 10.2A7.9 7.9 0 0 1 18 8.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M19.7 13.8A7.9 7.9 0 0 1 6 15.6"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M18.4 4.6v4h-4M5.6 19.4v-4h4"
    })),
    external: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M13.8 4.5H19.5V10"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M19.5 4.5 11 13"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M19.5 14.6v3.6c0 1-.8 1.8-1.8 1.8H5.3c-1 0-1.8-.8-1.8-1.8V6.3c0-1 .8-1.8 1.8-1.8h3.6"
    })),
    plus: /*#__PURE__*/React.createElement("path", {
      d: "M12 5v14M5 12h14"
    }),
    alert: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 4.6 21 19.4H3L12 4.6Z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M12 10v4.2M12 17.2v.1"
    })),
    info: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "8.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M12 11v5.2M12 7.9v.1"
    })),
    shield: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 3.6 19 6v5.4c0 4-2.8 7-7 8.9-4.2-1.9-7-4.9-7-8.9V6l7-2.4Z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M9 12.2 11.3 14.5 15.3 10"
    })),
    clock: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "8.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M12 7.4V12l3.2 1.9"
    })),
    qr: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
      x: "4",
      y: "4",
      width: "6",
      height: "6",
      rx: "1.2"
    }), /*#__PURE__*/React.createElement("rect", {
      x: "14",
      y: "4",
      width: "6",
      height: "6",
      rx: "1.2"
    }), /*#__PURE__*/React.createElement("rect", {
      x: "4",
      y: "14",
      width: "6",
      height: "6",
      rx: "1.2"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M14 14h2.6v2.6H14zM18.4 18.4H20V20h-1.6z"
    })),
    bell: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M6.4 10.2a5.6 5.6 0 0 1 11.2 0c0 4 1.4 5.4 1.4 5.4H5s1.4-1.4 1.4-5.4Z"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M10 19a2.2 2.2 0 0 0 4 0"
    })),
    power: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("path", {
      d: "M12 4.6v7"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M7.6 7.2a7 7 0 1 0 8.8 0"
    })),
    more: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "5",
      cy: "12",
      r: "1"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "12",
      r: "1"
    }), /*#__PURE__*/React.createElement("circle", {
      cx: "19",
      cy: "12",
      r: "1"
    })),
    medal: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "9",
      r: "5.5"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M8 13.5 6.5 21l5.5-3 5.5 3-1.5-7.5"
    }))
  };
  return /*#__PURE__*/React.createElement("svg", common, paths[name] || paths.info);
};
const Pulse = ({
  size = 16,
  className = ""
}) => /*#__PURE__*/React.createElement("svg", {
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "1.9",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  className: className,
  "aria-hidden": "true"
}, /*#__PURE__*/React.createElement("path", {
  d: "M2.6 12h4.2l2.3-6.2 3.5 12.4 2.6-8.6 1.7 2.4h4.5"
}));
Object.assign(window, {
  Icon,
  Pulse
});
})();
