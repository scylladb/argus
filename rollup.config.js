import svelte from "rollup-plugin-svelte";
import resolve from "@rollup/plugin-node-resolve";
import postcss from 'rollup-plugin-postcss';
import typescript from "@rollup/plugin-typescript";
import { sveltePreprocess } from "svelte-preprocess";
import commonjs from "@rollup/plugin-commonjs";
import sass from "@csstools/postcss-sass";


const environment = process.env.ROLLUP_ENV || "production";

export default {
    logLevel: "trace",
    input: {
        main: "./frontend/argus.js",
        fontAwesome: "./frontend/font-awesome.js",
        globalAlert: "./frontend/Alert.js",
        notificationCounter: "./frontend/notification-counter.js",
        flashDebug: "./frontend/flashDebug.js",
        login: "./frontend/login.js",
        workArea: "./frontend/work-area.js",
        adminPanel: "./frontend/admin-panel.js",
        releasePage: "./frontend/release-page.js",
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
    },
    output: {
        sourcemap: environment !== "production",
        compact: environment === "production",
        dir: "public/dist",
        format: "esm",
        entryFileNames: "[name].bundle.js",
        assetFileNames: "public/dist/assets/[name][extname]",
        globals: {
            globalAlert: 'sendMessage'
        }
    },
    plugins: [
        commonjs(),
        postcss({
            extract: "styles.css",
            plugins: [
                sass(),
            ]
        }),
        typescript(),
        resolve({ browser: true, exportConditions: ['svelte'], }),
        svelte({
            preprocess: sveltePreprocess(),
            include: "/**/*.svelte",
            emitCss: true,
        }),
    ]
};
