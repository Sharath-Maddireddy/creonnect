# Command: /remember
Description: Adds a new permanent rule, architectural decision, or lesson learned to CLAUDE.md so it is remembered in all future sessions.

## Context
The Persistent Memory Loop ensures that if you correct Claude on a mistake (e.g., using an outdated library, a wrong Pydantic structure, or missing a specific piece of business logic), it will never make that mistake again across any future sessions.

## Instructions
When the user says `/remember <rule or lesson>`:

1. Read the current contents of `CLAUDE.md` located in the repository root.
2. If it does not already exist, create a section at the bottom titled `## 🧠 Persistent Memory & Lessons Learned`.
3. Append the user's new rule to this section as a clear, actionable directive.
   - *Example User Input:* "/remember always use Redis pipelines when fetching more than 5 creator keys."
   - *Example Added Rule:* "- **Redis:** Always use Redis pipelines when fetching more than 5 creator keys to prevent network bottlenecking."
4. Save the updated `CLAUDE.md` file.
5. Confirm to the user that the rule has been permanently added to the repository's memory.
