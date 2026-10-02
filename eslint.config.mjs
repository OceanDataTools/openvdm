// ESLint config for the web UI's JavaScript.
//
// Bug-finding rules only (undefined names, unused and duplicate variables,
// unreachable code, and so on). Formatting is deliberately not checked: the
// existing code uses 4-space indentation and semicolons, and reformatting it
// is out of scope (see issue #128).
//
// The config imports nothing so it runs from the pre-commit ESLint hook
// without extra packages:
//
//     pre-commit run eslint --all-files

const bugRules = {
    'constructor-super': 'error',
    'for-direction': 'error',
    'getter-return': 'error',
    'no-async-promise-executor': 'error',
    'no-class-assign': 'error',
    'no-compare-neg-zero': 'error',
    'no-cond-assign': 'error',
    'no-const-assign': 'error',
    'no-constant-condition': ['error', { checkLoops: false }],
    'no-debugger': 'error',
    'no-delete-var': 'error',
    'no-dupe-args': 'error',
    'no-dupe-class-members': 'error',
    'no-dupe-else-if': 'error',
    'no-dupe-keys': 'error',
    'no-duplicate-case': 'error',
    'no-empty-character-class': 'error',
    'no-empty-pattern': 'error',
    'no-ex-assign': 'error',
    'no-fallthrough': 'error',
    'no-func-assign': 'error',
    'no-global-assign': 'error',
    'no-import-assign': 'error',
    'no-invalid-regexp': 'error',
    'no-loss-of-precision': 'error',
    'no-misleading-character-class': 'error',
    'no-new-native-nonconstructor': 'error',
    'no-obj-calls': 'error',
    // Globals declared below are defined by the scripts listed next to them.
    'no-redeclare': ['error', { builtinGlobals: false }],
    'no-self-assign': 'error',
    'no-setter-return': 'error',
    'no-shadow-restricted-names': 'error',
    'no-sparse-arrays': 'error',
    'no-this-before-super': 'error',
    'no-undef': 'error',
    'no-unreachable': 'error',
    'no-unsafe-finally': 'error',
    'no-unsafe-negation': 'error',
    'no-unsafe-optional-chaining': 'error',
    'no-unused-labels': 'error',
    'no-unused-vars': ['error', { args: 'none', caughtErrors: 'none' }],
    'use-isnan': 'error',
    'valid-typeof': 'error',
};

const browserGlobals = {
    window: 'readonly',
    document: 'readonly',
    console: 'readonly',
    location: 'readonly',
    navigator: 'readonly',
    alert: 'readonly',
    confirm: 'readonly',
    setTimeout: 'readonly',
    clearTimeout: 'readonly',
    setInterval: 'readonly',
    clearInterval: 'readonly',
    fetch: 'readonly',
    URL: 'readonly',
};

// Loaded from node_modules by www/app/templates/default/footer.php.
const libraryGlobals = {
    $: 'readonly',
    jQuery: 'readonly',
    L: 'readonly',
    Chart: 'readonly',
    ChartZoom: 'readonly',
    luxon: 'readonly',
    moment: 'readonly',
    Cookies: 'readonly',
    List: 'readonly',
};

// Set by the inline <script> block in www/app/templates/default/footer.php.
// The dashboard type lists and cruise values are only defined on the pages
// that need them.
const footerGlobals = {
    siteRoot: 'readonly',
    cruise_name: 'readonly',
    lowering_name: 'readonly',
    cruiseID: 'readonly',
    cruiseDataDir: 'readonly',
    subPages: 'readonly',
    geoJSONTypes: 'readonly',
    tmsTypes: 'readonly',
    jsonTypes: 'readonly',
    jsonReversedYTypes: 'readonly',
    jsonReversedYInvertedTypes: 'readonly',
    jsonInvertedTypes: 'readonly',
    jsonProfileTypes: 'readonly',
};

// Defined in other template scripts that load before the pages using them.
const templateGlobals = {
    colors: 'readonly', // chartColors.js
    openvdmBaseLayers: 'readonly', // mapBaseLayers.js
    openvdmDefaultBaseLayer: 'readonly',
    openvdmOverlayLayers: 'readonly',
    openvdmFeaturePositions: 'readonly',
    openvdmPointMarker: 'readonly',
    openvdmFeaturePopup: 'readonly',
    openvdmProfileChartConfig: 'readonly', // dashboardCharts.js
    openvdmInvertTimeChart: 'readonly',
};

export default [
    {
        // Third-party SB Admin 2 theme script.
        ignores: ['www/app/templates/default/js/sb-admin-2.js'],
    },
    {
        files: [
            'www/app/templates/default/js/**/*.js',
            'www/app/templates/default/js/**/*.js.dist',
        ],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: 'script',
            globals: {
                ...browserGlobals,
                ...libraryGlobals,
                ...footerGlobals,
                ...templateGlobals,
            },
        },
        linterOptions: {
            reportUnusedDisableDirectives: 'error',
        },
        rules: bugRules,
    },
];
