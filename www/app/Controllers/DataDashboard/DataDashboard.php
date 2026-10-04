<?php

namespace Controllers\DataDashboard;
use Core\Controller;
use Core\Router;
use Core\View;
use Helpers\Session;
use Helpers\Url;

class DataDashboard extends Controller {

    private $_warehouseModel;
    private $_dashboardDataModel;
    private $_dataDashboardModel;

    public function __construct(){

        $this->_warehouseModel = new \Models\Warehouse();
        $this->_dashboardDataModel = new \Models\DashboardData();
        $this->_dataDashboardModel = new \Models\DataDashboard();
    }

    public function index(){

        $data['title'] = 'Data Dashboard';
        $data['page'] = 'main';
        $data['cruiseID'] = $this->_warehouseModel->getCruiseID();
        $data['customDataDashboardTabs'] = $this->_dataDashboardModel->getDataDashboardTabs();
        $data['systemStatus'] = $this->_warehouseModel->getSystemStatus();
        $data['dataWarehouseApacheDir'] = $this->_warehouseModel->getShipboardDataWarehouseApacheDir();
        $data['css'] = array('leaflet');
        $data['javascript'] = array('dataDashboardMain', 'dataDashboardMainCustom', 'leaflet', 'charts');
        $data['dataTypes'] = $this->_dashboardDataModel->getDashboardDataTypes();
        $data['geoJSONTypes'] = $this->_dataDashboardModel->getGeoJSONTypes();
        $data['tmsTypes'] = $this->_dataDashboardModel->getTMSTypes();
        $data['jsonTypes'] = $this->_dataDashboardModel->getJSONTypes();
        $data['jsonReversedYTypes'] = $this->_dataDashboardModel->getJSONReversedYTypes();
        $data['jsonReversedYInvertedTypes'] = $this->_dataDashboardModel->getJSONReversedYInvertedTypes();
        $data['jsonInvertedTypes'] = $this->_dataDashboardModel->getJSONInvertedTypes();
        $data['jsonProfileTypes'] = $this->_dataDashboardModel->getJSONProfileTypes();

        $data['subPages'] = $this->_dataDashboardModel->getSubPages();

        View::renderTemplate('header', $data);
        View::renderTemplate('dataDashboardHeader', $data);
        if( is_array($data['dataTypes']) && sizeof($data['dataTypes']) > 0){
            View::render('DataDashboard/main', $data);
        } else {
            View::render('DataDashboard/noData', $data);
        }
        View::renderTemplate('footer', $data);
    }

    public function customTab($tabName) {

        $tab = $this->_dataDashboardModel->getDataDashboardTab($tabName);
        if ($tab === null) {
            header('Location: ' . DIR . 'dataDashboard');
            exit;
        }
        $data['title'] = $tab['title'];
        $data['page'] = $tabName;
        $data['cruiseID'] = $this->_warehouseModel->getCruiseID();
        $data['loweringID'] = $this->_warehouseModel->getLoweringID();
        $data['loweringIDs'] = $this->_warehouseModel->getLowerings();
        $data['customDataDashboardTabs'] = $this->_dataDashboardModel->getDataDashboardTabs();
        $data['systemStatus'] = $this->_warehouseModel->getSystemStatus();
        $data['dataWarehouseApacheDir'] = $this->_warehouseModel->getShipboardDataWarehouseApacheDir();

        $data['css'] = array();
        if (!empty($tab['cssArray']) && is_array($tab['cssArray']) && sizeof($tab['cssArray'])>0) {
            foreach ($tab['cssArray'] as $cssFile) {
                array_push($data['css'], $cssFile);
            }
        }

        $data['javascript'] = array();
        if (!empty($tab['jsArray']) && is_array($tab['jsArray']) && sizeof($tab['jsArray'])>0) {
            foreach ($tab['jsArray'] as $jsFile) {
                array_push($data['javascript'], $jsFile);
            }
        }

        $data['placeholders'] = array();
        if (!empty($tab['placeholderArray']) && is_array($tab['placeholderArray']) && sizeof($tab['placeholderArray'])>0) {
            foreach ($tab['placeholderArray'] as $placeholder) {
                $placeholder['dataFiles'] = array();
                foreach ($placeholder['dataArray'] as $k => $dataObj) {
                    if (($dataObj['visType'] ?? '') === 'json-profile') {
                        $placeholder['dataArray'][$k]['profileOptions'] = \Models\DataDashboard::profileOptions($dataObj);
                    }
                    $objects = $this->_dashboardDataModel->getDashboardObjectsByTypes($dataObj['dataType']);
                    array_push($placeholder['dataFiles'], $objects);
                }
                array_push($data['placeholders'], $placeholder);
            }
        }

        $noDataFiles = true;
        for($i = 0; $i < sizeof($data['placeholders']); $i++) {
            for($j = 0; $j < sizeof($data['placeholders'][$i]['dataFiles']); $j++) {
                if(is_array($data['placeholders'][$i]['dataFiles'][$j]) && sizeof($data['placeholders'][$i]['dataFiles'][$j]) > 0) {
                    $noDataFiles = false;
                    break;
                }
            }

            if(!$noDataFiles) {
                break;
            }
        }

        View::renderTemplate('header', $data);
        View::renderTemplate('dataDashboardHeader', $data);

        if ($noDataFiles) {
            View::render('DataDashboard/noData', $data);
        } else {
            View::render('DataDashboard/' . $tab['view'], $data);
        }
        View::renderTemplate('footer', $data);

    }

