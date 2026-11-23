"use strict";

const form = document.querySelector("#search");
const queryInput = document.querySelector("#query");
const statusLine = document.querySelector("#status");
const cards = document.querySelector("#cards");
const notices = document.querySelector("#notices");
const filters = document.querySelector("#filters");
const filterStatus = document.querySelector("#filter-status");
const filterFields = [...filters.querySelectorAll(".facet")];
const pagination = document.querySelector("#pagination");
const bottomPagination = document.querySelector("#bottom-pagination");
const pageSize = document.querySelector("#page-size");
const agreementDialog = document.querySelector("#agreement-dialog");
const agreementTitle = document.querySelector("#agreement-title");
const agreementBody = document.querySelector("#agreement-body");
let activeSearch;
const searchCache = new Map();
let oaOptions;
const articleSearch = document.querySelector("#article-search");
const RECENT_KEY = "jufosearch.recent.v1";
let recentSearches = readRecentSearches();

function recentQueries(queries) {
  if (!Array.isArray(queries)) return [];
  const seen = new Set();
  return queries.filter(query => {
    if (typeof query !== "string" || query.trim().length < 2 || query.trim().length > 160) return false;
    const key = query.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 5).map(query => query.trim());
}

function readRecentSearches() {
  try {
    return recentQueries(JSON.parse(localStorage.getItem(RECENT_KEY)));
  } catch {
    return [];
  }
}

function renderRecentSearches() {
  const list = document.querySelector("#recent-queries");
  list.replaceChildren(...recentSearches.map(query => {
    const button = element("button", query);
    button.type = "button";
    button.addEventListener("click", () => search(query));
    return button;
  }));
  document.querySelector("#recent-searches").hidden = recentSearches.length === 0;
}

function saveRecentSearches() {
  try {
    if (recentSearches.length) localStorage.setItem(RECENT_KEY, JSON.stringify(recentSearches));
    else localStorage.removeItem(RECENT_KEY);
  } catch {
    // Searches still work when browser storage is unavailable.
  }
  renderRecentSearches();
}

function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content) node.textContent = content;
  if (className) node.className = className;
  return node;
}

function link(label, href) {
  const node = element("a", label + " ↗");
  node.href = href;
  node.target = "_blank";
  node.rel = "noopener";
  return node;
}

function fact(label, value, note, tone) {
  const item = element("div", null, tone ? "fact " + tone : "fact");
  const definition = element("dd");
  definition.append(value);
  item.append(element("dt", label), definition);
  if (note) item.append(element("small", note));
  return item;
}

function rankTier(value, quartile = false) {
  const valid = quartile ? /^[1-4]$/ : /^[0-3]$/;
  if (!valid.test(String(value))) return 0;
  return quartile ? 4 - Number(value) : Number(value);
}

function rankBadge(label, value, quartile = false) {
  return element("span", label, "rank-badge rank-" + rankTier(value, quartile));
}

function sciFree(term) {
  return "https://search.scifree.se/aalto?" + new URLSearchParams({term});
}

function reported(value) {
  return value && value.toLowerCase() !== "unknown" ? value : null;
}

function publisherName(journal) {
  const name = journal.publisher_name;
  if (!name) return "Unknown publisher";
  return /[?\uFFFD]/.test(name) ? "Publisher name incomplete" : name.normalize("NFC");
}

const oaIconPaths = {
  lock: "M5 10h14v11H5zM8 10V7a4 4 0 0 1 7.5-2M12 14v3",
  repo: "M4 9h16v11H4zM3 5h18v4H3zM9 13h6",
  file: "M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 7v1m0 3v6",
  hybrid: "M12 3a9 9 0 1 0 0 18V3Zm0 0a9 9 0 0 1 0 18",
  chart: "M4 3v17h17M7 14l4-5 4 3 5-7",
  peers: "M9 3h12v12H9zM5 9H3v12h12v-2",
};

function sectionSummary(label, icon) {
  const summary = element("summary");
  summary.innerHTML = `<svg class="section-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${oaIconPaths[icon]}"/></svg>`;
  summary.append(element("span", label));
  return summary;
}

const oaDescriptions = {
  "Gold OA": "Fully open-access journal. Author fees may apply; check Aalto APC support separately.",
  "Diamond OA": "Fully open access, with no publication fees for authors.",
  "Hybrid OA": "OA is optional for individual articles. Other articles may require a subscription. Check Aalto APC support separately.",
  "Green OA": "A version is free in a repository. Publisher access and reuse rights may differ.",
  "Bronze OA": "Free to read at the publisher, without a confirmed open reuse licence.",
  "Not fully OA": "OpenAlex does not list this as a fully OA journal. Whether it offers optional OA for individual articles is not confirmed.",
};
let oaHelpId = 0;

function oaLabel(label, icon, source) {
  const wrapper = element("span", null, "oa-help");
  const badge = element("button", null, "oa-label oa-trigger");
  badge.type = "button";
  badge.setAttribute("aria-label", label + " · About open access");
  const tip = element("span", null, "oa-tooltip");
  tip.id = "oa-help-" + ++oaHelpId;
  tip.setAttribute("role", "tooltip");
  tip.setAttribute("popover", "auto");
  tip.append(element("span", oaDescriptions[label] || "Publishing model not confirmed in our sources. Check the journal website."));
  if (source?.provider) tip.append(element("small", source.provider + (source.as_of ? " · " + source.as_of : "")));
  badge.setAttribute("aria-describedby", tip.id);
  if (typeof tip.showPopover === "function") {
    const show = () => {
      if (!tip.matches(":popover-open")) tip.showPopover();
      const anchor = badge.getBoundingClientRect();
      const bounds = tip.getBoundingClientRect();
      tip.style.left = Math.max(12, Math.min(anchor.left, document.documentElement.clientWidth - bounds.width - 12)) + "px";
      tip.style.top = (anchor.bottom + bounds.height + 8 < innerHeight
        ? anchor.bottom + 8 : Math.max(12, anchor.top - bounds.height - 8)) + "px";
    };
    const hide = () => setTimeout(() => {
      if (!badge.matches(":hover, :focus") && !tip.matches(":hover") && tip.matches(":popover-open")) tip.hidePopover();
    }, 100);
    badge.addEventListener("pointerenter", show);
    badge.addEventListener("focus", show);
    badge.addEventListener("click", show);
    badge.addEventListener("pointerleave", hide);
    badge.addEventListener("blur", hide);
    tip.addEventListener("pointerleave", hide);
  } else {
    tip.hidden = true;
    badge.title = tip.textContent;
  }
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", oaIconPaths[icon]);
  svg.append(path);
  badge.append(svg, element("span", label));
  wrapper.append(badge, tip);
  return wrapper;
}

