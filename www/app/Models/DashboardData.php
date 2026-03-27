<?php

namespace Models;
use Core\Model;


class DashboardData extends Model {

    // const CONFIG_FN = 'ovdmConfig.json';
    // const MANIFEST_FN = 'manifest.json';

    private $_cruiseDataDir;
    private $_manifestObj;
    private $_cruiseID;
    private $_warehouseModel;

    public function __construct($cruiseID = null) {
        $this->_warehouseModel = new \Models\Warehouse();
        $this->_cruiseDataDir = $this->_warehouseModel->getShipboardDataWarehouseBaseDir();
        $this->_cruiseConfigFn = $this->_warehouseModel->getCruiseConfigFn();
        $this->_dataDashboardManifestFn = $this->_warehouseModel->getDataDashboardManifestFn();
        $this->_manifestObj = null;
        if ($cruiseID == null){
            $this->setCruiseID($this->_warehouseModel->getCruiseID());
        } else {
            $this->setCruiseID($cruiseID);
        }

    }

    public function getDashboardManifest() {
        return $this->_manifestObj;
    }

    private function buildManifestObj(){

        $results = array();

        if($this->_manifestObj === null && $this->_cruiseID != null) {

            //Get the list of directories
            if (is_dir($this->_cruiseDataDir . DIRECTORY_SEPARATOR . $this->_cruiseID))
            {
                //Check each Directory for the OpenVDM config file
                $cruiseList = scandir($this->_cruiseDataDir . DIRECTORY_SEPARATOR . $this->_cruiseID);
                foreach ($cruiseList as $cruiseKey => $cruiseValue){
                    if (in_array($cruiseValue,array($this->_cruiseConfigFn))){
                        $ovdmConfigContents = file_get_contents($this->_cruiseDataDir . DIRECTORY_SEPARATOR . $this->_cruiseID . DIRECTORY_SEPARATOR . $this->_cruiseConfigFn);
                        $ovdmConfigJSON = json_decode($ovdmConfigContents,true);
                        //Get the the directory that holds the DashboardData
                        if (array_key_exists('extraDirectoriesConfig', $ovdmConfigJSON)){	
                           for($i = 0; $i < sizeof($ovdmConfigJSON['extraDirectoriesConfig']); $i++){
                                if(strcmp($ovdmConfigJSON['extraDirectoriesConfig'][$i]['name'], 'Dashboard_Data') === 0){
                                    $dataDashboardList = scandir($this->_cruiseDataDir . DIRECTORY_SEPARATOR . $this->_cruiseID . DIRECTORY_SEPARATOR . $ovdmConfigJSON['extraDirectoriesConfig'][$i]['destDir']);
                                    foreach ($dataDashboardList as $dataDashboardKey => $dataDashboardValue){
                                        //If a manifest file is found, add CruiseID to output
                                        if (in_array($dataDashboardValue,array($this->_dataDashboardManifestFn))){
                                            $manifestContents = file_get_contents($this->_cruiseDataDir . DIRECTORY_SEPARATOR . $this->_cruiseID . DIRECTORY_SEPARATOR . $ovdmConfigJSON['extraDirectoriesConfig'][$i]['destDir'] . DIRECTORY_SEPARATOR . $this->_dataDashboardManifestFn);
					    $this->_manifestObj = json_decode($manifestContents,true);
                                            break;
                                        }
                                    }
                                    break;
                                }
                            }
                            break;
                        }
		    }
                }
            }
        }
    }

    public function getDashboardDataTypes() {

        $dataTypes = array();
        if (is_array($this->_manifestObj) && sizeof($this->_manifestObj) > 0) {
            foreach ($this->_manifestObj as $manifestItem){
                foreach ($manifestItem as $manifestItemKey => $manifestItemValue){
                    if (strcmp($manifestItemKey, 'type') === 0){
                        if(!in_array($manifestItemValue,$dataTypes)){
                            $dataTypes[] = $manifestItemValue;
                            continue;
                        }
                    }
                }
            }
            sort($dataTypes);
        }
        return $dataTypes;
    }

