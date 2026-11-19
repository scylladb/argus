import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

const suppressedSvelteCodes = [
    "a11y_click_events_have_key_events",
    "a11y_no_static_element_interactions",
];

export default defineConfig({
    plugins: [
        svelte({
            onwarn(warning, handler) {
                if (suppressedSvelteCodes.includes(warning.code)) return;
                handler(warning);
            },
        }),
    ],
    publicDir: false,
    base: "/s/dist/",
    build: {
        outDir: "public/dist",
        emptyOutDir: true,
        sourcemap: process.env.NODE_ENV !== "production",
        minify: process.env.NODE_ENV === "production",
        cssCodeSplit: false,
        rolldownOptions: {
            input: {
                main: "./frontend/argus.js",
                globalAlert: "./frontend/Alert.js",
                notificationCounter: "./frontend/notification-counter.js",
                healthIndicator: "./frontend/health-indicator.js",
                flashDebug: "./frontend/flashDebug.js",
                login: "./frontend/login.js",
                workArea: "./frontend/work-area.js",
                adminPanel: "./frontend/admin-panel.js",
                releasePage: "./frontend/release-page.js",
                viewsPage: "./frontend/views-page.js",
                testRunDetails: "./frontend/test-run-details.js",
                testRunsStandalone: "./frontend/test-runs-standalone.js",
                runByPlugin: "./frontend/run-by-plugin.js",
                testRuns: "./frontend/test-runs-breakout.js",
                releaseDashboard: "./frontend/release-dashboard.js",
                plan: "./frontend/plan.js",
                viewDashboard: "./frontend/view-dashboard.js",
                viewUserResolver: "./frontend/view-user-resolver.js",
                releaseScheduler: "./frontend/release-scheduler.js",
                releasePlanner: "./frontend/release-planner.js",
                dutyPlanner: "./frontend/duty-planner.js",
                profileJobs: "./frontend/profile-jobs.js",
                profileNotifications: "./frontend/profile-notifications.js",
                profileSchedules: "./frontend/profile-schedules.js",
                teams: "./frontend/teams.js",
                issueLinks: "./frontend/issue-links.js",
                costExplorer: "./frontend/cost-explorer.js",
            },
            output: {
                entryFileNames: "[name].bundle.js",
                chunkFileNames: "[name]-[hash].js",
                assetFileNames: "[name][extname]",
            },
        },
    },
    css: {
        preprocessorOptions: {
            scss: {
                silenceDeprecations: ["import", "global-builtin", "color-functions"],
            },
        },
    },
});
