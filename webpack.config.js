
const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = {
    plugins: [new MiniCssExtractPlugin()],
    mode: 'development',
    entry: {
        main: './argus/backend/assets/argus.js',
        noto: './argus/frontend/fonts/noto.css',
        globalAlert: { import: './argus/backend/assets/Alert.js', dependOn: 'main'},
        flashDebug: { import: './argus/backend/assets/flashDebug.js', dependOn: 'globalAlert'},
        workArea: { import: './argus/backend/assets/work-area.js', dependOn: 'globalAlert'},
        releasePage: { import: './argus/backend/assets/release-page.js', dependOn: 'globalAlert'},
        testRunDetails: { import: './argus/backend/assets/test-run-details.js', dependOn: 'globalAlert'},
        testRuns: { import: './argus/backend/assets/test-runs-breakout.js', dependOn: 'globalAlert'},
        releaseDashboard: { import: './argus/backend/assets/release-dashboard.js', dependOn: 'globalAlert'},
        releaseScheduler: { import: './argus/backend/assets/release-scheduler.js', dependOn: 'globalAlert'},
        dutyPlanner: { import: './argus/backend/assets/duty-planner.js', dependOn: 'globalAlert'},
        profileJobs: { import: './argus/backend/assets/profile-jobs.js', dependOn: 'globalAlert'},
        profileSchedules: { import: './argus/backend/assets/profile-schedules.js', dependOn: 'globalAlert'},
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
            test: /\.(woff|woff2|eot|ttf|otf)$/i,
            type: 'asset/resource',
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
