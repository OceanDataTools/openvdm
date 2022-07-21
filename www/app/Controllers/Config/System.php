<?php

namespace controllers\config;
use Core\Controller;
use Core\View;
use Helpers\Session;
use Helpers\Url;

class System extends Controller {
    
    private $_warehouseModel;
    private $_extraDirectoriesModel;
    private $_cruiseDataTransfersModel;
    private $_shipToShoreTransfersModel;
    private $_linksModel;


    private function _buildUseSSHKeyOptions() {
        
        $trueFalse = array(array('id'=>'useSSHKey0', 'name'=>'sshUseKey', 'value'=>'0', 'label'=>'No'), array('id'=>'useSSHKey1', 'name'=>'sshUseKey', 'value'=>'1', 'label'=>'Yes'));
        return $trueFalse;
    }


    private function updateCruiseDirectory() {
        if($this->_warehouseModel->getSystemStatus()) {

            $gmData['siteRoot'] = DIR;
            $gmData['shipboardDataWarehouse'] = $this->_warehouseModel->getShipboardDataWarehouseConfig();
            $gmData['cruiseID'] = $this->_warehouseModel->getCruiseID();
        
            # create the gearman client
            $gmc= new \GearmanClient();

            # add the default server (localhost)
            $gmc->addServer();

            #submit job to Gearman
            $job_handle = $gmc->doBackground("rebuildCruiseDirectory", json_encode($gmData));
        }
    }
    
    public function __construct(){
        
        if(!Session::get('loggedin')){
            Url::redirect('config/login');
        }
        
        $this->_warehouseModel = new \Models\Warehouse();
        $this->_extraDirectoriesModel = new \Models\Config\ExtraDirectories();
        $this->_cruiseDataTransfersModel = new \Models\Config\CruiseDataTransfers();
        $this->_shipToShoreTransfersModel = new \Models\Config\ShipToShoreTransfers();
        $this->_linksModel = new \Models\Config\Links();
    }
    
    public function index(){
            
        $data['title'] = 'Configuration';
        $data['javascript'] = array('system');
        $data['requiredCruiseDataTransfers'] = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();
        $data['requiredShipToShoreTransfers'] = $this->_shipToShoreTransfersModel->getRequiredShipToShoreTransfers();
        $data['requiredExtraDirectories'] = $this->_extraDirectoriesModel->getExtraDirectories(true, true);
        $data['links'] = $this->_linksModel->getLinks();
        $data['shipboardDataWarehouseStatus'] = $this->_warehouseModel->getShipboardDataWarehouseStatus();
        $data['shipToShoreBWLimitStatus'] = $this->_warehouseModel->getShipToShoreBWLimitStatus();
        $data['md5FilesizeLimit'] = $this->_warehouseModel->getMd5FilesizeLimit();
        $data['md5FilesizeLimitStatus'] = $this->_warehouseModel->getMd5FilesizeLimitStatus();


        $requiredCruiseDataTransfers = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();
                
        foreach($requiredCruiseDataTransfers as $row) {
            if(strcmp($row->name, 'SSDW') === 0 ) {

                $data['shipToShoreBWLimit'] = $row->bandwidthLimit;
                break;
            }
        }

        $this->_linksModel->processLinkURL($data['links']);
        
        View::rendertemplate('header',$data);
        View::render('Config/system',$data);
        View::rendertemplate('footer',$data);
    }
    
