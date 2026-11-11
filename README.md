# DealerOS Reconciliation Tool

A full-stack application to reconcile data between two financial systems (System A and System B) that record the same events but have discrepancies. Shows disagreements in a filterable, sortable table and provides a complete all-records view for both source systems.

## Stack

- **Backend:** Django 6.1.3 + Django REST Framework (Python 3.12)
- **Frontend:** React 19 + Vite
- **Database:** SQLite (development)
- **Data:** 3 CSV files (locations, system_a, system_b) - 120 rows each

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- npm or yarn

### Backend Setup

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Load data and detect disagreements
python manage.py load_csv_data
python manage.py detect_disagreements

# Start server (port 8000)
python manage.py runserver
```

### Frontend Setup

```bash
cd Frontend/DealerOS
npm install
npm run dev  # Starts on port 5173
```

### Verify

- Backend API: http://localhost:8000/api/disagreements/
- All records API: http://localhost:8000/api/records/
- Frontend: http://localhost:5173

The frontend expects the backend to be running on port 8000. Start the backend
first, then start Vite in a second terminal.

### Verification commands

```bash
# Backend
cd Backend
.venv/bin/python manage.py check
.venv/bin/python manage.py test

# Frontend
cd Frontend/DealerOS
npm run build
npm run lint
```

---

## What Was Built

### Backend

1. **Data Models** (`reconciliation/models.py`)
   - `Organization` - Tenant/org boundary (ORG-A, ORG-B)
   - `Location` - 5 locations, each belongs to one org
   - `SystemARecord` - 120 clean records from system_a.csv
   - `SystemBEntry` - 121 entries from system_b.csv (with dirty data handling)
   - `Disagreement` - 4 reason types with both systems' values and location/org context

2. **CSV Importer** (`reconciliation/management/commands/load_csv_data.py`)
   - Robust parsing with error tracking (no silent drops)
   - Handles: case variations, whitespace, missing prefixes, Indian number formatting (`1,25,400.00`), empty values
   - Stores parse errors per row for audit

3. **Matcher Service** (`reconciliation/services/matcher.py`)
   - Fuzzy matches System B `record_ref` → System A `record_id`
   - Normalizes: `rec1034`→`REC-1034`, `REC - 1070`→`REC-1070`, `1112`→`REC-1112`
   - Result: 120/121 matched, 1 orphan (REC-1999)

4. **Detector Service** (`reconciliation/services/detector.py`)
   - 4 disagreement rules with epsilon comparison (0.01):
     - **Missing in B** (2): System A record with no B entries
     - **Orphan in B** (1): B entry pointing to non-existent A record
     - **Duplicate in B** (2): Multiple B entries for same A record
     - **Value Mismatch** (7): Matched pairs with different values (>0.01)
   - Management command: `detect_disagreements`

5. **API** (`reconciliation/views.py`, `serializers.py`)
   - `GET /api/disagreements/` - Paginated, filterable (reason, org, location), sortable (system_a_value, system_b_value, created_at, reason)
   - `GET /api/disagreements/{id}/` - Detail view
   - `GET /api/disagreements/stats/` - Counts by reason
   - `GET /api/records/` - Every imported System A and System B row, including clean matches

6. **Tests** (`reconciliation/tests/test_detector.py`)
   - 18 tests covering all 4 disagreement types + epsilon logic + matcher + integration

### Frontend

1. **DisagreementsTable** (`src/components/DisagreementsTable.jsx`)
   - Columns: Reason (badge), System A Record, System B Entry, System A Value, System B Value, Location, Org, Detected At
   - Filter by reason (dropdown)
   - Sort by clicking column headers (value columns, reason, date)
   - Currency formatting, color-coded reason badges
   - Stats summary bar
   - Loading/error states

2. **RecordsTable** (`src/components/RecordsTable.jsx`)
   - Separate tabs for all System A records, all System B entries, and a combined view
   - Uses `/api/records/`, so clean records are included rather than deriving rows only from disagreements
   - Shows matched counterparts, disagreement badges, tenant/location, values, and source parse errors through the API

3. **Minimal Styling** (`src/index.css`)
   - Plain, functional CSS (no component library)
   - Responsive with horizontal scroll
   - Dark mode support

---

## What Was Deliberately NOT Built

| Feature | Reason |
|---------|--------|
| Authentication | Explicitly out of scope per brief |
| Pagination UI | Only 12 rows - show all |
| Export CSV/PDF | Not in requirements |
| Real-time updates | Not needed for this use case |
| Advanced UI/UX | "Plain and working beats pretty and broken" |
| Performance optimization | 120 rows is trivial |
| Tenant switching UI | No auth = no tenant context to switch |
| Drill-down detail modal | Table shows all key fields; detail endpoint exists for API consumers |

---

## How I Worked with the Agent

This project was built in collaboration with an AI agent (Claude Code). The agent handled:

- **Scaffolding & boilerplate:** Django app structure, model definitions, DRF serializers/views, React component structure
- **Data parsing logic:** Fuzzy matching for dirty `record_ref` values, Indian number format parsing, date parsing
- **Detection algorithms:** All 4 disagreement rules with epsilon comparison
- **Test generation:** 18 unit tests covering each rule and edge cases
- **API implementation:** Filtering, sorting, pagination with django-filter
- **Frontend component:** Table with filter/sort, currency formatting, badges

**My role:** Architecture decisions, requirement clarification, verifying outputs, fixing integration issues (JSON serialization of Decimals, duplicate entry_ids in CSV, test expectation correction), and writing documentation.

**Key learnings:** The agent excels at well-scoped, repetitive coding tasks but needs human oversight for:
- Edge case handling (e.g., Decimal JSON serialization)
- Business logic validation (e.g., confirming epsilon behavior)
- Scope management (knowing what to cut)

---

## Reflection Answers

**a. Name one thing the AI agent got wrong. How did you notice?**

The agent initially stored `Decimal` objects directly in JSON fields (`details`), which caused a `TypeError: Object of type Decimal is not JSON serializable` when bulk-creating disagreements. I noticed this when running `detect_disagreements` command - it crashed on `bulk_create`. The fix was adding a `_json_serializable()` helper that converts Decimals to strings before storage.

**b. Which part of your submission are you least confident about, and why?**

The duplicate detection logic. Currently it flags every extra entry beyond the first as a separate "duplicate_in_b" disagreement. This could be noisy for records with many duplicates (e.g., 5 entries → 4 disagreements). A grouped approach (one disagreement per record with count) might be better, but the brief says "the same record entered into System B twice" - flagging each duplicate instance is a valid interpretation.

**c. If you had a second day, what would you fix first?**

1. **Grouped duplicate reporting** - One disagreement per record with duplicate count and all entry IDs, instead of one per extra entry
2. **Add API tests** - Currently only unit tests for detector; should add integration tests for API endpoints
3. **Improve empty value handling** - REC-1050 has empty value in System B; currently flagged as value_mismatch (A=160405.85 vs B=null). Should probably be a separate "missing_value_in_b" reason or handled differently
4. **Frontend polish** - Add column resize, better mobile layout, keyboard navigation

---

## Project Structure

```
DealerOS_Assignment/
├── Backend/
│   ├── config/                 # Django settings
│   ├── reconciliation/
│   │   ├── models.py           # 5 models
│   │   ├── serializers.py      # DRF serializers
│   │   ├── views.py            # API views
│   │   ├── urls.py             # API routes
│   │   ├── services/
│   │   │   ├── matcher.py      # Fuzzy matching
│   │   │   └── detector.py     # 4 disagreement rules
│   │   ├── management/commands/
│   │   │   ├── load_csv_data.py
│   │   │   └── detect_disagreements.py
│   │   └── tests/
│   │       └── test_detector.py  # 18 tests
│   └── manage.py
├── Frontend/
│   └── DealerOS/
│       ├── src/
│       │   ├── api.js          # Axios client
│       │   ├── components/
│       │   │   └── DisagreementsTable.jsx
│       │   ├── App.jsx
│       │   ├── main.jsx
│       │   └── index.css       # Minimal styling
│       └── package.json
├── data/
│   ├── locations.csv
│   ├── system_a.csv
│   └── system_b.csv
├── Project_Context_here/
│   ├── AI_CONTEXT.md
│   ├── HUMAN_PROJECT_TRACK.md
│   └── DECISIONS.md
└── README.md
```

---

## License

MIT