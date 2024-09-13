import ViewGithubIssues from "../Views/Widgets/ViewGithubIssues.svelte";
import ViewReleaseStats from "../Views/Widgets/ViewReleaseStats.svelte";
import ViewTestDashboard from "../Views/Widgets/ViewTestDashboard.svelte";
import CheckValue from "../Views/WidgetSettingTypes/CheckValue.svelte";
import MultiSelectValue from "../Views/WidgetSettingTypes/MultiSelectValue.svelte";
import StringValue from "../Views/WidgetSettingTypes/StringValue.svelte";
import { TestStatus } from "./TestStatus";
import { subUnderscores, titleCase } from "./TextUtils";

export class Widget {
    constructor(position = -1, type = "testDashboard", settings = {}) {
        this.position = position;
        this.type = type;
        this.settings = settings;
    }
}


export const WIDGET_TYPES = {
    testDashboard: {
        type: ViewTestDashboard,
        friendlyName: "Test Dashboard",
        settingDefinitions: {
            targetVersion: {
                type: CheckValue,
                default: false,
                help: "Enable fixed version for this widget.",
                displayName: "Fixed version"
            },
            versionsIncludeNoVersion: {
                type: CheckValue,
                default: true,
                help: "Include No Version results for stat fetches",
                displayName: "Include No Version"
            },
            productVersion: {
                type: StringValue,
                default: "",
                help: "Target Version to Fetch with Stats",
                displayName: "Target Version"
            }
        },
    },
    releaseStats: {
        type: ViewReleaseStats,
        friendlyName: "Stat bar",
        settingDefinitions: {
            horizontal: {
                type: CheckValue,
                default: false,
                help: "Display Stats bar horizontally (EXPERIMENTAL)",
                displayName: "Horizontal Stats"
            },
            displayExtendedStats: {
                type: CheckValue,
                default: false,
                help: "Display investigation stats widget under stats bar",
                displayName: "Enable Per-Investigation Stats"
            },
            hiddenStatuses: {
                type: MultiSelectValue,
                default: [],
                values: Object.values(TestStatus),
                labels: Object.keys(TestStatus).map(s => subUnderscores(s).split(" ").map(s => titleCase(s)).join(" ")),
                help: "Select which statuses to exclude from investigation widget",
                displayName: "Statuses to exclude from extended stats"
            }
        }
    },
    githubIssues: {
        type: ViewGithubIssues,
        friendlyName: "Github Scoped Issue View",
        settingDefinitions: {
            submitDisabled: {
                type: CheckValue,
                default: true,
                help: "Disable user ability to attach issues",
                displayName: "Disable Issue Submit"
            },
            aggregateByIssue: {
                type: CheckValue,
                default: true,
                help: "Aggregate runs that have the same issue under same issue",
                displayName: "Aggregate Runs by Issue"
            }
        }
    }
};


export const ADD_ALL_ID = "db6f33b2-660b-4639-ba7f-79725ef96616";