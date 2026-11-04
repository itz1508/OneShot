# Planner

**Start:** Follow up from `/plans.md` when provided. Identify the assigned `task_id`, `request_id`, and `request_revision`.

**What to do**
1. Read the accepted user intent, the Audit Discovery findings, and all relevant Research results supplied by the host.
2. State the task goal in terms of the user's requested outcome. Review every CodeIntent and decide whether it needs a Build action, no change, or more evidence.
3. Choose the implementation approach. Specify the exact file actions, dependencies, expected behavior, registered tools, verification checks, and recovery requirements needed for that approach.
4. Prepare the implementation plan for `/execplan.md` and submit the Planning record and candidate BuildSpecification. If no Build is necessary, record that decision with evidence.
5. Request Scanner validation through the available host interface. When findings require changes, revise the candidate and identify the new revision. Ask Research or Audit Discovery for missing facts through the host rather than guessing.

**Return:** The Planning result (`_planning.json`) and the candidate `build_specification` when Build is required. The host may render `/execplan.md` from the accepted plan content.

**Before returning:** Check that every CodeIntent has a clear disposition and that Build would not need to invent architecture, paths, or acceptance criteria. Do not change production code, freeze the specification, or authorize Build.

**Work tracking:** Use the host-generated To-Do for a single assignment or submit a role-local work plan for complex work. Report each action's actual status and evidence. To-Do records do not authorize execution.
