const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
let ws, joy = {x: 0, y: 0}, turn = 0, keys = new Set(), moving = false, lastDets = "", lastDiag = "", sel = {colour: "", shape: ""};

function open() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.t === "state") render(m); };
  ws.onclose = () => { setStatus("brain offline", false); setTimeout(open, 1000); };
}
const send = o => ws && ws.readyState === 1 && ws.send(JSON.stringify(o));
const setStatus = (t, ok) => { const s = $("#status"); s.textContent = t; s.classList.toggle("off", !ok); };

function render(m) {
  $("#mode").textContent = m.sim ? "simulation" : "real robot";
  const nv = $("#novideo"); nv.hidden = m.fps > 0.5; nv.textContent = m.connected ? "Waiting for video from the robot…" : "Not connected. Type the robot IP and press Connect.";
  setStatus(m.connected ? `connected ${m.ip}` : "robot not connected", m.connected);
  $("#lat").textContent = m.latency != null ? `${m.latency.toFixed(0)} ms` : "";
  $("#c-dist").textContent = m.dist != null ? `distance ${(m.dist / 10).toFixed(0)} cm` : "distance –";
  $("#c-pan").textContent = `pan ${Math.round(m.pan)}°`; $("#c-fps").textContent = `${m.fps.toFixed(0)} fps`;
  document.body.classList.toggle("auto", m.auto);
  const key = JSON.stringify(m.dets);
  if (key !== lastDets) {
    lastDets = key; const box = $("#dets"); box.innerHTML = "";
    if (!m.dets.length) box.innerHTML = '<span class="hint">nothing in view</span>';
    m.dets.forEach(d => { const b = document.createElement("button"); b.textContent = `${d.label}: ${d.colour} ${d.shape}`;
      b.onclick = () => { $("#f-colour").value = d.colour; $("#f-shape").value = d.shape; }; box.appendChild(b); });
  }
  const order = ["SEARCH", "APPROACH", "ALIGN", "PICK", "DONE"], i = order.indexOf(m.state);
  $$("#rail li").forEach((li, n) => { li.className = m.state === "FAILED" && n === 0 ? "bad" : n < i || m.state === "DONE" ? "done" : n === i ? "cur" : ""; });
  $("#mmsg").textContent = m.state === "IDLE" ? "" : `${m.state}${m.msg ? ": " + m.msg : ""}`;
  $("#logbox").textContent = m.logs.join("\n");
  const dk = JSON.stringify(m.diag);
  if (dk !== lastDiag && m.diag) { lastDiag = dk; $("#run-diag").textContent = "Run self-check";
    $("#diag-t tbody").innerHTML = m.diag.map(r => `<tr><td class="s ${r.status}">${r.status}</td><td>${r.name}<br><span class="hint">${r.detail}</span></td></tr>`).join(""); }
}

// ---- driving: joystick, keys, turn buttons; sent 20x per second -----------
setInterval(() => {
  const k = c => keys.has(c) ? 1 : 0;
  let vx = joy.y + k("w") - k("s"), vy = -joy.x + k("a") - k("d"), wz = turn + k("q") - k("e");
  const c = v => Math.max(-1, Math.min(1, v)); vx = c(vx); vy = c(vy); wz = c(wz);
  const now = vx || vy || wz; if (now || moving) send({t: "drive", vx, vy, wz}); moving = !!now;
}, 50);
addEventListener("keydown", e => { if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.code === "Space") { e.preventDefault(); send({t: "estop"}); } else keys.add(e.key.toLowerCase()); });
addEventListener("keyup", e => keys.delete(e.key.toLowerCase()));
addEventListener("blur", () => keys.clear());

const pad = $("#pad"), knob = $("#knob");
function padMove(e) { const r = pad.getBoundingClientRect(), R = r.width / 2;
  let x = (e.clientX - r.left - R) / R, y = (e.clientY - r.top - R) / R, n = Math.hypot(x, y); if (n > 1) { x /= n; y /= n; }
  joy = {x, y: -y}; knob.style.transform = `translate(${x * R * .7}px,${y * R * .7}px)`; }
pad.onpointerdown = e => { pad.setPointerCapture(e.pointerId); padMove(e); };
pad.onpointermove = e => { if (pad.hasPointerCapture(e.pointerId)) padMove(e); };
pad.onpointerup = pad.onpointercancel = () => { joy = {x: 0, y: 0}; knob.style.transform = ""; };
$$(".hold").forEach(b => { b.onpointerdown = () => turn = +b.dataset.turn; b.onpointerup = b.onpointerleave = () => turn = 0; });

// ---- buttons ----------------------------------------------------------------
$("#conn").onsubmit = e => { e.preventDefault(); send({t: "connect", ip: $("#ip").value || "192.168.4.1"}); };
$("#stop").onclick = () => send({t: "estop"});
$$("#gaits button").forEach(b => b.onclick = () => { $$("#gaits button").forEach(x => x.classList.remove("on")); b.classList.add("on"); send({t: "gait", type: b.dataset.g}); });
$$("#acts button").forEach(b => b.onclick = () => send({t: "action", id: b.dataset.a}));
$("#pan").oninput = e => send({t: "pan", deg: +e.target.value});
$("#centre").onclick = () => { $("#pan").value = 0; send({t: "pan", deg: 0}); };
$("#sweep").onchange = e => send({t: "sweep", on: e.target.checked});
$("#go").onclick = () => send({t: "mission_start", colour: $("#f-colour").value, shape: $("#f-shape").value});
$("#halt").onclick = () => send({t: "mission_stop"});
$("#run-diag").onclick = e => { e.target.textContent = "Running…"; send({t: "diag"}); };
$$(".tabs button").forEach(b => b.onclick = () => { $$(".tabs button").forEach(x => x.classList.toggle("on", x === b));
  $$(".tab").forEach(t => t.hidden = t.id !== b.dataset.tab); });
open();
