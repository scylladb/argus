# Release and view chat

Every release and every view has one chat that all Argus users share. A user
asks a question about the release, or asks to run tests. A language model
answers from the release summary, from the chat's memories, and from tools
that read Argus. Everyone sees every question, who asked it, and every
answer, live.

Open the chat from the **Chat** bar at the top of the release dashboard. On a
view, add the **Chat** widget; it shows the same bar.

## Asking

Type a question and press Enter; Shift+Enter adds a line. The answer streams
in, and anyone with the chat open sees it arrive. Older answers are
collapsed to a short preview; **Show answer** opens one.

An open answer can show three more details:

- **Used N tools**: what the assistant looked up, with the arguments and
  the results.
- **Reasoning**: the model's reasoning, when the model reports it.
- **Context used**: the memories the answer followed. A memory changed or
  deleted since then is marked.

One question is answered at a time per chat. While an answer runs, **Stop**
ends it.

- **Try again** answers the last question again. The earlier answers stay,
  and the arrows next to an answer switch between them.
- **Undo** removes the last question and its answer for everyone. Jobs that
  already started keep running, and memory changes stay; revert those in the
  memory history.
- **Fork** on an earlier answer continues the chat from there: the next
  question starts a new branch, and the later messages stay on their own.
  The **Forks** tab lists every branch with where it parts, and **Switch**
  moves the chat to another branch, for everyone. Undo works only at the end
  of a branch.

Examples:

- "What failed on 2025.1.0~rc4? Give the counts and the test names."
- "How did rc3 do compared with rc4?"
- "Show the last runs of rolling-upgrade-ami-test on rc4."
- "Which errors did the latest rc4 run of rolling-upgrade-centos9-test report?"
- "Who changed the status of that run?"
- "Which tests of the week1 plan have not run on 2025.1.0 yet?"

An admin can clear a whole conversation with **Clear chat** in the chat's
header, for everyone. The memories stay.

## Naming things

Name a test, a group, a release or a run however you have it at hand: its
name or its pretty name, its id, its Jenkins job path or URL, `group/test`,
or `release/group/test`. A run is its id, `job-path#build`, any test name
with `#build`, or a Jenkins build URL. "Show me rolling-upgrade-centos9-test
#11" answers with a card that opens the run in a new tab.

## Running tests

The assistant can propose to start tests. It never starts them on its own.
Argus shows each proposal as a card in the chat, and nothing runs until a
user presses **Run** on it. Any user may confirm a card or dismiss it, and
the card names who did.

- "Rerun the rolling upgrade tests that failed on 2025.1.0~rc4, on gce."
- "Run the week1 tests on gce." The assistant takes the tests of the release
  plan that carry the `week1` label. A labelled group stands for its tests.
- "Run sanity-test with scylla_version 2025.1.1."
- "Rerun the Rolling Upgrades group on gce." A group or a release stands for its
  enabled tests, up to 50.

Each test starts with the parameters of its last build, overridden by what
the request asks for. "Start it with the job's defaults" or "rerun it as
build #41" takes the parameters from there instead. Overrides can differ per
test: "run both on gce, and the second one in us-west1". Before the card
appears, Argus checks every override against the test's own Jenkins job:

- the job must have the parameter
- when the parameter is a choice, the value must be one of its choices
- a Scylla Cluster Tests job follows the rules of the parameter wizard on the
  run page: a supported backend and a region of that backend, the known
  values of `provision_type` and the post-test actions, exactly one Scylla
  version source in its format, and a BYO branch that exists on GitHub.
  `scylla_version` takes a released version (`2025.1`, `2025.1.0`,
  `2025.1.0~rc1`) or a branch build: `master:latest`, `branch-2025.1:latest`,
  `master:1234`, or a build timestamp such as `master:2025-11-01T10:00:00Z`.
  Setting one version source clears the others, and a new backend gets its
  first supported region when the job leaves it empty.

A test that fails a check is listed on the card under **Left out**, with the
reason, and does not start. **All parameters** on the card shows every value
a test will start with. After **Run**, the card links each started run.

A card that waits for confirmation can still change. Ask the assistant
("use us-west1 for that start instead"), or press **Edit parameters** on the
card: it lists the job's parameters in the wizard's groups, with a list of
the allowed values where there is one. Every change is checked again; a
value Argus refuses keeps the card as it was and shows the reason.

## Plans

The assistant reads the release plans and edits them:

- "Which labels does the week plan have?" lists each label with the tests
  and groups that carry it.
- "Which tests would week1 start?" lists them without proposing anything.
- "Add the label week1 to the upgrade tests of the week plan, and assign them
  to Alice." proposes the edit as a card.

An edit adds or removes tests, removes groups, assigns or unassigns tests,
adds or removes labels, renames the plan, or changes its description, target
version or completion. Assigning a test that is not in the plan adds it, and
a new assignee becomes a participant. The card lists every change, and
**Apply** saves them, unless someone changed the plan since the proposal; then
the card fails and nothing changes. Creating, copying and deleting plans stay
in the planner.

## Auto mode

**Auto mode** in the question box confirms the cards of your own questions
for you: a proposed start, plan edit, issue link or tool call runs at once,
and the answer reports how it went. The card says it was confirmed
automatically, and for whom. Auto mode applies to the questions you send
while it is on, in this browser tab; it never confirms a card of someone
else's question.

The assistant can also propose to link an issue to a run, to unlink one, or
to post a comment on a run, which is posted as the user who confirms it.
These need a confirmation on the card too. It reads a run's comments, with
their authors, whenever a question needs them.

## Asking Zeus to investigate

