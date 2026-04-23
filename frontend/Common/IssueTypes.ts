import { sha1 } from "js-sha1";
import { faCheckCircle, faDotCircle, faSquare, type IconDefinition } from "@fortawesome/free-solid-svg-icons";

// ---- State types ----

export type GithubState = "open" | "closed";
export type JiraState =
    | "in review"
    | "blocked"
    | "todo"
    | "in progress"
    | "ready for merge"
    | "done"
    | "duplicate"
    | "won't fix"
    | "new";
export type State = GithubState | JiraState;

// ---- Entity interfaces ----

export interface Label {
    id: string;
    name: string;
    color: string;
    description: string;
}

export interface Link {
    id: string;
    test_id: string;
    run_id: string;
    release_id: string;
    type: string;
    added_on: string;
    user_id: string;
}

export interface Issue {
    subtype: "github" | "jira";
    id: string;
    state: State;
    event_id: string;
    added_on: string;
    labels: Label[];
    user_id: string;
    links: Link[];
}

export interface GithubSubtype extends Issue {
    repo: string;
    owner: string;
    number: string;
    title: string;
    state: GithubState;
    url: string;
    assignees: { html_url: string; login: string }[];
}

export interface JiraSubtype extends Issue {
    key: string;
    summary: string;
    project: string;
    permalink: string;
    state: JiraState;
    assignees: string[];
}

export type StateFilter = Record<State, boolean>;

export interface TestRun {
    build_id: string;
    build_number: string;
    build_job_url: string;
    assignee: string;
    group_id: string;
    release_id: string;
    test_id: string;
    id: string;
}

export interface RichAssignee {
    login: string;
    html_url: string;
}

// ---- State / icon maps ----

export const GithubIssueColorMap: Record<GithubState, string> = {
    open: "issue-open",
    closed: "issue-closed",
};

export const GithubIssueIcon: Record<GithubState, IconDefinition> = {
    open: faDotCircle,
    closed: faCheckCircle,
};

export const JiraIssueColorMap: Record<JiraState, string> = {
    "in progress": "jira-progress",
    "in review": "jira-review",
    "ready for merge": "jira-merge",
    "won't fix": "jira-fix",
    new: "jira-new",
    blocked: "jira-blocked",
    done: "jira-done",
    duplicate: "jira-dupe",
    todo: "jira-todo",
};

export const JiraIssueIcon: Record<JiraState, IconDefinition> = {
    "in progress": faDotCircle,
    "in review": faDotCircle,
    "ready for merge": faDotCircle,
    "won't fix": faCheckCircle,
    blocked: faSquare,
    done: faCheckCircle,
    duplicate: faCheckCircle,
    todo: faSquare,
    new: faDotCircle,
};

// ---- Polymorphic helpers ----

export const getTitle = function (i: Issue): string {
    if (i.subtype === "github") {
        return (i as GithubSubtype).title;
    } else {
        return (i as JiraSubtype).summary;
    }
};

export const getRepo = function (i: Issue): string {
    if (i.subtype === "github") {
        return (i as GithubSubtype).repo;
    } else {
        return (i as JiraSubtype).project;
    }
};

export const getNumber = function (i: Issue): number {
    if (i.subtype === "github") {
        return parseInt((i as GithubSubtype).number);
    } else {
        return parseInt((i as JiraSubtype).key.split("-")[1]);
    }
};

export const getUrl = function (i: Issue): string {
    if (i.subtype === "github") {
        return (i as GithubSubtype).url;
    } else {
        return (i as JiraSubtype).permalink;
    }
};

export const getAssignees = function (i: Issue): string[] {
    if (i.subtype === "github") {
        return (i as GithubSubtype).assignees.map((v) => v.login);
    } else {
        return (i as JiraSubtype).assignees;
    }
};

export const getKey = function (i: Issue): string {
    if (i.subtype === "github") {
        const iss = i as GithubSubtype;
        return `${iss.owner}/${iss.repo}#${iss.number}`;
    } else {
        const iss = i as JiraSubtype;
        return `${iss.key}`;
    }
};

export const getAssigneesRich = function (i: Issue): RichAssignee[] {
    if (i.subtype === "github") {
        return (i as GithubSubtype).assignees;
    } else {
        return (i as JiraSubtype).assignees.map((v) => ({ login: v, html_url: "#" }));
    }
};

export const label2color = function (label: Label): string {
    const START_COLOR = [255, 238, 0];
    const END_COLOR = [0, 32, 255];
    const factor = (parseInt(sha1(label.name).slice(0, 16), 16) % 10000) / 10000;

    const lerp = (c1: number, c2: number, frac: number) => Math.round((c2 - c1) * frac + c1) & 0xff;
    const color = START_COLOR.map((c1, idx) => lerp(c1, END_COLOR[idx], factor)).join(", ");
    return `rgb(${color})`;
};

// ---- Shared async helpers for issue card components ----

export const resolveRuns = async function (
    links: Link[],
    cache: { [key: string]: TestRun } | undefined,
): Promise<{ [key: string]: TestRun }> {
    if (cache) return cache;
    const response = await fetch("/api/v1/get_runs_by_test_id_run_id", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(links.map((v) => [v.test_id, v.run_id])),
    });
    const data = await response.json();
    if (data.status !== "ok") {
        throw new Error(data.response.arguments[0]);
    }
    return data.response.runs;
};

export const resolveFirstUserForAggregation = function (issue: Issue): { id: string; date: string } {
    if (!issue.links) return { id: issue.user_id, date: issue.added_on };
    const resolved = issue.links
        .filter((l) => !!l.added_on && !!l.user_id)
        .sort((a, b) => {
            const lhs = Date.parse(a.added_on);
            const rhs = Date.parse(b.added_on);
            return lhs > rhs ? 1 : rhs > lhs ? -1 : 0;
        });
    return {
        id: resolved?.[0]?.user_id ?? issue.user_id,
        date: resolved?.[0]?.added_on ?? issue.added_on,
    };
};

type DeleteIssueOptions = {
    issueId: string;
    runId: string;
    aggregated: boolean;
    onDeleted: (id: string) => void;
    onError: (msg: string, source: string) => void;
};

export const deleteIssue = async function (opts: DeleteIssueOptions): Promise<void> {
    if (opts.aggregated) throw new Error("Cannot delete aggregated issues");
    const apiResponse = await fetch("/api/v1/issues/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ issue_id: opts.issueId, run_id: opts.runId }),
    });
    const apiJson = await apiResponse.json();
    if (apiJson.status === "ok") {
        opts.onDeleted(opts.issueId);
    } else {
        const errObj = apiJson as { status: string; response: { arguments: string[] } };
        if (errObj?.status === "error") {
            opts.onError(`Unable to delete an issue.\nAPI Response: ${errObj.response.arguments[0]}`, "deleteIssue");
        } else {
            opts.onError("A backend error occurred during issue deleting", "deleteIssue");
        }
    }
};
