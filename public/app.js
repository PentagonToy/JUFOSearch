"use strict";

const form = document.querySelector("#search");
const queryInput = document.querySelector("#query");
const statusLine = document.querySelector("#status");
const cards = document.querySelector("#cards");
const notices = document.querySelector("#notices");
const queryLabel = document.querySelector("#query-label");
const filters = document.querySelector("#filters");
const filterStatus = document.querySelector("#filter-status");
const filterFields = [...filters.querySelectorAll(".facet")];
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
    publisher: journal.publisher_name || "Unknown publisher",
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
    field("Who qualifies", "The submitting corresponding author must be affiliated with Aalto University, select Aalto University as their affiliation and use their Aalto email.");
    field("Eligible article types", agreement.article_types);
    field("Quota", agreement.quota);
    field("Agreement licence", agreement.licence);
    if (agreement.discount < 100) {
      field("Remaining fee", "The publisher invoices the remaining APC. Confirm funding with your department before submitting.");
    }
    field(agreement.source ? "Title list checked" : "SciFree status recorded", agreement.checked);
  } else {
    const messages = {
      expired: "The agreement data for this journal is outside its recorded period. Check SciFree for current terms.",
      unavailable: "The FinELib title list could not be loaded. Check SciFree for current support.",
      unverified: "Check Aalto SciFree for title-level coverage, licence options and quotas."
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

function evaluationHistory(history) {
  const entries = Object.entries(history || {})
    .filter(([year]) => /^\d{4}$/.test(year))
    .map(([year, level]) => [year, /^[0-3]$/.test(String(level)) ? Number(level) : null])
    .sort(([a], [b]) => Number(b) - Number(a));
  const details = element("details");
  details.append(element("summary", "JUFO evaluation history"));
  if (!entries.length) {
    details.append(element("p", "JUFO has no recorded annual levels for this journal."));
    return details;
  }
  const plot = element("div", null, "history-plot");
  const chronological = entries.slice().reverse();
  const x = index => 36 + index * 396 / Math.max(1, entries.length - 1);
  const y = level => 112 - (level ?? 0) * 29;
  const grid = [0, 1, 2, 3].map(level =>
    `<path class="history-grid" d="M36 ${y(level)}H432"/><text x="14" y="${y(level) + 4}">${level}</text>`).join("");
  const points = chronological.map(([, level], index) => x(index) + "," + y(level)).join(" ");
  const markers = chronological.map(([year, level], index) =>
    `<circle class="${level === null ? "history-missing" : "history-recorded"}" cx="${x(index)}" cy="${y(level)}" r="4"><title>${year} · ${level === null ? "No level recorded" : "Level " + level}</title></circle>`).join("");
  plot.innerHTML = `<svg viewBox="0 0 456 148" role="img" aria-label="JUFO levels by year. See the table for exact values.">
    ${grid}<polyline class="history-line" points="${points}"/>${markers}
    <text x="36" y="137">${chronological[0][0]}</text>
    ${entries.length > 1 ? `<text x="432" y="137" text-anchor="end">${entries[0][0]}</text>` : ""}
  </svg>`;
  plot.append(element("p", "Open circles at 0 indicate years without a recorded level."));
  const table = element("table", null, "history-table");
  const headers = table.createTHead().insertRow();
  for (const label of ["Year", "JUFO level"]) {
    const header = element("th", label);
    header.scope = "col";
    headers.append(header);
  }
  const body = table.createTBody();
  for (const [year, level] of entries) {
    const row = body.insertRow();
    row.insertCell().textContent = year;
    row.insertCell().textContent = level === null ? "No level recorded" : "Level " + level;
  }
  details.append(plot, table);
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

function renderJournal(journal, topic) {
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
    element("p", [journal.publisher_name, identifiers.join(" / "),
      journal.is_active === false ? "Inactive" : ""].filter(Boolean).join(" · "), "metadata")
  );
  const indexing = journal.wos_indexing;
  const wosListed = journal.external?.index_info?.includes("WOS");
  if (indexing || wosListed) {
    const row = element("div", null, "indexing");
    if (indexing) {
      for (const collection of indexing.collections) {
        row.append(link(collection, indexing.source));
      }
      row.append(element("small", "Indexing source checked " + indexing.checked));
    } else {
      row.append(element("small", "Web of Science · Collection unverified"));
    }
    article.append(row);
  }
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

  if (journal.matched_acronym) {
    article.append(element("p", "Matches initials " + journal.matched_acronym, "evidence"));
  }

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
  } else if (topic) {
    article.append(element("p", "Topic starting point", "evidence"));
  }

  const notes = element("details");
  notes.append(element("summary", "Journal notes"));
  const fields = journal.okm_disciplines?.map(item => item.localized_labels?.en).filter(Boolean);
  notes.append(element("p", "JUFO ID " + journal.jufo_id + (fields?.length ? " · " + fields.join(" · ") : "")));
  if (oa?.immediate_sa_allowed_accepted === "yes") {
    const acceptedLicence = journal.external?.license?.sa_accepted;
    notes.append(element("p", "JUFO reports immediate self-archiving of the accepted manuscript"
      + (acceptedLicence ? " under " + acceptedLicence : "") + "."));
  }
  if (indexing || wosListed) {
    const indexing = element("p", "Check current Web of Science coverage by ISSN in the ");
    indexing.append(link("Clarivate Master Journal List", "https://mjl.clarivate.com/"));
    notes.append(indexing);
  }
  article.append(evaluationHistory(journal.level_history), notes);
  const sources = element("div", null, "sources");
  sources.append(link("Aalto SciFree", sciFreeUrl),
    link("JUFO record", "https://jufo-rest.csc.fi/v2.1/channel/" + journal.jufo_id));
  article.append(sources);
  return article;
}

function showResults(journals, topic) {
  const rows = journals.map(journal => ({
    values: journalFacts(journal),
    card: renderJournal(journal, topic),
  }));
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

    let visible = 0;
    for (const {values, card} of rows) {
      card.hidden = active.some(([name, selected]) => !selected.includes(values[name]));
      if (!card.hidden) visible++;
    }
    filterStatus.textContent = visible ? visible + " of " + rows.length + " shown"
      : "No journals match these filters. Clear a filter to see more results.";
    reset.disabled = !active.length;
  }

  const reset = document.querySelector("#reset-filters");
  filters.onchange = applyFilters;
  reset.onclick = () => {
    for (const input of filters.querySelectorAll("input:checked")) input.checked = false;
    applyFilters();
    filterFields[0].querySelector("summary").focus();
  };
  filterStatus.hidden = rows.length === 0;
  if (rows.length) applyFilters();
  cards.replaceChildren(...rows.map(row => row.card));
}

