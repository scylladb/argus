import ViewGithubIssues from "../Views/Widgets/ViewGithubIssues.svelte";
import ViewReleaseStats from "../Views/Widgets/ViewReleaseStats.svelte";
import ViewTestDashboard from "../Views/Widgets/ViewTestDashboard.svelte";
import ViewUnsupportedPlaceholder from "../Views/Widgets/ViewUnsupportedPlaceholder.svelte";
import CheckValue from "../Views/WidgetSettingTypes/CheckValue.svelte";
import MultiSelectValue from "../Views/WidgetSettingTypes/MultiSelectValue.svelte";
import MultiStringValue from "../Views/WidgetSettingTypes/MultiStringValue.svelte";
import StringValue from "../Views/WidgetSettingTypes/StringValue.svelte";
import {TestStatus} from "./TestStatus";
import {subUnderscores, titleCase} from "./TextUtils";
import ViewHighlights from "../Views/Widgets/ViewHighlights/ViewHighlights.svelte";
import IntegerValue from "../Views/WidgetSettingTypes/IntegerValue.svelte";
import SummaryWidget from "../Views/Widgets/SummaryWidget/SummaryWidget.svelte";
import GraphWidget from "../Views/Widgets/GraphsWidget/GraphsWidget.svelte";
import ViewNemesisStats from "../Views/Widgets/ViewNemesisStats.svelte";
import ViewGraphedStats from "../Views/Widgets/ViewGraphedStats.svelte";

export class Widget {
    constructor(position = -1, type = "testDashboard", settings = {}) {
        this.position = position;
        this.type = type;
        this.settings = settings;
    }
}


export const WIDGET_TYPES = {
    UNSUPPORTED: {
        type: ViewUnsupportedPlaceholder,
        hidden: true,
        friendlyName: "Dummy widget",
        settingDefinitions: {
        }
    },
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
    },
    highlights: {
        type: ViewHighlights,
        friendlyName: "Highlights and action items for the view",
        settingDefinitions: {
            index: {
                type: IntegerValue,
                default: 0,
                help: "Index of the highlight (for support multiple highlight widgets in one view)",
                displayName: "Index"
            }
        },
    },
    summary: {
        type: SummaryWidget,
        friendlyName: "Per version summary for specified release",
        settingDefinitions: {
            packageName: {
                type: StringValue,
                default: "scylla-server",
                help: "Package name (from Packages tab) to monitor",
                displayName: "Package Name"
            }
        },
    },
    graphs: {
        type: GraphWidget,
        friendlyName: "Graphs Views",
        settingDefinitions: {}
    },
    nemesisStats: {
        type: ViewNemesisStats,
        friendlyName: "Nemesis stats",
        settingDefinitions: {
        },
    },
    graphedStats: {
        type: ViewGraphedStats,
        friendlyName: "Graphed Stats",
        settingDefinitions: {
            testFilters: {
                type: MultiStringValue,
                default: [],
                help: "Regular expressions to filter out tests (e.g. .*/artifacts/)",
                displayName: "Test Filters"
            },
        },
    },
};


export const ADD_ALL_ID = "db6f33b2-660b-4639-ba7f-79725ef96616";
