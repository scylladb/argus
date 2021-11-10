
const path = require('path');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

module.exports = {
    plugins: [new MiniCssExtractPlugin()],
    mode: 'development',
    entry: {
        main: './argus/backend/assets/argus.js',
        runDashboard: './argus/backend/assets/RunsDashboard/runs-dashboard.js',
        testRunDetails: './argus/backend/assets/RunsDashboard/test-run-details.js'
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
};
