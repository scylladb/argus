const path = require("path");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

const environment = process.env.WEBPACK_ENVIRONMENT || "production";

module.exports = {
    plugins: [new MiniCssExtractPlugin()],
    mode: environment,
    entry: {
        main: "./frontend/argus.js",
        fontAwesome: "./frontend/font-awesome.js",
        noto: "./frontend/fonts/noto.css",
        globalAlert: {
            import: "./frontend/Alert.js",
            dependOn: "main"
        },
        notificationCounter: {
            import: "./frontend/notification-counter.js",
            dependOn: "globalAlert"
        },
        flashDebug: {
            import: "./frontend/flashDebug.js",
            dependOn: "globalAlert"
        },
        login: {
            import: "./frontend/login.js",
            dependOn: "globalAlert"
        },
        workArea: {
            import: "./frontend/work-area.js",
            dependOn: "globalAlert"
        },
        adminPanel: {
            import: "./frontend/admin-panel.js",
            dependOn: "globalAlert"
        },
        releasePage: {
            import: "./frontend/release-page.js",
            dependOn: "globalAlert"
        },
        testRunDetails: {
            import: "./frontend/test-run-details.js",
            dependOn: "globalAlert"
        },
        testRunsStandalone: {
            import: "./frontend/test-runs-standalone.js",
            dependOn: "globalAlert"
        },
        runByPlugin: {
            import: "./frontend/run-by-plugin.js",
            dependOn: "globalAlert"
        },
        testRuns: {
            import: "./frontend/test-runs-breakout.js",
            dependOn: "globalAlert"
        },
        releaseDashboard: {
            import: "./frontend/release-dashboard.js",
            dependOn: "globalAlert"
        },
        plan: {
            import: "./frontend/plan.js",
            dependOn: "globalAlert"
        },
        viewDashboard: {
            import: "./frontend/view-dashboard.js",
            dependOn: "globalAlert"
        },
        viewUserResolver: {
            import: "./frontend/view-user-resolver.js",
            dependOn: "globalAlert"
        },
        releaseScheduler: {
            import: "./frontend/release-scheduler.js",
            dependOn: "globalAlert"
        },
        releasePlanner: {
            import: "./frontend/release-planner.js",
            dependOn: "globalAlert"
        },
        dutyPlanner: {
            import: "./frontend/duty-planner.js",
            dependOn: "globalAlert"
        },
        profileJobs: {
            import: "./frontend/profile-jobs.js",
            dependOn: "globalAlert"
        },
        profileNotifications: {
            import: "./frontend/profile-notifications.js",
            dependOn: "globalAlert"
        },
        profileSchedules: {
            import: "./frontend/profile-schedules.js",
            dependOn: "globalAlert"
        },
        teams: {
            import: "./frontend/teams.js",
            dependOn: "globalAlert"
        },
    },
    output: {
        path: path.resolve(__dirname, "public/dist"),
        filename: "[name].bundle.js",
    },
    resolve: {
        alias: {
            svelte: path.resolve("node_modules", "svelte")
        },
        extensions: [".mjs", ".js", ".svelte", ".ts", ".tsx"],
        mainFields: ["svelte", "browser", "module", "main"]
    },
    module: {
        rules: [{
            test: /\.css$/,
            use: [MiniCssExtractPlugin.loader, "css-loader"]
        },
        {
            test: /\.tsx?$/,
            use: "ts-loader",
            exclude: /node_modules/,
        },
        {
            test: /\.svelte$/,
            use: {
                loader: "svelte-loader",

                options: {
                    preprocess: require("svelte-preprocess")({

                    })
                },
            }
        },
        {
            test: /\.(woff|woff2|eot|ttf|otf)$/i,
            type: "asset/resource",
        },
        {
            test: /node_modules\/svelte\/.*\.mjs$/,
            resolve: {
                fullySpecified: false
            }
        }
        ],
    },
    devtool: environment == "production" ? "source-map" : "eval-source-map"
};