    public function editShipboardDataWarehouse(){

        $data['title'] = 'Configuration';
        $data['javascript'] = array();
        $data['shipboardDataWarehouseConfig'] = $this->_warehouseModel->getShipboardDataWarehouseConfig();

        if(isset($_POST['submit'])){
            $shipboardDataWarehouseIP = $_POST['shipboardDataWarehouseIP'];
            $shipboardDataWarehouseUsername = $_POST['shipboardDataWarehouseUsername'];
            $shipboardDataWarehousePublicDataDir = $_POST['shipboardDataWarehousePublicDataDir'];

            if($shipboardDataWarehouseIP == ''){
                $error[] = 'Shipboard Data Warehouse IP is required';
            }

            if($shipboardDataWarehouseUsername == ''){
                $error[] = 'Shipboard Data Warehouse Username is required';
            }
            
            if($shipboardDataWarehousePublicDataDir == ''){
                $error[] = 'Shipboard Data Warehouse Public Data Directory is required';
            }

            if(!$error){
                $postdata = array(
                    'shipboardDataWarehouseIP' => $shipboardDataWarehouseIP,
                    'shipboardDataWarehouseUsername' => $shipboardDataWarehouseUsername,
                    'shipboardDataWarehousePublicDataDir' => $shipboardDataWarehousePublicDataDir,
                );
                
                $this->_warehouseModel->setShipboardDataWarehouseConfig($postdata);
                Session::set('message','Shipboard Data Warehouse Updated');
                Url::redirect('config/system');
            } else {
                $data['shipboardDataWarehouseConfig'] = array(
                    'shipboardDataWarehouseIP' => $shipboardDataWarehouseIP,
                    'shipboardDataWarehouseUsername' => $shipboardDataWarehouseUsername,
                    'shipboardDataWarehousePublicDataDir' => $shipboardDataWarehousePublicDataDir,
                );
            }
        }
        
        View::rendertemplate('header',$data);
        View::render('Config/editShipboardDataWarehouse',$data, $error);
        View::rendertemplate('footer',$data);
    }
    
    public function editShoresideDataWarehouse(){

        $data['title'] = 'Configuration';
        $data['javascript'] = array('SSDWFormHelper');
        $data['useSSHKeyOptions'] = $this->_buildUseSSHKeyOptions();
        $data['requiredCruiseDataTransfers'] = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();
        $data['shoresideDataWarehouseConfig'] = array();
        

        foreach($data['requiredCruiseDataTransfers'] as $row) {
            if(strcmp($row->name, 'SSDW') === 0 ) {
                $data['shoresideDataWarehouseConfig']['cruiseDataTransferID'] = $row->cruiseDataTransferID;
                $data['shoresideDataWarehouseConfig']['sshServer'] = $row->sshServer;
                $data['shoresideDataWarehouseConfig']['sshUser'] = $row->sshUser;
                $data['shoresideDataWarehouseConfig']['sshUseKey'] = $row->sshUseKey;
                $data['shoresideDataWarehouseConfig']['sshPass'] = $row->sshPass;
                $data['shoresideDataWarehouseConfig']['destDir'] = $row->destDir;
                break;
            }
        }
            
        if(isset($_POST['submit'])){
            $sshServer = $_POST['sshServer'];
            $sshUser = $_POST['sshUser'];
            $sshUseKey = $_POST['sshUseKey'];
            $sshPass = $_POST['sshPass'];
            $destDir = $_POST['destDir'];

            if($sshServer == ''){
                $error[] = 'Shoreside Data Warehouse IP is required';
            }

            if($sshUser == ''){
                $error[] = 'Shipboard Data Warehouse Username is required';
            }

            if(($sshPass == '') && ($sshUseKey == '0')){
                $error[] = 'Shipboard Data Warehouse Password is required';
            }

            if($destDir == ''){
                $error[] = 'Shoreside Data Warehouse Base Directory is required';
            }

            if(!$error){
                $postdata = array(
                    'sshServer' => $sshServer,
                    'sshUser' => $sshUser,
                    'sshUseKey' => $sshUseKey,
                    'sshPass' => $sshPass,
                    'destDir' => $destDir,
                );
                
                $where = array('cruiseDataTransferID' => $data['shoresideDataWarehouseConfig']['cruiseDataTransferID']);
                            
                $this->_cruiseDataTransfersModel->updateCruiseDataTransfer($postdata, $where);
                Session::set('message','Shoreside Data Warehouse Updated');
                Url::redirect('config/system');
            } else {
                $data['shoresideDataWarehouseConfig'] = array(
                    'sshServer' => $sshServer,
                    'sshUser' => $sshUser,
                    'sshUseKey' => $sshUseKey,
                    'sshPass' => $sshPass,
                    'destDir' => $destDir,
                );
            }
        }
        
        View::rendertemplate('header',$data);
        View::render('Config/editShoresideDataWarehouse',$data, $error);
        View::rendertemplate('footer',$data);
    }
    
