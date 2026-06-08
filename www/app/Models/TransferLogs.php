<?php

namespace Models;
use Core\Model;


class TransferLogs extends Model {

    private $_warehouseModel;
    private $_transferLogDir;
    private $_cruiseID;

    public function __construct(){
        $this->_warehouseModel = new \Models\Warehouse();
        $this->_transferLogDir = $this->_warehouseModel->getTransferLogDir();
        $this->_cruiseID = $this->_warehouseModel->getCruiseID();
    }

    private function outputLogFilenames($files) {
        $returnArray = array();
        for($i = 0; $i < sizeof($files); $i++) {
            array_push($returnArray, $files[$i]);
        }
        return $returnArray;
    }

    private function outputLogFileSummary($files) {
        $returnArray = array();
        $date = '';

        for($i = 0; $i < sizeof($files); $i++) {
            if (file_exists($files[$i]) && is_readable($files[$i])) {
                $transferLogSummary = json_decode(file_get_contents($files[$i]));
                $filename = basename($files[$i], '.log');
                $filenameArray = explode("_", $filename);
                array_shift($filenameArray); // remove cruiseID prefix
                $date = array_pop($filenameArray);
                $collectionSystem = join("_", $filenameArray);

                if ($transferLogSummary === null) {
                    continue;
                }

                if (strcmp($date, "Exclude") === 0) {
                    $obj = (object) array('collectionSystemName' => $collectionSystem, 'errorFiles' => $transferLogSummary->exclude);
                    array_push($returnArray, $obj);
                } else {
                    $obj = (object) array('collectionSystemName' => $collectionSystem, 'date' => $date, 'newFiles' => $transferLogSummary->new, 'updatedFiles' => $transferLogSummary->updated);
                    array_push($returnArray, $obj);
                }
            }
        }

        if(strcmp($date, "Exclude") != 0) {
            if(is_array($returnArray) && sizeof($returnArray) > 0) {
                $sortArray = array();

                foreach($returnArray as $dataObject){
                    foreach($dataObject as $key=>$value){
                        if(!isset($sortArray[$key])){
                            $sortArray[$key] = array();
                        }
                        $sortArray[$key][] = $value;
                    }
                }

                $orderby = "date";

                array_multisort($sortArray[$orderby],SORT_DESC,$returnArray);
            }
        }

        return $returnArray;
    }

    public function getExcludeLogFilenames() {
        $files = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_*_Exclude.log");
        return $this->outputLogFilenames($files);
    }

    public function getExcludeLogsSummary() {
        $files = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_*_Exclude.log");
        return $this->outputLogFileSummary($files);
    }

    public function getShipboardLogFilenames($count = 0) {
        $files = preg_grep('#_SSDW_#', glob($this->_transferLogDir . "/" . $this->_cruiseID . "_*Z.log"), PREG_GREP_INVERT);
        if (is_array($files) && sizeof($files) > $count) {
            array_splice($files, 0, sizeof($files)-$count);
        }
        return $this->outputLogFilenames($files);
    }

    public function getShipboardLogsSummary($count = 0) {
        $fileList = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_*Z.log");
        $fileList = preg_grep('#_SSDW_#', $fileList, PREG_GREP_INVERT);
        array_multisort(array_map('filemtime', $files = $fileList), SORT_ASC, $files);
        if (is_array($files) && sizeof($files) > $count) {
            array_splice($files, 0, sizeof($files)-$count);
        }
        return $this->outputLogFileSummary($files);
    }

    public function getShipToShoreLogFilenames($count = 0) {
        $files = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_SSDW_*Z.log");
        if (is_array($files) && sizeof($files) > $count) {
            array_splice($files, 0, sizeof($files)-$count);
        }
        return $this->outputLogFilenames($files);
    }

    public function getShipToShoreLogsSummary($count = 0) {
        $fileList = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_SSDW_*Z.log");
        array_multisort(array_map('filemtime', $files = $fileList), SORT_ASC, $files);
        if (is_array($files) && sizeof($files) > $count) {
            array_splice($files, 0, sizeof($files)-$count);
        }
        return $this->outputLogFileSummary($files);
    }

    public function getExcludeLogFilenameByName($name) {
        $files = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_" . $name . "_Exclude.log");
        return $this->outputLogFilenames($files);
    }

    public function getExcludeLogSummaryByName($name) {
        $files = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_" . $name . "_Exclude.log");
        return $this->outputLogFileSummary($files);
    }

    public function getShipboardLogFilenamesByName($name, $count = 0) {
        $files = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_" . $name . "_*Z.log");
        if (is_array($files) && sizeof($files) > $count) {
            array_splice($files, 0, sizeof($files)-$count);
        }
        return $this->outputLogFilenames($files);
    }

    public function getShipboardLogsSummaryByName($name, $count = 0) {
        $files = glob($this->_transferLogDir . "/" . $this->_cruiseID . "_" . $name . "_*Z.log");
        if (is_array($files) && sizeof($files) > $count) {
            array_splice($files, 0, sizeof($files)-$count);
        }
        return $this->outputLogFileSummary($files);
    }
}