function setMode(mode) {
  form.elements.mode.value = mode;
  const label = mode === "topic" ? "Research topic" : "Journal title, ISSN or initials";
  queryLabel.textContent = label;
  queryInput.placeholder = label;
}

function topicButton(query) {
  const button = element("button", "Search by research topic", "secondary");
  button.type = "button";
  button.addEventListener("click", () => {
    setMode("topic");
    search(query);
  });
  return button;
}

async function search(query) {
  activeSearch?.abort();
  const request = new AbortController();
  activeSearch = request;
  const mode = form.elements.mode.value;
  const params = new URLSearchParams({q: query});
  if (mode === "topic") params.set("mode", mode);
  queryInput.value = query;
  history.replaceState(null, "", "?" + params);
  cards.replaceChildren();
  filters.hidden = true;
  filterStatus.hidden = true;
  notices.hidden = true;
  statusLine.textContent = mode === "topic" ? "Finding journals that publish on this topic…" : "Searching journals…";
  try {
    const response = await fetch("/api/search?" + params, {signal: request.signal});
    const data = await response.json();
    if (request.signal.aborted) return;
    if (!response.ok) throw new Error(data.error);
    const count = data.results.length;
    if (data.topic) {
      statusLine.textContent = count ? "Journals for “" + data.topic + "” · " + count + " found"
        : "No journals found for “" + data.topic + "”. Try a shorter topic or a synonym.";
    } else {
      statusLine.textContent = count ? (count === 30 ? "First 30 matches" : count + (count === 1 ? " match" : " matches"))
        : "No JUFO matches. Try the full journal title or an ISSN.";
    }
    if (data.notices.length) {
      notices.textContent = data.notices.join(" ");
      notices.hidden = false;
    }
    const acronymCount = data.results.filter(journal => journal.matched_acronym).length;
    if (acronymCount > 1) {
      statusLine.textContent += " · " + acronymCount + " share these initials.";
    }
    showResults(data.results, data.topic);
    if (!count && !data.topic) {
      const actions = element("div", null, "sources");
      if (!/^\d{4}-?\d{3}[0-9x]$/i.test(query)) actions.append(topicButton(query));
      actions.append(link("Search Aalto SciFree", sciFree(query)));
      cards.append(actions);
    }
  } catch (error) {
    if (request.signal.aborted) return;
    statusLine.textContent = error.message || "Search failed. Please try again.";
    if (mode === "journal") cards.append(link("Search Aalto SciFree", sciFree(query)));
  }
}

form.addEventListener("change", () => setMode(form.elements.mode.value));
form.addEventListener("submit", event => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (query.length >= 2) search(query);
  else statusLine.textContent = "Enter a journal title, ISSN or research topic.";
});
document.querySelectorAll("[data-query]").forEach(button => {
  button.addEventListener("click", () => {
    setMode("topic");
    search(button.dataset.query);
  });
});
const initialParams = new URLSearchParams(location.search);
const initialQuery = initialParams.get("q");
setMode(initialParams.get("mode") === "topic" ? "topic" : "journal");
if (initialQuery?.trim().length >= 2 && initialQuery.length <= 160) search(initialQuery.trim());
