---
name: deadline-submit
description: Preview and submit Deadline 10 jobs or retry explicitly selected tasks with user authorization of the concrete operation.
---

Submission requires actual UTF-8 `JobInfo` and `PluginInfo` files and optional auxiliary files. Build or use the user's requested settings; do not guess renderer, scene, output path or frame range. Consult that render plugin's submission specification when producing these files. `deadline_submit_job` checks syntax and file hashes, but cannot guarantee plugin-specific settings, licensing or render-worker path accessibility.

Always call with `confirmed=false` first. Show the job name, renderer plugin, frame range, initial status, important job/plugin settings and all auxiliary filenames from the preview. Explain that Active jobs may render immediately. Obtain authorization for this concrete job if not already supplied. Repeat exactly those inputs with `confirmed=true` and the returned one-use `preview_token` (10-minute expiry). File/settings changes require a new preview. Tokens are in-memory and disappear when the MCP server exits.

For retry, read job/tasks first and map user-specified frame ranges to explicit task IDs. A task can contain multiple frames: disclose the complete affected frame ranges. `retry_failed` accepts Failed tasks only; `requeue_completed` re-renders Completed tasks only. Never expand to whole-job retry. Preview `deadline_retry_tasks`, present ID/frame/state selection, then confirm the same arguments only when authorized.

Do not automatically retry failed or timed-out mutations: a job may already have been submitted or a task state changed. Read current job/task state and report uncertain outcomes. Return submission JobID only when verified in CLI output; an exit code alone is not proof of submission. A successful queued state is not proof that rendering completed correctly.
