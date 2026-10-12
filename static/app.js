const form = document.getElementById("search-form");
const button = document.getElementById("submit-btn");
const output = document.getElementById("output");
const errorBox = document.getElementById("error");
const summary = document.getElementById("summary");
const resultsList = document.getElementById("results-list");
const count = document.getElementById("result-count");

function safeText(value) {
  return String(value ?? "");
}

function normalizeCell(value, fallback = "Unknown") {
  const text = safeText(value)
    .replace(/\r?\n+/g, " ")
    .replace(/\|/g, " ")
    .replace(/[•●◦◉\u2022*\-–—]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text || fallback;
}

function humanize(value, fallback = "Unknown") {
  const text = normalizeCell(value, fallback).replace(/_/g, " ");
  return text
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function normalizeMarkdown(text) {
  return String(text ?? "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/\r\n/g, "\n")
    .replace(/^\s*```(?:markdown|md|html)?\s*/i, "")
    .replace(/\s*```\s*$/i, "")
    .trim();
}

function stripMarkdownTables(text) {
  return String(text ?? "")
    .split(/\n+/)
    .filter((line) => {
      const trimmed = line.trim();
      if (!trimmed.includes("|")) return true;
      return !/^\|?\s*:?[ -]+:\s*\|/.test(trimmed) && !/^\|.*\|$/.test(trimmed);
    })
    .join("\n")
    .trim();
}

function buildOverviewRows(results) {
  const rows = Array.isArray(results) ? results : [];
  return rows.map((result) => {
    const link = getSafeUrl(result?.link || "");
    return {
      source: normalizeCell(result?.source || getHostname(link) || "Unknown", "Unknown"),
      title: normalizeCell(result?.title || "Untitled opportunity", "Untitled opportunity"),
      key_points: normalizeCell(
        result?.snippet || result?.deadline_evidence || result?.source_check_note || "No description provided.",
        "No description provided."
      ),
      listing_type: normalizeCell(result?.listing_quality || "Unknown", "Unknown"),
      source_check: [
        safeText(result?.source_check_status).toLowerCase() === "checked"
          ? "Readable; identity unverified"
          : ({
            unreachable: "Unreachable",
            not_checked: "Not checked"
          }[safeText(result?.source_check_status).toLowerCase()] ||
            humanize(result?.source_check_status || "Unverified", "Unverified")),
        result?.source_check_note ? normalizeCell(result.source_check_note) : ""
      ].filter(Boolean).join(" — "),
      application_status: humanize(result?.application_status || "Unknown", "Unknown"),
      deadline_status: [
        humanize(result?.opportunity_status || "Unknown", "Unknown"),
        result?.deadline ? normalizeCell(result.deadline) : "",
      ].filter(Boolean).join(" — "),
      link,
    };
  });
}

function createOverviewTable(rows) {
  const table = document.createElement("table");
  table.className = "report-overview-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Source", "Title", "Key points", "Listing type", "Source check", "Application status", "Deadline status"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const sourceCell = document.createElement("td");
    const sourceText = humanize(row.source || "Unknown", "Unknown");
    if (row.link) {
      const link = document.createElement("a");
      link.href = row.link;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = sourceText;
      sourceCell.appendChild(link);
    } else {
      sourceCell.textContent = sourceText;
    }
    tr.appendChild(sourceCell);

    [
      ["title", row.title || "Untitled opportunity"],
      ["key_points", row.key_points || "No description provided."],
      ["listing_type", row.listing_type || "Unknown"],
      ["source_check", row.source_check || "Unverified"],
      ["application_status", row.application_status || "Unknown"],
      ["deadline_status", row.deadline_status || "Unknown"],
    ].forEach(([key, value]) => {
      const cell = document.createElement("td");
      cell.textContent = humanize(value, key === "title" ? "Untitled opportunity" : "Unknown");
      tr.appendChild(cell);
    });

    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  return table;
}

function getSafeUrl(value) {
  try {
    const url = new URL(String(value || ""));
    if (url.protocol === "https:" || url.protocol === "http:") {
      return url.href;
    }
  } catch {
    // Invalid or missing URL.
  }
  return "";
}

function normalizeName(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/^www\./, "")
    .replace(/[^a-z0-9]/g, "");
}

function getHostname(value) {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function findMatchingResult(sourceLabel, results) {
  const source = normalizeName(sourceLabel);
  if (!source) return null;

  for (const result of results) {
    const url = getSafeUrl(result.link);
    if (!url) continue;

    const domain = normalizeName(getHostname(url));
    const resultSource = normalizeName(result.source);

    if (source === resultSource || source === domain) {
      return result;
    }
  }

  for (const result of results) {
    const url = getSafeUrl(result.link);
    if (!url) continue;

    const domain = normalizeName(getHostname(url));
    const resultSource = normalizeName(result.source);

    if (
      source.length >= 5 &&
      (
        (resultSource.length >= 5 && resultSource.includes(source)) ||
        (domain.length >= 5 && domain.includes(source))
      )
    ) {
      return result;
    }
  }

  return null;
}

function linkReportSources(results) {
  const rows = summary.querySelectorAll("table tbody tr");

  rows.forEach((row) => {
    const firstCell = row.querySelector("td");
    if (!firstCell || firstCell.querySelector("a")) return;

    const sourceLabel = firstCell.textContent.trim();
    const match = findMatchingResult(sourceLabel, results);
    if (!match) return;

    const url = getSafeUrl(match.link);
    if (!url) return;

    const link = document.createElement("a");
    link.className = "report-source-link";
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = sourceLabel;
    link.title = "Open matching original search result";

    firstCell.replaceChildren(link);
  });
}

function displaySummary(data) {
  summary.replaceChildren();

  const narrativeText = stripMarkdownTables(
    normalizeMarkdown(data.summary || "No AI summary is available.")
  );

  if (narrativeText) {
    if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
      summary.textContent = narrativeText;
      console.error("Markdown libraries did not load. Check index.html.");
    } else {
      const html = marked.parse(narrativeText, { gfm: true, breaks: true });
      const fragment = document.createElement("div");
      fragment.innerHTML = DOMPurify.sanitize(html);
      summary.appendChild(fragment);
    }
  }

  const reportRows = buildOverviewRows(Array.isArray(data.results) ? data.results : []);

  if (reportRows.length > 0) {
    const heading = document.createElement("h3");
    heading.textContent = "Overview of search results";
    summary.appendChild(heading);
    summary.appendChild(createOverviewTable(reportRows));
  }

  if (Array.isArray(data.recommendations) && data.recommendations.length > 0) {
    const recommendations = document.createElement("div");
    recommendations.className = "summary-recommendations";
    const list = document.createElement("ul");
    data.recommendations.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = safeText(item);
      list.appendChild(li);
    });
    recommendations.appendChild(list);
    summary.appendChild(recommendations);
  }
}

