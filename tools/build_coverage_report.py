"""Build the offline roster coverage matrix without changing any source data.

Run from the project root with ``py tools/build_coverage_report.py``. Optional
``--prettier PATH`` formats the generated HTML using an existing installation.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clashlab.catalog import Catalog
from clashlab.common import read_json, write_json
from clashlab.engine_coverage import build_engine_coverage


HTML = r"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Clash Lab · Engine coverage</title>
    <style>
      :root {
        color-scheme: light;
        --ink: #17283c;
        --muted: #58677a;
        --paper: #f4f6f8;
        --line: #dce2e8;
        --blue: #2449a5;
        --blue-pale: #e9efff;
        --amber: #88551a;
        --amber-pale: #fff3df;
      }
      * {
        box-sizing: border-box;
      }
      body {
        margin: 0;
        color: var(--ink);
        background: var(--paper);
        font:
          15px/1.6 system-ui,
          -apple-system,
          BlinkMacSystemFont,
          "Segoe UI",
          sans-serif;
      }
      button,
      input,
      select {
        font: inherit;
      }
      button,
      select,
      summary {
        cursor: pointer;
      }
      a {
        color: var(--blue);
      }
      a:hover {
        text-decoration-thickness: 2px;
      }
      button:focus-visible,
      input:focus-visible,
      select:focus-visible,
      summary:focus-visible,
      a:focus-visible {
        outline: 3px solid #8faafb;
        outline-offset: 3px;
      }
      .shell {
        width: min(1480px, calc(100% - 64px));
        margin: 0 auto;
      }
      header {
        background: var(--ink);
        color: #fff;
        padding: 40px 0 44px;
      }
      .eyebrow {
        margin: 0 0 9px;
        color: #adbfda;
        font-size: 12px;
        font-weight: 750;
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }
      h1 {
        margin: 0 0 10px;
        font-size: clamp(32px, 5vw, 50px);
        line-height: 1.12;
        letter-spacing: -0.03em;
      }
      header .lead {
        color: #d5dfeb;
        max-width: 850px;
        margin: 0;
        font-size: 17px;
      }
      nav {
        margin-top: 22px;
        display: flex;
        flex-wrap: wrap;
        gap: 18px;
      }
      nav a {
        color: #e1eaff;
        font-size: 14px;
      }
      main {
        padding: 28px 0 60px;
      }
      section {
        scroll-margin-top: 18px;
        margin-bottom: 30px;
      }
      h2 {
        font-size: 25px;
        line-height: 1.25;
        letter-spacing: -0.025em;
        margin: 0 0 8px;
      }
      h3 {
        font-size: 17px;
        margin: 0 0 8px;
        line-height: 1.4;
      }
      p {
        margin: 0 0 12px;
      }
      .muted {
        color: var(--muted);
      }
      .small {
        font-size: 13px;
      }
      .notice {
        border-left: 4px solid #bf852f;
        background: var(--amber-pale);
        padding: 18px 22px;
        margin-bottom: 22px;
        border-radius: 0 8px 8px 0;
      }
      .notice strong {
        display: block;
        margin-bottom: 4px;
      }
      .notice p {
        margin: 0;
      }
      .metrics {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
        margin-bottom: 26px;
      }
      .metric,
      .panel {
        border: 1px solid var(--line);
        border-radius: 10px;
        background: #fff;
      }
      .metric {
        padding: 18px 20px;
      }
      .metric .value {
        font-weight: 770;
        font-size: 31px;
        line-height: 1.2;
      }
      .metric .label {
        color: var(--muted);
        font-size: 13px;
        margin-top: 6px;
      }
      .panel {
        padding: 24px;
      }
      .table-wrap {
        overflow-x: auto;
        border: 1px solid var(--line);
        border-radius: 8px;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        background: #fff;
        text-align: left;
      }
      th {
        color: var(--muted);
        background: #f7f9fc;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      th,
      td {
        padding: 12px 14px;
        border-bottom: 1px solid var(--line);
        vertical-align: top;
      }
      tbody tr:last-child td {
        border-bottom: 0;
      }
      tbody tr:hover {
        background: #fafcff;
      }
      .number {
        text-align: right;
        font-variant-numeric: tabular-nums;
      }
      .filters {
        display: grid;
        grid-template-columns: 1.4fr 1.3fr 1fr 1fr 1fr;
        gap: 12px;
        margin-top: 18px;
      }
      label {
        display: grid;
        gap: 5px;
        font-size: 12px;
        font-weight: 680;
        color: var(--muted);
      }
      input,
      select {
        width: 100%;
        min-width: 0;
        padding: 10px 11px;
        color: var(--ink);
        background: #fff;
        border: 1px solid #bbc7d4;
        border-radius: 6px;
        font-size: 14px;
      }
      .matrix-toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin: 14px 0;
      }
      button {
        border: 1px solid #b6c5db;
        border-radius: 6px;
        background: #fff;
        color: var(--blue);
        padding: 7px 12px;
        font-size: 13px;
        font-weight: 650;
      }
      button:hover {
        background: var(--blue-pale);
      }
      #matrix {
        min-width: 1030px;
        table-layout: fixed;
      }
      #matrix .entity-col {
        width: 19%;
      }
      #matrix .cap-col {
        width: 6%;
      }
      #matrix .behavior-col {
        width: 43%;
      }
      #matrix .evidence-col {
        width: 20%;
      }
      .entity-name {
        display: block;
        font-weight: 740;
      }
      .entity-id {
        display: block;
        color: var(--muted);
        font:
          11px/1.5 ui-monospace,
          Consolas,
          monospace;
        overflow-wrap: anywhere;
        margin-top: 3px;
      }
      .badge {
        display: inline-block;
        border-radius: 5px;
        padding: 3px 7px;
        font-size: 11px;
        font-weight: 720;
        line-height: 1.45;
        margin: 0 5px 6px 0;
      }
      .conditional_mechanics {
        color: #2449a5;
        background: #e9efff;
      }
      .passive_target_only {
        color: #5b527c;
        background: #efedf7;
      }
      .missing_behavior {
        color: #8a4a16;
        background: #fff0e2;
      }
      .not_battle_actor {
        color: #5d6772;
        background: #edf0f3;
      }
      .category-badge {
        color: #526176;
        background: #edf1f7;
      }
      details {
        margin-top: 10px;
      }
      details summary {
        color: var(--blue);
        font-size: 13px;
      }
      details ul {
        padding-left: 20px;
        margin: 8px 0;
      }
      details li {
        margin-bottom: 7px;
        font-size: 13px;
      }
      .detail-label {
        display: block;
        font-weight: 740;
        margin-top: 13px;
        font-size: 13px;
      }
      .caps {
        font-variant-numeric: tabular-nums;
        font-weight: 700;
      }
      .subtle-list {
        padding-left: 19px;
        color: var(--muted);
        font-size: 13px;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 14px;
      }
      .priority {
        padding: 19px;
      }
      .priority-number {
        color: var(--blue);
        font-size: 12px;
        font-weight: 760;
        letter-spacing: 0.08em;
        margin-bottom: 8px;
      }
      .priority p,
      .archetype p {
        font-size: 13px;
        color: var(--muted);
      }
      .archetype {
        padding: 19px;
      }
      .archetype .count {
        color: var(--blue);
        font-weight: 740;
      }
      .archetype .entity-list {
        font-size: 12px;
        color: var(--muted);
        margin: 10px 0;
      }
      .archetype button {
        margin-top: 7px;
      }
      .source-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 22px;
      }
      code {
        font-family: ui-monospace, Consolas, monospace;
        font-size: 12px;
        overflow-wrap: anywhere;
      }
      footer {
        padding-top: 15px;
        border-top: 1px solid var(--line);
        color: var(--muted);
        font-size: 12px;
      }
      #empty {
        padding: 26px;
        text-align: center;
        color: var(--muted);
      }
      @media (max-width: 1100px) {
        .filters {
          grid-template-columns: repeat(3, 1fr);
        }
        .grid {
          grid-template-columns: repeat(2, 1fr);
        }
      }
      @media (max-width: 700px) {
        .shell {
          width: calc(100% - 28px);
        }
        header {
          padding: 30px 0;
        }
        .metrics {
          grid-template-columns: repeat(2, 1fr);
        }
        .filters,
        .grid,
        .source-grid {
          grid-template-columns: 1fr;
        }
        .panel {
          padding: 17px;
        }
        .metric {
          padding: 16px;
        }
      }
      @media print {
        body {
          background: #fff;
          font-size: 11px;
        }
        header {
          background: #fff;
          color: #17283c;
          padding: 20px 0;
        }
        header .lead,
        .eyebrow {
          color: #58677a;
        }
        .shell {
          width: 100%;
        }
        nav,
        .filters,
        button {
          display: none;
        }
        .table-wrap {
          overflow: visible;
        }
        .grid {
          grid-template-columns: repeat(2, 1fr);
        }
        #matrix {
          min-width: 0;
        }
        th,
        td {
          padding: 7px;
        }
        .panel,
        .metric {
          break-inside: avoid;
        }
      }
    </style>
  </head>
  <body>
    <header>
      <div class="shell">
        <p class="eyebrow">Clash Lab / local evidence audit</p>
        <h1>Whole-roster engine coverage</h1>
        <p class="lead">
          Every home-village catalog entity, TH16 attack eligibility, TH18
          donation candidates and TH17–18 opponents. This view is independent of
          any current loadout.
        </p>
        <nav aria-label="Report sections">
          <a href="#coverage">Category counts</a>
          <a href="#matrix-section">Entity matrix</a>
          <a href="#archetypes">Attack families</a>
          <a href="#blockers">Next systems</a>
          <a href="#sources">Evidence</a>
          <a href="bound-battle/index.html">Connected battle benchmark</a>
          <a href="engine-coverage.json" download>Download JSON</a>
        </nav>
      </div>
    </header>
    <main class="shell">
      <div class="notice">
        <strong>Full-village prediction remains unvalidated and incomplete.</strong>
        <p>
          Conditional mechanics can run controlled combat experiments. No entity
          has been certified against held-out replays, and a passive structure
          supplies only a damageable footprint and HP. The counts below measure
          coverage, not completion percentages or army strength.
        </p>
      </div>
      <div class="metrics" id="metrics" aria-label="Coverage counts"></div>
      <section id="coverage" class="panel">
        <h2>Coverage by category</h2>
        <p class="muted small">
          One count per catalog entity. Weapon modes, Town Hall levels and
          supercharge restrictions appear in the matrix details. All categories
          still require integrated battle validation.
        </p>
        <div class="table-wrap">
          <table id="categories">
            <thead>
              <tr>
                <th>Category</th>
                <th class="number">Catalog</th>
                <th class="number">Conditional</th>
                <th class="number">Passive only</th>
                <th class="number">Missing</th>
                <th class="number">Noncombat</th>
                <th class="number">TH16 attack</th>
                <th class="number">TH16 conditional</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>
      <section id="matrix-section" class="panel">
        <h2>Entity matrix</h2>
        <p class="muted small">
          Level ceilings use the pinned catalog and its secondary caps. “—”
          means no available ordinary level in that mapping; crafted modules and
          unverified unlocks need their own configuration. Donation candidates
          still require the receiver’s actual rules and confirmed account caps.
        </p>
        <div class="filters">
          <label
            >Search<input
              id="search"
              type="search"
              placeholder="Name, ID or missing behavior…"
          /></label>
          <label
            >Roster view<select id="role">
              <option value="all">All catalog entities</option>
              <option value="th16">TH16 attack eligibility</option>
              <option value="donation">TH18 donation candidates</option>
              <option value="opponent16">TH16 defending options</option>
              <option value="opponent17">TH17 defending options</option>
              <option value="opponent18">TH18 defending options</option>
            </select></label
          >
          <label
            >Category<select id="category">
              <option value="all">All categories</option>
            </select></label
          >
          <label
            >Behavior<select id="behavior">
              <option value="all">All behavior states</option>
            </select></label
          >
          <label
            >Attack family<select id="archetype">
              <option value="all">All families</option>
            </select></label
          >
        </div>
        <div class="matrix-toolbar">
          <span
            id="result-count"
            class="small muted"
            role="status"
            aria-live="polite"
          ></span
          ><button id="reset" type="button">Reset filters</button>
        </div>
        <div class="table-wrap">
          <table id="matrix">
            <colgroup>
              <col class="entity-col" />
              <col class="cap-col" />
              <col class="cap-col" />
              <col class="cap-col" />
              <col class="behavior-col" />
              <col class="evidence-col" />
            </colgroup>
            <thead>
              <tr>
                <th>Entity</th>
                <th class="number">TH16</th>
                <th class="number">TH17</th>
                <th class="number">TH18</th>
                <th>Behavior and remaining work</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
          <div id="empty" hidden>No entities match these filters.</div>
        </div>
      </section>
      <section id="archetypes">
        <h2>Coverage across attack families</h2>
        <p class="muted small">
          These are coverage families, not recommended armies. Each combines
          several possible alternatives; all also depend on a complete defending
          village.
        </p>
        <div class="grid" id="archetype-cards"></div>
      </section>
      <section id="blockers">
        <h2>The path to complete battles</h2>
        <p class="muted small">
          Implementation priorities follow shared dependencies. They do not
          assign arbitrary completion scores.
        </p>
        <div class="grid" id="priority-cards"></div>
      </section>
      <section id="sources" class="panel">
        <h2>Source evidence and unresolved content</h2>
        <div class="source-grid">
          <div id="source-summary"></div>
          <div>
            <h3>How to read this report</h3>
            <ul id="limitations" class="subtle-list"></ul>
          </div>
        </div>
        <details>
          <summary id="supplemental-heading">Extraction-only records</summary>
          <p class="muted small">
            These entries do not enter the TH16 legal-roster or donation counts.
            Seasonal flags and numeric records cannot establish current
            availability.
          </p>
          <div class="table-wrap">
            <table id="supplemental">
              <thead>
                <tr>
                  <th>Record</th>
                  <th>Group</th>
                  <th>Source flag</th>
                  <th>Availability</th>
                </tr>
              </thead>
              <tbody></tbody>
            </table>
          </div>
        </details>
        <details>
          <summary>
            Announced content still missing a verified numeric or availability
            mapping
          </summary>
          <div id="announcements"></div>
        </details>
      </section>
      <footer id="footer"></footer>
    </main>
    <script id="coverage-data" type="application/json">
      __REPORT_DATA__
    </script>
    <script>
      "use strict";
      const report = JSON.parse(
        document.getElementById("coverage-data").textContent,
      );
      const byId = new Map(report.entities.map((row) => [row.id, row]));
      const filters = Object.fromEntries(
        ["search", "role", "category", "behavior", "archetype"].map((id) => [
          id,
          document.getElementById(id),
        ]),
      );

      function node(tag, text, className) {
        const result = document.createElement(tag);
        if (text !== undefined && text !== null)
          result.textContent = String(text);
        if (className) result.className = className;
        return result;
      }

      function list(parent, values) {
        const output = node("ul");
        values.forEach((value) => output.append(node("li", value)));
        parent.append(output);
      }

      function link(text, url) {
        const output = node("a", text);
        output.href = url;
        output.target = "_blank";
        output.rel = "noopener noreferrer";
        return output;
      }

      function displayNames(ids) {
        return ids.map((id) => byId.get(id)?.name || id).join(", ");
      }

      function badge(text, className) {
        return node("span", text, "badge " + className);
      }

      function option(select, value, label) {
        const output = node("option", label);
        output.value = value;
        select.append(output);
      }

      function addDetails(cell, row) {
        const details = node("details");
        details.append(
          node("summary", "Inspect behavior, eligibility and variants"),
        );
        const shown = displayedBehavior(row);
        list(details, shown.remaining || row.behavior.remaining);
        if (row.behavior.defending_role) {
          details.append(
            node(
              "p",
              "Defending role: " + row.behavior.defending_role.implemented,
              "small",
            ),
          );
        }
        row.additional_availability_requirements.forEach((value) =>
          details.append(node("p", value, "small")),
        );
        if (row.th18_donation.candidate) {
          const donation = row.th18_donation;
          details.append(
            node("span", "TH18 donation candidate", "detail-label"),
          );
          details.append(
            node(
              "p",
              `Donor catalog ceiling: ${donation.donor_catalog_max_level}. Known receiver-lab mapping ceiling: ${donation.max_level_under_known_catalog_lab_cap ?? "unresolved"}. Maximum catalog TH16 castle: level ${donation.receiver_max_catalog_castle_level}; lab cap ${donation.receiver_catalog_lab_level_cap}.`,
              "small",
            ),
          );
          details.append(node("p", donation.note, "small muted"));
        }
        if (row.mode_variants.length) {
          details.append(node("span", "Weapon modes", "detail-label"));
          list(
            details,
            row.mode_variants.map(
              (mode) =>
                `${mode.id}: ${mode.conditional_weapon_registered ? "conditional " + mode.pattern + " weapon registered" : "no weapon mode registered"}; available from level ${mode.available_from_level}.`,
            ),
          );
        }
        if (row.town_hall_variants.length) {
          details.append(
            node("span", "Every catalog Town Hall level", "detail-label"),
          );
          list(
            details,
            row.town_hall_variants.map(
              (variant) =>
                `TH${variant.level}${variant.weapon ? " · " + variant.weapon : ""}: ${variant.detail}`,
            ),
          );
        }
        if (row.crafted_phase !== undefined && row.crafted_phase !== null) {
          details.append(
            node(
              "p",
              `Crafting phase: ${row.crafted_phase}. Current in this snapshot: ${String(row.crafted_current_in_snapshot)}. Modules have independent upgrades; there is no single ordinary level cap.`,
              "small",
            ),
          );
        }
        if (Object.keys(row.placement_counts).length) {
          details.append(
            node("span", "Catalog placement counts", "detail-label"),
          );
          list(
            details,
            Object.entries(row.placement_counts).map(
              ([th, counts]) =>
                `TH${th}: ${counts.count}${counts.countAfterMerges === undefined ? "" : "; after merges: " + counts.countAfterMerges}.`,
            ),
          );
        }
        details.append(
          node(
            "p",
            `Supercharge: ${row.behavior.supercharge_behavior.replaceAll("_", " ")}.`,
            "small muted",
          ),
        );
        if (row.level_cap_errors.length) list(details, row.level_cap_errors);
        cell.append(details);
      }

      function evidenceCell(row) {
        const cell = node("td");
        cell.append(link("Catalog source", row.sources.catalog));
        const matched = row.sources.extracted_match !== "unmapped";
        cell.append(
          node(
            "p",
            matched
              ? row.sources.extracted_match.replaceAll("_", " ")
              : "No exact extraction match",
            "small muted",
          ),
        );
        if (matched)
          cell.append(
            link("Extraction source", report.source_evidence.extraction.url),
          );
        if (row.sources.extracted_match === "unique_exact_name_evidence_only")
          cell.append(
            node(
              "p",
              "Name evidence only; direct numeric fields have not been compared.",
              "small muted",
            ),
          );
        if (row.sources.unmapped_exact_name_candidates.length)
          cell.append(
            node(
              "p",
              "Name candidates exist; an exact numeric identity needs reconciliation.",
              "small muted",
            ),
          );
        const differences = row.sources.direct_statistic_differences;
        if (differences.length) {
          const details = node("details");
          details.append(
            node(
              "summary",
              `${differences.length} direct statistic differences`,
            ),
          );
          list(
            details,
            differences.map(
              (difference) =>
                `${difference.level === null ? "Entity" : "Level " + difference.level} ${difference.field}: catalog ${difference.catalog_value}; extraction ${difference.extracted_value}.`,
            ),
          );
          cell.append(details);
        }
        if (row.sources.declared_extracted_branch_fields.length) {
          cell.append(
            node(
              "p",
              `${row.sources.declared_extracted_branch_fields.length} selected branch fields; report applies none.`,
              "small muted",
            ),
          );
        }
        return cell;
      }

      function displayedBehavior(row) {
        if (filters.role.value.startsWith("opponent"))
          return row.opponent_behavior_by_town_hall[
            filters.role.value.slice(8)
          ];
        return row.behavior;
      }

      function matches(row) {
        if (filters.role.value === "th16" && !row.th16_attack_eligible)
          return false;
        if (filters.role.value === "donation" && !row.th18_donation.candidate)
          return false;
        if (filters.role.value.startsWith("opponent")) {
          const status =
            row.opponent_status_by_town_hall[filters.role.value.slice(8)];
          if (
            ![
              "catalog_available",
              "available_defending_conditional_mechanics",
              "garrison_donor_candidate_conditional_mechanics",
              "available_defending_banner_metadata",
              "available_defending_behavior_missing",
              "module_configuration_unverified",
              "availability_unverified",
            ].includes(status)
          )
            return false;
        }
        if (
          filters.category.value !== "all" &&
          row.category !== filters.category.value
        )
          return false;
        if (
          filters.behavior.value !== "all" &&
          displayedBehavior(row).status !== filters.behavior.value
        )
          return false;
        if (
          filters.archetype.value !== "all" &&
          !row.archetypes.includes(filters.archetype.value)
        )
          return false;
        const query = filters.search.value.trim().toLowerCase();
        const searchable = [
          row.name,
          row.id,
          row.category,
          row.behavior.implemented,
          displayedBehavior(row).implemented,
          ...row.behavior.remaining,
        ]
          .join(" ")
          .toLowerCase();
        return !query || searchable.includes(query);
      }

      function renderMatrix() {
        const selected = report.entities.filter(matches);
        const body = document.querySelector("#matrix tbody");
        body.replaceChildren();
        const fragment = document.createDocumentFragment();
        selected.forEach((row) => {
          const tr = node("tr");
          const identity = node("td");
          identity.append(node("span", row.name, "entity-name"));
          identity.append(node("code", row.id, "entity-id"));
          identity.append(badge(row.category, "category-badge"));
          tr.append(identity);
          ["16", "17", "18"].forEach((th) =>
            tr.append(
              node("td", row.max_level_by_town_hall[th] ?? "—", "number caps"),
            ),
          );
          const behavior = node("td");
          const shown = displayedBehavior(row);
          behavior.append(badge(shown.label, shown.status));
          behavior.append(node("p", shown.implemented, "small"));
          addDetails(behavior, row);
          tr.append(behavior, evidenceCell(row));
          fragment.append(tr);
        });
        body.append(fragment);
        document.getElementById("empty").hidden = selected.length !== 0;
        document.getElementById("result-count").textContent =
          `${selected.length} of ${report.entities.length} catalog entities shown · 0 replay-calibrated · 0 complete-battle certified`;
      }

      function renderSummary() {
        const metrics = [
          [report.summary.catalog_entities, "Catalog entities inspected"],
          [
            report.summary.th16_attack_eligible,
            "TH16 attack-eligible catalog options",
          ],
          [
            report.summary.th16_attack_with_conditional_mechanics,
            "TH16 options with conditional mechanics",
          ],
          [
            report.summary.th18_donation_candidates,
            "TH18 donor candidates · receipt unconfirmed",
          ],
        ];
        const container = document.getElementById("metrics");
        metrics.forEach(([value, label]) => {
          const card = node("div", null, "metric");
          card.append(node("div", value, "value"), node("div", label, "label"));
          container.append(card);
        });
        const body = document.querySelector("#categories tbody");
        Object.entries(report.by_category).forEach(([category, values]) => {
          const row = node("tr");
          row.append(node("td", category));
          [
            "catalog_entities",
            "conditional_mechanics",
            "passive_target_only",
            "missing_behavior",
            "not_battle_actor",
            "th16_attack_eligible",
            "th16_attack_with_conditional_mechanics",
          ].forEach((field) => row.append(node("td", values[field], "number")));
          body.append(row);
        });
      }

      function renderFamilies() {
        const container = document.getElementById("archetype-cards");
        report.archetypes.forEach((family) => {
          const card = node("article", null, "panel archetype");
          card.append(node("h3", family.name));
          card.append(
            node(
              "p",
              `${family.conditional_entities.length} conditional options · ${family.missing_entities.length} options missing behavior`,
              "count",
            ),
          );
          card.append(node("p", family.behavior_dependencies.join(" · ")));
          card.append(
            node(
              "div",
              "Remaining: " + displayNames(family.missing_entities),
              "entity-list",
            ),
          );
          const button = node("button", "Show this family in the matrix");
          button.type = "button";
          button.addEventListener("click", () => {
            resetFilters(false);
            filters.archetype.value = family.id;
            renderMatrix();
            document
              .getElementById("matrix-section")
              .scrollIntoView({ behavior: "smooth" });
          });
          card.append(button);
          container.append(card);
        });
        const priorities = document.getElementById("priority-cards");
        report.prioritized_blockers.forEach((blocker) => {
          const card = node("article", null, "panel priority");
          card.append(
            node(
              "div",
              "DEPENDENCY " + String(blocker.priority).padStart(2, "0"),
              "priority-number",
            ),
          );
          card.append(node("h3", blocker.title), node("p", blocker.why));
          if (blocker.remaining_entities.length)
            card.append(
              node("p", displayNames(blocker.remaining_entities), "small"),
            );
          priorities.append(card);
        });
      }

      function renderSources() {
        const evidence = report.source_evidence;
        const summary = document.getElementById("source-summary");
        summary.append(node("h3", "Pinned source ledger"));
        summary.append(
          node("p", "Catalog snapshot", "small muted"),
          node("code", report.catalog_snapshot),
        );
        summary.append(
          node("p", "Independent extraction", "small muted"),
          node("code", evidence.extraction.commit),
        );
        summary.append(
          node(
            "p",
            `${evidence.mapped_statistic_comparisons} directly mapped comparisons; ${evidence.direct_statistic_differences} disagreements. ${evidence.declared_extracted_branch_selection.length} fields have an opt-in branch selection. This report changes no statistics.`,
            "small",
          ),
        );
        summary.append(node("p", evidence.comparison_scope, "small muted"));
        summary.append(
          node("p", "Rebuild: py tools/build_coverage_report.py", "small"),
        );
        summary.append(
          node(
            "p",
            "The report fingerprints the inspected Python sources so later changes can be audited by rebuilding it.",
            "small muted",
          ),
        );
        const limitations = document.getElementById("limitations");
        report.limitations.forEach((value) =>
          limitations.append(node("li", value)),
        );
        document.getElementById("supplemental-heading").textContent =
          `${report.extracted_only_records.length} extraction-only records · availability unverified`;
        const body = document.querySelector("#supplemental tbody");
        report.extracted_only_records.forEach((record) => {
          const row = node("tr");
          const availability = record.catalog_exact_name_ids.length
            ? "Separate source variant shares a catalog name; availability unverified: " +
              record.catalog_exact_name_ids.join(", ")
            : "Unverified; excluded from legal-roster counts";
          [
            record.name + " (" + record.data_id + ")",
            record.group,
            record.seasonal_in_source ? "Seasonal" : "No seasonal flag",
            availability,
          ].forEach((value) => row.append(node("td", value)));
          body.append(row);
        });
        const announcements = document.getElementById("announcements");
        (report.unresolved_announced_content.items || []).forEach((item) => {
          announcements.append(node("h3", item.id));
          announcements.append(
            node("p", item.status.replaceAll("_", " "), "small"),
          );
          list(announcements, item.unknown || []);
        });
        if (report.unresolved_announced_content.source)
          announcements.append(
            link(
              "Recorded announcement source",
              report.unresolved_announced_content.source,
            ),
          );
        document.getElementById("footer").textContent =
          `Report ${report.report_fingerprint} · Adapter ${report.adapter_version} · Offline audit; no game interaction or publishing.`;
      }

      function resetFilters(render = true) {
        Object.entries(filters).forEach(([name, control]) => {
          control.value = name === "search" ? "" : "all";
        });
        if (render) renderMatrix();
      }

      Object.keys(report.by_category).forEach((category) =>
        option(filters.category, category, category),
      );
      Object.entries(report.status_definitions).forEach(([value, label]) =>
        option(filters.behavior, value, label),
      );
      report.archetypes.forEach((family) =>
        option(filters.archetype, family.id, family.name),
      );
      Object.values(filters).forEach((control) =>
        control.addEventListener("input", renderMatrix),
      );
      document
        .getElementById("reset")
        .addEventListener("click", () => resetFilters());
      renderSummary();
      renderFamilies();
      renderSources();
      renderMatrix();
    </script>
  </body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--prettier", type=Path)
    args = parser.parse_args()
    code_files = {
        path.relative_to(ROOT).as_posix(): path.read_bytes()
        for path in sorted((ROOT / "src/clashlab").glob("*.py"))
    }
    code_files["tools/build_coverage_report.py"] = Path(__file__).read_bytes()
    report = build_engine_coverage(
        Catalog.load(ROOT / "data"),
        read_json(ROOT / "data/clashking-static-data.json"),
        read_json(ROOT / "data/clashking-static-source.json"),
        read_json(ROOT / "data/extracted-stat-selection.json"),
        read_json(ROOT / "data/unresolved-content.json"),
        code_files,
    )
    output_dir = args.output_dir.resolve()
    json_path = output_dir / "engine-coverage.json"
    html_path = output_dir / "engine-coverage.html"
    write_json(json_path, report)
    embedded = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    html_path.write_text(HTML.replace("__REPORT_DATA__", embedded), encoding="utf-8")
    if args.prettier:
        subprocess.run(
            ["node", str(args.prettier.resolve()), "--write", str(html_path)],
            check=True,
        )
    print(
        json.dumps(
            {
                "json": str(json_path),
                "html": str(html_path),
                "summary": report["summary"],
                "fingerprint": report["report_fingerprint"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
