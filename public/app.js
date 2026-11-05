"use strict";

const form = document.querySelector("#search");
const queryInput = document.querySelector("#query");
const statusLine = document.querySelector("#status");
const cards = document.querySelector("#cards");
const notices = document.querySelector("#notices");
const queryLabel = document.querySelector("#query-label");
const filters = document.querySelector("#filters");
const filterStatus = document.querySelector("#filter-status");
const filterFields = [...filters.querySelectorAll("select")];
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

function journalFacts(journal) {
  const agreement = journal.agreement;
  const model = agreement?.model || reported(journal.external?.oa_info?.open_access_type);
  const fee = agreement?.status === "quota_exhausted" ? "Quota exhausted"
    : agreement?.discount === 100 ? "Fully covered"
    : agreement ? agreement.discount + "% APC discount" : "Check SciFree";
  return {
    level: journal.level == null ? "Unclassified" : String(journal.level),
    publisher: journal.publisher_name || "Unknown publisher",
    fee,
    licence: agreement?.licence || reported(journal.external?.license?.channel) || "See journal",
    model: model === "Pure OA" || model === "Open access" ? "Fully open access" : model || "See journal",
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
    .filter(([year, level]) => /^\d{4}$/.test(year) && /^[0-3]$/.test(String(level)))
    .sort(([a], [b]) => Number(b) - Number(a));
  const details = element("details");
  details.append(element("summary", "JUFO evaluation history"));
  if (!entries.length) {
    details.append(element("p", "JUFO has no recorded annual levels for this journal."));
    return details;
  }
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
    row.insertCell().textContent = "Level " + level;
  }
  details.append(table);
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
  const facts = element("dl", null, "facts");
  facts.append(
    fact("JUFO classification", level, "Publication Forum", "accent"),
    fact("Aalto publishing fees", feeButton, agreement?.source ? "FinELib · " + agreement.publisher
      : agreement ? "Aalto SciFree · " + agreement.publisher : "Verify with Aalto", feeTone),
    fact(agreement?.licence ? "Agreement licence" : "Journal licence", licence,
      agreement?.licence ? "Aalto agreement" : licence === "See journal" ? "Licence unavailable in JUFO" : "Reported by JUFO"),
    fact("Publishing model", model, agreement?.source ? "FinELib title list" : agreement ? "Aalto SciFree"
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
      item.append(link(work.title, "https://doi.org/" + encodeURI(work.doi)));
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
    const present = new Set(rows.map(row => row.values[field.name]));
    const values = field.name === "level"
      ? ["0", "1", "2", "3", ...(present.has("Unclassified") ? ["Unclassified"] : [])]
      : [...present].sort();
    field.replaceChildren(new Option("All", ""), ...values.map(value => new Option(value, value)));
    field.disabled = values.length < 2;
  }
  filters.hidden = rows.length < 2;

  function applyFilters() {
    let visible = 0;
    for (const {values, card} of rows) {
      card.hidden = filterFields.some(field => field.value && values[field.name] !== field.value);
      if (!card.hidden) visible++;
    }
    filterStatus.hidden = visible === rows.length;
    filterStatus.textContent = visible ? visible + " of " + rows.length + " shown"
      : "No journals match these filters. Clear a filter to see more results.";
  }

  filters.onchange = applyFilters;
  document.querySelector("#reset-filters").onclick = () => {
    for (const field of filterFields) field.value = "";
    applyFilters();
  };
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
      statusLine.textContent += " · " + acronymCount + " share these initials. Compare titles and ISSNs.";
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
