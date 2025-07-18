<?php

namespace models;
use Core\Model;

class Warehouse extends Model {
    
    // const CONFIG_FN = 'ovdmConfig.json';
    // const LOWERING_CONFIG_FN = 'loweringConfig.json';
    // const MANIFEST_FN = 'manifest.json';

    public function getFreeSpace() {
        $baseDir = $this->getShipboardDataWarehouseBaseDir();
        if (is_dir($baseDir)){
            $data['freeSpace'] = disk_free_space($baseDir);
        } else {
            $data['error'] = '(getFreeSpace) Base Directory: ' . $baseDir . ' is not a directory';            
        }
        
        return $data;
    }
    

    public function getTotalSpace() {
        $baseDir = $this->getShipboardDataWarehouseBaseDir();
        if (is_dir($baseDir)){
            $data['totalSpace'] = disk_total_space($baseDir);
        } else {
            $data['error'] = '(getFreeSpace) Base Directory: ' . $baseDir . ' is not a directory';            
        }
        
        return $data;
    }

   	public function getCruiseSize() {
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'cruiseSize'");
        $data['cruiseSize'] = intval($row[0]->value);
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'cruiseSizeUpdated'");
        $data['cruiseSizeUpdated'] = $row[0]->value;
        if ($data['cruiseSize'] === 0) {
            $data['error'] = '(getCruiseSize) Unable to get size of cruise directory';
        }
        
        return $data;
    }

    public function getLoweringSize() {
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'loweringSize'");
        $data['loweringSize'] = intval($row[0]->value);
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'loweringSizeUpdated'");
        $data['loweringSizeUpdated'] = $row[0]->value;
            if ($data['loweringSize'] === 0) {
                $data['error'] = '(getLoweringSize) Unable to get size of lowering directory';
            }
        
        return $data;
    }


    public function getSystemStatus(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'systemStatus'");
        if(strcmp($row[0]->value, "On") == 0 ){
            return true;
        } else {
            return false;
        }
    }

    public function getShowLoweringComponents(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'showLoweringComponents'");
        if(strcmp($row[0]->value, "Yes") == 0 ){
            return true;
        } else {
            return false;
        }
    }
    
    public function getShipboardDataWarehouseStatus(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'shipboardDataWarehouseStatus'");
        return $row[0]->value;
    }
    
    public function getCruiseConfigFn(){
        return CRUISE_CONFIG_FN;
    }

    public function getCruiseDataURLPath(){
        return CRUISEDATA_APACHEDIR;
    }

    public function getCruiseID(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'cruiseID'");
        return $row[0]->value;
    }
    
    public function getCruiseStartDate(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'cruiseStartDate'");
        return $row[0]->value;
    }
    
    public function getCruiseEndDate(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'cruiseEndDate'");
        return $row[0]->value;
    }

    public function getCruiseStartPort(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'cruiseStartPort'");
        return $row[0]->value;
    }

    public function getCruiseEndPort(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'cruiseEndPort'");
        return $row[0]->value;
    }

    public function getLoweringConfigFn(){
        return LOWERING_CONFIG_FN;
    }

    public function getLoweringID(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'loweringID'");
        return $row[0]->value;
    }
    
    public function getLoweringStartDate(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'loweringStartDate'");
        return $row[0]->value;
    }
    
    public function getLoweringEndDate(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'loweringEndDate'");
        return $row[0]->value;
    }
    
    public function getShipToShoreBWLimitStatus(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'shipToShoreBWLimitStatus'");
        return $row[0]->value;
    }

    public function getMd5SummaryFn(){
        return MD5_SUMMARY_FN;
    }

    public function getMd5SummaryMd5Fn(){
        return MD5_SUMMARY_MD5_FN;
    }

    public function getMd5FilesizeLimit(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'md5FilesizeLimit'");
        return $row[0]->value;
    }
    
    public function getMd5FilesizeLimitStatus(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'md5FilesizeLimitStatus'");
        return $row[0]->value;
    }

    public function getDataDashboardManifestFn(){
        return DATA_DASHBOARD_MANIFEST_FN;
    }

    public function getShipboardDataWarehouseBaseDir(){
        return CRUISEDATA_BASEDIR;
    }

    public function getShipboardDataWarehouseApacheDir(){
        return CRUISEDATA_APACHEDIR;
    }
    
    public function getLoweringDataBaseDir(){
        return LOWERINGDATA_BASEDIR;
    }