When Zeus is connected (`ZEUS_HOST` and `ZEUS_TOKEN` in `argus_web.yaml`),
the assistant can propose to have Zeus investigate up to 5 runs at once:

- "Ask Zeus why rolling-upgrade-ami-test failed on rc4."
- "Have Zeus investigate the failed upgrade runs of 2025.1.0~rc4; focus on the
  upgrade step."

The card lists the runs and the question, and **Queue** sends one
investigation per run. Zeus works through its queue one investigation at a
time, each in up to 30 minutes. While the chat is open, the card checks Zeus
every 30 seconds and shows each run's state: queued, processing, completed,
or failed. A completed card holds Zeus's report under **Zeus report**. Later
answers know the reports, and "what did Zeus find?" reads them.

### Reports Zeus posted itself

Zeus also investigates the failed builds of the Jenkins jobs it watches, and
posts its report into the run's discussion. Ask for it: "What did Zeus find
on rolling-upgrade-centos9-test #11?" The chat shows the whole report as a
card with a link to the run, and the assistant summarizes it. "Show the
discussion of that run" lists every comment, with Zeus's marked. Argus knows
Zeus's comments by their author: a service account with "zeus" in its name.

## People

The assistant knows people by name. Run assignees, comment authors, plan
owners and memory authors come with their username and full name.

- "Who is assigned to the upgrade tests?" lists, for each test, the assignee
  of every active plan that holds it, the test's and the group's assignees,
  and who its last run is assigned to.

## Memories

Memories are short notes that the assistant follows in every answer. There
are two kinds:

- a **note** is a convention: "we run tests on GCE when the job supports it",
  "for each minor release we run the sanity and the performance tests"
- a **finding** is something the automation does not know, such as the
  result of an investigation. Findings also show in the release summary,
  under **Findings**, with their author.

Anyone can add, edit, or delete a memory from the **Memories** panel, or ask
the assistant: "remember that…", "add a finding: rc3 failures were an
infrastructure outage". A memory written from the chat carries a robot icon
and links to the message that wrote it.

**History** lists every change: who made it, when, and the text before and
after. **Revert this change** restores the memory as it was before that
change. A revert is a change of its own, so it can be reverted too.

A release chat follows the memories of the release. A view chat follows the
memories of the view and of every release its tests belong to. In a view
chat, the memory form can store a new memory on one of those releases
instead.

## Context

The **Context** panel shows how much of the model's context window the
conversation fills. A long conversation answers more slowly and, near the
limit, loses its start. **Compact context** asks the model to summarize the
conversation so far. Later answers start from that summary; the earlier
messages stay readable. Undo removes a compaction like a question.

## Setting up the model

An administrator connects Argus to a model in the Admin Panel, under
**Chat**. Any endpoint that speaks the OpenAI chat completions API works,
such as OpenWebUI (`https://host/api`), vLLM, or llama.cpp.

1. **Add connection**: a name, the endpoint's base URL, and a token. The token
   is stored encrypted with a key derived from `SECRET_KEY` and is never shown
   again. Changing `SECRET_KEY` makes stored tokens unreadable; the panel
   says so, and the token has to be entered again.
2. **Change default model**: pick a connection. Argus asks the endpoint for
   its chat models and shows each one's context window and whether it supports
   tool calling and vision, when the endpoint says. An aggregator such as AIML
   API lists a model once per API it serves; the list keeps one entry per
   model, for chat completions. **Test** checks tool
   calling with one short request. **Set as default** makes that model answer
   in every chat.

3. **Identity** (the badge button of a connection): a name and a picture for
   the assistant. The picture is cropped to a circle in the browser and stored
   as a 256×256 PNG; the server takes square PNG, JPEG, GIF or WebP pictures
   up to 1 MB. **Use this identity** makes it the one every chat shows and the
   name the model answers as. Without an active identity the chat shows
   "Assistant".

Connections can also come from `argus_web.yaml`; they show in the panel but
are edited only in the file:

```yaml
CHAT_MODELS:
  - name: local-webui
    endpoint: https://host/api
    token: your-token
    model: Gemma-4-12B-it-GGUF   # optional: used until an admin picks a default
```

### MCP servers

The **MCP servers** tab connects the chat to tools outside Argus. Add a
server by its URL, over Streamable HTTP or SSE, with any headers it needs,
such as `Authorization`; header values are stored encrypted and never shown
again. **Probe** lists the server's tools. Each tool starts **Off**; switch it
to **Direct**, which runs whenever the model calls it, or **Confirm**, which
proposes a card first. The chat offers the switched-on tools of the enabled
servers, named `mcp_<server>__<tool>`.

### Prompt and skills

The **Prompt & skills** tab edits the system prompt. It is a template whose
placeholders Argus fills for each answer; `{tool_rules}`, `{scope}`,
`{memories}` and `{summary}` must stay, and a literal brace is written `{{`
or `}}`. **Reset to default** brings back the prompt Argus ships.

A skill is a piece of instructions with a name:

- **Always**: its text joins every system prompt.
- **On demand**: the prompt lists its name and description, and the model
  loads the text when a question needs it.
- **Off**: kept but unused.

A model without tool calling still answers, from the summary and the
memories only. It cannot look anything up, propose tests, or write memories.
Small models also read numbers less reliably, so prefer a model with tool
calling.

## How it works

- Answers run in the background on the server. Closing the chat does not
  stop an answer.
- The chat opens on the questions of the last 3 days; **Show earlier
  questions** unfolds the older ones.
- The page follows the chat over a server-sent event stream. The stream
  reconnects by itself, and the page falls back to refreshing every
  3 seconds while it cannot connect.
- The tools reach only the tests of the chat: a release chat reaches the
  release, and a view chat reaches the view's tests.
