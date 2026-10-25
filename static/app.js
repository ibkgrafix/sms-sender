/* Bulk SMS — front-end controller */

/* ---------- helpers ---------- */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const toast = (msg, bad) => {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(t._t);
  t._t = setTimeout(() => { t.className = "toast"; }, 3600);
};

/* ---------- theme toggle (every page) ---------- */
const themeBtn = $("#theme");
if (themeBtn) {
  themeBtn.onclick = () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.smsTheme = next;
  };
}

/* ---------- compose page only ---------- */
if ($("#quick")) {
  let CFG = { per_sms: 0, currency: "EUR" };
  let warnedBalance = false;

  /* GSM 03.38 basic + extension charsets.
     Extension chars cost 2 septets but stay in GSM-7 — they do NOT force UCS-2. */
  const GSM_BASIC = new Set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà");
  const GSM_EXT = new Set("\f^{}\\[~]|€");

  function segments(text) {
    if (!text) return { n: 1, enc: "GSM-7", len: 0, limit: 160 };
    let uni = false, septets = 0;
    for (const ch of text) {
      if (GSM_BASIC.has(ch)) septets += 1;
      else if (GSM_EXT.has(ch)) septets += 2;
      else { uni = true; break; }
    }
    if (uni) {
      return { n: Math.max(1, Math.ceil(text.length / 70)), enc: "UCS-2", len: text.length, limit: 70 };
    }
    return { n: Math.max(1, Math.ceil(septets / 160)), enc: "GSM-7", len: septets, limit: 160 };
  }

  const phones = () => {
    const seen = new Set();
    return ($("#quick").value || "")
      .split(/[,\n;]+/)
      .map(s => s.trim())
      .filter(Boolean)
      .filter(p => !seen.has(p) && seen.add(p));
  };

  function recalc() {
    const list = phones();
    const seg = segments($("#message").value);
    const total = list.length * seg.n;

    $("#count").textContent = list.length;
    $("#sCount").textContent = list.length;
    $("#sSegs").textContent = seg.n;
    $("#sMsgs").textContent = total;
    $("#sCost").textContent = CFG.per_sms ? `${CFG.currency} ${(total * CFG.per_sms).toFixed(3)}` : "—";
    $("#segs").textContent = `${seg.len}/${seg.limit} · ${seg.enc} · ${seg.n} SMS`;

    const uni = seg.enc !== "GSM-7";
    $("#enc").textContent = uni ? "Unicode encoding — limit drops to 70" : "";
    const warn = $("#encWarn");
    warn.hidden = !uni;
    warn.textContent = uni
      ? "Non-GSM characters (emoji, smart quotes, ₦) force UCS-2: 70 chars per SMS, so every message costs more."
      : "";
  }

  async function poll() {
    try {
      const s = await (await fetch("/status")).json();
      if (!s.total) return;

      const done = s.sent + s.failed;
      $("#progressCard").hidden = false;
      $("#barFill").style.width = `${(done / s.total) * 100}%`;
      $("#pTotal").textContent = s.total;
      $("#pSent").textContent = s.sent;
      $("#pFail").textContent = s.failed;
      $("#resCount").textContent = s.log.length;

      $("#rows").innerHTML = s.log.slice().reverse().map(e =>
        `<tr><td class="num">${esc(e.phone)}</td>` +
        `<td><span class="badge ${e.status === "failed" ? "err" : "ok"}"><i class="dot"></i>${esc(e.status)}</span></td>` +
        `<td class="detail" title="${esc(e.detail)}">${esc(e.detail)}</td>` +
        `<td class="num">${esc(e.id)}</td></tr>`
      ).join("") || `<tr><td colspan="4" class="empty">Nothing sent yet.</td></tr>`;

      const badge = $("#statusBadge");
      badge.className = "badge " + (s.running ? "warn" : "mute");
      badge.innerHTML = `<i class="dot"></i>${s.running ? "Sending" : "Done"}`;

      $("#send").disabled = s.running;
      $("#stop").disabled = !s.running;

      if (!s.running && !warnedBalance && s.total > 0 && s.sent === 0 && s.failed === s.total &&
          s.log.every(e => /insufficient|balance|credit/i.test(e.detail))) {
        warnedBalance = true;
        toast("Every message failed — provider balance is empty.", true);
      }
    } catch (e) { /* server restarting */ }
  }

  $("#send").onclick = async () => {
    const list = phones();
    const file = $("#file").files[0];
    if (!list.length && !file) return toast("Add a number or upload a CSV.", true);
    if (!$("#message").value.trim()) return toast("Message body is empty.", true);

    warnedBalance = false;
    const fd = new FormData();
    if (file) fd.append("file", file);
    fd.append("message", $("#message").value);
    fd.append("brand", $("#brand").value);
    fd.append("quick", $("#quick").value);

    let r, j;
    try {
      r = await fetch("/send", { method: "POST", body: fd });
      j = await r.json();
    } catch (e) {
      return toast("Could not reach the server.", true);
    }
    if (!j.ok) return toast(j.error || "Send failed.", true);
    toast(`Started — ${j.count} recipient(s).`);
    poll();
  };

  $("#stop").onclick = async () => {
    await fetch("/stop", { method: "POST" });
    toast("Stopping…");
  };

  $("#file").onchange = e => {
    const f = e.target.files[0];
    $("#fileName").textContent = f ? f.name : "Choose a .csv file";
    $("#drop").classList.toggle("hot", !!f);
  };

  ["#quick", "#message", "#brand"].forEach(s => {
    const el = $(s);
    if (el) el.addEventListener("input", recalc);
  });

  (async () => {
    try { CFG = await (await fetch("/api/config")).json(); } catch (e) {}
    recalc();
    poll();
    setInterval(poll, 900);
  })();
}