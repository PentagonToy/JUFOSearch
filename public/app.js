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
  item.append(element("dt", label), definition, element("small", note));
  return item;
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
};

function oaLabel(label, icon) {
  const badge = element("span", null, "oa-label");
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", oaIconPaths[icon]);
  svg.append(path);
  badge.append(svg, element("span", label));
  return badge;
}

function articleAccess(doi) {
  const button = element("button", "Check article OA", "secondary");
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
        hybrid: ["Hybrid OA", "Open access at publisher", "lock"],
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
  const oa = journal.external?.oa_info;
  const model = agreement?.model || reported(oa?.open_access_type);
  const fee = agreement?.status === "quota_exhausted" ? "Quota exhausted"
    : agreement?.discount === 100 ? "Fully covered"
    : agreement ? agreement.discount + "% APC discount" : "Check SciFree";
  return {
    level: journal.level == null ? "Unclassified" : String(journal.level),
    publisher: publisherName(journal),
    fee,
    licence: agreement?.licence || reported(journal.external?.license?.channel) || "See journal",
    model: oa?.is_diamondOA === true ? "Diamond OA"
      : model === "Pure OA" || model === "Open access" ? "Gold OA"
      : model === "Hybrid" ? "Hybrid OA" : model || "See journal",
  };
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
  const details = element("details", null, "evaluation-history");
  details.append(element("summary", "JUFO evaluation history"));
  details.addEventListener("toggle", () => {
    if (!details.open || details.childElementCount > 1) return;
    const entries = annualLevels(history, yearStart);
    if (!entries.length) {
      details.append(element("p", "No annual JUFO levels recorded."));
      return;
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
      const label = level === null ? "Not recorded (shown at baseline)" : "Level " + level;
      return `<circle class="${className}" cx="${x(year)}" cy="${y(level ?? 0)}" r="4"><title>${year} · ${label}</title></circle>`;
    }).join("");
    const ticks = historyTicks(entries).map(year => {
      const anchor = first === last ? "middle" : year === first ? "start" : year === last ? "end" : "middle";
      return `<path class="history-grid" d="M${x(year)} 116v5"/><text x="${x(year)}" y="146" text-anchor="${anchor}">${year}</text>`;
    }).join("");
    const plot = element("figure", null, "history-plot");
    plot.innerHTML = `<svg viewBox="0 0 456 160" role="img" aria-label="Annual JUFO levels from ${first} to ${last}. Open circles at 0 and dashed links indicate missing records. Filled circles show recorded levels. Recent values are in the table.">
      ${grid}${lines}${markers}${ticks}
    </svg>`;
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
      row.insertCell().append(element("span", level === null ? "Not recorded" : "Level " + level,
        level === null ? "history-unrecorded" : level === 0 ? "history-level history-level-zero" : "history-level"));
    }
    const content = element("div", null, "history-content");
    content.append(plot, table);
    details.append(content);
  });
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

function renderJournal(journal) {
  const agreement = journal.agreement;
  const oa = journal.external?.oa_info;
  const level = journal.level == null ? "Unclassified" : "Level " + journal.level;
  const {fee, licence, model} = journalFacts(journal);
  const sciFreeUrl = sciFree('"' + journal.title + '"');
  const heading = element("h2");
  const publisherUrl = journalWebsite(journal);
  if (publisherUrl) heading.append(link(journal.title, publisherUrl));
  else heading.textContent = journal.title;
  const feeButton = element("button", fee, "fee-link");
  feeButton.type = "button";
  feeButton.setAttribute("aria-haspopup", "dialog");
  feeButton.setAttribute("aria-label", fee + " · View agreement for " + journal.title);
  feeButton.addEventListener("click", () => showAgreement(journal, sciFreeUrl));
  const feeTone = agreement?.status === "quota_exhausted" ? "warning"
    : agreement?.discount === 100 ? "accent" : "";
  const identifiers = [...new Set([journal.issn_electronic, journal.issn_print, journal.issnl].filter(Boolean))];
  const article = element("article", null, "card");
  article.append(
    heading,
    element("p", [publisherName(journal), identifiers.join(" / "),
      journal.is_active === false ? "Inactive" : ""].filter(Boolean).join(" · "), "metadata")
  );
  const wosListed = journal.external?.index_info?.includes("WOS");
  const facts = element("dl", null, "facts");
  facts.append(
    fact("JUFO classification", level, "Publication Forum", "accent"),
    fact("Aalto publishing fees", feeButton, agreement?.source ? "FinELib · " + agreement.publisher
      : agreement ? "Aalto SciFree · " + agreement.publisher : "Verify with Aalto", feeTone),
    fact(agreement?.licence ? "Agreement licence" : "Journal licence", licence,
      agreement?.licence ? "Aalto agreement" : licence === "See journal" ? "Licence unavailable in JUFO" : "Reported by JUFO"),
    fact("Publishing model", model.endsWith(" OA") ? oaLabel(model, "lock") : model,
      model === "Diamond OA" ? "No APC · JUFO"
        : agreement?.source ? "FinELib title list" : agreement ? "Aalto SciFree"
        : model === "See journal" ? "Model unavailable in JUFO" : "Reported by JUFO")
  );
  article.append(facts);

  if (journal.examples?.length) {
    const evidence = element("div", null, "evidence");
    evidence.append(element("p", "Matching articles · Crossref"));
    const list = element("ul");
    for (const work of journal.examples) {
      const item = element("li");
      item.append(link(work.title, "https://doi.org/" + encodeURI(work.doi)), articleAccess(work.doi));
      list.append(item);
    }
    evidence.append(list);
    article.append(evidence);
  } else if (journal.topic_match) {
    article.append(element("p", "Topic starting point", "evidence"));
  }

  const notes = element("details");
  notes.append(element("summary", "Journal notes"));
  const fields = journal.okm_disciplines?.map(item => item.localized_labels?.en).filter(Boolean);
  notes.append(element("p", "JUFO ID " + journal.jufo_id + (fields?.length ? " · " + fields.join(" · ") : "")));
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
  article.append(evaluationHistory(journal.level_history, journal.year_start), notes);
  const sources = element("div", null, "sources");
  sources.append(link("Aalto SciFree", sciFreeUrl),
    link("JUFO record", "https://jufo-rest.csc.fi/v2.1/channel/" + journal.jufo_id));
  article.append(sources);
  return article;
}

