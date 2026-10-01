<?php

namespace Models;
use Core\Model;

class DataDashboard extends Model {

    private $_tabs;
    private $_dashboardDataModel;

    public function __construct(){

        $this->_dashboardDataModel = new \Models\DashboardData();
        $this->_tabs = yaml_parse_file(DASHBOARD_CONF);
    }

    private function getAllDataTypes() {
        $dataTypes = array();
        foreach($this->_tabs as $tab) {
            foreach($tab['placeholderArray'] as $placeholder) {
                foreach($placeholder['dataArray'] as $data) {
                    array_push($dataTypes, $data['dataType']);
                }
            }
        }
        return array_unique($dataTypes, SORT_REGULAR);
    }

    private function getDataTypeByVisType($visType) {
        $dataTypes = array();
        foreach($this->_tabs as $tab) {
            foreach($tab['placeholderArray'] as $placeholder) {
                foreach($placeholder['dataArray'] as $data) {
                    if( strcmp($data['visType'], $visType) === 0 ) {
                        array_push($dataTypes, $data['dataType']);
                    }
                }
            }
        }
        return array_unique($dataTypes, SORT_REGULAR);
    }

    public function getJSONTypes() {
        return $this->getDataTypeByVisType('json');
    }

    public function getJSONReversedYTypes() {
        return $this->getDataTypeByVisType('json-reversedY');
    }

    public function getJSONReversedYInvertedTypes() {
        return $this->getDataTypeByVisType('json-reversedY-inverted');
    }

    public function getJSONInvertedTypes() {
        return $this->getDataTypeByVisType('json-inverted');
    }

    /**
     * Return the chart options of a json-profile data entry (#274).
     *
     * profileSeries may be a YAML list or a comma-separated string.
     *
     * @param array $dataObj A dataArray entry from datadashboard.yaml.
     * @return array 'depthSeries' (default 'Depth') and 'profileSeries'
     *     (a list of series labels, or null for all but the depth series).
     */
    public static function profileOptions(array $dataObj) {
        $profileSeries = $dataObj['profileSeries'] ?? null;
        if (is_string($profileSeries)) {
            $profileSeries = array_filter(array_map('trim', explode(',', $profileSeries)), 'strlen');
        }
        return array(
            'depthSeries' => (!empty($dataObj['depthSeries']) && is_string($dataObj['depthSeries'])) ? $dataObj['depthSeries'] : 'Depth',
            'profileSeries' => (is_array($profileSeries) && sizeof($profileSeries) > 0) ? array_values(array_map('strval', $profileSeries)) : null,
        );
    }

    /**
     * Return the data types shown as a depth profile on the main dashboard page (#274).
     *
     * A data type that a tab also charts against time keeps its time-series
     * tile there.
     *
     * @return array Data type => its profile options (see profileOptions()).
     */
    public function getJSONProfileTypes() {
        $timeSeriesTypes = array_merge($this->getJSONTypes(), $this->getJSONReversedYTypes(),
                                       $this->getJSONReversedYInvertedTypes(), $this->getJSONInvertedTypes());
        $profileTypes = array();
        foreach($this->_tabs as $tab) {
            foreach($tab['placeholderArray'] as $placeholder) {
                foreach($placeholder['dataArray'] as $data) {
                    if (strcmp($data['visType'], 'json-profile') === 0
                        && !isset($profileTypes[$data['dataType']])
                        && !in_array($data['dataType'], $timeSeriesTypes)) {
                        $profileTypes[$data['dataType']] = self::profileOptions($data);
                    }
                }
            }
        }
        return $profileTypes;
    }

    public function getGeoJSONTypes() {
        return $this->getDataTypeByVisType('geoJSON');
    }

    public function getTMSTypes() {
        return $this->getDataTypeByVisType('tms');
    }

    public function getSubPages() {
        $dataTypes = $this->getAllDataTypes();
        $subPages = array();
        foreach($dataTypes as $dataType) {
            foreach($this->_tabs as $tab) {
                foreach($tab['placeholderArray'] as $placeholder) {
                    foreach($placeholder['dataArray'] as $data) {
                        if( strcmp($data['dataType'], $dataType) === 0 ) {
                            $subPages[$dataType] = $tab['page'];
                            break;
                        }
                    }
                }
            }
        }
        return $subPages;
    }

    public function getDataDashboardTabs() {
        return $this->_tabs;
    }

    public function getDataDashboardTab($tabName) {
        foreach($this->_tabs as $tab) {

            if($tab['page'] == $tabName) {
                return $tab;
            }
        }
        return;
    }

}
?>
