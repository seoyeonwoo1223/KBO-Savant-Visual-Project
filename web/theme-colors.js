// JS-side mirror of theme.css's --kbo-diverge-* tokens (no build step in this project, so CSS
// custom properties aren't importable from JS — this file is the counterpart a tool's own script
// reads instead of inventing its own endpoint hex). Keep values in sync with theme.css by hand.
//
// Not wired into any page yet. pitch-arsenal.js, leaderboards.js, and movement-zones.js each
// still carry their own named diverging-scale constants (a deliberate, unmigrated choice — see
// PR #9). A future consumer that needs this scale — most likely a Zone Awareness redesign, since
// ZA v7's DV/DV+ is exactly this kind of positive/negative magnitude — should include this file
// with a plain <script src="../theme-colors.js"></script> before its own script and read
// KBO_COLORS instead of hardcoding new hex.
window.KBO_COLORS = Object.freeze({
  divergePositive: "#c83249",
  divergeNegative: "#3474b8",
  divergeNeutral: "#f7f8fa",
  divergeInkLight: "#ffffff",
  divergeInkDark: "#1d3148",
});