    public function getShipboardDataWarehouseConfig(){
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'shipboardDataWarehouseIP'");
        $shipboardDataWarehouseIP = $row[0]->value;
        $shipboardDataWarehouseBaseDir = $this->getShipboardDataWarehouseBaseDir();
        $shipboardDataWarehouseApacheDir = $this->getShipboardDataWarehouseApacheDir();
        $row = $this->db->select("SELECT * FROM ".PREFIX."CoreVars WHERE name = 'shipboardDataWarehouseUsername'");
        $shipboardDataWarehouseUsername = $row[0]->value;
        $shipboardDataWarehousePublicDataDir = PUBLICDATA_DIR;
        $loweringDataBaseDir = $this->getLoweringDataBaseDir();
        $cruiseConfigFn = $this->getCruiseConfigFn();
        $cruiseDataURLPath = $this->getCruiseDataURLPath();
        $loweringConfigFn = $this->getLoweringConfigFn();
        $dataDashboardManifestFn = $this->getDataDashboardManifestFn();
        $md5SummaryFn = $this->getMd5SummaryFn();
        $md5SummaryMd5Fn = $this->getMd5SummaryMd5Fn();
         
        return array(
            'shipboardDataWarehouseIP' => $shipboardDataWarehouseIP,
            'shipboardDataWarehouseBaseDir' => $shipboardDataWarehouseBaseDir,
            'shipboardDataWarehouseApacheDir' => $shipboardDataWarehouseApacheDir,
            'shipboardDataWarehouseUsername' => $shipboardDataWarehouseUsername,
            'shipboardDataWarehousePublicDataDir' => $shipboardDataWarehousePublicDataDir,
            'loweringDataBaseDir' => $loweringDataBaseDir,
            'cruiseConfigFn' => $cruiseConfigFn,
            'cruiseDataURLPath' => $cruiseDataURLPath,
            'loweringConfigFn' => $loweringConfigFn,
            'dataDashboardManifestFn' => $dataDashboardManifestFn,
            'md5SummaryFn' => $md5SummaryFn,
            'md5SummaryMd5Fn' => $md5SummaryMd5Fn
        );
    }
    