    public function getDashboardObjectsByTypes($dataType) {

        $dataObjects = array();
        if(is_array($this->_manifestObj) && sizeof($this->_manifestObj) > 0) {
            foreach ($this->_manifestObj as $manifestItem) {
                foreach ($manifestItem as $manifestItemKey => $manifestItemValue){
                    if (strcmp($manifestItemKey, 'type') === 0){
                        if(strcmp($manifestItemValue, $dataType) === 0) {
                            $dataObjects[] = $manifestItem;
                            continue;
                        }
                    }
                }
            }
        }

        if(is_array($dataObjects) && sizeof($dataObjects) > 0) {
            $sortArray = array();

            foreach($dataObjects as $dataObject){
                foreach($dataObject as $key=>$value){
                    if(!isset($sortArray[$key])){
                        $sortArray[$key] = array();
                    }
                    $sortArray[$key][] = $value;
                }
            }

            $orderby = "dd_json"; //change this to whatever key you want from the array

            array_multisort($sortArray[$orderby],SORT_ASC,$dataObjects);
        }
        return $dataObjects;
    }

    private function extractSection($obj, $section, $dataType = null) {
        if (!$obj) {
            return null;
        }

        // OLD FORMAT
        if (isset($obj->$section)) {
            return $obj->$section;
        }

        // NEW FORMAT with known dataType
        if ($dataType !== null && isset($obj->$dataType->$section)) {
            return $obj->$dataType->$section;
        }

        // NEW FORMAT fallback: first available dataType
        // foreach ($obj as $dataset) {
        //     if (isset($dataset->$section)) {
        //         return $dataset->$section;
        //     }
        // }
        print($dataType);

        return null;
    }


    public function getDashboardObjectContentsByJsonName($dd_json){
        $dataObjectContents = '';

        $foundIt = false;
        foreach (($this->_manifestObj ?? []) as $manifestItem) {
            foreach ($manifestItem as $manifestItemKey => $manifestItemValue){
                if (strcmp($manifestItemKey, 'dd_json') === 0){
                    if(strcmp($manifestItemValue, $dd_json) === 0) {
                        $dataObjectContents = file_get_contents($this->_cruiseDataDir . DIRECTORY_SEPARATOR . $dd_json);
                        $foundIt = true;
                        break;
                    }
                }
            }
            if($foundIt) {
                break;
            }
        }
        return $dataObjectContents;
    }

    public function getDashboardObjectContentsByRawName($raw_data){
        $dataObjectContents = '';

        $foundIt = false;
        foreach (($this->_manifestObj ?? []) as $manifestItem) {
            foreach ($manifestItem as $manifestItemKey => $manifestItemValue){
                if (strcmp($manifestItemKey, 'raw_data') === 0){
                    if(strcmp($manifestItemValue, $raw_data) === 0) {
                        $dataObjectContents = file_get_contents($this->_cruiseDataDir . DIRECTORY_SEPARATOR . $manifestItem['dd_json']);
                        $foundIt = true;
                        break;
                    }
                }
            }
            if($foundIt) {
                break;
            }
        }
        return $dataObjectContents;
    }

    public function getDashboardObjectDataTypeByJsonName($dd_json){
        $dataType = '';

        foreach (($this->_manifestObj ?? []) as $manifestItem) {
            if (strcmp($manifestItem['dd_json'], $dd_json) === 0) {
                $dataType = $manifestItem['type'];
                break;
            }
        }
        return $dataType;
    }

    public function getDashboardObjectDataTypeByRawName($raw_data){
        $dataType = '';

        foreach (($this->_manifestObj ?? []) as $manifestItem) {
            if (strcmp($manifestItem['raw_data'], $raw_data) === 0) {
                $dataType = $manifestItem['type'];
                break;
            }
        }
        return $dataType;
    }

