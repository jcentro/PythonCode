# v1.0.0-rc1 QA Checklist

This checklist is for release-candidate stabilization. It focuses on validating
the existing end-to-end workflows without introducing new features.

## Automated Verification

- Backend tests: `.\.venv\Scripts\python -m pytest backend/tests`
- Backend lint: `.\.venv\Scripts\python -m ruff check backend`
- Frontend lint: `cd frontend && npm run lint`
- Frontend build: `cd frontend && npm run build`

Notes:

- The frontend currently does not have a configured unit/integration test
  runner in `package.json`.
- Backend `pytest` coverage exists for trades, fills, import preview/commit,
  backup restore, admin wipe, and analytics APIs.

## 1. First-Run / Empty State

- [ ] Open Settings and use `Wipe All Data`.
- [ ] Confirm the destructive warning is clear and requires typing `DELETE`.
- [ ] Confirm Dashboard welcome state appears after reload.
- [ ] Confirm the top-right `+ Add Trade` button is hidden while welcome state is visible.
- [ ] Confirm the welcome-state `Add Trade` button opens the Add Trade modal.
- [ ] Confirm the first trade can be created without selecting setup or emotion.
- [ ] Confirm setup and emotion can be created inline from the Add Trade form.
- [ ] Confirm no `NaN`, `undefined`, or blank broken values appear in KPI cards or charts.

## 2. Manual Simple Trade

- [ ] Create a simple manual trade with entry price, exit price, quantity, and rule status.
- [ ] Confirm PnL calculation matches `(exit - entry) * quantity * multiplier`.
- [ ] Confirm the trade appears on Dashboard.
- [ ] Confirm the trade appears in Trade History.
- [ ] Confirm the trade appears in Statistics for the selected range.
- [ ] Confirm exported values display consistently as human-readable date + USD.

## 3. Manual Scaled Trade

- [ ] Open Add Trade and enable `Use fills (scaling)`.
- [ ] Add multiple `BUY` and `SELL` fills.
- [ ] Confirm preview summary shows weighted avg entry, weighted avg exit, total quantity, and total PnL.
- [ ] Confirm mismatched total buy/sell quantities are rejected.
- [ ] Save the trade and confirm it appears in Trade History with correct top-level values.
- [ ] Open `View Fills` and confirm all fill rows appear in read-only mode.

## 4. Edit / Duplicate

- [ ] Edit a simple trade and confirm updates persist.
- [ ] Edit a scaled trade and confirm fills are replaced correctly.
- [ ] Duplicate a trade from Trade History.
- [ ] Confirm the Add Trade form is prefilled with duplicated values.
- [ ] Confirm the duplicated trade does not copy source/import metadata.

## 5. Inbox

- [ ] Create or import trades missing setup, emotion, or rule status.
- [ ] Confirm Inbox shows unclassified trades only.
- [ ] Classify one trade using row-level controls and save.
- [ ] Create setup inline from Inbox and confirm it becomes selectable immediately.
- [ ] Create emotion inline from Inbox and confirm it becomes selectable immediately.
- [ ] Select multiple rows and use bulk classification.
- [ ] Confirm fully classified rows disappear from Inbox after save.
- [ ] Confirm partially classified rows remain in Inbox.
- [ ] Confirm the empty state reads `Inbox is clear.` when no rows remain.

## 6. Import

- [ ] Upload a valid ThinkorSwim CSV.
- [ ] Confirm import preview renders detected trades and fill details.
- [ ] Confirm duplicates are flagged in preview.
- [ ] Confirm duplicate rows are skipped by default.
- [ ] Re-import the same CSV and confirm duplicate rows are skipped.
- [ ] Confirm Import History records the batch and duplicate counts.

## 7. Export / Backup / Restore

- [ ] Export trades to CSV from Trade History.
- [ ] Confirm setup/emotion names are exported as names, not ids.
- [ ] Download backup JSON from Settings.
- [ ] Confirm backup JSON includes `schema_version`, `exported_at`, setups, emotions, trades, and fills.
- [ ] Wipe all data.
- [ ] Restore the downloaded backup.
- [ ] Confirm trades, fills, setups, and emotions are restored.
- [ ] Confirm Dashboard and Statistics match the restored data.

