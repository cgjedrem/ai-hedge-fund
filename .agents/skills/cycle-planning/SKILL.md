---
name: cycle-planning
description: Interactive skill for starting a new planning cycle. The planning agent walks the user through OKR goal iteration, project selection (max 3), epic activation, and 6-week MIT (Most Important Task) definition. Triggered by the user saying "start cycle planning" or similar. Do not use for task creation within a cycle (use task-creation), daily reviews, or retro analysis.
---

# Cycle Planning Skill

## Trigger
User says "start cycle planning", "plan cycle", "begin cycle", or similar.

## Prerequisites
- Current cycle file exists (or this is the first cycle)
- Life-Goals.md exists
- At least one epic exists per project being considered

## Steps

### 1. Goal Iteration (OKR)
- Read `Life-Goals.md`
- Present current objectives and key results
- Ask user: "Any objectives to add, change, or retire?"
- Update `Life-Goals.md` with changes
- Confirm each objective has at least one key result

### 2. Epic Review
- Walk `02_Active/E00X-*/epic.md` across all scopes in the vault
- Present each epic: name, status, completion_condition, which goal it serves
- Cross-check: read tasks in the same epic folder to confirm progress claims
- Flag: epics without goal_ref (drift), epics past their cycle focus but still active, empty epic folders (epic with no tasks)
- Ask user: "Any epics to mark done, move to backlog, or adjust?"

### 3. Project Selection (Max 3)
- Read `Epic-Dependency-Map.md` — surface blockers
- Present candidates: projects with active epics + momentum
- Ask user: "Which 3 projects get focus this cycle?"
- Validate: each selected project must have at least one epic with completion condition
- Planning cycle exception: epic definition IS the cycle work, but epic must exist before slot is confirmed

### 4. Epic Activation
- For each selected project, confirm which epic(s) get `cycle_focus` this cycle
- Update epic frontmatter: add `cycle_focus: [{cycle: "XXX", role: "primary"}]`
- Check dependency map — flag any blockers

### 5. MIT Definition (All 6 Weeks)
- Ask user: "Define 1-3 MITs for each week of the focus phase"
- Record in cycle file under Weekly MITs section
- MITs should be concrete, completable within a week
- Planning cycle: MITs focus on setup, design, and scaffolding

### 6. Mandatory Obligations
- Ask user: "Any mandatory obligations this cycle?" (work, training, meditation)
- These don't count toward the 3-project limit
- Record in cycle file

### 7. Write Cycle File
- Create `Cycle-XXX.md` with all decisions
- Update `Epic-Dependency-Map.md` if dependencies changed
- Deliver summary to the planning agent's notification channel (e.g. Discord #tasker in the ENSO implementation)

## Rules
- User decides everything. The planning agent proposes, user approves/rejects.
- The planning agent adapts proposals based on user input (not rigid question-answer).
- If user wants fewer than 3 projects, that's valid.
- If a project has no epic, the planning agent proposes one — user must approve before slot is confirmed.