    public function getDashboardObjectVisualizerDataByJsonName($dd_json, $dataType){
        // $dataObjectContentsOBJ = json_decode($this->getDashboardObjectContentsByJsonName($dd_json));
        // return $dataObjectContentsOBJ->visualizerData;
        $json = $this->getDashboardObjectContentsByJsonName($dd_json);
        $obj  = json_decode($json);

        // $dataType = $this->getDashboardObjectDataTypeByJsonName($dd_json);

        return $this->extractSection($obj, 'visualizerData', $dataType);
    }

    public function getDashboardObjectVisualizerDataByRawName($raw_data, $dataType){
        // $dataObjectContentsOBJ = json_decode($this->getDashboardObjectContentsByRawName($raw_data));
        // return $dataObjectContentsOBJ->visualizerData;
        $json = $this->getDashboardObjectContentsByRawName($raw_data);
        $obj  = json_decode($json);

        // $dataType = $this->getDashboardObjectDataTypeByRawName($raw_data);

        return $this->extractSection($obj, 'visualizerData', $dataType);
    }

    public function getDashboardObjectStatsByJsonName($dd_json, $dataType){
        // $dataObjectContentsOBJ = json_decode($this->getDashboardObjectContentsByJsonName($dd_json));
        // return $dataObjectContentsOBJ->stats;
        $json = $this->getDashboardObjectContentsByJsonName($dd_json);
        $obj  = json_decode($json);

        // $dataType = $this->getDashboardObjectDataTypeByJsonName($dd_json);

        return $this->extractSection($obj, 'stats', $dataType);
    }

    public function getDashboardObjectStatsByRawName($raw_data, $dataType){
        // $dataObjectContentsOBJ = json_decode($this->getDashboardObjectContentsByRawName($raw_data));
        // return $dataObjectContentsOBJ->stats;
        $json = $this->getDashboardObjectContentsByRawName($raw_data);
        $obj  = json_decode($json);

        // $dataType = $this->getDashboardObjectDataTypeByRawName($raw_data);

        return $this->extractSection($obj, 'stats', $dataType);
    }

    public function getDashboardObjectQualityTestsByJsonName($dd_json, $dataType){
        // $dataObjectContentsOBJ = json_decode($this->getDashboardObjectContentsByJsonName($dd_json));
        // return $dataObjectContentsOBJ->qualityTests;
        $json = $this->getDashboardObjectContentsByJsonName($dd_json);
        $obj  = json_decode($json);

        // $dataType = $this->getDashboardObjectDataTypeByJsonName($dd_json);

        return $this->extractSection($obj, 'qualityTests', $dataType);
    }

    public function getDashboardObjectQualityTestsByRawName($raw_data, $dataType){
        // $dataObjectContentsOBJ = json_decode($this->getDashboardObjectContentsByRawName($raw_data));
        // return $dataObjectContentsOBJ->qualityTests;
        $json = $this->getDashboardObjectContentsByRawName($raw_data);
        $obj  = json_decode($json);

        // $dataType = $this->getDashboardObjectDataTypeByRawName($raw_data);

        return $this->extractSection($obj, 'qualityTests', $dataType);
    }

    public function getCruiseID(){
        return $this->_cruiseID;
    }

    public function setCruiseID($cruiseID) {
        $this->_cruiseID = $cruiseID;
        $this->buildManifestObj();
    }