function getActionLabel() {
  const type = safeText(
    document.getElementById("type")?.value
  ).toLowerCase();

  if (type.includes("internship")) return "View Internship / Apply ↗";
  if (type.includes("scholarship")) return "View Scholarship ↗";
  if (type.includes("hackathon")) return "View Hackathon ↗";
  if (type.includes("job")) return "View Job / Apply ↗";

  return "View Opportunity ↗";
}

function getDeadlineStatus(result) {
  // Prefer the backend's explicit classification over frontend guesses.
  const status = safeText(result.opportunity_status || "unverified");
  const labels = {
    potentially_expired: {
      label: "Potentially expired — verify",
      className: "status-warning"
    },
    deadline_today: {
      label: "Possible deadline today",
      className: "status-warning"
    },
    deadline_soon: {
      label: "Possible deadline within 7 days",
      className: "status-upcoming"
    },
    deadline_upcoming: {
      label: "Possible upcoming deadline",
      className: "status-upcoming"
    },
    unverified: {
      label: "Deadline unverified",
      className: "status-unknown"
    }
  };

  const found = labels[status] || labels.unverified;
  return {
    ...found,
    deadline: safeText(result.deadline || ""),
    evidence: safeText(result.deadline_evidence || "")
  };
}

function getListingQuality(result) {
  const raw = safeText(result.listing_quality || "Unclassified");
  const labels = {
    "Possible direct listing": "Possible direct listing",
    "Individual-looking listing (aggregator)": "Job portal listing",
    "Job search page": "General search page",
    "Directory / listing page": "Directory — open individual listing",
    "Specific opportunity page": "Specific opportunity page",
    "Opportunity page": "Opportunity page",
    "Search / information page": "Information page",
    "Guide or learning page": "Guide / learning page",
    "Unranked fallback": "Needs manual verification"
  };
  return labels[raw] || raw;
}

function makeBadge(text, className, title = "") {
  const badge = document.createElement("span");
  badge.className = `result-badge ${className}`;
  badge.textContent = text;
  if (title) badge.title = title;
  return badge;
}