    public function enableSystem(){
        $data = array('value' => 'On');   
        $where = array('name' => 'systemStatus');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function disableSystem(){
        $data = array('value' => 'Off');   
        $where = array('name' => 'systemStatus');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function enableShipToShoreTransfers(){
        $data = array('value' => 'On');   
        $where = array('name' => 'shipToShoreTransfersStatus');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function disableShipToShoreTransfers(){
        $data = array('value' => 'Off');   
        $where = array('name' => 'shipToShoreTransfersStatus');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function showLoweringComponents(){
        $data = array('value' => 'Yes');   
        $where = array('name' => 'showLoweringComponents');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function hideLoweringComponents(){
        $data = array('value' => 'No');   
        $where = array('name' => 'showLoweringComponents');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function enableShipToShoreBWLimit(){
        $data = array('value' => 'On');   
        $where = array('name' => 'shipToShoreBWLimitStatus');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function disableShipToShoreBWLimit(){
        $data = array('value' => 'Off');   
        $where = array('name' => 'shipToShoreBWLimitStatus');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function setMd5FilesizeLimit($data){
        $where = array('name' => 'md5FilesizeLimit');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function enableMd5FilesizeLimit(){
        $data = array('value' => 'On');   
        $where = array('name' => 'md5FilesizeLimitStatus');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function disableMd5FilesizeLimit(){
        $data = array('value' => 'Off');   
        $where = array('name' => 'md5FilesizeLimitStatus');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function setMd5SummaryFns($data){
        $where = array('name' => 'md5SummaryFn');
        $this->db->update(PREFIX."CoreVars", array('value' => $data['md5SummaryFn']), $where);
        $where = array('name' => 'md5SummaryMd5Fn');
        $this->db->update(PREFIX."CoreVars", array('value' => $data['md5SummaryMd5Fn']), $where);
    }

    public function setCruiseConfigFn($data){
        $where = array('name' => 'cruiseConfigFn');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function setCruiseID($data){
        $where = array('name' => 'cruiseID');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function setCruiseStartDate($data){
	// var_dump($data);    
	$where = array('name' => 'cruiseStartDate');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function setCruiseEndDate($data){
        $where = array('name' => 'cruiseEndDate');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function setCruiseStartPort($data){
    // var_dump($data);    
    $where = array('name' => 'cruiseStartPort');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function setCruiseEndPort($data){
        $where = array('name' => 'cruiseEndPort');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function setCruiseSize($data){
        $where = array('name' => 'cruiseSize');
        $this->db->update(PREFIX."CoreVars",$data, $where);

        $where = array('name' => 'cruiseSizeUpdated');
        $data = array('value' => gmdate('Y/m/d H:i:s'));
        $this->db->update(PREFIX."CoreVars", $data, $where);
    }

    public function setLoweringConfigFn($data){
        $where = array('name' => 'loweringConfigFn');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function setLoweringID($data){
        $where = array('name' => 'loweringID');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function setLoweringStartDate($data){
        $where = array('name' => 'loweringStartDate');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }
    
    public function setLoweringEndDate($data){
        $where = array('name' => 'loweringEndDate');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function setLoweringSize($data){
        $where = array('name' => 'loweringSize');
        $this->db->update(PREFIX."CoreVars",$data, $where);

        $where = array('name' => 'loweringSizeUpdated');
        $data = array('value' => gmdate('Y/m/d H:i:s'));
        $this->db->update(PREFIX."CoreVars", $data, $where);

    }

    public function setDataDashboardManifestFn($data){
        $where = array('name' => 'dataDashboardManifestFn');
        $this->db->update(PREFIX."CoreVars",$data, $where);
    }

    public function setShipboardDataWarehouseConfig($data){
        $where = array('name' => 'shipboardDataWarehouseIP');
        $this->db->update(PREFIX."CoreVars", array('value' => $data['shipboardDataWarehouseIP']), $where);
        $where = array('name' => 'shipboardDataWarehouseUsername');
        $this->db->update(PREFIX."CoreVars", array('value' => $data['shipboardDataWarehouseUsername']), $where);
        
    }
    
    public function setErrorShipboardDataWarehouseStatus(){
        $where = array('name' => 'shipboardDataWarehouseStatus');
        $this->db->update(PREFIX."CoreVars", array('value' => '3'), $where);
    }
    
    public function clearErrorShipboardDataWarehouseStatus(){
        $where = array('name' => 'shipboardDataWarehouseStatus');
        $this->db->update(PREFIX."CoreVars", array('value' => '2'), $where);
    }
    
    public function getCruises(){
        
        if (!$this->_cruises || (is_array($this->_cruises) && sizeof($this->_cruises) == 0)) {
        
            $baseDir = $this->getShipboardDataWarehouseBaseDir();
            #var_dump($baseDir);
            //Get the list of directories
            if (is_dir($baseDir)) {
                $rootList = scandir($baseDir);
                #var_dump($rootList);

                foreach ($rootList as $rootKey => $rootValue)
                {
                    if (!in_array($rootValue,array(".","..")))
                    {
                        if (is_dir($baseDir . DIRECTORY_SEPARATOR . $rootValue) && is_readable($baseDir . DIRECTORY_SEPARATOR . $rootValue))
                        {
                            //Check each Directory for the OpenVDM Config file.json
                            $cruiseList = scandir($baseDir . DIRECTORY_SEPARATOR . $rootValue);
                            foreach ($cruiseList as $cruiseKey => $cruiseValue){

                                if (in_array($cruiseValue,array($this->getCruiseConfigFn()))){
                                    $ovdmConfigContents = file_get_contents($baseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                                    $ovdmConfigJSON = json_decode($ovdmConfigContents,true);

                                    //Get the the directory that holds the DashboardData
				                    if (array_key_exists('extraDirectoriesConfig', $ovdmConfigJSON)){

				                        for($i = 0; $i < sizeof($ovdmConfigJSON['extraDirectoriesConfig']); $i++){

                                            if(strcmp($ovdmConfigJSON['extraDirectoriesConfig'][$i]['name'], 'Dashboard_Data') === 0){
                                                $dataDashboardList = scandir($baseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $ovdmConfigJSON['extraDirectoriesConfig'][$i]['destDir']);

                                                foreach ($dataDashboardList as $dataDashboardKey => $dataDashboardValue){

                                                    //If a manifest file is found, add CruiseID to output
                                                    if (in_array($dataDashboardValue,array($this->getDataDashboardManifestFn()))){
                                                        $this->_cruises[] = $rootValue;
                                                        break;
                                                    }
                                                }
                                                break;
                                            }
                                        }
				                    }
                                    break;
                                }
                            }
                        }
                    }
                }
            }
            #var_dump($this->_cruises);

            if(is_array($this->_cruises) && sizeof($this->_cruises) > 0) {
                rsort($this->_cruises);
            }
            return $this->_cruises;
        } else {
            return array("Error"=>"Could not find base directory.");
        }
    }

    public function getLowerings(){
        // var_dump($this->_lowerings); 
        if (!$this->_lowerings || (is_array($this->_lowerings) && sizeof($this->_lowerings) == 0)) {
        
            $baseDir = $this->getShipboardDataWarehouseBaseDir();
            $cruiseDir = $baseDir . DIRECTORY_SEPARATOR . $this->getCruiseID();
            $loweringDataBaseDir = $cruiseDir . DIRECTORY_SEPARATOR . $this->getLoweringDataBaseDir();
            #var_dump($baseDir);
            //Get the list of directories
            if (is_dir($loweringDataBaseDir)) {
                $rootList = scandir($loweringDataBaseDir);
                #var_dump($rootList);

                foreach ($rootList as $rootKey => $rootValue)
                {
                    if (!in_array($rootValue,array(".","..")))
                    {
                        if (is_dir($loweringDataBaseDir . DIRECTORY_SEPARATOR . $rootValue) && is_readable($loweringDataBaseDir . DIRECTORY_SEPARATOR . $rootValue))
                        {
                            //Check each Directory for ovdmConfig.json
                            $loweringList = scandir($loweringDataBaseDir . DIRECTORY_SEPARATOR . $rootValue);
                            #var_dump($cruiseList);
                            foreach ($loweringList as $loweringKey => $loweringValue){
                                #var_dump($loweringValue);
                                if (in_array($loweringValue,array($this->getLoweringConfigFn()))){
                                    #var_dump($loweringDataBaseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $this->getLoweringConfigFn());
                                    $loweringConfigContents = file_get_contents($loweringDataBaseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $this->getLoweringConfigFn());
                                    $loweringConfigJSON = json_decode($loweringConfigContents,true);
                                    #var_dump($ovdmConfigJSON['extraDirectoriesConfig']);
                                    //Get the the directory that holds the DashboardData
                                    $this->_lowerings[] = $rootValue;
                                    break;
                                }
                            }
                        }
                    }
                }
            }
            //var_dump($this->_lowerings);

            //If there are no lowerings
            if(!$this->_lowerings) {
                return array();
            }

            if(is_array($this->_lowerings) && sizeof($this->_lowerings) > 0) {
                rsort($this->_lowerings);
            }
            return $this->_lowerings;
        } else {
            return array("Error"=>"Could not find base directory.");
        }
    }

    
    public function getLatestCruise() {
        return $this->getCruises()[0];
    }

    public function getCruiseDates($cruiseID = '') {
        if (strcmp($cruiseID, '') == 0 ){
            $cruiseID = $this->getCruiseID();
        }

        $cruiseDir = $this->getShipboardDataWarehouseBaseDir() . DIRECTORY_SEPARATOR . $cruiseID;
        #var_dump($cruiseDir);
        if (is_dir($cruiseDir)) {
            //Check cruise Directory for ovdmConfig.json
            $cruiseFileList = scandir($cruiseDir);
            #var_dump($cruiseList);
            foreach ($cruiseFileList as $cruiseKey => $cruiseValue){
                #var_dump($cruiseValue);
                if (in_array($cruiseValue,array($this->getCruiseConfigFn()))){
                    #var_dump($baseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                    $ovdmConfigContents = file_get_contents($cruiseDir . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                    $ovdmConfigJSON = json_decode($ovdmConfigContents,true);
                    
                    return array('cruiseStartDate' => $ovdmConfigJSON['cruiseStartDate'],'cruiseEndDate' => $ovdmConfigJSON['cruiseEndDate']); 
                }
            }
            return array("Error"=>"Could not find cruise config file.");

        } else {
            return array("Error"=>"Could not find cruise directory.");
        }
    }

    public function getCruisePorts($cruiseID = '') {
        if (strcmp($cruiseID, '') == 0 ){
            $cruiseID = $this->getCruiseID();
        }

        $cruiseDir = $this->getShipboardDataWarehouseBaseDir() . DIRECTORY_SEPARATOR . $cruiseID;
        #var_dump($cruiseDir);
        if (is_dir($cruiseDir)) {
            //Check cruise Directory for ovdmConfig.json
            $cruiseFileList = scandir($cruiseDir);
            #var_dump($cruiseList);
            foreach ($cruiseFileList as $cruiseKey => $cruiseValue){
                #var_dump($cruiseValue);
                if (in_array($cruiseValue,array($this->getCruiseConfigFn()))){
                    #var_dump($baseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                    $ovdmConfigContents = file_get_contents($cruiseDir . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                    $ovdmConfigJSON = json_decode($ovdmConfigContents,true);
                    
                    return array('cruiseStartPort' => $ovdmConfigJSON['cruiseStartPort'],'cruiseEndPort' => $ovdmConfigJSON['cruiseEndPort']); 
                }
            }
            return array("Error"=>"Could not find cruise config file.");

        } else {
            return array("Error"=>"Could not find cruise directory.");
        }
    }

    public function getCruiseFinalizedDate($cruiseID = '') {
        if (strcmp($cruiseID, '') == 0 ){
            $cruiseID = $this->getCruiseID();
        }

        $cruiseDir = $this->getShipboardDataWarehouseBaseDir() . DIRECTORY_SEPARATOR . $cruiseID;
        #var_dump($cruiseDir);
        if (is_dir($cruiseDir)) {
            //Check cruise Directory for ovdmConfig.json
            $cruiseFileList = scandir($cruiseDir);
            #var_dump($cruiseList);
            foreach ($cruiseFileList as $cruiseKey => $cruiseValue){
                #var_dump($cruiseValue);
                if (in_array($cruiseValue,array($this->getCruiseConfigFn()))){
                    #var_dump($baseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                    $ovdmConfigContents = file_get_contents($cruiseDir . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                    $ovdmConfigJSON = json_decode($ovdmConfigContents,true);
                    
                    return array('cruiseFinalizedOn' => $ovdmConfigJSON['cruiseFinalizedOn']); 
                }
            }
            return array("Error"=>"Could not find cruise config file.", 'cruiseFinalizedOn' => null);

        } else {
            return array("Error"=>"Could not find cruise directory.", 'cruiseFinalizedOn' => null);
        }
    }

    public function getLatestLowering() {
        return $this->getLowerings()[0];
    }

    public function getLoweringDates($loweringID = '') {
        if (strcmp($loweringID, '') == 0 ){
            $loweringID = $this->getLoweringID();
        }

        $loweringDir = $this->getShipboardDataWarehouseBaseDir() . DIRECTORY_SEPARATOR . $this->getCruiseID() . DIRECTORY_SEPARATOR . $this->getLoweringDataBaseDir() . DIRECTORY_SEPARATOR . $loweringID;
        #var_dump($loweringDir);
        if (is_dir($loweringDir)) {
            //Check lowering Directory for ovdmConfig.json
            $loweringFileList = scandir($loweringDir);
            #var_dump($loweringList);
            foreach ($loweringFileList as $loweringKey => $loweringValue){
                #var_dump($loweringValue);
                if (in_array($loweringValue,array($this->getLoweringConfigFn()))){
                    #var_dump($baseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                    $loweringConfigContents = file_get_contents($loweringDir . DIRECTORY_SEPARATOR . $this->getLoweringConfigFn());
                    $loweringConfigJSON = json_decode($loweringConfigContents,true);
                    
                    return array('loweringStartDate' => $loweringConfigJSON['loweringStartDate'],'loweringEndDate' => $loweringConfigJSON['loweringEndDate']); 
                }
            }
            return array("Error"=>"Could not find lowering config file.");

        } else {
            return array("Error"=>"Could not find lowering directory.");
        }
    }

    public function getLoweringFinalizedDate($loweringID = '') {
        if (strcmp($loweringID, '') == 0 ){
            $loweringID = $this->getLoweringID();
        }

        $loweringDir = $this->getShipboardDataWarehouseBaseDir() . DIRECTORY_SEPARATOR . $this->getCruiseID() . DIRECTORY_SEPARATOR . $this->getLoweringDataBaseDir() . DIRECTORY_SEPARATOR . $loweringID;
        #var_dump($loweringDir);
        if (is_dir($loweringDir)) {
            //Check lowering Directory for ovdmConfig.json
            $loweringFileList = scandir($loweringDir);
            #var_dump($loweringList);
            foreach ($loweringFileList as $loweringKey => $loweringValue){
                #var_dump($loweringValue);
                if (in_array($loweringValue,array($this->getLoweringConfigFn()))){
                    #var_dump($baseDir . DIRECTORY_SEPARATOR . $rootValue . DIRECTORY_SEPARATOR . $this->getCruiseConfigFn());
                    $loweringConfigContents = file_get_contents($loweringDir . DIRECTORY_SEPARATOR . $this->getLoweringConfigFn());
                    $loweringConfigJSON = json_decode($loweringConfigContents,true);
                    
                    return array('loweringFinalizedOn' => $loweringConfigJSON['loweringFinalizedOn']); 
                }
            }
            return array("Error"=>"Could not find lowering config file.", 'loweringFinalizedOn' => null);

        } else {
            return array("Error"=>"Could not find lowering directory.", 'loweringFinalizedOn' => null);
        }
    }


}