## 8. Dashboard

- [ ] Switch WTD / MTD / YTD and confirm KPIs update.
- [ ] Confirm mini charts and top tables update with the selected range.
- [ ] Confirm Add Trade modal opens, submits, and closes cleanly.
- [ ] Confirm Recent Trades renders cleanly and dates are human-readable.
- [ ] Confirm Win Rates donuts update with the selected range.
- [ ] Confirm no `NaN`, `undefined`, or raw null-like values appear.

## 9. Statistics

- [ ] Confirm Weekly PnL `Recent (13W)` renders with recent buckets.
- [ ] Confirm Weekly PnL `View All (YTD)` renders correctly.
- [ ] Confirm Equity Curve `Recent (30D)` renders with recent buckets.
- [ ] Confirm Equity Curve `View All (YTD)` renders correctly.
- [ ] Confirm empty buckets render safely without broken axes or console errors.
- [ ] Confirm recent-mode drilldowns open trades modal.
- [ ] Confirm view-all drilldowns are disabled.
- [ ] Confirm setup charts render and setup drilldowns work.
- [ ] Confirm ticker chart renders and ticker drilldowns work.

## 10. Settings

- [ ] Confirm setup management still creates, edits, and lists setups correctly.
- [ ] Confirm emotion management still creates, edits, and lists emotions correctly.
- [ ] Confirm backup / restore status messages are clear.
- [ ] Confirm wipe-data warning remains strong and separate from backup controls.
- [ ] Confirm Data Quality panel renders counts correctly.
- [ ] Confirm the healthy state is clean when no issues exist.

## Manual Browser Verification Required

These flows were statically inspected and covered by lint/build/backend tests
where possible, but they still require direct browser interaction before final
release sign-off.

- [ ] First-run welcome flow:
  wipe all data, confirm the welcome card replaces normal dashboard controls,
  confirm the welcome-card `Add Trade` button opens the modal, and confirm the
  top-right `+ Add Trade` button stays hidden until the first trade is saved.
- [ ] Add Trade modal interaction:
  open/close via button, overlay, `Escape`, and successful submit; verify the
  first meaningful input receives focus and validation messages appear inline.
- [ ] Inline setup/emotion creation:
  from Add Trade and Inbox, create new setup/emotion values, confirm they are
  selected automatically, and confirm backend errors surface cleanly inline.
- [ ] Scaled trade entry/editing:
  add/remove fill rows, verify the computed preview updates live, verify
  mismatched quantities block submit, and confirm editing an existing scaled
  trade reloads the saved fills correctly.
- [ ] View Fills modal:
  open from a scaled trade, verify summary values match the trade row, and
  confirm modal close actions (`X`, overlay, `Escape`) all work.
- [ ] Inbox row and bulk triage:
  save one edited row, then bulk-update multiple rows, and verify fully
  classified rows disappear while partially classified rows remain visible.
- [ ] Import preview and duplicate detection:
  upload a CSV, verify duplicate badges/selection defaults in preview, then
  confirm final import messaging reports imported vs skipped duplicates.
- [ ] Backup / wipe / restore browser flow:
  download backup JSON, wipe all data, restore the file through the Settings
  UI, and confirm the app reloads with trades, fills, setups, and emotions
  restored.
- [ ] Statistics drilldowns:
  in recent modes, click weekly/equity/setup/ticker chart regions and confirm
  the trades modal opens; in view-all modes, confirm the same charts stay
  non-interactive.
- [ ] Draggable modal behavior:
  verify weekly and equity drilldown modals drag smoothly, snap near edges,
  persist position, and recenter on header double-click.
- [ ] Sidebar collapse / expand:
  toggle the sidebar in expanded and collapsed states, verify navigation stays
  usable, and confirm the `v1.0.0-rc1` version label renders cleanly.

## Release Readiness Notes

Mark any blocker discovered during QA with:

- page / flow
- exact steps to reproduce
- expected behavior
- actual behavior
- console/network errors if any

Suggested blocker label:

- `RC BLOCKER`