function makeResultCard(result, index, label = "RESULT") {
  const article = document.createElement("article");
  article.className = "result-card";

  const top = document.createElement("div");
  top.className = "result-top";

  const number = document.createElement("span");
  number.className = "result-num";
  number.textContent = `${label} ${String(index + 1).padStart(2, "0")}`;

  const sourceUrl = getSafeUrl(result.link);
  const source = document.createElement(sourceUrl ? "a" : "span");
  source.className = "source";
  source.textContent = safeText(
    result.source || getHostname(sourceUrl) || "Web result"
  );

  if (sourceUrl) {
    source.href = sourceUrl;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.title = "Open original source";
  }

  top.append(number, source);

  const title = document.createElement("h3");
  title.textContent = safeText(result.title || "Untitled opportunity");

  const snippet = document.createElement("p");
  snippet.className = "result-snippet";
  snippet.textContent = safeText(
    result.snippet || "No description was provided by the search engine."
  );

  const badges = document.createElement("div");
  badges.className = "opportunity-meta";

  const quality = getListingQuality(result);
  badges.append(
    makeBadge(quality, "quality-badge", "Page type is estimated from search text and URL.")
  );

  const deadline = getDeadlineStatus(result);
  badges.append(
    makeBadge(
      deadline.label,
      deadline.className,
      deadline.evidence || "Confirm the deadline on the original website."
    )
  );

  const sourceStatus = safeText(result.source_check_status || "unverified");
  const sourceLabels = {
    checked: ["Page readable; identity unverified", "status-unknown"],
    unreachable: ["Source unreachable", "status-warning"],
    invalid_url: ["Invalid source URL", "status-warning"],
    not_checked: ["Source not checked", "status-unknown"],
    unverified: ["Source unverified", "status-unknown"]
  };
  const sourceInfo = sourceLabels[sourceStatus] || sourceLabels.unverified;
  badges.append(
    makeBadge(
      sourceInfo[0],
      sourceInfo[1],
      safeText(
        result.source_check_note ||
        "Page accessibility does not verify source identity or employer affiliation."
      )
    )
  );

  const applicationStatus = safeText(result.application_status || "unknown");
  const applicationLabels = {
    open: ["Page suggests applications are open", "status-upcoming"],
    closed: ["Page suggests applications are closed", "status-warning"],
    unknown: ["Application status unknown", "status-unknown"]
  };
  const applicationInfo = applicationLabels[applicationStatus] || applicationLabels.unknown;
  badges.append(
    makeBadge(
      applicationInfo[0],
      applicationInfo[1],
      safeText(
        result.application_status_note ||
        "Based on automated page-text detection; confirm on the official source."
      )
    )
  );

  const score = Number(result.relevance_score);
  if (Number.isFinite(score)) {
    badges.append(
      makeBadge(`Relevance score: ${score}`, "score-badge",
        "Heuristic keyword score, not a probability or eligibility rating.")
    );
  }

  article.append(top, title, snippet, badges);

  if (result.source_check_note) {
    const sourceCheckDetail = document.createElement("p");
    sourceCheckDetail.className = "source-check-detail";
    const sourceCheckLabel = sourceStatus === "checked"
      ? "Source check: Readable; identity unverified. "
      : sourceStatus === "not_checked"
        ? "Source check: Not checked. "
        : sourceStatus === "unreachable"
          ? "Source check: Unreachable. "
          : "Source check: Unverified. ";
    sourceCheckDetail.textContent = sourceCheckLabel + safeText(result.source_check_note);
    article.append(sourceCheckDetail);
  }

  if (deadline.deadline || deadline.evidence) {
    const dateLine = document.createElement("p");
    dateLine.className = "deadline-detail";
    const dateText = deadline.deadline
      ? `Detected deadline date: ${deadline.deadline}. `
      : "No exact deadline date detected. ";
    dateLine.textContent =
      dateText +
      safeText(deadline.evidence || "Confirm the date on the original source.");
    article.append(dateLine);
  }

  if (result.relevance_note) {
    const note = document.createElement("p");
    note.className = "result-note";
    note.textContent = safeText(result.relevance_note);
    article.append(note);
  }

  if (sourceUrl) {
    const link = document.createElement("a");
    link.className = "opportunity-link";
    link.href = sourceUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = getActionLabel();
    article.append(link);
  } else {
    const unavailable = document.createElement("p");
    unavailable.className = "muted";
    unavailable.textContent = "Original link unavailable.";
    article.append(unavailable);
  }

  return article;
}

function setError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function setLoading(loading) {
  button.disabled = loading;
  button.textContent = loading
    ? "◌ Searching live web…"
    : "⌕ Discover opportunities →";
}

