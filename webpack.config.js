
const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = {
    plugins: [new MiniCssExtractPlugin()],
    mode: 'development',
    entry: {
        main: './argus/backend/assets/argus.js',
        globalAlert: { import: './argus/backend/assets/RunsDashboard/Alert.js', dependOn: 'main'},
        flashDebug: { import: './argus/backend/assets/RunsDashboard/flashDebug.js', dependOn: 'globalAlert'},
        runDashboard: { import: './argus/backend/assets/RunsDashboard/runs-dashboard.js', dependOn: 'globalAlert'},
        releasePage: { import: './argus/backend/assets/RunsDashboard/release-page.js', dependOn: 'globalAlert'},
        testRunDetails: { import: './argus/backend/assets/RunsDashboard/test-run-details.js', dependOn: 'globalAlert'},
        testRuns: { import: './argus/backend/assets/RunsDashboard/test-runs-breakout.js', dependOn: 'globalAlert'},
        releaseDashboard: { import: './argus/backend/assets/RunsDashboard/release-dashboard.js', dependOn: 'globalAlert'},
        releaseScheduler: { import: './argus/backend/assets/RunsDashboard/release-scheduler.js', dependOn: 'globalAlert'},
        profileJobs: { import: './argus/backend/assets/RunsDashboard/profile-jobs.js', dependOn: 'globalAlert'},
        profileSchedules: { import: './argus/backend/assets/RunsDashboard/profile-schedules.js', dependOn: 'globalAlert'},
    },
    output: {
        path: path.resolve(__dirname, 'argus/backend/static/dist'),
        filename: '[name].bundle.js',
    },
    resolve: {
        alias: {
            svelte: path.resolve('node_modules', 'svelte')
        },
        extensions: ['.mjs', '.js', '.svelte'],
        mainFields: ['svelte', 'browser', 'module', 'main']
    },
    module: {
        rules: [{
            test: /\.css$/,
            use: [MiniCssExtractPlugin.loader, 'css-loader']
        },
        {
            test: /\.svelte$/,
            use: 'svelte-loader'
        },
        {
            test: /node_modules\/svelte\/.*\.mjs$/,
            resolve: {
                fullySpecified: false
            }
        }],
    },
    devtool: "eval-source-map"
};
