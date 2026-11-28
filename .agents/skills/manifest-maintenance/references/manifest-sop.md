# 📖 SOP: Area Manifest System

## 📍 Purpose
Standardized meta-knowledge layer for persistent "Areas of Responsibility." Ensures humans and agents can navigate without data bloat.

---

## 🏗️ 01. Physical Architecture
Each Area MUST follow a 3-Tier directory structure under its `Reference/` folder:

1.  **`01_Core/`**:
    - **Content:** Master Truths, SOPs, and High-Authority Architectural Specs.
    - **Status:** Immune to automatic archiving.
2.  **`02_Active/`**:
    - **Content:** Recent context (modified < 30-60 days).
    - **Capacity:** Capped at 30 individual files.
3.  **`03_Archive/`**:
    - **Content:** Legacy knowledge and bulk logs.
    - **Visibility:** Grouped into "Semantic Clusters."

---

## 📜 02. The Manifest (`MANIFEST.md`)
The Area root MUST contain a `MANIFEST.md` that serves as a **Dashboard**:

### Required Sections:
- **1. Status:** High-level counts of files/projects.
- **2. Projects:** Links to related finite tasks in `03_Projects/`.
- **3. Knowledge Index:** Filtered 3-Tiered table (Core + Active + Archive Groups).
- **4. Agent Steering:** Explicit instructions for LLMs querying this folder.

---

## 🤖 03. Maintenance Rules (Scribe Agent)
1.  **Disk-to-Index Sync:** Verify all files listed in Manifest exist on disk.
2.  **Archiving Trigger:** When `02_Active` exceeds 30 files, Scribe triggers **Grouping Workflow**.
3.  **Conflict & Decisions:** Contradiction with Core SOP requires a `[!] CONFLICT` entry and THEK approval.
