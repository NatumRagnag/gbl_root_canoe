/* Read-only inspector UI. Versions stay as decimal strings (no signed coercion). */
const arbText = {
  zh: {
    title: "防回滚版本检查（只读）",
    help: "对比当前活动槽位的原始镜像。支持 Qualcomm MBN v7 ELF；不是硬件熔丝或 AVB 索引检查，版本相同不代表可以安全刷入。",
    partition: "分区名（不含 _a / _b）", path: "手机上的原始镜像绝对路径",
    slots: "检查 A/B 槽位", image: "与指定镜像对比", source: "来源", comparison: "与当前对比",
    waiting: "点击检查以读取版本", reading: "正在读取镜像元数据…", current: "当前基准",
    same: "相同", higher: "较高", lower: "较低", mixed: "不一致（OEM/QTI 方向不同）",
    unknown: "无法判断", domain: "无法比较（SW ID 不同）", authorities: "无法比较（签名方不同）",
    absent: "无此元数据", invalidPart: "请输入不含槽位后缀的分区名，例如 abl 或 xbl_config。",
    invalidPath: "请输入手机上镜像的绝对路径。", noModule: "WebUI 未连接模块。",
    busy: "刷写任务运行中，请结束后重新检查。", file: "指定镜像", slot: "槽位",
    baseline: "基准：当前槽位", unknownSlot: "当前槽位未知，不能判断是否一致。",
    failed: "读取失败", stale: "刷写任务正在运行，先前检查结果已失效，请结束后重新检查。"
  },
  en: {
    title: "Anti-rollback version check (read only)",
    help: "Compare raw images against the active slot. Supports Qualcomm MBN v7 ELF; this does not read hardware fuses or AVB indices. Matching versions do not establish flash safety.",
    partition: "Partition name (without _a / _b)", path: "Absolute image path on the phone",
    slots: "Check A/B slots", image: "Compare image", source: "Source", comparison: "Compared to current",
    waiting: "Run a check to read versions", reading: "Reading image metadata…", current: "Current baseline",
    same: "Same", higher: "Higher", lower: "Lower", mixed: "Different (OEM/QTI directions differ)",
    unknown: "Unknown", domain: "Not comparable (different SW IDs)", authorities: "Not comparable (different authorities)",
    absent: "Absent", invalidPart: "Enter a partition without a slot suffix, e.g. abl or xbl_config.",
    invalidPath: "Enter an absolute image path on the phone.", noModule: "WebUI is not connected to the module.",
    busy: "A flash task is running. Check again after it finishes.", file: "Image", slot: "Slot",
    baseline: "Baseline: active slot", unknownSlot: "Active slot is unknown; comparison is unavailable.",
    failed: "Read failed", stale: "A flash task is running. Previous results are stale; check again after it finishes."
  }
};
const arbErrors = {
  zh: {
    UNSUPPORTED_FORMAT: "不支持的格式；需要原始 Qualcomm ELF，不能用提取后的 boot.efi",
    UNSUPPORTED_MBN_VERSION: "暂不支持此 MBN 版本（当前支持 v7）",
    NOT_FILE_OR_BLOCK_DEVICE: "文件或分区不存在，或不是普通文件/块设备",
    OPEN_FAILED: "文件或分区无法读取", INSPECTOR_MISSING: "模块缺少 arb_inspect，请安装重新构建的模块",
    UNKNOWN_SLOT: "无法识别当前活动槽位", NO_ARB_METADATA: "没有防回滚元数据"
  }, en: {}
};
let arbSnapshot = null;
const arbMessage = document.getElementById("arbMessage");

function compareArb(reference, candidate) {
  if (reference.STATUS !== "ok" || candidate.STATUS !== "ok") return "unknown";
  if (reference.SW_ID !== candidate.SW_ID || reference.SECONDARY_SW_ID !== candidate.SECONDARY_SW_ID) return "domain";
  const directions = [];
  for (const key of ["OEM_ARB", "QTI_ARB"]) {
    const a = reference[key], b = candidate[key];
    if (a === "absent" && b === "absent") continue;
    if (a === "absent" || b === "absent") return "authorities";
    if (!/^\d+$/.test(a || "") || !/^\d+$/.test(b || "")) return "unknown";
    // Both are uint32 fields; these are exactly representable in JavaScript.
    directions.push(Math.sign(Number(b) - Number(a)));
  }
  if (!directions.length) return "unknown";
  if (directions.includes(-1) && directions.includes(1)) return "mixed";
  return directions.includes(-1) ? "lower" : directions.includes(1) ? "higher" : "same";
}

