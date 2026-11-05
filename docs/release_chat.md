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
the request asks for. Before the card appears, Argus checks every override
against the test's own Jenkins job:

- the job must have the parameter
- when the parameter is a choice, the value must be one of its choices
- a Scylla Cluster Tests job must keep exactly one Scylla version source

A test that fails a check is listed on the card under **Left out**, with the
reason, and does not start. **All parameters** on the card shows every value
a test will start with. After **Run**, the card links each started run.

The assistant can also propose to link an issue to a run, or to unlink one.
These need a confirmation on the card too.

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

A model without tool calling still answers, from the summary and the
memories only. It cannot look anything up, propose tests, or write memories.
Small models also read numbers less reliably, so prefer a model with tool
calling.

## How it works

- Answers run in the background on the server. Closing the chat does not
  stop an answer.
- The page follows the chat over a server-sent event stream. The stream
  reconnects by itself, and the page falls back to refreshing every
  3 seconds while it cannot connect.
- The tools reach only the tests of the chat: a release chat reaches the
  release, and a view chat reaches the view's tests.
