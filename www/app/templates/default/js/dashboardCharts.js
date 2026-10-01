/**
 * Shared chart helpers for the data dashboard.
 *
 * - openvdmProfileChartConfig(): depth profiles (json-profile, #274). Depth
 *   runs down the vertical axis and one or more measured values across, each
 *   on its own x axis, with points joined in time order.
 * - openvdmInvertTimeChart(): turns a time-series chart on its side
 *   (json-inverted and json-reversedY-inverted, #275).
 *
 * Loaded automatically wherever the 'charts' script bundle is included (see
 * templates/default/footer.php), so the dashboard, lowering and main dashboard
 * scripts can call them.
 */

/* exported openvdmProfileChartConfig, openvdmInvertTimeChart */

/**
 * Build the Chart.js configuration for a depth profile.
 *
 * Each profile series is paired with the depth series by timestamp; points
 * without a depth or value at the same time are left out.
 *
 * @param {Array} data - Visualizer data: series of {label, unit, data: [[ms, value], ...]}.
 * @param {Object} [options]
 * @param {string} [options.depthSeries='Depth'] - Label of the series on the vertical axis.
 * @param {string[]} [options.profileSeries] - Labels of the series plotted across, in this order
 *     (default: all series except the depth series).
 * @param {boolean} [options.showAxes=true] - Show axes, titles and the legend;
 *     false for the main dashboard's thumbnails.
 * @returns {Object} {config: <Chart.js configuration>}, or {error: <message>}.
 */
function openvdmProfileChartConfig (data, options) {
    options = options || {};
    var depthLabel = options.depthSeries || 'Depth';
    var showAxes = options.showAxes !== false;

    if (!Array.isArray(data)) {
        return { error: (data && data.error) || 'No data' };
    }

    var depthSeries = data.find(function (series) { return series.label === depthLabel; });
    if (!depthSeries) {
        return { error: 'No "' + depthLabel + '" series in this data' };
    }

    var depthAt = new Map();
    depthSeries.data.forEach(function (point) {
        if (point[1] !== null) {
            depthAt.set(point[0], point[1]);
        }
    });

    // In the order profileSeries lists them, skipping labels not in the data
    var profileSeries = options.profileSeries ?
        options.profileSeries.map(function (label) {
            return data.find(function (series) { return series.label === label && label !== depthLabel; });
        }).filter(Boolean) :
        data.filter(function (series) { return series.label !== depthLabel; });
    if (profileSeries.length === 0) {
        return { error: 'No series to plot against "' + depthLabel + '"' };
    }

    var depthUnit = depthSeries.unit;
    var scales = {
        depth: {
            type: 'linear',
            axis: 'y',
            position: 'left',
            reverse: true,
            display: showAxes,
            title: { display: showAxes, text: depthLabel + ' (' + depthUnit + ')' }
        }
    };

    var datasets = profileSeries.map(function (series, i) {
        var color = colors[i % colors.length];
        var axisID = 'x' + i;

        scales[axisID] = {
            type: 'linear',
            axis: 'x',
            position: (i % 2) ? 'top' : 'bottom',
            display: showAxes,
            ticks: { color: color },
            title: { display: showAxes, text: series.label + ' (' + series.unit + ')', color: color },
            grid: { drawOnChartArea: i === 0 }
        };

        return {
            label: series.label + ' (' + series.unit + ')',
            data: series.data.filter(function (point) {
                return point[1] !== null && depthAt.has(point[0]);
            }).map(function (point) {
                return { x: point[1], y: depthAt.get(point[0]), t: point[0] };
            }),
            xAxisID: axisID,
            yAxisID: 'depth',
            showLine: true,
            borderColor: color,
            backgroundColor: color,
            borderWidth: 1.5,
            pointRadius: 0
        };
    });

    return {
        config: {
            type: 'scatter',
            data: { datasets: datasets },
            options: {
                animation: false,
                responsive: true,
                maintainAspectRatio: false,
                scales: scales,
                interaction: showAxes ? { mode: 'nearest', axis: 'xy', intersect: false } : { mode: 'none' },
                plugins: {
                    legend: {
                        display: showAxes,
                        position: 'bottom',
                        // Hide a series together with its x axis
                        onClick: function (event, legendItem, legend) {
                            var chart = legend.chart;
                            var dataset = chart.data.datasets[legendItem.datasetIndex];
                            dataset.hidden = !dataset.hidden;
                            chart.options.scales[dataset.xAxisID].display = !dataset.hidden;
                            chart.update();
                        }
                    },
                    tooltip: {
                        callbacks: {
                            title: function (items) {
                                return luxon.DateTime.fromMillis(items[0].raw.t, { zone: 'UTC' }).toFormat('yyyy-LL-dd HH:mm:ss') + ' UTC';
                            },
                            label: function (item) {
                                return item.dataset.label + ': ' + item.raw.x + ' at ' + item.raw.y + ' ' + depthUnit;
                            }
                        }
                    }
                }
            }
        }
    };
}

/**
 * Turn a time-series chart configuration on its side (#275).
 *
 * Time moves to a vertical axis on the left, earliest at the top, and each
 * series' value axis runs across (alternating bottom/top), as the inverted
 * charts did before the move to Chart.js. Zoom and pan follow the time axis.
 *
 * @param {Object} config - A Chart.js 'line' configuration as the dashboard
 *     scripts build it: time scale 'x', and one value scale per dataset,
 *     named by the dataset's yAxisID, with {x: time, y: value} points.
 * @returns {Object} The same configuration, changed in place.
 */
function openvdmInvertTimeChart (config) {
    var scales = config.options.scales;
    var timeScale = scales.x;
    delete scales.x;
    timeScale.axis = 'y';
    timeScale.position = 'left';
    timeScale.reverse = true;
    scales.time = timeScale;

    config.data.datasets.forEach(function (dataset, i) {
        var valueScale = scales[dataset.yAxisID];
        valueScale.axis = 'x';
        valueScale.position = (i % 2) ? 'top' : 'bottom';
        dataset.xAxisID = dataset.yAxisID;
        dataset.yAxisID = 'time';
        dataset.data = dataset.data.map(function (point) {
            return { x: point.y, y: point.x };
        });
    });
    config.options.indexAxis = 'y';

    var plugins = config.options.plugins || {};
    if (plugins.legend && plugins.legend.onClick) {
        // Hide a series together with its value axis
        plugins.legend.onClick = function (event, legendItem, legend) {
            var chart = legend.chart;
            var dataset = chart.data.datasets[legendItem.datasetIndex];
            dataset.hidden = !dataset.hidden;
            chart.options.scales[dataset.xAxisID].display = !dataset.hidden;
            chart.update();
        };
    }
    if (plugins.zoom) {
        if (plugins.zoom.limits && plugins.zoom.limits.x) {
            plugins.zoom.limits = { y: plugins.zoom.limits.x };
        }
        ['zoom', 'pan'].forEach(function (key) {
            if (plugins.zoom[key] && plugins.zoom[key].mode === 'x') {
                plugins.zoom[key].mode = 'y';
            }
        });
    }
    return config;
}