    public function editExtraDirectories($id){
        $data['title'] = 'Edit Extra Directory';
        $data['javascript'] = array('extraDirectoriesFormHelper');
        $data['row'] = $this->_extraDirectoriesModel->getExtraDirectory($id);

        if(isset($_POST['submit'])){
            $longName = $_POST['longName'];
            $destDir = $_POST['destDir'];

            if($longName == ''){
                $error[] = 'Long name is required';
            } 

            if($destDir == ''){
                $error[] = 'Destination directory is required';
            } 
                
            if(!$error){
                $postdata = array(
                    'longName' => $longName,
                    'destDir' => $destDir,
                );
            
                
                $where = array('extraDirectoryID' => $id);
                $this->_extraDirectoriesModel->updateExtraDirectory($postdata,$where);
                Session::set('message','Extra Directory Updated');
                Url::redirect('config/system');
            } else {
                
                $data['row'][0]->name = $name;
                $data['row'][0]->longName = $longName;
                $data['row'][0]->destDir = $destDir;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editRequiredExtraDirectories',$data,$error);
        View::rendertemplate('footer',$data);
    }
    
    public function editShipToShoreTransfers($id){
        $data['title'] = 'Edit Ship-to-Shore Transfer';
        $data['javascript'] = array('shipToShoreTransfersFormHelper');
        $data['row'] = $this->_shipToShoreTransfersModel->getShipToShoreTransfer($id);

        if(isset($_POST['submit'])){
            $longName = $_POST['longName'];
            $includeFilter = $_POST['includeFilter'];

            if($longName == ''){
                $error[] = 'Long name is required';
            }
            
            if($includeFilter == ''){
                $includeFilter = '*';
            } 

            if(!$error){
                $postdata = array(
                    'longName' => $longName,
                    'includeFilter' => $includeFilter,
                );
            
                
                $where = array('shipToShoreTransferID' => $id);
                $this->_shipToShoreTransfersModel->updateShipToShoreTransfer($postdata,$where);
                Session::set('message','Ship-to-Shore Transfers Updated');
                Url::redirect('config/system');
            } else {
                
                $data['row'][0]->longName = $longName;
                $data['row'][0]->includeFilter = $includeFilter;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editRequiredShipToShoreTransfers',$data,$error);
        View::rendertemplate('footer',$data);
    }
    
    public function enableShipToShoreTransfers($id) {

        $this->_shipToShoreTransfersModel->enableShipToShoreTransfer($id);
        Url::redirect('config/system');
    }
    
    public function disableShipToShoreTransfers($id) {

        $this->_shipToShoreTransfersModel->disableShipToShoreTransfer($id);
        Url::redirect('config/system');
    }
    
    public function editShipToShoreBWLimit(){
        $data['title'] = 'Edit Ship-to-Shore Bandwidth Limit';
        $data['javascript'] = array();

        $requiredCruiseDataTransfers = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();

        $ssdw = null;
        
        foreach($requiredCruiseDataTransfers as $row) {
            if(strcmp($row->name, 'SSDW') === 0 ) {
                $ssdw = $row;
                break;
            }
        }

        $data['shipToShoreBWLimit'] = $ssdw->bandwidthLimit;

        if(isset($_POST['submit'])){
            $shipToShoreBWLimit = $_POST['shipToShoreBWLimit'];

            if($shipToShoreBWLimit == ''){
                $shipToShoreBWLimit = '0';
            } elseif (!((string)(int)$shipToShoreBWLimit == $shipToShoreBWLimit)){
                $error[] = 'Bandwidth limit must be an integer';
            }
                
            if(!$error){

                $postdata = array(
                    'bandwidthLimit' => (int)$shipToShoreBWLimit
                );
                $where = array('cruiseDataTransferID' => $ssdw->cruiseDataTransferID);
                $this->_cruiseDataTransfersModel->updateCruiseDataTransfer($postdata,$where);

                Session::set('message','Ship-to-Shore Bandwidth Limit Updated');
                Url::redirect('config/system');
            } else {
                
                $data['shipToShoreBWLimit'] = $shipToShoreBWLimit;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editShipToShoreBWLimit',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function enableShipToShoreBWLimit() {

        $this->_warehouseModel->enableShipToShoreBWLimit();
        Url::redirect('config/system');
    }
    
    public function disableShipToShoreBWLimit() {

        $this->_warehouseModel->disableShipToShoreBWLimit();
        Url::redirect('config/system');
    }
    
    public function editMD5FilesizeLimit(){
        $data['title'] = 'Edit MD5 Checksum Filesize Limit';
        $data['javascript'] = array();
        $data['md5FilesizeLimit'] = $this->_warehouseModel->getMd5FilesizeLimit();

        if(isset($_POST['submit'])){
            $md5FilesizeLimit = $_POST['md5FilesizeLimit'];

            if($md5FilesizeLimit == ''){
                $error[] = 'MD5 filesize limit is required';
            } elseif (!is_numeric($md5FilesizeLimit)){
                $error[] = 'MD5 filesize limit must be a number';
            }
                
            if(!$error){
                $postdata = array(
                    'value' => $md5FilesizeLimit
                );

                $this->_warehouseModel->setMd5FilesizeLimit($postdata);
                Session::set('message','MD5 Filesize Limit Updated');
                Url::redirect('config/system');
            } else {
                
                $data['md5FilesizeLimit'] = $md5FilesizeLimit;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editMD5FilesizeLimit',$data,$error);
        View::rendertemplate('footer',$data);
    }
    
    public function enableMD5FilesizeLimit() {

        $this->_warehouseModel->enableMd5FilesizeLimit();
        Url::redirect('config/system');
    }
    
    public function disableMD5FilesizeLimit() {

        $this->_warehouseModel->disableMd5FilesizeLimit();
        Url::redirect('config/system');
    }

    public function testShipboardDataWarehouse() {
        
        $_warehouseModel = new \Models\Warehouse();
        $shipboardDataWarehouseConfig = $_warehouseModel->getShipboardDataWarehouseConfig();
        
	$data['testResults'] = array();
	$parts = array();

        $baseDirectoryTest = (object) array();
        $publicDataDirectoryTest = (object) array();
        $usernameTest = (object) array();
        $finalVerdict = (object) array();
        
        $finalVerdict->partName = 'FinalVerdict';
        $finalVerdict->result = 'Pass';
                
        $baseDirectoryTest->partName = 'Base Directory';
        if(is_dir( $shipboardDataWarehouseConfig['shipboardDataWarehouseBaseDir'] )) {
            $baseDirectoryTest->result = 'Pass';
        } else {
            $baseDirectoryTest->result = 'Fail';
            $finalVerdict->result = 'Fail';
        }
        
        array_push($parts, $baseDirectoryTest);

        $publicDataDirectoryTest->partName = 'Public Data Directory';
        if(is_dir( $shipboardDataWarehouseConfig['shipboardDataWarehousePublicDataDir'] )) {
            $publicDataDirectoryTest->result = 'Pass';
        } else {
            $publicDataDirectoryTest->result = 'Fail';
            $finalVerdict->result = 'Fail';
        }
        
        array_push($parts, $publicDataDirectoryTest);
        
        $command = 'getent passwd ' . $shipboardDataWarehouseConfig['shipboardDataWarehouseUsername'];
        exec($command,$op);
        
        $usernameTest->partName = 'Username';
        if(isset($op[0])) {
            $usernameTest->result = 'Pass';
        } else {
            $usernameTest->result = 'Fail';
            $finalVerdict->result = 'Fail';
        }
        
        array_push($parts, $usernameTest);
        array_push($parts, $finalVerdict);

        $data['testResults']['parts'] = json_decode(json_encode($parts), true);

        if (strcmp($finalVerdict->result, "Pass") === 0 ) {
            $_warehouseModel->clearErrorShipboardDataWarehouseStatus();
        } else {
            $_warehouseModel->setErrorShipboardDataWarehouseStatus();
        }
        
        $data['title'] = 'Configuration';
        $data['javascript'] = array('system');
        $data['requiredCruiseDataTransfers'] = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();
        $data['requiredShipToShoreTransfers'] = $this->_shipToShoreTransfersModel->getRequiredShipToShoreTransfers();
        $data['requiredExtraDirectories'] = $this->_extraDirectoriesModel->getExtraDirectories(true, true);
        $data['shipboardDataWarehouseStatus'] = $this->_warehouseModel->getShipboardDataWarehouseStatus();
        $data['shipToShoreBWLimitStatus'] = $this->_warehouseModel->getShipToShoreBWLimitStatus();
        $data['md5FilesizeLimit'] = $this->_warehouseModel->getMd5FilesizeLimit();
        $data['md5FilesizeLimitStatus'] = $this->_warehouseModel->getMd5FilesizeLimitStatus();
        $data['links'] = $this->_linksModel->getLinks();

        $requiredCruiseDataTransfers = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();

        foreach($requiredCruiseDataTransfers as $row) {
            if(strcmp($row->name, 'SSDW') === 0 ) {

                $data['shipToShoreBWLimit'] = $row->bandwidthLimit;
                break;
            }
        }

        $this->_linksModel->processLinkURL($data['links']);

        //additional data needed for view
        $data['testWarehouseName'] = 'Shipboard Data Warehouse';

        View::rendertemplate('header',$data);
        View::render('Config/system',$data);
        View::rendertemplate('footer',$data);
    }

 
    public function testShoresideDataWarehouse() {
        
        $_warehouseModel = new \Models\Warehouse();
        $gmData['siteRoot'] = DIR;
        $gmData['shipboardDataWarehouse'] = $_warehouseModel->getShipboardDataWarehouseConfig();
        $gmData['cruiseID'] = $_warehouseModel->getCruiseID();
        $requiredCruiseDataTransfers = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();
        
        foreach($requiredCruiseDataTransfers as $row) {
            if(strcmp($row->name, 'SSDW') === 0 ) {
                $gmData['cruiseDataTransfer'] = $row;
                break;
            }
        }
        
        # create the gearman client
        $gmc= new \GearmanClient();

        # add the default server (localhost)
        $gmc->addServer();

        #submit job to Gearman, wait for results
        $data['testResults'] = json_decode($gmc->doNormal("testCruiseDataTransfer", json_encode($gmData)), true);
        
        # update collectionSystemTransfer status if needed
        #if(strcmp($data['testResults'][sizeof($data['testResults'])-1]->result, "Fail") === 0) {
        #    $this->_collectionSystemTransfersModel->setError_collectionSystemTransfer($id);
        #} else {
        #    $this->_collectionSystemTransfersModel->setIdle_collectionSystemTransfer($id);
        #}

        $data['title'] = 'Configuration';
        $data['javascript'] = array('system');
        $data['requiredCruiseDataTransfers'] = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();
        $data['requiredShipToShoreTransfers'] = $this->_shipToShoreTransfersModel->getRequiredShipToShoreTransfers();
        $data['requiredExtraDirectories'] = $this->_extraDirectoriesModel->getExtraDirectories(true, true);
        $data['shipToShoreBWLimitStatus'] = $this->_warehouseModel->getShipToShoreBWLimitStatus();
        $data['md5FilesizeLimit'] = $this->_warehouseModel->getMd5FilesizeLimit();
        $data['md5FilesizeLimitStatus'] = $this->_warehouseModel->getMd5FilesizeLimitStatus();
        $data['links'] = $this->_linksModel->getLinks();

        $requiredCruiseDataTransfers = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();

        foreach($requiredCruiseDataTransfers as $row) {
            if(strcmp($row->name, 'SSDW') === 0 ) {

                $data['shipToShoreBWLimit'] = $row->bandwidthLimit;
                break;
            }
        }

        $this->_linksModel->processLinkURL($data['links']);

        $data['testWarehouseName'] = 'Shoreside Data Warehouse';

        View::rendertemplate('header',$data);
        View::render('Config/system',$data);
        View::rendertemplate('footer',$data);
    }
    
    public function addLink(){
        $data['title'] = 'Edit Link';
        $data['javascript'] = array('LinksFormHelper');

        if(isset($_POST['submit'])){
            $name = $_POST['name'];
            $url = $_POST['url'];

            if($name == ''){
                $error[] = 'Name is required';
            } 

            if($url == ''){
                $error[] = 'URL is required';
            } 
                
            if(!$error){
                $postdata = array(
                    'name' => $name,
                    'url' => $url,
                    'private' => '0',
                    'enable' => '0',
                );
            
                $this->_linksModel->insertLink($postdata,$where);
                Session::set('message','Link Added');
                Url::redirect('config/system');
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/addLink',$data,$error);
        View::rendertemplate('footer',$data);
    }
    
    public function editLink($id){
        $data['title'] = 'Edit Link';
        $data['javascript'] = array('LinksFormHelper');
        $data['row'] = $this->_linksModel->getLink($id);

        if(isset($_POST['submit'])){
            $name = $_POST['name'];
            $url = $_POST['url'];

            if($name == ''){
                $error[] = 'Name is required';
            } 

            if($url == ''){
                $error[] = 'URL is required';
            } 
                
            if(!$error){
                $postdata = array(
                    'name' => $name,
                    'url' => $url,
                );
            
                
                $where = array('linkID' => $id);
                $this->_linksModel->updateLink($postdata,$where);
                Session::set('message','Link Updated');
                Url::redirect('config/system');
            } else {
                
                $data['row'][0]->name = $name;
                $data['row'][0]->url = $url;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editLink',$data,$error);
        View::rendertemplate('footer',$data);
    }
    
    public function deleteLink($id) {

        $where = array('linkID' => $id);
        $this->_linksModel->deleteLink($where);
        Url::redirect('config/system');
    }

    public function enableLink($id) {

        $this->_linksModel->enableLink($id);
        Url::redirect('config/system');
    }
    
    public function disableLink($id) {

        $this->_linksModel->disableLink($id);
        Url::redirect('config/system');
    }
    
    public function privateLink($id) {

        $this->_linksModel->privateLink($id);
        Url::redirect('config/system');
    }
    
    public function publicLink($id) {

        $this->_linksModel->publicLink($id);
        Url::redirect('config/system');
    }

    public function editCruiseConfigFn(){
        $data['title'] = 'Edit Cruise Config Filename';
        $data['javascript'] = array('LinksFormHelper');
        $data['cruiseConfigFn'] = $this->_warehouseModel->getCruiseConfigFn();

        if(isset($_POST['submit'])){
            $cruiseConfigFn = $_POST['cruiseConfigFn'];

            if($cruiseConfigFn == ''){
                $error[] = 'Cruise config filename is required';
            }
            
            if($cruiseConfigFn == trim($cruiseConfigFn) && strpos($cruiseConfigFn, ' ') !== false) {
               $error[] = 'Cruise config filename contains spaces';
            }

            if(substr($cruiseConfigFn, -strlen('.json')) !== '.json') {
               $error[] = 'Cruise config filename does not end with .json';
            }

            if(!$error){
                $postdata = array(
                    'value' => $cruiseConfigFn,
                );
            
                $this->_warehouseModel->setCruiseConfigFn($postdata);
                Session::set('message','Filename Updated');
                Url::redirect('config/system');
            } else {
                
                $data['cruiseConfigFn'] = $cruiseConfigFn;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editCruiseConfigFn',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function editLoweringConfigFn(){
        $data['title'] = 'Edit Lowering Config Filename';
        $data['javascript'] = array('LinksFormHelper');
        $data['loweringConfigFn'] = $this->_warehouseModel->getLoweringConfigFn();

        if(isset($_POST['submit'])){
            $loweringConfigFn = $_POST['loweringConfigFn'];

            if($loweringConfigFn == ''){
                $error[] = 'Lowering config filename is required';
            }
            
            if($loweringConfigFn == trim($loweringConfigFn) && strpos($loweringConfigFn, ' ') !== false) {
               $error[] = 'Lowering config filename contains spaces';
            }

            if(substr($loweringConfigFn, -strlen('.json')) !== '.json') {
               $error[] = 'Lowering config filename does not end with .json';
            }

            if(!$error){
                $postdata = array(
                    'value' => $loweringConfigFn,
                );
            
                $this->_warehouseModel->setLoweringConfigFn($postdata);
                Session::set('message','Filename Updated');
                Url::redirect('config/system');
            } else {
                
                $data['loweringConfigFn'] = $loweringConfigFn;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editLoweringConfigFn',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function editDataDashboardManifestFn(){
        $data['title'] = 'Edit Data Dashboard Manifest Filename';
        $data['javascript'] = array('LinksFormHelper');
        $data['dataDashboardManifestFn'] = $this->_warehouseModel->getDataDashboardManifestFn();

        if(isset($_POST['submit'])){
            $dataDashboardManifestFn = $_POST['dataDashboardManifestFn'];

            if($dataDashboardManifestFn == ''){
                $error[] = 'Data dashboard manifest filename is required';
            }
            
            if($dataDashboardManifestFn == trim($dataDashboardManifestFn) && strpos($dataDashboardManifestFn, ' ') !== false) {
               $error[] = 'Data dashboard manifest filename contains spaces';
            }

            if(substr($dataDashboardManifestFn, -strlen('.json')) !== '.json') {
               $error[] = 'Data dashboard manifest filename does not end with .json';
            }

            if(!$error){
                $postdata = array(
                    'value' => $dataDashboardManifestFn,
                );
            
                $this->_warehouseModel->setDataDashboardManifestFn($postdata);
                Session::set('message','Filename Updated');
                Url::redirect('config/system');
            } else {
                
                $data['dataDashboardManifestFn'] = $dataDashboardManifestFn;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editDataDashboardManifestFn',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function editMD5SummaryFns(){
        $data['title'] = 'Edit Data Dashboard Manifest Filename';
        $data['javascript'] = array('LinksFormHelper');
        $data['md5SummaryFn'] = $this->_warehouseModel->getMd5SummaryFn();
        $data['md5SummaryMd5Fn'] = $this->_warehouseModel->getMd5SummaryMd5Fn();

        if(isset($_POST['submit'])){
            $md5SummaryFn = $_POST['md5SummaryFn'];
            $md5SummaryMd5Fn = $_POST['md5SummaryMd5Fn'];

            if($md5SummaryFn == ''){
                $error[] = 'MD5 summary filename is required';
            }
            
            if($md5SummaryFn == trim($md5SummaryFn) && strpos($md5SummaryFn, ' ') !== false) {
               $error[] = 'MD5 summary filename contains spaces';
            }

            if(substr($md5SummaryFn, -strlen('.txt')) !== '.txt') {
               $error[] = 'MD5 summary filename does not end with .txt';
            }

            if($md5SummaryMd5Fn == ''){
                $error[] = 'MD5 summary MD5 filename is required';
            } 

            if($md5SummaryMd5Fn == trim($md5SummaryMd5Fn) && strpos($md5SummaryMd5Fn, ' ') !== false) {
               $error[] = 'MD5 summary MD5 filename contains spaces';
            }

            if(substr($md5SummaryMd5Fn, -strlen('.md5')) !== '.md5') {
               $error[] = 'MD5 summary MD5 filename does not end with .md5';
            }

            if(!$error){
                $postdata = array(
                    'md5SummaryFn' => $md5SummaryFn,
                    'md5SummaryMd5Fn' => $md5SummaryMd5Fn,
                );
            
                $this->_warehouseModel->setMd5SummaryFns($postdata);
                Session::set('message','Filename Updated');
                Url::redirect('config/system');
            } else {
                
                $data['md5SummaryFn'] = $md5SummaryFn;
                $data['md5SummaryMd5Fn'] = $md5SummaryMd5Fn;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editMD5SummaryFns',$data,$error);
        View::rendertemplate('footer',$data);
    }
}
