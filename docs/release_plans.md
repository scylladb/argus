# Release plans and their labels

A release plan lists the tests and groups that a release, or one of its
versions, needs to run, with an assignee for each. **Release Planner** on
the release list opens the plans of a release.

## Labels

A label names a batch of a plan, such as `week1` or `sanity`. A test or a
group of the plan carries any number of labels. A labelled group stands for
its enabled tests. Labels belong to the plan: the same test can carry
`week1` in one plan and nothing in another.

### In the planner

- Each plan card lists its labels, with the number of tests and groups that
  carry each one.
- The plan editor shows the labels of every test and group of the plan.
  **Add label** adds one: type it and press Enter, or pick one of the plan's
  labels from the suggestions. The cross on a label removes it. A label is
  free text. An item cannot carry the same label twice, in any letter case.
- The label buttons above the list show only the items that carry the chosen
  labels. They hide items and change nothing in the plan.
- **Edit** saves the labels with the rest of the plan.
- **Split group into tests** gives each test the group's labels.
- A plan created from another one, or copied to another release, keeps the
  labels.
- The grid view shows the labels of the plan's tests.

### On the dashboard

The filters of a release dashboard, and of a view's test dashboard, include
**Filter by plan label**. It lists "plan · label" for the plans of the
dashboard's releases, and keeps the tests that carry the label, directly or
through their group. A kept test shows its labels on its card. The filter is
remembered with the other filters.

### From the command line

```bash
argus planner update --plan-id <release#n> --label <test-or-group>=week1
argus planner update --plan-id <release#n> --unlabel <test-or-group>=week1
```

`argus planner create` takes `--label` too.

## Running a plan from the chat

The release chat starts the tests of a plan, or of its labels, once a user
confirms the card. It also reports how a label did on a version, and
starts only what failed or did not run. See
[Release and view chat](release_chat.md#plans).