function publishingInfo(journal) {
  const oa = journal.external?.oa_info;
  const agreement = journal.agreement;
  if (oa?.is_diamondOA === true) return {model:"Diamond OA", source:{provider:"JUFO"}};
  let model = agreement?.model;
  let source = model ? {provider:agreement.source ? "FinELib" : "Aalto SciFree", as_of:agreement.checked} : null;
  if (!model) {
    model = reported(oa?.open_access_type) || (oa?.is_hybrid === true ? "Hybrid" : oa?.is_oa === true ? "Open access" : null);
    if (model) source = {provider:"JUFO"};
  }
  if (!model && journal.publishing_model) {
    model = journal.publishing_model.model;
    source = journal.publishing_model;
  }
  const labels = {"Pure OA":"Gold OA", "Open access":"Gold OA", "Hybrid":"Hybrid OA"};
  return {model:labels[model] || model || "Not listed", source};
}

function articleAccess(doi) {
  const button = element("button", "Check article OA", "text-button");
  button.type = "button";
  const result = element("span", null, "article-oa-result");
  result.setAttribute("role", "status");
  const access = element("div", null, "article-access");
  access.append(button, result);
  button.addEventListener("click", async () => {
    button.disabled = true;
    result.textContent = "Checking OpenAlex…";
    try {
      const response = await fetch("https://api.openalex.org/works/https://doi.org/"
        + encodeURIComponent(doi) + "?select=open_access", {signal: AbortSignal.timeout(8000)});
      if (!response.ok) throw new Error("OpenAlex lookup failed");
      const {open_access: oa} = await response.json();
      const status = oa?.oa_status;
      const labels = {
        diamond: ["Diamond OA", "No APC", "lock"],
        gold: ["Gold OA", "Fully open access", "lock"],
        hybrid: ["Hybrid OA", "Open access at publisher", "hybrid"],
        green: ["Green OA", "Repository copy", "repo"],
        bronze: ["Bronze OA", "Free to read · Open licence unverified", "file"],
      };
      if (Object.hasOwn(labels, status)) {
        const [label, note, icon] = labels[status];
        result.replaceChildren(oaLabel(label, icon), element("small", note));
        if (/^https?:\/\//i.test(oa.oa_url || "")) result.append(link("Read open copy", oa.oa_url));
      } else {
        result.textContent = status === "closed" ? "OpenAlex found no open copy." : "OA status unavailable.";
      }
      button.hidden = true;
    } catch {
      result.textContent = "Could not check article OA. Try again.";
      button.disabled = false;
    }
  });
  return access;
}

function journalFacts(journal) {
  const agreement = journal.agreement;
  const fee = agreement?.status === "quota_exhausted" ? "Quota exhausted"
    : agreement?.discount === 100 ? "Fully covered"
    : agreement ? agreement.discount + "% discount" : "Check SciFree";
  return {
    level: journal.level == null ? "Unclassified" : String(journal.level),
    publisher: publisherName(journal),
    fee,
    licence: agreement?.licence || reported(journal.external?.license?.channel) || "Not listed",
    model: publishingInfo(journal).model,
  };
}

function listedAPC(journal) {
  const values = (journal.apc?.prices || []).filter(row => typeof row.amount === "number"
    && Number.isFinite(row.amount) && row.amount >= 0 && /^[A-Z]{3}$/.test(row.currency));
  const price = values.find(row => row.currency === "EUR") || values.find(row => row.currency === "USD") || values[0];
  if (!price) return null;
  return price.currency + " " + new Intl.NumberFormat("en", {maximumFractionDigits: 2}).format(price.amount);
}

function priceLink(journal) {
  const text = listedAPC(journal);
  if (!text) return element("span", "APC not listed");
  const anchor = link(text, journal.apc.source);
  anchor.textContent = text.replace(" ", "\u00a0");
  const note = "OpenAlex snapshot " + journal.apc.snapshot_date + ". List price; confirm current charges and taxes with the publisher.";
  anchor.title = note;
  anchor.setAttribute("aria-label", "Listed APC " + text + ". " + note);
  return anchor;
}

function selectedFilters() {
  return filterFields.map(field => [field.dataset.field,
    [...field.querySelectorAll("input:checked")].map(input => input.value)]).filter(([, values]) => values.length);
}

function passesFilters(values, active) {
  return active.every(([name, selected]) => selected.includes(values[name]));
}

function showAgreement(journal, sciFreeUrl) {
  const {agreement, agreement_status: status} = journal;
  agreementTitle.textContent = journal.title;
  const detail = element("dl", null, "agreement-details");
  function field(label, value) {
    detail.append(element("dt", label), element("dd", value));
  }
  field("APC support", journalFacts(journal).fee);
  if (agreement) {
    const expiry = new Intl.DateTimeFormat("en-GB", {dateStyle: "long", timeZone: "UTC"});
    field("Agreement expires", expiry.format(new Date(agreement.until)));
    field("Who qualifies", "Submitting corresponding author at Aalto, using Aalto affiliation and email.");
    field("Eligible article types", agreement.article_types);
    field("Quota", agreement.quota);
    field("Agreement licence", agreement.licence);
    if (agreement.discount < 100) {
      field("Remaining fee", "Publisher invoices the remaining APC. Confirm department funding before submission.");
    }
    field(agreement.source ? "Title list checked" : "SciFree status recorded", agreement.checked);
  } else {
    const messages = {
      expired: "Check current agreement dates in SciFree.",
      unavailable: "Title list unavailable. Check SciFree.",
      unverified: "Check SciFree for coverage, licences and quotas."
    };
    field("Coverage", messages[status] || messages.unverified);
  }
  const sources = element("div", null, "sources");
  sources.append(link("Open in Aalto SciFree", sciFreeUrl));
  if (agreement?.guidelines) sources.append(link("Agreement guidelines", agreement.guidelines));
  if (agreement?.source) sources.append(link("FinELib title list", agreement.source));
  agreementBody.replaceChildren(detail, sources);
  agreementDialog.showModal();
}

function annualLevels(history, yearStart) {
  const years = Object.keys(history || {}).filter(year => /^\d{4}$/.test(year)).map(Number).sort((a, b) => a - b);
  if (!years.length) return [];
  const first = /^\d{4}$/.test(String(yearStart)) ? Math.max(years[0], Number(yearStart)) : years[0];
  const last = years.at(-1);
  return Array.from({length: Math.max(0, last - first + 1)}, (_, index) => {
    const year = first + index;
    const value = history[year];
    return [year, /^[0-3]$/.test(String(value)) ? Number(value) : null];
  });
}

function historyTicks(entries) {
  const first = entries[0][0];
  const last = entries.at(-1)[0];
  const step = last - first <= 12 ? 2 : 5;
  const ticks = [first];
  for (let year = Math.ceil(first / step) * step; year < last; year += step) {
    if (year - first >= Math.min(step / 2, 2) && last - year >= Math.min(step / 2, 2)) ticks.push(year);
  }
  if (last > first) ticks.push(last);
  return ticks;
}

function historySegments(entries) {
  return entries.slice(1).map(([year, level], index) => {
    const [previousYear, previousLevel] = entries[index];
    return {
      from: [previousYear, previousLevel ?? 0],
      to: [year, level ?? 0],
      missing: previousLevel === null || level === null,
    };
  });
}

function evaluationHistory(history, yearStart) {
  const details = element("section", null, "evaluation-history");
  details.append(element("h3", "JUFO history"));
  const entries = annualLevels(history, yearStart);
  if (!entries.length) {
    details.append(element("p", "No annual JUFO levels recorded."));
    return details;
  }
  const first = entries[0][0];
  const last = entries.at(-1)[0];
  const x = year => first === last ? 234 : 40 + (year - first) * 392 / (last - first);
  const y = level => 116 - level * 30;
  const grid = [0, 1, 2, 3].map(level =>
    `<path class="history-grid" d="M40 ${y(level)}H432"/><text x="14" y="${y(level) + 5}">${level}</text>`).join("");
  const lines = historySegments(entries).map(({from, to, missing}) => {
    const className = missing ? "history-line history-line-unrecorded" : "history-line";
    return `<path class="${className}" d="M${x(from[0])} ${y(from[1])}L${x(to[0])} ${y(to[1])}"/>`;
  }).join(" ");
  const markers = entries.map(([year, level]) => {
    const className = level === null ? "history-missing" : "history-recorded";
    const label = level === null ? "Not recorded" : "Level " + level;
    return `<g class="history-point" data-year="${year}" tabindex="0" role="img" aria-label="${year} · ${label}">
      <circle class="history-hit-area" cx="${x(year)}" cy="${y(level ?? 0)}" r="18"/>
      <circle class="${className}" cx="${x(year)}" cy="${y(level ?? 0)}" r="4"/>
    </g>`;
  }).join("");
  const ticks = historyTicks(entries).map(year => {
    const anchor = first === last ? "middle" : year === first ? "start" : year === last ? "end" : "middle";
    return `<path class="history-grid" d="M${x(year)} 116v5"/><text x="${x(year)}" y="146" text-anchor="${anchor}">${year}</text>`;
  }).join("");
  const plot = element("figure", null, "history-plot");
  plot.innerHTML = `<svg viewBox="0 0 456 160" role="group" aria-label="Annual JUFO levels from ${first} to ${last}. Open circles at 0 and dashed links indicate missing records. Filled circles show recorded levels. Recent values are in the table.">
    ${grid}${lines}${markers}${ticks}
  </svg>`;
  const tooltip = element("div", null, "history-tooltip");
  tooltip.setAttribute("role", "tooltip");
  tooltip.hidden = true;
  for (const point of plot.querySelectorAll(".history-point")) {
    const show = () => {
      tooltip.textContent = point.getAttribute("aria-label");
      tooltip.hidden = false;
    };
    const hide = () => {
      if (!point.matches(":hover") && !point.matches(":focus")) tooltip.hidden = true;
    };
    point.addEventListener("pointerenter", show);
    point.addEventListener("pointerleave", hide);
    point.addEventListener("focus", show);
    point.addEventListener("blur", hide);
  }
  plot.append(tooltip);
  const legend = element("figcaption", null, "history-legend");
  for (const [label, missing] of [["Recorded", false], ["Not recorded", true]]) {
    const key = element("span", null, "history-key");
    key.innerHTML = `<svg viewBox="0 0 32 12" aria-hidden="true">
      <path class="history-line${missing ? " history-line-unrecorded" : ""}" d="M1 6H31"/>
      <circle class="${missing ? "history-missing" : "history-recorded"}" cx="16" cy="6" r="3.5"/>
    </svg>`;
    key.append(element("span", label));
    legend.append(key);
  }
  plot.append(legend);

  const table = element("table", null, "history-table");
  table.append(element("caption", "Recent annual JUFO evaluations", "sr-only"));
  const headers = table.createTHead().insertRow();
  for (const label of ["Year", "JUFO level"]) {
    const header = element("th", label);
    header.scope = "col";
    headers.append(header);
  }
  const body = table.createTBody();
  for (const [year, level] of entries.slice(-5).reverse()) {
    const row = body.insertRow();
    const yearCell = element("th", String(year));
    yearCell.scope = "row";
    row.append(yearCell);
    row.insertCell().append(rankBadge(level === null ? "Not recorded" : "Level " + level, level));
  }
  const content = element("div", null, "history-content");
  content.append(plot, table);
  details.append(content);
  return details;
}

function journalWebsite(journal) {
  let url;
  try {
    url = new URL(journal.website);
  } catch {
    return journal.agreement?.journal_url;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return;
  if (/^(www\.)?journals\.elsevier\.com$/.test(url.hostname)) {
    const slug = url.pathname.match(/^\/([a-z0-9-]+)\/?$/i);
    if (slug) return "https://www.sciencedirect.com/journal/" + slug[1];
  }
  if (/^(www\.)?elsevier\.com$/.test(url.hostname) && url.pathname.startsWith("/wps/")) {
    return journal.agreement?.journal_url || url.href;
  }
  return url.href;
}

function quartileDetails(data) {
  const section = element("section", null, "quartiles");
  section.append(element("h3", "OpenAlex quartiles"));
  if (!data?.fields?.length) {
    section.append(element("p", "No comparable OpenAlex data available."));
    return section;
  }
  section.append(element("p", `JUFOSearch · ${data.edition} · CWTS Core · Not JCR`, "detail-meta"));
  const table = element("table", null, "history-table quartile-table");
  const caption = element("caption", "OpenAlex-derived quartiles by subject area");
  caption.className = "sr-only";
  const head = element("thead");
  const labels = element("tr");
  for (const label of ["Subject area", "Quartile"]) {
    const cell = element("th", label);
    cell.scope = "col";
    labels.append(cell);
  }
  head.append(labels);
  const body = element("tbody");
  for (const field of data.fields) {
    const row = element("tr");
    const name = element("th", field.name);
    name.scope = "row";
    const quartile = element("td");
    const rank = `Q${field.quartile} · Rank ${field.rank} of ${field.total}`;
    quartile.title = rank;
    quartile.setAttribute("aria-label", rank);
    quartile.append(rankBadge("Q" + field.quartile, field.quartile, true));
    row.append(name, quartile);
    body.append(row);
  }
  table.append(caption, head, body);
  const source = element("div", null, "metric-source");
  source.append(element("small", `Snapshot ${data.snapshot_date}`), link("OpenAlex", data.source_id));
  section.append(table, source);
  return section;
}

function rankings(journal) {
  const section = element("details", null, "rankings");
  section.append(sectionSummary("Rankings", "chart"));
  section.addEventListener("toggle", () => {
    if (!section.open || section.childElementCount > 1) return;
    section.append(evaluationHistory(journal.level_history, journal.year_start), quartileDetails(journal.quartiles));
  });
  return section;
}

function renderJournal(journal, signal) {
  const agreement = journal.agreement;
  const oa = journal.external?.oa_info;
  const level = journal.level == null ? "Unclassified" : "Level " + journal.level;
  const {fee, licence, model} = journalFacts(journal);
  const modelInfo = publishingInfo(journal);
  const sciFreeUrl = sciFree(journal.title);
  const heading = element("h2");
  const publisherUrl = journalWebsite(journal);
  if (publisherUrl) heading.append(link(journal.title, publisherUrl));
  else heading.textContent = journal.title;
  const feeButton = agreement ? element("button", fee, "fee-link") : link(fee, sciFreeUrl);
  if (agreement) {
    feeButton.type = "button";
    feeButton.setAttribute("aria-haspopup", "dialog");
    feeButton.setAttribute("aria-label", fee + " · View agreement for " + journal.title);
    feeButton.addEventListener("click", () => showAgreement(journal, sciFreeUrl));
  }
  const feeTone = agreement?.status === "quota_exhausted" ? "warning"
    : agreement?.discount === 100 ? "accent" : "";
  const identifiers = [...new Set([journal.issn_electronic, journal.issn_print, journal.issnl].filter(Boolean))];
  const article = element("article", null, "card");
  article.dataset.jufoId = journal.jufo_id;
  article.append(
    heading,
    element("p", [publisherName(journal), identifiers.join(" / "),
      journal.is_active === false ? "Inactive" : ""].filter(Boolean).join(" · "), "metadata")
  );
  const wosListed = journal.external?.index_info?.includes("WOS");
  const facts = element("dl", null, "facts");
  const support = fact("Aalto APC support", feeButton, agreement?.source ? "FinELib agreement"
    : agreement ? "Aalto SciFree" : null, feeTone);
  const price = element("small");
  price.append(priceLink(journal));
  support.append(price);
  facts.append(
    fact("JUFO level", level, null, "rank-panel rank-" + rankTier(journal.level)),
    support,
    fact(agreement?.licence ? "Agreement licence" : "Journal licence", licence),
    fact("Publishing model", oaLabel(model, model === "Hybrid OA" ? "hybrid" : ["Gold OA", "Diamond OA"].includes(model) ? "lock" : "info", modelInfo.source),
      model === "Diamond OA" ? "No APC · JUFO" : null)
  );
  article.append(facts);

  if (journal.examples?.length) {
    const evidence = element("details", null, "evidence");
    const coverage = journal.matched_keywords?.length
      ? ` · ${journal.matched_keywords.length}/${journal.keyword_total} keywords` : "";
    evidence.append(element("summary", "Matching articles" + coverage));
    evidence.addEventListener("toggle", () => {
      if (!evidence.open || evidence.querySelector("ul")) return;
      const list = element("ul");
      for (const work of journal.examples) {
        const item = element("li");
        item.append(link(work.title, "https://doi.org/" + encodeURI(work.doi)));
        if (work.keywords?.length) item.append(element("small", work.keywords.join(" · ")));
        item.append(articleAccess(work.doi));
        list.append(item);
      }
      evidence.append(element("p", "Crossref · Article titles"), list);
    });
    article.append(evidence);
  } else if (journal.matched_topics?.length) {
    const matched = element("details", null, "evidence");
    matched.append(element("summary", "Related topics"));
    matched.addEventListener("toggle", () => {
      if (!matched.open || matched.querySelector("p")) return;
      matched.append(element("p", journal.matched_topics.join(" · ")),
        element("small", "OpenAlex · " + journal.profile_keywords.join(" · ") + " · Broad topic match"));
    });
    article.append(matched);
  } else if (journal.topic_match) {
    article.append(element("p", "Topic starting point", "evidence"));
  }

  const notes = element("details");
  notes.append(sectionSummary("Notes", "file"));
  const fields = journal.okm_disciplines?.map(item => item.localized_labels?.en).filter(Boolean);
  notes.append(element("p", "JUFO ID " + journal.jufo_id + (fields?.length ? " · " + fields.join(" · ") : "")));
  if (modelInfo.source?.source) notes.append(link("Publishing model source", modelInfo.source.source));
  if (journal.apc) notes.append(element("p", "APC list-price snapshot · " + journal.apc.snapshot_date
    + ". Discounts, taxes, article type and eligibility can change the payable amount."));
  if (publisherName(journal) === "Publisher name incomplete") {
    notes.append(element("p", "JUFO publisher name incomplete. Verify on the journal website."));
  }
  if (oa?.immediate_sa_allowed_accepted === "yes") {
    const acceptedLicence = journal.external?.license?.sa_accepted;
    notes.append(element("p", "JUFO reports immediate self-archiving of the accepted manuscript"
      + (acceptedLicence ? " under " + acceptedLicence : "") + "."));
  }
  if (wosListed) {
    const indexing = element("p", "Web of Science listed in JUFO. Verify by ISSN in ");
    indexing.append(link("Clarivate Master Journal List", "https://mjl.clarivate.com/"));
    notes.append(indexing);
  }
  article.append(rankings(journal), similarJournals(journal, signal), oaGuidance(journal, signal), notes);
  const sources = element("div", null, "sources");
  sources.append(link("JUFO record", "https://jufo-rest.csc.fi/v2.1/channel/" + journal.jufo_id));
  article.append(sources);
  return article;
}

const OA_PROFILE_KEY = "jufosearch.oa-profile.v1";
let oaProfile;
try { oaProfile = JSON.parse(localStorage.getItem(OA_PROFILE_KEY)); } catch { oaProfile = null; }
let rememberOA = Boolean(oaProfile);

function validOAProfile(profile, options) {
  return Boolean(profile && options.funders.some(row => row.id === profile.funder)
    && profile.institution && /^0[a-z0-9]{6}[0-9]{2}$/.test(profile.institution.id)
    && typeof profile.institution.country === "string" && profile.institution.country.length > 0
    && typeof profile.institution.title === "string" && profile.institution.title.length > 0
    && profile.institution.title.length <= 200);
}

function currentOAProfile(options) {
  return validOAProfile(oaProfile, options) ? oaProfile
    : {institution: options.institution, funder: "academyoffinlandaka"};
}

function loadOAOptions() {
  if (!oaOptions) oaOptions = fetch("/api/oa").then(async response => {
    if (!response.ok) throw new Error("Could not load OA preferences. Try again.");
    return response.json();
  }).catch(error => { oaOptions = null; throw error; });
  return oaOptions;
}

function applyOAProfile(profile, remember) {
  oaProfile = profile;
  rememberOA = remember;
  let stored = true;
  try {
    if (remember && profile) localStorage.setItem(OA_PROFILE_KEY, JSON.stringify(profile));
    else localStorage.removeItem(OA_PROFILE_KEY);
  } catch { stored = false; }
  for (const panel of document.querySelectorAll(".oa-checker, .oa-controls")) panel.dispatchEvent(new Event("oa-profile-change"));
  return stored;
}

function oaProfileEditor(options, key, signal) {
  const controls = element("form", null, "oa-controls");
  const institutionLabel = element("div", null, "oa-field");
  const institutionText = element("label", "Institution");
  const institution = element("input");
  institution.type = "search";
  institution.required = true;
  institution.maxLength = 100;
  institution.placeholder = "Institution name or ROR";
  institution.id = "oa-institution-" + key;
  institutionText.htmlFor = institution.id;
  institution.hidden = true;
  const chosen = element("button", null, "oa-institution");
  chosen.type = "button";
  const suggestions = element("datalist");
  suggestions.id = "oa-institutions-" + key;
  institution.setAttribute("list", suggestions.id);
  const choices = new Map();
  const addChoice = row => {
    const name = row.country + " · " + row.title;
    if (![...suggestions.options].some(option => option.value === name)) {
      const option = element("option");
      option.value = name;
      suggestions.append(option);
    }
    choices.set(name, row);
    return name;
  };
  const showChoice = () => {
    chosen.textContent = institution.value;
    chosen.setAttribute("aria-label", institution.value + ". Change institution");
    chosen.title = "Change institution";
    chosen.hidden = false;
    institution.hidden = true;
  };
  chosen.addEventListener("click", () => {
    chosen.hidden = true;
    institution.hidden = false;
    institution.focus();
    institution.select();
  });
  institution.addEventListener("change", () => { if (choices.has(institution.value)) showChoice(); });
  institutionLabel.append(institutionText, chosen, institution, suggestions);
  const funderLabel = element("label", "Funder");
  const funder = element("select");
  for (const country of [...new Set(options.funders.map(row => row.country))].sort()) {
    const group = element("optgroup");
    group.label = country;
    for (const row of options.funders.filter(row => row.country === country)) {
      const option = element("option", row.name);
      option.value = row.id;
      group.append(option);
    }
    funder.append(group);
  }
  funderLabel.append(funder);
  const rememberLabel = element("label", null, "oa-remember");
  const remember = element("input");
  remember.type = "checkbox";
  rememberLabel.append(remember, "Remember on this browser");
  const actions = element("div", null, "oa-actions");
  const apply = element("button", "Apply", "secondary");
  apply.type = "submit";
  const reset = element("button", "Reset", "text-button");
  reset.type = "button";
  const status = element("p", null, "metadata oa-editor-status");
  status.setAttribute("role", "status");
  actions.append(reset, apply);
  controls.append(institutionLabel, funderLabel, rememberLabel, actions, status);
  const sync = () => {
    const profile = currentOAProfile(options);
    institution.value = addChoice(profile.institution);
    institution.setCustomValidity("");
    showChoice();
    funder.value = profile.funder;
    remember.checked = rememberOA && validOAProfile(oaProfile, options);
  };
  sync();
  let timer, request;
  signal.addEventListener("abort", () => { clearTimeout(timer); request?.abort(); }, {once:true});
  institution.addEventListener("input", () => {
    institution.setCustomValidity("");
    clearTimeout(timer);
    request?.abort();
    if (choices.has(institution.value)) { status.textContent = ""; return; }
    const query = institution.value.trim();
    status.textContent = query.length < 3 ? "Type at least three characters." : "Searching institutions…";
    if (query.length < 3) return;
    timer = setTimeout(async () => {
      const pending = new AbortController();
      request = pending;
      try {
        const response = await fetch("/api/institutions?" + new URLSearchParams({q:query}), {signal:pending.signal});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error);
        if (signal.aborted || pending.signal.aborted || institution.value.trim() !== query) return;
        suggestions.replaceChildren();
        for (const row of data.results) addChoice(row);
        status.textContent = data.results.length ? "Select an institution from the suggestions." : "No match. Try a more specific name or ROR.";
      } catch {
        if (!signal.aborted && !pending.signal.aborted) status.textContent = "Institution search failed. Type again to retry.";
      }
    }, 350);
  });
  controls.addEventListener("submit", event => {
    event.preventDefault();
    const selected = choices.get(institution.value);
    if (!selected) {
      institution.hidden = false;
      chosen.hidden = true;
      institution.setCustomValidity("Choose an institution from the suggestions.");
      institution.reportValidity();
      return;
    }
    clearTimeout(timer);
    request?.abort();
    const stored = applyOAProfile({institution:selected, funder:funder.value}, remember.checked);
    status.textContent = remember.checked && !stored ? "Applied for this page. Browser storage is unavailable."
      : remember.checked ? "Saved on this browser." : "Applied for this page.";
    showChoice();
    if (key === "home" && (stored || !remember.checked)) document.querySelector("#oa-preferences").hidePopover();
  });
  reset.addEventListener("click", () => {
    clearTimeout(timer);
    request?.abort();
    applyOAProfile(null, false);
    sync();
    status.textContent = "Preferences cleared.";
  });
  controls.addEventListener("oa-profile-change", sync);
  return controls;
}

function setupOAPreferences() {
  const panel = document.querySelector("#oa-preferences");
  let loading = false;
  panel.addEventListener("toggle", async () => {
    if (!panel.matches(":popover-open") || loading || panel.querySelector("form")) return;
    loading = true;
    const status = element("p", "Loading…", "metadata");
    panel.append(status);
    try {
      const options = await loadOAOptions();
      panel.append(oaProfileEditor(options, "home", new AbortController().signal));
      status.remove();
    } catch (error) { status.textContent = error.message; }
    finally { loading = false; }
  });
}

function oaGuidance(journal, signal) {
  const section = element("details", null, "oa-checker");
  section.append(sectionSummary("OA routes", "repo"));
  const issn = journal.issn_electronic || journal.issn_print || journal.issnl;
  if (!issn) { section.append(element("p", "An ISSN is needed to check this journal.")); return section; }
  let initialized = false;
  section.addEventListener("toggle", async () => {
    if (!section.open || initialized) return;
    initialized = true;
    const status = element("p", "Loading…", "metadata");
    status.setAttribute("role", "status");
    section.append(status);
    try {
      const options = await loadOAOptions();
      if (signal.aborted) return;
      const context = element("div", null, "oa-context");
      const names = element("dl", null, "oa-context-fields");
      const change = element("button", "Change", "text-button");
      change.type = "button";
      change.setAttribute("aria-expanded", "false");
      context.append(names, change);
      const editor = element("div");
      editor.hidden = true;
      change.addEventListener("click", () => {
        if (!editor.firstChild) editor.append(oaProfileEditor(options, journal.jufo_id, signal));
        editor.hidden = !editor.hidden;
        change.setAttribute("aria-expanded", String(!editor.hidden));
      });
      const check = element("button", "Check routes", "secondary oa-check");
      check.type = "button";
      const result = element("div", null, "oa-result");
      const verdict = element("div", null, "oa-verdict");
      verdict.append(status, result);
      verdict.hidden = true;
      let request, version = 0;
      const sync = () => {
        version++;
        request?.abort();
        const profile = currentOAProfile(options);
        const institution = element("div");
        institution.append(element("dt", "Institution"), element("dd", profile.institution.title));
        const funder = element("div");
        funder.append(element("dt", "Funder"), element("dd", options.funders.find(row => row.id === profile.funder).name));
        names.replaceChildren(institution, funder);
        editor.hidden = true;
        change.setAttribute("aria-expanded", "false");
        result.replaceChildren();
        verdict.hidden = true;
        verdict.className = "oa-verdict";
        status.textContent = "";
        section.setAttribute("aria-busy", "false");
        check.disabled = false;
        check.textContent = "Check routes";
      };
      sync();
      section.addEventListener("oa-profile-change", sync);
      signal.addEventListener("abort", () => request?.abort(), {once:true});
      section.append(context, editor, check, verdict);
      check.addEventListener("click", async () => {
        request?.abort();
        const current = ++version;
        const profile = currentOAProfile(options);
        const params = new URLSearchParams({issn, journal:journal.jufo_id, funder:profile.funder, ror:profile.institution.id});
        request = new AbortController();
        const pending = request;
        check.disabled = true;
        check.textContent = "Checking…";
        section.setAttribute("aria-busy", "true");
        try {
          const response = await fetch("/api/oa?" + params, {signal:pending.signal});
          const data = await response.json();
          if (!response.ok) {
            const error = new Error(data.error);
            error.code = data.code;
            throw error;
          }
          if (signal.aborted || pending.signal.aborted || version !== current) return;
          result.replaceChildren();
          verdict.hidden = false;
          verdict.className = "oa-verdict " + (data.compliant ? "oa-confirmed" : "oa-unconfirmed");
          status.textContent = data.compliant ? "OA route confirmed" : "No compliant OA route found by JCT";
          const routes = element("ul", null, "oa-routes");
          for (const card of data.cards.filter(card => card.available)) {
            const instructions = {
              fully_oa: ["Publish open access", "lock"],
              fully_oa_by_exception: ["Publish open access", "lock"],
              ta: ["Use your institution's agreement", "file"],
              ta_aq: ["Use your institution's agreement", "file"],
              self_archiving: ["Self-archive your manuscript", "repo"],
              sa_rr: ["Self-archive using rights retention", "repo"],
              tj: ["Choose the supported OA option", "lock"],
            };
            const [title, icon] = instructions[card.id] || [card.title, "info"];
            const action = card.summary || card.conditions;
            const item = element("li");
            const heading = element("h3", title);
            const symbol = element("span", null, "oa-route-icon");
            symbol.innerHTML = `<svg class="section-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${oaIconPaths[icon]}"/></svg>`;
            heading.prepend(symbol);
            item.append(heading, element("p", action));
            routes.append(item);
          }
          result.append(routes);
          if (!data.compliant) result.append(element("p", "Try another journal, or check another funder or institution you are affiliated with."));
          const conditions = element("details", null, "oa-conditions");
          conditions.append(element("summary", "Conditions and sources"));
          for (const card of data.cards) {
            conditions.append(element("h3", card.title), element("p", card.conditions));
          }
          if (data.ror === "020hwjq30") {
            const note = element("p", "Aalto's prior licence policy may offer another route for manuscripts submitted from 1 January 2026. ");
            note.append(link("Check eligibility", "https://www.aalto.fi/en/open-science-and-research/aalto-university-prior-licence-model"));
            conditions.append(note);
          }
          const attribution = element("p", "cOAlition S / European Science Foundation · ", "metadata");
          attribution.append(link("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"));
          conditions.append(attribution);
          result.append(element("p", "APC funding is checked separately.", "metadata"), conditions);
          const source = element("p", null, "oa-source");
          source.append(link("Full JCT result", data.source), element("small", "Checked " + data.checked.slice(0,10)));
          result.append(source);
        } catch (error) {
          if (!signal.aborted && !pending.signal.aborted && version === current) {
            result.replaceChildren();
            verdict.hidden = false;
            verdict.className = "oa-verdict oa-unconfirmed";
            status.textContent = error.code === "journal_mismatch" ? "Journal not matched · OA policy not checked" : "Check unavailable · OA policy not checked";
            result.append(element("p", error.code === "journal_mismatch" ? "JCT returned a different journal for this ISSN. Select the exact title on JCT." : "Try again, or check directly on JCT."));
            result.append(link("Open Journal Checker Tool", error.code === "journal_mismatch" ? "https://journalcheckertool.org/" : "https://journalcheckertool.org/?" + params));
          }
        } finally {
          if (version === current) {
            check.disabled = false;
            check.textContent = "Check again";
            section.setAttribute("aria-busy", "false");
          }
        }
      });
    } catch {
      initialized = false;
      status.textContent = "Could not load OA checker. Close and reopen to retry.";
      section.addEventListener("toggle", () => { if (!section.open) status.remove(); }, {once:true});
    }
  });
  return section;
}

function similarJournals(journal, signal) {
  const section = element("details", null, "similar");
  section.append(sectionSummary("Similar journals", "peers"));
  const status = element("p", "Finding similar journals…", "metadata");
  status.setAttribute("role", "status");
  let loaded = false, pending = false;
  const load = async () => {
    if (pending) return;
    pending = true;
    section.querySelector(".peer-retry")?.remove();
    status.textContent = "Finding similar journals…";
    section.append(status);
    try {
      const response = await fetch("/api/recommend?" + new URLSearchParams({id: journal.jufo_id}), {signal});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      if (signal.aborted) return;
      loaded = true;
      const active = selectedFilters();
      const peers = data.results.filter(row => passesFilters(journalFacts(row), active));
      if (!peers.length) {
        status.textContent = data.notices[0] || (active.length ? "No suggestions match the current filters." : "No comparable journals found.");
        return;
      }
      const list = element("div", null, "peer-list");
      const append = rows => {
        for (const row of rows) {
          const card = element("article", null, "peer");
          const heading = element("h3");
          const anchor = element("a", row.title);
          anchor.href = "/?" + new URLSearchParams({q: row.issn_electronic || row.issn_print || row.title, from:"similar"});
          heading.append(anchor);
          const ranks = element("div", null, "peer-ranks");
          ranks.append(rankBadge("JUFO " + row.level, row.level));
          const values = row.quartiles.fields.map(field => field.quartile);
          const first = Math.min(...values), last = Math.max(...values);
          ranks.append(element("span", "OpenAlex Q" + first + (last > first ? "–Q" + last : "")));
          const fees = element("p", null, "peer-fees");
          fees.append(priceLink(row), " · ");
          if (row.agreement) {
            const value = journalFacts(row).fee;
            const support = element("button", "Aalto " + value.toLowerCase(), "text-button");
            support.type = "button";
            support.addEventListener("click", () => showAgreement(row, sciFree(row.title)));
            fees.append(support);
          } else fees.append(link("Check Aalto support", sciFree(row.title)));
          card.append(heading, element("p", publisherName(row), "peer-publisher"), ranks, fees, element("p", row.recommendation_reason));
          list.append(card);
        }
      };
      append(peers.slice(0, 6));
      status.remove();
      section.append(element("p", "JUFO · OpenAlex", "metadata"), list);
      if (peers.length > 6) {
        const more = element("button", "Show " + (peers.length - 6) + " more", "secondary");
        more.type = "button";
        more.setAttribute("aria-expanded", "false");
        let expanded = false;
        more.addEventListener("click", () => {
          expanded = !expanded;
          if (expanded) append(peers.slice(6, 12));
          else for (const card of [...list.children].slice(6)) card.remove();
          more.textContent = expanded ? "Show fewer" : "Show " + (peers.length - 6) + " more";
          more.setAttribute("aria-expanded", String(expanded));
          if (expanded) list.children[6].querySelector("h3 a").focus({preventScroll: true});
        });
        section.append(more);
      }
    } catch (error) {
      if (signal.aborted) return;
      status.textContent = "Similar journals unavailable.";
      const retry = element("button", "Try again", "text-button peer-retry");
      retry.type = "button";
      retry.onclick = () => { retry.remove(); status.textContent = "Finding similar journals…"; load(); };
      section.append(retry);
    } finally {
      pending = false;
    }
  };
  section.addEventListener("toggle", () => { if (section.open && !loaded) load(); });
  return section;
}

function showResults(journals, signal) {
  const rows = journals.map(journal => ({
    values: journalFacts(journal),
    journal,
  }));
  let filteredRows = rows;
  let page = 0;
  for (const field of filterFields) {
    const name = field.dataset.field;
    const present = new Set(rows.map(row => row.values[name]));
    const values = name === "level"
      ? ["0", "1", "2", "3", ...(present.has("Unclassified") ? ["Unclassified"] : [])]
      : [...present].sort();
    field.open = false;
    field.querySelector(".choices").replaceChildren(...values.map(value => {
      const label = element("label");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.value = value;
      label.append(checkbox, element("span", value));
      return label;
    }));
  }
  filters.hidden = rows.length < 2;

  function applyFilters() {
    const active = [];
    for (const field of filterFields) {
      const selected = [...field.querySelectorAll("input:checked")].map(input => input.value);
      field.querySelector("summary span").textContent = !selected.length ? ""
        : field.dataset.field === "level" ? selected.join(", ") : String(selected.length);
      if (selected.length) active.push([field.dataset.field, selected]);
    }

    filteredRows = rows.filter(({values}) => passesFilters(values, active));
    page = 0;
    reset.hidden = !active.length;
    renderPage();
  }

  function renderPage() {
    const size = Number(pageSize.value);
    const pages = Math.max(1, Math.ceil(filteredRows.length / size));
    const start = page * size;
    const end = Math.min(start + size, filteredRows.length);
    const existing = new Map([...cards.children].map(card => [Number(card.dataset.jufoId), card]));
    cards.replaceChildren(...filteredRows.slice(start, end).map(({journal}) => existing.get(journal.jufo_id) || renderJournal(journal, signal)));
    filterStatus.textContent = filteredRows.length ? (pages > 1 ? `${start + 1}–${end} of ` : "")
      + `${filteredRows.length} ${filteredRows.length === 1 ? "journal" : "journals"}`
      + (filteredRows.length !== rows.length ? ` · Filtered from ${rows.length}` : "")
      : "No matches. Clear a filter.";
    pagination.hidden = filteredRows.length <= 50;
    pagination.querySelector("nav").hidden = pages <= 1;
    bottomPagination.hidden = pages <= 1 || !filteredRows.length;
    for (const label of document.querySelectorAll("[data-page-label]")) label.textContent = `${page + 1} / ${pages}`;
    for (const button of document.querySelectorAll("[data-page]")) {
      const previous = button.dataset.page === "previous";
      button.disabled = previous ? page === 0 : page === pages - 1;
      button.onclick = () => {
        page += previous ? -1 : 1;
        renderPage();
        pagination.querySelector("[data-page-label]").focus({preventScroll: true});
        pagination.scrollIntoView({block: "start"});
      };
    }
  }

  const reset = document.querySelector("#reset-filters");
  filters.onchange = applyFilters;
  pageSize.onchange = () => {
    page = 0;
    renderPage();
  };
  reset.onclick = () => {
    for (const input of filters.querySelectorAll("input:checked")) input.checked = false;
    applyFilters();
    filterFields[0].querySelector("summary").focus();
  };
  filterStatus.hidden = rows.length === 0;
  applyFilters();
}

async function loadSearchPages(params, readPage, progress = () => {}, firstPage = () => {}) {
  const first = await readPage(params);
  const pages = [first];
  if (first.next_offset != null) firstPage(first);
  if (first.next_offset == null) return pages;
  if (Number.isInteger(first.total) && first.total <= 100000 && first.next_offset === 1000) {
    const offsets = [];
    for (let offset = 1000; offset < first.total; offset += 1000) offsets.push(offset);
    let next = 0, completed = first.results.length;
    await Promise.all(Array.from({length: Math.min(3, offsets.length)}, async () => {
      while (next < offsets.length) {
        const index = next++;
        const page = new URLSearchParams(params);
        page.set("offset", offsets[index]);
        pages[index + 1] = await readPage(page);
        completed += pages[index + 1].results.length;
        progress(completed);
      }
    }));
  } else {
    while (pages.at(-1).next_offset != null) {
      const page = new URLSearchParams(params);
      page.set("offset", pages.at(-1).next_offset);
      pages.push(await readPage(page));
    }
  }
  return pages;
}

async function search(query, mode = "fast", remember = true) {
  if (remember) {
    recentSearches = recentQueries([query, ...recentSearches]);
    saveRecentSearches();
  }
  activeSearch?.abort();
  const request = new AbortController();
  activeSearch = request;
  const submit = document.querySelector("#search button[type=submit]");
  submit.disabled = true;
  submit.textContent = "Searching…";
  cards.setAttribute("aria-busy", "true");
  const queryKey = query.normalize("NFKC").trim().toLowerCase().replace(/\s+/g, " ")
    .replace(/\s*[,;，]\s*/g, ", ");
  const params = new URLSearchParams({q: queryKey, mode, batch: "5"});
  queryInput.value = query;
  const address = new URLSearchParams({q: query});
  if (!remember) address.set("from", "similar");
  if (mode === "articles") address.set("mode", mode);
  history.replaceState(null, "", "?" + address);
  cards.replaceChildren();
  filters.hidden = true;
  pagination.hidden = true;
  bottomPagination.hidden = true;
  filterStatus.hidden = true;
  notices.hidden = true;
  articleSearch.hidden = true;
  statusLine.textContent = "Searching…";
  statusLine.hidden = false;
  try {
    const matches = new Map();
    const messages = new Set();
    let data;
    let matchedTopic;
    const pages = await loadSearchPages(params, async page => {
      const cacheKey = page.toString();
      const cached = searchCache.get(cacheKey);
      let pageData = cached?.expires > Date.now() ? cached.data : null;
      if (!pageData) {
        const response = await fetch("/api/search?" + page, {signal: request.signal});
        pageData = await response.json();
        if (!response.ok) throw new Error(pageData.error || "Search failed. Please try again.");
        if (!pageData.notices?.length && mode !== "articles") {
          searchCache.set(cacheKey, {data: pageData, expires: Date.now() + 300000});
          if (searchCache.size > 10) searchCache.delete(searchCache.keys().next().value);
        }
      }
      return pageData;
    }, count => { if (!request.signal.aborted) statusLine.textContent = "Loading remaining results… " + count; }, first => {
      if (request.signal.aborted) return;
      showResults(first.results, request.signal);
      filters.hidden = true;
      pagination.hidden = true;
      bottomPagination.hidden = true;
      filterStatus.textContent = "First " + Math.min(Number(pageSize.value), first.results.length) + " journals · loading remaining results";
      statusLine.textContent = "Loading remaining results…";
    });
    for (data of pages) {
      if (request.signal.aborted) return;
      for (const journal of data.results) {
        if (matches.get(journal.jufo_id)?.topic_match && !journal.topic_match) continue;
        matches.set(journal.jufo_id, journal);
      }
      if (data.topic) matchedTopic = data.topic;
      for (const notice of data.notices) messages.add(notice);
    }
    const journals = [...matches.values()];
    const count = journals.length;
    if (!remember && count === 1 && queryInput.value === query) queryInput.value = journals[0].title;
    statusLine.hidden = count > 0;
    if (!count) statusLine.textContent = matchedTopic
      ? "No journals matched. Try fewer keywords or a broader term."
      : "No JUFO matches. Try the full journal title or an ISSN.";
    if (messages.size) {
      notices.textContent = [...messages].join(" ");
      notices.hidden = false;
    }
    const acronymCount = journals.filter(journal => journal.matched_acronym).length;
    if (acronymCount > 1) {
      statusLine.textContent = "This abbreviation matches multiple titles. Compare titles and ISSNs.";
      statusLine.hidden = false;
    }
    showResults(journals, request.signal);
    articleSearch.hidden = !matchedTopic;
    articleSearch.textContent = mode === "articles" ? "Back to topic matches" : "Find matching articles";
    articleSearch.onclick = () => search(query, mode === "articles" ? "fast" : "articles", remember);
    if (data.catalogue_checked) {
      const date = document.querySelector("#catalogue-date");
      date.textContent = "JUFO snapshot · " + data.catalogue_checked;
      date.hidden = false;
    }
    if (!count) {
      const actions = element("div", null, "sources");
      actions.append(link("Search Aalto SciFree", sciFree(query)));
      cards.append(actions);
    }
  } catch (error) {
    if (request.signal.aborted) return;
    if (cards.querySelector(".card")) filterStatus.textContent = "Partial results · retry search to load all journals";
    statusLine.hidden = false;
    statusLine.textContent = error.message || "Search failed. Please try again.";
    if (mode === "articles") {
      const back = element("button", "Back to topic matches", "secondary");
      back.type = "button";
      back.addEventListener("click", () => search(query, "fast", remember));
      cards.append(back);
    }
    cards.append(link("Search Aalto SciFree", sciFree(query)));
  } finally {
    if (activeSearch === request) {
      submit.disabled = false;
      submit.textContent = "Search";
      cards.setAttribute("aria-busy", "false");
    }
  }
}

function closeFilters(except) {
  for (const field of filterFields) if (field !== except) field.open = false;
}

for (const field of filterFields) {
  field.addEventListener("toggle", () => { if (field.open) closeFilters(field); });
}
document.addEventListener("click", event => {
  if (!filters.contains(event.target)) closeFilters();
});
document.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  const open = filterFields.find(field => field.open);
  if (open) {
    closeFilters();
    open.querySelector("summary").focus();
  }
});

form.addEventListener("submit", event => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (query.length >= 2) search(query);
  else statusLine.textContent = "Enter a journal title, ISSN or research topic.";
});
queryInput.addEventListener("input", () => {
  const submit = document.querySelector("#search button[type=submit]");
  submit.disabled = false;
  submit.textContent = "Search";
});
document.querySelector("#clear-recent").addEventListener("click", () => {
  recentSearches = [];
  saveRecentSearches();
  queryInput.focus();
});
renderRecentSearches();
setupOAPreferences();
const initialParams = new URLSearchParams(location.search);
const initialQuery = initialParams.get("q");
if (initialQuery?.trim().length >= 2 && initialQuery.length <= 160) {
  search(initialQuery.trim(), initialParams.get("mode") === "articles" ? "articles" : "fast", initialParams.get("from") !== "similar");
}