function arbRecord(info, prefix) {
  return Object.fromEntries(Object.entries(info).filter(([k]) => k.startsWith(`${prefix}_`))
    .map(([k, v]) => [k.slice(prefix.length + 1), v]));
}

function renderArb() {
  if (!arbSnapshot) return;
  const t = arbText[state.lang];
  const {info, mode, path, part} = arbSnapshot;
  const slot = info.CURRENT_SLOT;
  const current = mode === "image" ? "CURRENT" : slot === "_a" ? "A" : slot === "_b" ? "B" : "";
  const reference = arbRecord(info, current || "UNKNOWN");
  const rows = mode === "image" ? ["CURRENT", "FILE"] : ["A", "B"];
  arbMessage.textContent = current && slot !== "unknown"
    ? `${t.baseline} ${slot} / ${part}${slot} · ${arbSnapshot.time}` : t.unknownSlot;
  document.getElementById("arbResults").innerHTML = rows.map(prefix => {
    const record = arbRecord(info, prefix);
    const source = prefix === "FILE" ? `${t.file}: ${path}` : `${t.slot} ${prefix === "CURRENT" ? slot : `_${prefix.toLowerCase()}`} / ${part}`;
    let result = prefix === current && record.STATUS === "ok" ? "current" : compareArb(reference, record);
    let message = t[result];
    if (record.STATUS !== "ok") {
      const error = record.ERROR || "NO_RESULT";
      message = `${t.failed}: ${arbErrors[state.lang][error] || error}`;
      result = "unknown";
    }
    const version = key => record.STATUS !== "ok" ? "—" : record[key] === "absent" ? t.absent : record[key] || "—";
    const badge = result === "same" || result === "current" ? "ok" : result === "higher" || result === "lower" || result === "mixed" ? "bad" : "";
    return `<tr><td>${escapeHtml(source)}</td><td>${escapeHtml(version("SW_ID"))} / ${escapeHtml(version("SECONDARY_SW_ID"))}</td><td>${escapeHtml(version("OEM_ARB"))}</td><td>${escapeHtml(version("QTI_ARB"))}</td><td><span class="status-pill ${badge}">${escapeHtml(message)}</span></td></tr>`;
  }).join("");
}

globalThis.refreshArbLanguage = () => {
  document.querySelectorAll("[data-arb-i18n]").forEach(el => {
    el.textContent = arbText[state.lang][el.dataset.arbI18n];
  });
  renderArb();
};

globalThis.updateArbRunning = running => {
  document.getElementById("arbSlotsButton").disabled = running;
  document.getElementById("arbImageButton").disabled = running;
  if (running && arbSnapshot) {
    arbSnapshot = null;
    document.getElementById("arbResults").replaceChildren();
    arbMessage.textContent = arbText[state.lang].stale;
  }
};

function checkArb(mode) {
  const t = arbText[state.lang];
  const part = document.getElementById("arbPartition").value.trim();
  const path = document.getElementById("arbImagePath").value.trim();
  // Clear old results even when validation or the next read fails.
  arbSnapshot = null;
  document.getElementById("arbResults").replaceChildren();
  if (!/^[a-zA-Z0-9_]+$/.test(part) || /_[ab]$/.test(part)) { arbMessage.textContent = t.invalidPart; return; }
  if (mode === "image" && (!path.startsWith("/") || /[\x00-\x1f]/.test(path))) { arbMessage.textContent = t.invalidPath; return; }
  if (!state.moduleDir) { arbMessage.textContent = t.noModule; return; }
  if (refreshStatus()?.RUNNING === "1") { arbMessage.textContent = t.busy; return; }
  arbMessage.textContent = t.reading;
  try {
    const command = [`MODDIR=${shellQuote(state.moduleDir)}`, "sh", shellQuote(`${state.moduleDir}/bin/arb_check.sh`),
      shellQuote(mode), shellQuote(part)];
    if (mode === "image") command.push(shellQuote(path));
    const info = parseKeyValueOutput(exec(command.join(" ")));
    if (info.ERROR) throw new Error(arbErrors[state.lang][info.ERROR] || info.ERROR);
    if (!info.CURRENT_SLOT) throw new Error("NO_RESULT");
    arbSnapshot = {info, mode, path, part, time: new Date().toLocaleTimeString()};
    renderArb();
  } catch (e) { arbMessage.textContent = `${t.failed}: ${e.message}`; }
}

document.getElementById("arbSlotsButton").addEventListener("click", () => checkArb("slots"));
document.getElementById("arbImageButton").addEventListener("click", () => checkArb("image"));
globalThis.refreshArbLanguage();
globalThis.updateArbRunning(state.status?.RUNNING === "1");