if (!form || !button || !output || !errorBox || !summary || !resultsList || !count) {
  console.error(
    "Opportunity Radar AI: one or more required HTML elements are missing. " +
    "Expected #search-form, #submit-btn, #output, #error, #summary, #results-list, #result-count."
  );
} else {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    errorBox.textContent = "";
    errorBox.classList.add("hidden");
    output.classList.add("hidden");
    setLoading(true);

    try {
      const topic = document.getElementById("topic")?.value.trim() || "";
      const type = document.getElementById("type")?.value || "Hackathons";
      const location = document.getElementById("location")?.value.trim() || "India";
      const level = document.getElementById("level")?.value || "Undergraduate";

      if (topic.length < 2) {
        throw new Error("Enter a topic with at least 2 characters.");
      }

      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          opportunity_type: type,
          location,
          student_level: level
        })
      });

      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error("The server returned an invalid response.");
      }

      if (!response.ok) {
        throw new Error(data.detail || "Search failed. Please try again.");
      }

      displaySummary(data);

      const results = Array.isArray(data.results) ? data.results : [];
      count.textContent = `${results.length} live results`;

      resultsList.replaceChildren();
      if (data.search_message) {
        const message = document.createElement("p");
        message.className = "search-status-note";
        message.textContent = safeText(data.search_message);
        resultsList.append(message);
      }

      if (results.length === 0) {
        if (!data.search_message) {
          const empty = document.createElement("p");
          empty.className = "muted";
          empty.textContent =
            "No strong matches were found. Try a broader topic or another opportunity type.";
          resultsList.append(empty);
        }
      } else {
        resultsList.append(...results.map((result, index) => makeResultCard(result, index)));
      }

      const secondaryResults = Array.isArray(data.secondary_results)
        ? data.secondary_results
        : [];
      if (secondaryResults.length > 0) {
        const selectedType = safeText(
          document.getElementById("type")?.value
        ).toLowerCase();
        const isScholarshipSearch = selectedType.includes("scholarship");
        const hasAdjacentTopicLead = secondaryResults.some(
          (result) => result?.topic_relevance_tier === "secondary"
        );
        const secondaryHeading = document.createElement("h3");
        secondaryHeading.className = "secondary-results-heading";
        secondaryHeading.textContent = hasAdjacentTopicLead
          ? "Adjacent-topic leads — secondary"
          : isScholarshipSearch
            ? "Third-party scholarship leads — secondary"
            : "Directories and job-portal leads — secondary";
        const secondaryNote = document.createElement("p");
        secondaryNote.className = "muted secondary-results-note";
        secondaryNote.textContent = hasAdjacentTopicLead
          ? "These results match a broad search term but not the requested specialist domain. Review them as leads only; source readability, authenticity, and application status are separate and may be unverified."
          : isScholarshipSearch
            ? "These third-party leads do not verify scholarship details, application status, or deadlines. Confirm them on an official government, ministry, National Scholarship Portal, or university source."
            : "These are not confirmed individual vacancies. Check the employer’s official careers page before applying.";
        resultsList.append(
          secondaryHeading,
          secondaryNote,
          ...secondaryResults.map((result, index) =>
            makeResultCard(result, index, "SECONDARY")
          )
        );
      }

      output.classList.remove("hidden");
      output.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      setError(error.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  });
}

// Small styling additions; existing styles remain in control of the dashboard.
(function addResultBadgeStyles() {
  if (document.getElementById("opportunity-radar-badge-styles")) return;

  const style = document.createElement("style");
  style.id = "opportunity-radar-badge-styles";
  style.textContent = `
    .opportunity-meta {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 7px;
      margin: 12px 0;
    }
    .result-badge {
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      padding: 5px 9px;
      border: 1px solid var(--border-color, #334155);
      border-radius: 8px;
      font-size: 11px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }
    .quality-badge { color: var(--text-color, #dce8f5); }
    .status-warning { border-color: #a85a48; color: #ffc3b6; }
    .status-upcoming { border-color: #8b7b3b; color: #ffe49a; }
    .status-unknown { color: #b8c5d5; }
    .score-badge { color: #66f2d3; }
    .deadline-detail, .result-note {
      font-size: 12px;
      opacity: .85;
      overflow-wrap: anywhere;
    }
    .report-source-link { color: inherit; text-decoration: underline; }
    .opportunity-link { display: inline-block; margin-top: 8px; }
  `;
  document.head.append(style);
})();