    /**
     * Fill in the Data Quality tab's data types, their files, and each file's
     * quality tests and stats.
     *
     * A file with neither quality tests nor stats is left out, and so is a
     * data type with no files left (#310). Missing tests or stats are empty
     * arrays.
     *
     * @param array $data The view data, updated in place.
     */
    private function loadDataQuality(&$data) {
        $data['dataTypes'] = array();
        $data['dataObjects'] = array();
        $data['dataObjectsQualityTests'] = array();
        $data['dataObjectsStats'] = array();

        foreach ($this->_dashboardDataModel->getDashboardDataTypes() as $dataType) {
            $objects = array();
            $qualityTests = array();
            $stats = array();
            foreach ($this->_dashboardDataModel->getDashboardObjectsByTypes($dataType) as $object) {
                $objectQualityTests = $this->_dashboardDataModel->getDashboardObjectQualityTestsByJsonName($object['dd_json'], $dataType);
                $objectStats = $this->_dashboardDataModel->getDashboardObjectStatsByJsonName($object['dd_json'], $dataType);
                $objectQualityTests = is_array($objectQualityTests) ? $objectQualityTests : array();
                $objectStats = is_array($objectStats) ? $objectStats : array();
                if (empty($objectQualityTests) && empty($objectStats)) {
                    continue;
                }
                $objects[] = $object;
                $qualityTests[] = $objectQualityTests;
                $stats[] = $objectStats;
            }
            if (empty($objects)) {
                continue;
            }
            $data['dataTypes'][] = $dataType;
            $data['dataObjects'][] = $objects;
            $data['dataObjectsQualityTests'][] = $qualityTests;
            $data['dataObjectsStats'][] = $stats;
        }
    }

    public function dataQuality(){

        $data['title'] = 'Data Quality';
        $data['page'] = 'dataQuality';
        $data['cruiseID'] = $this->_warehouseModel->getCruiseID();
        $data['customDataDashboardTabs'] = $this->_dataDashboardModel->getDataDashboardTabs();
        $data['systemStatus'] = $this->_warehouseModel->getSystemStatus();
        $data['dataWarehouseApacheDir'] = $this->_warehouseModel->getShipboardDataWarehouseApacheDir();
        $data['javascript'] = array('dataDashboardQuality');
        $this->loadDataQuality($data);
        $data['stats'] = null;

        View::renderTemplate('header', $data);
        View::renderTemplate('dataDashboardHeader', $data);

        if( is_array($data['dataTypes']) && sizeof($data['dataTypes']) > 0) {
            View::render('DataDashboard/dataQuality', $data);
        } else {
            View::render('DataDashboard/noData', $data);
        }
        View::renderTemplate('footer', $data);
    }

    public function dataQualityShowFileStats($dataType, $rawData){

        $data['title'] = 'Data Quality';
        $data['page'] = 'dataQuality';
        $data['cruiseID'] = $this->_warehouseModel->getCruiseID();
        $data['customDataDashboardTabs'] = $this->_dataDashboardModel->getDataDashboardTabs();
        $data['systemStatus'] = $this->_warehouseModel->getSystemStatus();
        $data['javascript'] = array('dataDashboardQuality');
        $data['dataWarehouseApacheDir'] = $this->_warehouseModel->getShipboardDataWarehouseApacheDir();
        $this->loadDataQuality($data);

        $data['statsTitle'] = array_pop(explode("/", $rawData));
        $data['statsDataType'] = $this->_dashboardDataModel->getDashboardObjectDataTypeByRawName($rawData, $dataType);
        $data['stats'] = $this->_dashboardDataModel->getDashboardObjectStatsByRawName($rawData, $dataType);

        View::renderTemplate('header', $data);
        View::renderTemplate('dataDashboardHeader', $data);

        View::render('DataDashboard/dataQuality', $data);
        View::renderTemplate('footer', $data);
    }

    public function dataQualityShowDataTypeStats($dataType){

        $data['title'] = 'Data Quality';
        $data['page'] = 'dataQuality';
        $data['cruiseID'] = $this->_warehouseModel->getCruiseID();
        $data['customDataDashboardTabs'] = $this->_dataDashboardModel->getDataDashboardTabs();
        $data['systemStatus'] = $this->_warehouseModel->getSystemStatus();
        $data['javascript'] = array('dataDashboardQuality');
        $data['dataWarehouseApacheDir'] = $this->_warehouseModel->getShipboardDataWarehouseApacheDir();
        $this->loadDataQuality($data);

        $data['statsTitle'] = $dataType;
        $data['statsDataType'] = $dataType;
        $data['stats'] = $this->_dashboardDataModel->getDataTypeStats($dataType);

        View::renderTemplate('header', $data);
        View::renderTemplate('dataDashboardHeader', $data);

        View::render('DataDashboard/dataQuality', $data);
        View::renderTemplate('footer', $data);
    }

}
