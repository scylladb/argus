Summarize this ScyllaDB test (SCT) ERROR/CRITICAL event into a short, readable triage summary.

This is the FIRST-PASS view for an engineer or AI investigator. The full original event is always available on demand, so do NOT reproduce it verbatim — compress by cutting redundant log noise, repeated lines, and library-glue stack frames. Compress the NOISE, never the identifying facts below. Your job is to let the reader understand what failed, where, and under what conditions, and decide whether to open the original.

Always preserve — these are the triage index, not boilerplate. Copy them verbatim when the event contains them; never drop one to save tokens:
- the failure/event type and severity, stated exactly as the event gives it
- the event id and timestamp
- every node identifier the event names: node name AND every IP (public and internal are different facts — keep both), plus instance type / rack / shard when present
- the disruption context: `during_nemesis` / the active nemesis or disruption, and the event `duration` / period type
- the exact error string(s) and error codes, keyspace/table names, and every numeric value that characterizes the failure (timeouts, replica counts, consistency level, sizes, thread/RF/duration parameters of a triggering command)
- the triggering command and its key parameters, if the event carries one (e.g. the cassandra-stress / scylla-bench invocation)

Adapt the SHAPE to the event:

- If the event is SHORT (a line or two, no real stack trace): return the essential line(s) with redundant noise removed — keep every fact from the list above, but do NOT expand into a field-per-line form and do NOT invent Root cause / Call chain sections. Do not crush multiple distinct facts into one line if that forces you to drop any of them.

- If the event carries a STACK TRACE or is long: output compact Markdown with
  - **Headline**: failure/event type, key value(s), node/shard, severity as literally stated
  - **Context**: the nemesis/disruption, duration, and triggering command parameters, if present
  - **Root cause**: one or two lines, only if the trace/message actually shows it — name the operation and subsystem from the decoded symbols present in the trace
  - **Call chain**: keep the exception line, the top frames, the deepest few frames, and any allocation/reclaim/stall chain — collapse only long runs of unrelated library glue and hex addresses
  - **Event ID** and **timestamp**

Faithfulness rules (non-negotiable — a wrong summary is worse than a terse one):
- State severity (non-fatal / fatal) ONLY if the event text says so. Do not infer it.
- Do NOT guess a trigger, root cause, or call chain that the event does not evidence. Only decode symbols and frames that literally appear in the trace. If the cause isn't determinable, write "root cause not evident from the event" — never speculate.
- Copy exact identifiers (event id, node, IPs, numbers, error strings) rather than paraphrasing; never contradict a value in the event.
- No hedging prose, no "may/might/likely" speculation about unstated behavior.

Length discipline: never output more characters than you received — a summary longer than the original is a failure. Aim for the fewest tokens that still carry every fact above. Output concise Markdown (or the essential line(s) for short events), no preamble.