function showResults(journals) {
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
      field.querySelector("summary span").textContent = selected.length ? selected.length + " selected" : "";
      if (selected.length) active.push([field.dataset.field, selected]);
    }

    filteredRows = rows.filter(({values}) => !active.some(([name, selected]) => !selected.includes(values[name])));
    page = 0;
    reset.disabled = !active.length;
    renderPage();
  }

  function renderPage() {
    const size = Number(pageSize.value);
    const pages = Math.max(1, Math.ceil(filteredRows.length / size));
    const start = page * size;
    const end = Math.min(start + size, filteredRows.length);
    cards.replaceChildren(...filteredRows.slice(start, end).map(({journal}) => renderJournal(journal)));
    filterStatus.textContent = filteredRows.length ? `Showing ${start + 1}–${end} of ${filteredRows.length} ${filteredRows.length === 1 ? "journal" : "journals"}`
      + (filteredRows.length !== rows.length ? ` · Filtered from ${rows.length}` : "")
      : "No matches. Clear a filter.";
    pagination.hidden = filteredRows.length <= 50;
    bottomPagination.hidden = pages <= 1 || !filteredRows.length;
    for (const label of document.querySelectorAll("[data-page-label]")) label.textContent = `Page ${page + 1} of ${pages}`;
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

async function search(query, mode = "auto") {
  activeSearch?.abort();
  const request = new AbortController();
  activeSearch = request;
  const params = new URLSearchParams({q: query, mode, batch: "5"});
  queryInput.value = query;
  const address = new URLSearchParams({q: query});
  if (mode === "topic") address.set("mode", mode);
  history.replaceState(null, "", "?" + address);
  cards.replaceChildren();
  filters.hidden = true;
  pagination.hidden = true;
  bottomPagination.hidden = true;
  filterStatus.hidden = true;
  notices.hidden = true;
  statusLine.textContent = "Searching…";
  try {
    const matches = new Map();
    const messages = new Set();
    let data;
    let matchedTopic;
    do {
      const response = await fetch("/api/search?" + params, {signal: request.signal});
      data = await response.json();
      if (request.signal.aborted) return;
      if (!response.ok) throw new Error(data.error);
      for (const journal of data.results) {
        if (matches.get(journal.jufo_id)?.topic_match && !journal.topic_match) continue;
        matches.set(journal.jufo_id, journal);
      }
      if (data.topic) matchedTopic = data.topic;
      for (const notice of data.notices) messages.add(notice);
      if (data.next_offset != null) {
        params.set("offset", data.next_offset);
        statusLine.textContent = "Searching… " + matches.size + " found";
      }
    } while (data.next_offset != null);
    const journals = [...matches.values()];
    const count = journals.length;
    if (matchedTopic) {
      statusLine.textContent = count ? "Journals for “" + matchedTopic + "” · " + count + " found"
        : "No journals found for “" + matchedTopic + "”. Try a shorter topic or a synonym.";
    } else {
      statusLine.textContent = count ? count + (count === 1 ? " match" : " matches")
        : "No JUFO matches. Try the full journal title or an ISSN.";
    }
    if (messages.size) {
      notices.textContent = [...messages].join(" ");
      notices.hidden = false;
    }
    const acronymCount = journals.filter(journal => journal.matched_acronym).length;
    if (acronymCount > 1) {
      statusLine.textContent += " · " + acronymCount + " share these initials.";
    }
    showResults(journals);
    if (!count) {
      const actions = element("div", null, "sources");
      actions.append(link("Search Aalto SciFree", sciFree(query)));
      cards.append(actions);
    }
  } catch (error) {
    if (request.signal.aborted) return;
    statusLine.textContent = error.message || "Search failed. Please try again.";
    cards.append(link("Search Aalto SciFree", sciFree(query)));
  }
}

form.addEventListener("submit", event => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (query.length >= 2) search(query);
  else statusLine.textContent = "Enter a journal title, ISSN or research topic.";
});
document.querySelectorAll("[data-query]").forEach(button => {
  button.addEventListener("click", () => {
    search(button.dataset.query);
  });
});
const initialParams = new URLSearchParams(location.search);
const initialQuery = initialParams.get("q");
if (initialQuery?.trim().length >= 2 && initialQuery.length <= 160) {
  search(initialQuery.trim(), initialParams.get("mode") === "topic" ? "topic" : "auto");
}
