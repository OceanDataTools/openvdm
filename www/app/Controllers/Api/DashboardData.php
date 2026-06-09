<?php
/*
 * api/dashboardData - RESTful api interface to dashboard data objects.
 *
 * @license   https://opensource.org/licenses/MIT
 * @author Webb Pinner - webbpinner@gmail.com
 * @version 2.9
 * @date 2022-07-01
*/

namespace Controllers\Api;
use Core\Controller;

class DashboardData extends Controller {

    private $_model;

    public function __construct(){

        $this->_model = new \Models\DashboardData();
    }

    public function getCruises() {
        $cruiseModel = new \Models\Cruises();
        echo json_encode($cruiseModel->getCruises());
    }

    public function getDashboardDataTypes($cruiseID) {
        $this->_model->setCruiseID($cruiseID);
        echo json_encode($this->_model->getDashboardDataTypes($dataType));
    }

    public function getDataObjectsByType($cruiseID, $dataType){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectList = $this->_model->getDashboardObjectsByTypes($dataType);
        if(is_array($dataObjectList) && sizeof($dataObjectList) > 0) {
            echo json_encode($dataObjectList);
        } else {
            echo json_encode(array());
        }
    }

    public function getLatestDataObjectByType($cruiseID, $dataType){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectList = $this->_model->getDashboardObjectsByTypes($dataType);
        if(is_array($dataObjectList) && sizeof($dataObjectList) > 0) {
            echo json_encode(array($dataObjectList[sizeof($dataObjectList)-1]));
        } else {
            echo json_encode(array());
        }
    }

    public function getLatestVisualizerDataByType($cruiseID, $dataType){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectList = $this->_model->getDashboardObjectsByTypes($dataType);
        if(is_array($dataObjectList) && sizeof($dataObjectList) > 0) {
            $lastDataObject = $dataObjectList[sizeof($dataObjectList)-1];
            //echo $lastDataObject['dd_json'];
            echo json_encode($this->_model->getDashboardObjectVisualizerDataByJsonName($lastDataObject['dd_json'], $dataType));
        } else {
            echo json_encode(array());
        }
    }

    public function getLatestStatsByType($cruiseID, $dataType){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectList = $this->_model->getDashboardObjectsByTypes($dataType);
        if(is_array($dataObjectList) && sizeof($dataObjectList) > 0) {
            $lastDataObject = $dataObjectList[sizeof($dataObjectList)-1];
            //echo $lastDataObject['dd_json'];
            echo json_encode($this->_model->getDashboardObjectStatsByJsonName($lastDataObject['dd_json'], $dataType));
        } else {
            echo json_encode(array());
        }
    }

    public function getLatestQualityTestsByType($cruiseID, $dataType){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectList = $this->_model->getDashboardObjectsByTypes($dataType);
        if(is_array($dataObjectList) && sizeof($dataObjectList) > 0) {
            $lastDataObject = $dataObjectList[sizeof($dataObjectList)-1];
            //echo $lastDataObject['dd_json'];
            echo json_encode($this->_model->getDashboardObjectQualityTestsByJsonName($lastDataObject['dd_json'], $dataType));
        } else {
            echo json_encode(array());
        }
    }

    public function getDashboardObjectVisualizerDataByJsonName($cruiseID, $dataType, $ddJSON){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectVisualizerData = $this->_model->getDashboardObjectVisualizerDataByJsonName($ddJSON, $dataType);
        if(is_array($dataObjectVisualizerData) && sizeof($dataObjectVisualizerData) > 0) {
            echo json_encode($dataObjectVisualizerData);
        } else {
            echo json_encode(array());
        }
    }

    public function getDashboardObjectVisualizerDataByRawName($cruiseID, $dataType, $rawData){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectVisualizerData = $this->_model->getDashboardObjectVisualizerDataByRawName($rawData, $dataType);
        if(is_array($dataObjectVisualizerData) && sizeof($dataObjectVisualizerData) > 0) {
            echo json_encode($dataObjectVisualizerData);
        } else {
            echo json_encode(array());
        }
    }

    public function getDashboardObjectStatsByJsonName($cruiseID, $dataType, $ddJSON){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectStats = $this->_model->getDashboardObjectStatsByJsonName($ddJSON, $dataType);
        if(is_array($dataObjectStats) && sizeof($dataObjectStats) > 0) {
            echo json_encode($dataObjectStats);
        } else {
            echo json_encode(array());
        }
    }

    public function getDashboardObjectStatsByRawName($cruiseID, $dataType, $rawData){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectStats = $this->_model->getDashboardObjectStatsByRawName($rawData, $dataType);
        if(is_array($dataObjectStats) && sizeof($dataObjectStats) > 0) {
            echo json_encode($dataObjectStats);
        } else {
            echo json_encode(array());
        }
    }

    public function getDashboardObjectStatsByDataType($cruiseID, $dataType){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectStats = $this->_model->getDataTypeStats($dataType);
        if(is_array($dataObjectStats) && sizeof($dataObjectStats) > 0) {
            echo json_encode($dataObjectStats);
        } else {
            echo json_encode(array());
        }
    }

    public function getDashboardObjectQualityTestsByJsonName($cruiseID, $dataType, $ddJSON){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectQualityTests = $this->_model->getDashboardObjectQualityTestsByJsonName($ddJSON, $dataType);
        if(is_array($dataObjectQualityTests) && sizeof($dataObjectQualityTests) > 0) {
            echo json_encode($dataObjectQualityTests);
        } else {
            echo json_encode(array());
        }
    }

    public function getDashboardObjectQualityTestsByRawName($cruiseID, $dataType, $rawData){
        $this->_model->setCruiseID($cruiseID);
        $dataObjectQualityTests = $this->_model->getDashboardObjectQualityTestsByRawName($rawData, $dataType);
        if(is_array($dataObjectQualityTests) && sizeof($dataObjectQualityTests) > 0) {
            echo json_encode($dataObjectQualityTests);
        } else {
            echo json_encode(array());
        }
    }
}
