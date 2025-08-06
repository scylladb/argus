import svelte from "rollup-plugin-svelte";
import resolve from "@rollup/plugin-node-resolve";
import css from "rollup-plugin-import-css";
import typescript from "@rollup/plugin-typescript";
import autoPreprocess from "svelte-preprocess";
import commonjs from '@rollup/plugin-commonjs';



export default {
    logLevel: "trace",
    input: {
        main: "./frontend/argus.js",
        fontAwesome: "./frontend/font-awesome.js",
        //noto: "./frontend/fonts/noto.css",
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
        sourcemap: true,
        dir: "public/dist",
        format: "esm",
        entryFileNames: "[name].bundle.js",
        assetFileNames: "public/dist/assets/[name][extname]",
    },
    plugins: [
        commonjs(),
        css(),
        typescript(),
        resolve({ browser: true, exportConditions: ['svelte'], }),
        svelte({
            preprocess: autoPreprocess(),
            include: "/**/*.svelte",
        }),
    ]
};