    public function getDataTypeStats($dataType) {

        $return = array((object)array());

        $dataObjects = $this->getDashboardObjectsByTypes($dataType);

        if(is_array($dataObjects) && sizeof($dataObjects) === 0){
            $return[0]->error = 'No objects found of type ' . $dataType;
            return $return;
        }

        $dataTypeStatsObj = array((object)array());

        $init = false;
        for ($i=0; $i < sizeof($dataObjects); $i++) {
            $dataFileStatsObj = $this->getDashboardObjectStatsByJsonName($dataObjects[$i]['dd_json'], $dataType);

            if($dataFileStatsObj[0]->error) {
                $return[0]->error = $dataFileStatsObj[0]->error;
                return $return;
            } else {
                if(!$init){
                    $dataTypeStatsObj = $dataFileStatsObj;
                    $init = true;
                } else {
                    for ($j=0; $j < sizeof($dataFileStatsObj); $j++) {
                        switch ($dataFileStatsObj[$j]->statType){
                            case "timeBounds":
                                #Start Time
                                if($dataFileStatsObj[$j]->statValue[0] < $dataTypeStatsObj[$j]->statValue[0]){
                                    $dataTypeStatsObj[$j]->statValue[0] = $dataFileStatsObj[$j]->statValue[0];
                                }

                                #End Time
                                if($dataFileStatsObj[$j]->statValue[1] > $dataTypeStatsObj[$j]->statValue[1]){
                                    $dataTypeStatsObj[$j]->statValue[1] = $dataFileStatsObj[$j]->statValue[1];
                                }

                                break;

                            case "geoBounds":
                                #North
                                if($dataFileStatsObj[$j]->statValue[0] > $dataTypeStatsObj[$j]->statValue[0]){
                                    $dataTypeStatsObj[$j]->statValue[0] = $dataFileStatsObj[$j]->statValue[0];
                                }

                                #East
                                if($dataFileStatsObj[$j]->statValue[1] < $dataTypeStatsObj[$j]->statValue[1]){
                                    $dataTypeStatsObj[$j]->statValue[1] = $dataFileStatsObj[$j]->statValue[1];
                                }

                                #South
                                if($dataFileStatsObj[$j]->statValue[2] < $dataTypeStatsObj[$j]->statValue[2]){
                                    $dataTypeStatsObj[$j]->statValue[2] = $dataFileStatsObj[$j]->statValue[2];
                                }

                                #West
                                if($dataFileStatsObj[$j]->statValue[3] < $dataTypeStatsObj[$j]->statValue[3]){
                                    $dataTypeStatsObj[$j]->statValue[3] = $dataFileStatsObj[$j]->statValue[3];
                                }

                                break;

                            case "bounds":
                                #Min
                                if($dataFileStatsObj[$j]->statValue[0] < $dataTypeStatsObj[$j]->statValue[0]){
                                    $dataTypeStatsObj[$j]->statValue[0] = $dataFileStatsObj[$j]->statValue[0];
                                }

                                #Max
                                if($dataFileStatsObj[$j]->statValue[1] > $dataTypeStatsObj[$j]->statValue[1]){
                                    $dataTypeStatsObj[$j]->statValue[1] = $dataFileStatsObj[$j]->statValue[1];
                                }

                                break;

                            case "totalValue":
                                #Sum values
                                $dataTypeStatsObj[$j]->statValue[0] += $dataFileStatsObj[$j]->statValue[0];

                                break;

                            case "valueValidity":
                                #Sum values
                                $dataTypeStatsObj[$j]->statValue[0] += $dataFileStatsObj[$j]->statValue[0];

                                $dataTypeStatsObj[$j]->statValue[1] += $dataFileStatsObj[$j]->statValue[1];

                                break;
                            case "rowValidity":
                                #Sum values
                                $dataTypeStatsObj[$j]->statValue[0] += $dataFileStatsObj[$j]->statValue[0];

                                $dataTypeStatsObj[$j]->statValue[1] += $dataFileStatsObj[$j]->statValue[1];

                                break;

                        }
                    }
                }
            }
        }

        $fileCountStat = new \stdClass();
        $fileCountStat->statType = "totalValue";
        $fileCountStat->statName = "File Count";
        $fileCountStat->statUnit = "files";
        $fileCountStat->statValue = array();
        $fileCountStat->statValue[0] = sizeof($dataObjects);

        array_unshift($dataTypeStatsObj, $fileCountStat);

        $return = $dataTypeStatsObj;
        return $return;
    }
}
