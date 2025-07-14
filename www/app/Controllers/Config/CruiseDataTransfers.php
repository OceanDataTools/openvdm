<?php

namespace Controllers\Config;
use Core\Controller;
use Core\View;
use Helpers\Url;
use Helpers\Session;

class CruiseDataTransfers extends Controller {

    private $_cruiseDataTransfersModel,
            $_collectionSystemTransfersModel,
            $_extraDirectoriesModel,
            $_transferTypesModel;
    
    private function _buildTransferTypesOptions($checkedType = null) {
        $transferTypes = $this->_transferTypesModel->getTransferTypes();
        
        $output = array();
        $i=1;

        foreach($transferTypes as $row){
            $option = array('id'=>'transferType'.$i++, 'name'=>'transferType', 'value'=>$row->transferTypeID, 'label'=>$row->transferType);
            array_push($output, $option);
        }
        
        return $output;
    }

    private function _buildSkipEmptyDirsOptions() {
        
        $trueFalse = array(array('id'=>'skipEmptyDirs0', 'name'=>'skipEmptyDirs', 'value'=>'0', 'label'=>'No'), array('id'=>'skipEmptyDirs1', 'name'=>'skipEmptyDirs', 'value'=>'1', 'label'=>'Yes'));
        return $trueFalse;
    }

    private function _buildSkipEmptyFilesOptions() {
        
        $trueFalse = array(array('id'=>'skipEmptyFiles0', 'name'=>'skipEmptyFiles', 'value'=>'0', 'label'=>'No'), array('id'=>'skipEmptyFiles1', 'name'=>'skipEmptyFiles', 'value'=>'1', 'label'=>'Yes'));
        return $trueFalse;
    }

    private function _buildSyncToDestOptions() {
        
        $trueFalse = array(array('id'=>'syncToDest0', 'name'=>'syncToDest', 'value'=>'0', 'label'=>'No'), array('id'=>'syncToDest1', 'name'=>'syncToDest', 'value'=>'1', 'label'=>'Yes'));
        return $trueFalse;
    }

    private function _buildUseSSHKeyOptions() {
        
        $trueFalse = array(array('id'=>'useSSHKey0', 'name'=>'sshUseKey', 'value'=>'0', 'label'=>'No'), array('id'=>'useSSHKey1', 'name'=>'sshUseKey', 'value'=>'1', 'label'=>'Yes'));
        return $trueFalse;
    }

    private function _buildUseLocalMountPointOptions() {
        
        $trueFalse = array(array('id'=>'localDirIsMountPoint0', 'name'=>'localDirIsMountPoint', 'value'=>'0', 'label'=>'No'), array('id'=>'localDirIsMountPoint1', 'name'=>'localDirIsMountPoint', 'value'=>'1', 'label'=>'Yes'));
        return $trueFalse;
    }
    
    private function _buildIncludeOVDMFilesOptions() {
        
        $trueFalse = array(array('id'=>'includeOVDMFilesOptions0', 'name'=>'includeOVDMFiles', 'value'=>'0', 'label'=>'No'), array('id'=>'includeOVDMFilesOptions1', 'name'=>'includeOVDMFiles', 'value'=>'1', 'label'=>'Yes'));
        return $trueFalse;
    }

    public function __construct(){
        if(!Session::get('loggedin')){
            Url::redirect('config/login');
        }

        $this->_cruiseDataTransfersModel = new \Models\Config\CruiseDataTransfers();
        $this->_collectionSystemTransfersModel = new \Models\Config\CollectionSystemTransfers();
        $this->_extraDirectoriesModel = new \Models\Config\ExtraDirectories();
        $this->_transferTypesModel = new \Models\Config\TransferTypes();
    }

    public function index(){
        $data['title'] = 'Configuration';
        $data['cruiseDataTransfers'] = $this->_cruiseDataTransfersModel->getCruiseDataTransfers("longName");
        $data['javascript'] = array('cruiseDataTransfers');
        $data['filter'] = $_GET['filter'] ?? '';

        View::rendertemplate('header',$data);
        View::render('Config/cruiseDataTransfers',$data);
        View::rendertemplate('footer',$data);
    }

    public function add(){
        $data['title'] = 'Add ' . CRUISE_NAME . ' Data Transfer';
        $data['javascript'] = array('cruiseDataTransfersFormHelper');
        $data['filter'] = $_GET['filter'] ?? '';
        $data['transferTypeOptions'] = $this->_buildTransferTypesOptions($_POST['transferType']);
        $data['skipEmptyDirsOptions'] = $this->_buildSkipEmptyDirsOptions();
        $data['skipEmptyFilesOptions'] = $this->_buildSkipEmptyFilesOptions();
        $data['syncToDestOptions'] = $this->_buildSyncToDestOptions();
        $data['useSSHKeyOptions'] = $this->_buildUseSSHKeyOptions();
        $data['useLocalMountPointOptions'] = $this->_buildUseLocalMountPointOptions();
        $data['includeOVDMFilesOptions'] = $this->_buildIncludeOVDMFilesOptions();
        $data['collectionSystemTransfers'] = $this->_collectionSystemTransfersModel->getCollectionSystemTransfers();
        $data['extraDirectories'] = $this->_extraDirectoriesModel->getExtraDirectories(true);

        if(isset($_POST['submit'])){
            $name = $_POST['name'];
            $longName = $_POST['longName'];
            $includeOVDMFiles = $_POST['includeOVDMFiles'];
            $bandwidthLimit = $_POST['bandwidthLimit'];
            $transferType = $_POST['transferType'];
            $skipEmptyDirs = $_POST['skipEmptyDirs'];
            $skipEmptyFiles = $_POST['skipEmptyFiles'];
            $syncToDest = $_POST['syncToDest'];
            $destDir = $_POST['destDir'];
            $localDirIsMountPoint = $_POST['localDirIsMountPoint'];
            $rsyncServer = $_POST['rsyncServer'];
            $rsyncUser = $_POST['rsyncUser'];
            $rsyncPass = $_POST['rsyncPass'];
            $smbServer = $_POST['smbServer'];
            $smbUser = $_POST['smbUser'];
            $smbPass = $_POST['smbPass'];
            $smbDomain = $_POST['smbDomain'];
            $sshServer = $_POST['sshServer'];
            $sshUser = $_POST['sshUser'];
            $sshUseKey = $_POST['sshUseKey'];
            $sshPass = $_POST['sshPass'];
            $status = 3;
            $enable = 0;
            $excludedCollectionSystems = ($_POST['excludedCollectionSystems']) ? join(",", $_POST['excludedCollectionSystems']) : "";
            $excludedExtraDirectories = ($_POST['excludedExtraDirectories']) ? join(",", $_POST['excludedExtraDirectories']) : "";

            if($name == ''){
                $error[] = 'Name is required';
            } 
            elseif( preg_match('/\s/',$name) ){
                $error[] = 'Name cannot contain whitespace, underscores are acceptable';
	    }
	    
            if($longName == ''){
                $error[] = 'Long name is required';
            } 

            if($transferType == ''){
                $error[] = 'Transfer type is required';
            } 

            if($destDir == ''){
                $error[] = 'Destination Directory is required';
            }

            if ($bandwidthLimit === '') {
                $bandwidthLimit = '0';
            } elseif(!((string)(int)$bandwidthLimit == $bandwidthLimit)) {
                $error[] = 'Transfer limit must be an integer';
            }

            if ($transferType == 1) { //local directory
                $smbServer = '';
                $smbUser = '';
                $smbPass = '';
                $smbDomain = '';
                $rsyncServer = '';
                $rsyncUser = '';
                $rsyncPass = '';
                $sshServer = '';
                $sshUser = '';
                $sshUseKey = '0';
                $sshPass = '';

            } elseif ($transferType == 2) { // Rsync Server
                $rsyncDataCheck = true;
                if($rsyncServer == ''){
                    $error[] = 'Rsync Server is required';
                    $rsyncDataCheck = false;
                } 

                if($rsyncUser == ''){
                    $error[] = 'Rsync Username is required';
                    $rsyncDataCheck = false;
                } 

                if($rsyncUser != 'anonymous' && $rsyncPass == ''){
                    $error[] = 'Rsync Password is required';
                    $rsyncDataCheck = false;
                }
                
                if($rsyncDataCheck) {
                    $localDirIsMountPoint = '0';
                    $smbServer = '';
                    $smbUser = '';
                    $smbDomain = '';
                    $smbPass = '';
                    $sshServer = '';
                    $sshUser = '';
                    $sshUseKey = '0';
                    $sshPass = '';
                }

            } elseif ($transferType == 3) { // SMB Share
                $smbDataCheck = true;
                if($smbServer == ''){
                    $error[] = 'SMB Server is required';
                    $smbDataCheck = false;
                } 

                if($smbUser == ''){
                    $error[] = 'SMB Username is required';
                    $smbDataCheck = false;
                } 

                if($smbUser != 'guest' && $smbPass == ''){
                    $error[] = 'SMB Password is required';
                    $smbDataCheck = false;
                } 
            
                if($smbDomain == ''){
                    $smbDomain = 'WORKGROUP';
                    $smbDataCheck = false;
                }
                
                if($smbDataCheck) {
                    $localDirIsMountPoint = '0';
                    $rsyncServer = '';
                    $rsyncUser = '';
                    $rsyncPass = '';
                    $sshServer = '';
                    $sshUser = '';
                    $sshUseKey = '0';
                    $sshPass = '';
                }
                        
            } elseif ($transferType == 4) { // SSH Server
                $sshDataCheck = true;
                if($sshServer == ''){
                    $error[] = 'SSH Server is required';
                    $sshDataCheck = false;
                }

                if($sshUser == ''){
                    $error[] = 'SSH Username is required';
                    $sshDataCheck = false;
                }

                if((($sshPass == '') || is_null($sshPass)) && ($sshUseKey == 0)){
                    $error[] = 'SSH Password is required';
                    $sshDataCheck = false;
                }

                if($sshDataCheck) {
                    $localDirIsMountPoint = '0';
                    $smbServer = '';
                    $smbUser = '';
                    $smbDomain = '';
                    $smbPass = '';
                    $rsyncServer = '';
                    $rsyncUser = '';
                    $rsyncPass = '';
                }
            }

            if(!$error){
                $postdata = array(
                    'name' => $name,
                    'longName' => $longName,
                    'includeOVDMFiles' => $includeOVDMFiles,
                    'bandwidthLimit' => $bandwidthLimit,
                    'transferType' => $transferType,
                    'skipEmptyDirs' => $skipEmptyDirs,
                    'skipEmptyFiles' => $skipEmptyFiles,
                    'syncToDest' => $syncToDest,
                    'destDir' => $destDir,
                    'localDirIsMountPoint' => $localDirIsMountPoint,
                    'rsyncServer' => $rsyncServer,
                    'rsyncUser' => $rsyncUser,
                    'rsyncPass' => $rsyncPass,
                    'smbServer' => $smbServer,
                    'smbUser' => $smbUser,
                    'smbPass' => $smbPass,
                    'smbDomain' => $smbDomain,
                    'sshServer' => $sshServer,
                    'sshUser' => $sshUser,
                    'sshUseKey' => $sshUseKey,
                    'sshPass' => $sshPass,
                    'status' => $status,
                    'enable' => $enable,
                    'excludedCollectionSystems' => $excludedCollectionSystems,
                    'excludedExtraDirectories' => $excludedExtraDirectories,

                );

                $this->_cruiseDataTransfersModel->insertCruiseDataTransfer($postdata);
                Session::set('message',CRUISE_NAME . ' Data Transfer Added');
                Url::redirect('config/cruiseDataTransfers');
            }
        } elseif(isset($_POST['inlineTest'])){
            $name = $_POST['name'];
            $longName = $_POST['longName'];
            $includeOVDMFiles = $_POST['includeOVDMFiles'];
            $bandwidthLimit = $_POST['bandwidthLimit'];
            $transferType = $_POST['transferType'];
            $skipEmptyDirs = $_POST['skipEmptyDirs'];
            $skipEmptyFiles = $_POST['skipEmptyFiles'];
            $syncToDest = $_POST['syncToDest'];
            $destDir = $_POST['destDir'];
            $localDirIsMountPoint = $_POST['localDirIsMountPoint'];
            $rsyncServer = $_POST['rsyncServer'];
            $rsyncUser = $_POST['rsyncUser'];
            $rsyncPass = $_POST['rsyncPass'];
            $smbServer = $_POST['smbServer'];
            $smbUser = $_POST['smbUser'];
            $smbPass = $_POST['smbPass'];
            $smbDomain = $_POST['smbDomain'];
            $sshServer = $_POST['sshServer'];
            $sshUser = $_POST['sshUser'];
            $sshUseKey = $_POST['sshUseKey'];
            $sshPass = $_POST['sshPass'];
            $status = 3;
            $enable = 0;
            $excludedCollectionSystems = ($_POST['excludedCollectionSystems']) ? join(",", $_POST['excludedCollectionSystems']) : "";
            $excludedExtraDirectories = ($_POST['excludedExtraDirectories']) ? join(",", $_POST['excludedExtraDirectories']) : "";

            if($name == ''){
                $error[] = 'Name is required';
	    }
	    elseif( preg_match('/\s/',$name) ){
                $error[] = 'Name cannot contain whitespace, underscores are acceptable';
            }

            if($longName == ''){
                $error[] = 'Long name is required';
            } 

            if($transferType == ''){
                $error[] = 'Transfer type is required';
            } 

            if($destDir == ''){
                $error[] = 'Destination Directory is required';
            } 

            if ($bandwidthLimit === '') {
                $bandwidthLimit = '0';
            } elseif(!((string)(int)$bandwidthLimit == $bandwidthLimit)){
                $error[] = 'Transfer limit must be an integer';
            }

            if ($transferType == 1) { //local directory
                $smbServer = '';
                $smbUser = '';
                $smbPass = '';
                $smbDomain = '';
                $rsyncServer = '';
                $rsyncUser = '';
                $rsyncPass = '';
                $sshServer = '';
                $sshUser = '';
                $sshUseKey = '0';
                $sshPass = '';
            
            } elseif ($transferType == 2) { // Rsync Server
                $rsyncDataCheck = true;
                if($rsyncServer == ''){
                    $error[] = 'Rsync Server is required';
                    $rsyncDataCheck = false;
                } 

                if($rsyncUser == ''){
                    $error[] = 'Rsync Username is required';
                    $rsyncDataCheck = false;
                } 

                if($rsyncUser != 'anonymous' && $rsyncPass == ''){
                    $error[] = 'Rsync Password is required';
                    $rsyncDataCheck = false;
                }
                
                if($rsyncDataCheck) {
                    $localDirIsMountPoint = '0';
                    $smbServer = '';
                    $smbUser = '';
                    $smbPass = '';
                    $smbDomain = '';
                    $sshServer = '';
                    $sshUser = '';
                    $sshUseKey = '0';
                    $sshPass = '';
                }

            } elseif ($transferType == 3) { // SMB Share
                $smbDataCheck = true;
                if($smbServer == ''){
                    $error[] = 'SMB Server is required';
                    $smbDataCheck = false;
                } 

                if($smbUser == ''){
                    $error[] = 'SMB Username is required';
                    $smbDataCheck = false;
                } 

                if($smbUser != 'guest' && $smbPass == ''){
                    $error[] = 'SMB Password is required';
                    $smbDataCheck = false;
                } 
            
                if($smbDomain == ''){
                    $smbDomain = 'WORKGROUP';
                    $smbDataCheck = false;
                }
                
                if($smbDataCheck) {
                    $localDirIsMountPoint = '0';
                    $rsyncServer = '';
                    $rsyncUser = '';
                    $rsyncPass = '';
                    $sshServer = '';
                    $sshUser = '';
                    $sshUseKey = '0';
                    $sshPass = '';
                }
            
            } elseif ($transferType == 4) { // SSH Server
                $sshDataCheck = true;
                if($sshServer == ''){
                    $error[] = 'SSH Server is required';
                    $sshDataCheck = false;
                } 

                if($sshUser == ''){
                    $error[] = 'SSH Username is required';
                    $sshDataCheck = false;
                } 

                if((($sshPass == '') || is_null($sshPass)) && ($sshUseKey == 0)){
                    $error[] = 'SSH Password is required';
                    $sshDataCheck = false;
                }
                
                if($sshDataCheck) {
                    $localDirIsMountPoint = '0';
                    $smbServer = '';
                    $smbUser = '';
                    $smbDomain = '';
                    $smbPass = '';
                    $rsyncServer = '';
                    $rsyncUser = '';
                    $rsyncPass = '';
                }                
            }

            if(!$error){
                $_warehouseModel = new \Models\Warehouse();
                $gmData['cruiseDataTransfer'] = (object)array(
                    'name' => $name,
                    'longName' => $longName,
                    'includeOVDMFiles' => $includeOVDMFiles,
                    'bandwidthLimit' => $bandwidthLimit,
                    'transferType' => $transferType,
                    'skipEmptyDirs' => $skipEmptyDirs,
                    'skipEmptyFiles' => $skipEmptyFiles,
                    'syncToDest' => $syncToDest,
                    'destDir' => $destDir,
                    'localDirIsMountPoint' => $localDirIsMountPoint,
                    'rsyncServer' => $rsyncServer,
                    'rsyncUser' => $rsyncUser,
                    'rsyncPass' => $rsyncPass,
                    'smbServer' => $smbServer,
                    'smbUser' => $smbUser,
                    'smbPass' => $smbPass,
                    'smbDomain' => $smbDomain,
                    'sshServer' => $sshServer,
                    'sshUser' => $sshUser,
                    'sshUseKey' => $sshUseKey,
                    'sshPass' => $sshPass,
                    'status' => '4',
                    'enable' => '0',
                    'excludedCollectionSystems' => $excludedCollectionSystems,
                    'excludedExtraDirectories' => $excludedExtraDirectories,
                );
            
                # create the gearman client
                $gmc= new \GearmanClient();

                # add the default server (localhost)
                $gmc->addServer();

                #submit job to Gearman, wait for results
                $data['testResults'] = json_decode($gmc->doNormal("testCruiseDataTransfer", json_encode($gmData)), true);
                $data['testCruiseDataTransferName'] = $longName;     
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/addCruiseDataTransfers',$data,$error);
        View::rendertemplate('footer',$data);
    }
        
    public function edit($id){
        $data['title'] = 'Edit ' . CRUISE_NAME . ' Data Transfer';
        $data['javascript'] = array('cruiseDataTransfersFormHelper');
        $data['filter'] = $_GET['filter'] ?? '';
        $data['transferTypeOptions'] = $this->_buildTransferTypesOptions();
        $data['skipEmptyDirsOptions'] = $this->_buildSkipEmptyDirsOptions();
        $data['skipEmptyFilesOptions'] = $this->_buildSkipEmptyFilesOptions();
        $data['syncToDestOptions'] = $this->_buildSyncToDestOptions();
        $data['useSSHKeyOptions'] = $this->_buildUseSSHKeyOptions();
        $data['useLocalMountPointOptions'] = $this->_buildUseLocalMountPointOptions();
        $data['includeOVDMFilesOptions'] = $this->_buildIncludeOVDMFilesOptions();
        $data['collectionSystemTransfers'] = $this->_collectionSystemTransfersModel->getCollectionSystemTransfers();
        $data['extraDirectories'] = $this->_extraDirectoriesModel->getExtraDirectories(true);

        $data['row'] = $this->_cruiseDataTransfersModel->getCruiseDataTransfer($id);

        if(isset($_POST['submit'])){
            $name = $_POST['name'];
            $longName = $_POST['longName'];
            $includeOVDMFiles = $_POST['includeOVDMFiles'];
            $bandwidthLimit = $_POST['bandwidthLimit'];
            $transferType = $_POST['transferType'];
            $skipEmptyDirs = $_POST['skipEmptyDirs'];
            $skipEmptyFiles = $_POST['skipEmptyFiles'];
            $syncToDest = $_POST['syncToDest'];
            $destDir = $_POST['destDir'];
            $localDirIsMountPoint = $_POST['localDirIsMountPoint'];
            $rsyncServer = $_POST['rsyncServer'];
            $rsyncUser = $_POST['rsyncUser'];
            $rsyncPass = $_POST['rsyncPass'];
            $smbServer = $_POST['smbServer'];
            $smbUser = $_POST['smbUser'];
            $smbPass = $_POST['smbPass'];
            $smbDomain = $_POST['smbDomain'];
            $sshServer = $_POST['sshServer'];
            $sshUser = $_POST['sshUser'];
            $sshUseKey = $_POST['sshUseKey'];
            $sshPass = $_POST['sshPass'];
            $excludedCollectionSystems = ($_POST['excludedCollectionSystems']) ? join(",", $_POST['excludedCollectionSystems']) : "";
            $excludedExtraDirectories = ($_POST['excludedExtraDirectories']) ? join(",", $_POST['excludedExtraDirectories']) : "";

            if($name == ''){
                $error[] = 'Name is required';
	    }
	    elseif( preg_match('/\s/',$name) ){
                $error[] = 'Name cannot contain whitespace, underscores are acceptable';
            }

            if($longName == ''){
                $error[] = 'Long name is required';
            } 

            if($transferType == ''){
                $error[] = 'Transfer type is required';
            } 

            if($destDir == ''){
                $error[] = 'Destination Directory is required';
            }

            if ($bandwidthLimit === '') {
                $bandwidthLimit = '0';
            } else if(!((string)(int)$bandwidthLimit == $bandwidthLimit)){
                $error[] = 'Transfer limit must be an integer';
            }

            if ($transferType == 1) { //local directory
                $smbServer = '';
                $smbUser = '';
                $smbPass = '';
                $smbDomain = '';
                $rsyncServer = '';
                $rsyncUser = '';
                $rsyncPass = '';
                $sshServer = '';
                $sshUser = '';
                $sshUseKey = '0';
                $sshPass = '';
            
            } elseif ($transferType == 2) { //rsync
                $rsyncDataCheck = true;
                if($rsyncServer == ''){
                    $error[] = 'Rsync Server is required';
                    $rsyncDataCheck = false;
                } 

                if($rsyncUser == ''){
                    $error[] = 'Rsync Username is required';
                    $rsyncDataCheck = false;
                } 

                if($rsyncUser != 'anonymous' && $rsyncPass == ''){
                    $error[] = 'Rsync Password is required';
                    $rsyncDataCheck = false;
                }
                
                if($rsyncDataCheck) {
                    $localDirIsMountPoint = '0';
                    $smbServer = '';
                    $smbUser = '';
                    $smbDomain = '';
                    $smbPass = '';
                    $sshServer = '';
                    $sshUser = '';
                    $sshUseKey = '0';
                    $sshPass = '';
                }

            } elseif ($transferType == 3) { //smb
                $smbDataCheck = true;
                if($smbServer == ''){
                    $error[] = 'SMB Server is required';
                    $smbDataCheck = false;
                } 

                if($smbUser == ''){
                    $error[] = 'SMB Username is required';
                    $smbDataCheck = false;
                } 

//                if($smbUser != 'guest' && $smbPass == ''){
//                    $error[] = 'SMB Password is required';
//                    $smbDataCheck = false;
//                } 
                        
                if($smbDomain == ''){
                    $smbDomain = 'WORKGROUP';
                    $smbDataCheck = false;
                }
                
                if($smbDataCheck) {
                    $localDirIsMountPoint = '0';
                    $rsyncServer = '';
                    $rsyncUser = '';
                    $rsyncPass = '';
                    $sshServer = '';
                    $sshUser = '';
                    $sshPass = '';
                }
            } elseif ($transferType == 4) { // SSH Server
                $sshDataCheck = true;
                if($sshServer == ''){
                    $error[] = 'SSH Server is required';
                    $sshDataCheck = false;
                } 

                if($sshUser == ''){
                    $error[] = 'SSH Username is required';
                    $sshDataCheck = false;
                } 

                if((($sshPass == '') || is_null($sshPass)) && ($sshUseKey == 0)){
                    $error[] = 'SSH Password is required';
                    $sshDataCheck = false;
                } 
                
                if($sshDataCheck) {
                    $localDirIsMountPoint = '0';
                    $smbServer = '';
                    $smbUser = '';
                    $smbDomain = '';
                    $smbPass = '';
                    $rsyncServer = '';
                    $rsyncUser = '';
                    $rsyncPass = '';
                }
            }
                
            if(!$error){
                $postdata = array(
                    'name' => $name,
                    'longName' => $longName,
                    'includeOVDMFiles' => $includeOVDMFiles,
                    'bandwidthLimit' => $bandwidthLimit,
                    'transferType' => $transferType,
                    'skipEmptyDirs' => $skipEmptyDirs,
                    'skipEmptyFiles' => $skipEmptyFiles,
                    'syncToDest' => $syncToDest,
                    'destDir' => $destDir,
                    'localDirIsMountPoint' => $localDirIsMountPoint,
                    'rsyncServer' => $rsyncServer,
                    'rsyncUser' => $rsyncUser,
                    'rsyncPass' => $rsyncPass,
                    'smbServer' => $smbServer,
                    'smbUser' => $smbUser,
                    'smbPass' => $smbPass,
                    'smbDomain' => $smbDomain,
                    'sshServer' => $sshServer,
                    'sshUser' => $sshUser,
                    'sshUseKey' => $sshUseKey,
                    'sshPass' => $sshPass,
                    'excludedCollectionSystems' => $excludedCollectionSystems,
                    'excludedExtraDirectories' => $excludedExtraDirectories,
                );
                
                $where = array('cruiseDataTransferID' => $id);
                $this->_cruiseDataTransfersModel->updateCruiseDataTransfer($postdata,$where);
                
                $filter = $_GET['filter'] ? '?filter='.$_GET['filter'] : "";
                Session::set('message',CRUISE_NAME . ' Data Transfers Updated');
                Url::redirect('config/cruiseDataTransfers'.$filter);
            } else {
                
                $data['row'][0]->name = $name;
                $data['row'][0]->longName = $longName;
                $data['row'][0]->includeOVDMFiles = $includeOVDMFiles;
                $data['row'][0]->bandwidthLimit = $bandwidthLimit;
                $data['row'][0]->transferType = $transferType;
                $data['row'][0]->skipEmptyDirs = $skipEmptyDirs;
                $data['row'][0]->skipEmptyFiles = $skipEmptyFiles;
                $data['row'][0]->syncToDest = $syncToDest;
                $data['row'][0]->destDir = $destDir;
                $data['row'][0]->localDirIsMountPoint = $localDirIsMountPoint;
                $data['row'][0]->rsyncServer = $rsyncServer;
                $data['row'][0]->rsyncUser = $rsyncUser;
                $data['row'][0]->rsyncPass = $rsyncPass;
                $data['row'][0]->smbServer = $smbServer;
                $data['row'][0]->smbUser = $smbUser;
                $data['row'][0]->smbPass = $smbPass;
                $data['row'][0]->smbDomain = $smbDomain;
                $data['row'][0]->sshServer = $sshServer;
                $data['row'][0]->sshUser = $sshUser;
                $data['row'][0]->sshUseKey = $sshUseKey;
                $data['row'][0]->sshPass = $sshPass;
                $data['row'][0]->excludedCollectionSystems = $excludedCollectionSystems;
                $data['row'][0]->excludedExtraDirectories = $excludedExtraDirectories;
            }
        } else if(isset($_POST['inlineTest'])){

            $name = $_POST['name'];
            $longName = $_POST['longName'];
            $includeOVDMFiles = $_POST['includeOVDMFiles'];
            $bandwidthLimit = $_POST['bandwidthLimit'];
            $transferType = $_POST['transferType'];
            $skipEmptyDirs = $_POST['skipEmptyDirs'];
            $skipEmptyFiles = $_POST['skipEmptyFiles'];
            $syncToDest = $_POST['syncToDest'];
            $destDir = $_POST['destDir'];
            $localDirIsMountPoint = $_POST['localDirIsMountPoint'];
            $rsyncServer = $_POST['rsyncServer'];
            $rsyncUser = $_POST['rsyncUser'];
            $rsyncPass = $_POST['rsyncPass'];
            $smbServer = $_POST['smbServer'];
            $smbUser = $_POST['smbUser'];
            $smbPass = $_POST['smbPass'];
            $smbDomain = $_POST['smbDomain'];
            $sshServer = $_POST['sshServer'];
            $sshUser = $_POST['sshUser'];
            $sshUseKey = $_POST['sshUseKey'];
            $sshPass = $_POST['sshPass'];
            $excludedCollectionSystems = ($_POST['excludedCollectionSystems']) ? join(",", $_POST['excludedCollectionSystems']) : "";
            $excludedExtraDirectories = ($_POST['excludedExtraDirectories']) ? join(",", $_POST['excludedExtraDirectories']) : "";

            if($name == ''){
                $error[] = 'Name is required';
	    }
	    elseif( preg_match('/\s/',$name) ){
                $error[] = 'Name cannot contain whitespace, underscores are acceptable';
            } 

            if($longName == ''){
                $error[] = 'Long name is required';
            } 

            if($transferType == ''){
                $error[] = 'Transfer type is required';
            } 

            if($destDir == ''){
                $error[] = 'Destination Directory is required';
            }

            if ($bandwidthLimit === '') {
                $bandwidthLimit = '0';
            } elseif(!((string)(int)$bandwidthLimit == $bandwidthLimit)){
                $error[] = 'Transfer limit must be an integer';
            }

            if ($transferType == 1) { //local directory
                $smbServer = '';
                $smbUser = '';
                $smbPass = '';
                $smbDomain = '';
                $rsyncServer = '';
                $rsyncUser = '';
                $rsyncPass = '';
                $sshServer = '';
                $sshUser = '';
                $sshUseKey = '0';
                $sshPass = '';
            
            } elseif ($transferType == 2) { //rsync
                $rsyncDataCheck = true;
                if($rsyncServer == ''){
                    $error[] = 'Rsync Server is required';
                    $rsyncDataCheck = false;
                } 

                if($rsyncUser == ''){
                    $error[] = 'Rsync Username is required';
                    $rsyncDataCheck = false;
                } 

                if($rsyncUser != 'anonymous' && $rsyncPass == ''){
                    $error[] = 'Rsync Password is required';
                    $rsyncDataCheck = false;
                }
                
                if($rsyncDataCheck) {
                    $localDirIsMountPoint = '0';
                    $smbServer = '';
                    $smbUser = '';
                    $smbDomain = '';
                    $smbPass = '';
                    $sshServer = '';
                    $sshUser = '';
                    $sshUseKey = '0';
                    $sshPass = '';
                }

            } elseif ($transferType == 3) { //smb
                $smbDataCheck = true;
                if($smbServer == ''){
                    $error[] = 'SMB Server is required';
                    $smbDataCheck = false;
                } 

                if($smbUser == ''){
                    $error[] = 'SMB Username is required';
                    $smbDataCheck = false;
                } 

//                if($smbUser != 'guest' && $smbPass == ''){
//                    $error[] = 'SMB Password is required';
//                    $smbDataCheck = false;
//                } 
                        
                if($smbDomain == ''){
                    $smbDomain = 'WORKGROUP';
                    $smbDataCheck = false;
                }
                
                if($smbDataCheck) {
                    $localDirIsMountPoint = '0';
                    $rsyncServer = '';
                    $rsyncUser = '';
                    $rsyncPass = '';
                    $sshServer = '';
                    $sshUser = '';
                    $sshPass = '';
                }
            } elseif ($transferType == 4) { //ssh
                $sshDataCheck = true;
                if($sshServer == ''){
                    $error[] = 'SSH Server is required';
                    $sshDataCheck = false;
                } 

                if($sshUser == ''){
                    $error[] = 'SSH Username is required';
                    $sshDataCheck = false;
                } 

                if((($sshPass == '') || is_null($sshPass)) && ($sshUseKey == 0)){
                    $error[] = 'SSH Password is required';
                    $sshDataCheck = false;
                } 
                
                if($sshDataCheck) {
                    $localDirIsMountPoint = '0';
                    $smbServer = '';
                    $smbUser = '';
                    $smbDomain = '';
                    $smbPass = '';
                    $rsyncServer = '';
                    $rsyncUser = '';
                    $rsyncPass = '';
                }
            }
                
            if(!$error){

                $gmData['cruiseDataTransfer'] = $this->_cruiseDataTransfersModel->getCruiseDataTransfer($id)[0];
                
                $gmData['cruiseDataTransfer']->name = $name;
                $gmData['cruiseDataTransfer']->longName = $longName;
                $gmData['cruiseDataTransfer']->includeOVDMFiles = $includeOVDMFiles;
                $gmData['cruiseDataTransfer']->bandwidthLimit = $bandwidthLimit;
                $gmData['cruiseDataTransfer']->transferType = $transferType;
                $gmData['cruiseDataTransfer']->skipEmptyDirs = $skipEmptyDirs;
                $gmData['cruiseDataTransfer']->skipEmptyFiles = $skipEmptyFiles;
                $gmData['cruiseDataTransfer']->syncToDest = $syncToDest;
                $gmData['cruiseDataTransfer']->destDir = $destDir;
                $gmData['cruiseDataTransfer']->localDirIsMountPoint = $localDirIsMountPoint;
                $gmData['cruiseDataTransfer']->rsyncServer = $rsyncServer;
                $gmData['cruiseDataTransfer']->rsyncUser = $rsyncUser;
                $gmData['cruiseDataTransfer']->rsyncPass = $rsyncPass;
                $gmData['cruiseDataTransfer']->smbServer = $smbServer;
                $gmData['cruiseDataTransfer']->smbUser = $smbUser;
                $gmData['cruiseDataTransfer']->smbPass = $smbPass;
                $gmData['cruiseDataTransfer']->smbDomain = $smbDomain;
                $gmData['cruiseDataTransfer']->sshServer = $sshServer;
                $gmData['cruiseDataTransfer']->sshUser = $sshUser;
                $gmData['cruiseDataTransfer']->sshUseKey = $sshUseKey;
                $gmData['cruiseDataTransfer']->sshPass = $sshPass;
                $gmData['cruiseDataTransfer']->excludedCollectionSystems = $excludedCollectionSystems;
                $gmData['cruiseDataTransfer']->excludedExtraDirectories = $excludedExtraDirectories;
                
                # create the gearman client
                $gmc= new \GearmanClient();

                # add the default server (localhost)
                $gmc->addServer();

                #submit job to Gearman, wait for results
                $data['testResults'] = json_decode($gmc->doNormal("testCruiseDataTransfer", json_encode($gmData)), true);
                $data['testCruiseDataTransferName'] = $longName;      
            }

            #additional data needed for view
            $data['row'][0]->name = $name;
            $data['row'][0]->longName = $longName;
            $data['row'][0]->includeOVDMFiles = $includeOVDMFiles;
            $data['row'][0]->bandwidthLimit = $bandwidthLimit;
            $data['row'][0]->transferType = $transferType;
            $data['row'][0]->skipEmptyDirs = $skipEmptyDirs;
            $data['row'][0]->skipEmptyFiles = $skipEmptyFiles;
            $data['row'][0]->syncToDest = $syncToDest;
            $data['row'][0]->destDir = $destDir;
            $data['row'][0]->localDirIsMountPoint = $localDirIsMountPoint;
            $data['row'][0]->rsyncServer = $rsyncServer;
            $data['row'][0]->rsyncUser = $rsyncUser;
            $data['row'][0]->rsyncPass = $rsyncPass;
            $data['row'][0]->smbServer = $smbServer;
            $data['row'][0]->smbUser = $smbUser;
            $data['row'][0]->smbPass = $smbPass;
            $data['row'][0]->smbDomain = $smbDomain;
            $data['row'][0]->sshServer = $sshServer;
            $data['row'][0]->sshUser = $sshUser;
            $data['row'][0]->sshUseKey = $sshUseKey;
            $data['row'][0]->sshPass = $sshPass;
            $data['row'][0]->excludedCollectionSystems = $excludedCollectionSystems;
            $data['row'][0]->excludedExtraDirectories = $excludedExtraDirectories;
        
        }
        
        View::rendertemplate('header',$data);
        View::render('Config/editCruiseDataTransfers',$data,$error);
        View::rendertemplate('footer',$data);
    }
    
    public function delete($id){
                
        $where = array('cruiseDataTransferID' => $id);
        $this->_cruiseDataTransfersModel->deleteCruiseDataTransfer($where);
        $filter = $_GET['filter'] ? '?filter='.$_GET['filter'] : "";
        Session::set('message','Collection System Transfer Deleted');
        Url::redirect('config/cruiseDataTransfers'.$filter);
    }
    
    public function enable($id) {

        $this->_cruiseDataTransfersModel->enableCruiseDataTransfer($id);
        $filter = $_GET['filter'] ? '?filter='.$_GET['filter'] : "";
        Url::redirect('config/cruiseDataTransfers'.$filter);
    }
    
    public function disable($id) {

        $this->_cruiseDataTransfersModel->disableCruiseDataTransfer($id);
        $filter = $_GET['filter'] ? '?filter='.$_GET['filter'] : "";
        Url::redirect('config/cruiseDataTransfers'.$filter);
    }
    
    public function test($id) {
        
        $cruiseDataTransfer = $this->_cruiseDataTransfersModel->getCruiseDataTransfer($id)[0];
        $gmData = array(
            'cruiseDataTransfer' => array(
                'cruiseDataTransferID' => $cruiseDataTransfer->cruiseDataTransferID
            )
        );
                
        # create the gearman client
        $gmc= new \GearmanClient();

        # add the default server (localhost)
        $gmc->addServer();

        #submit job to Gearman, wait for results
        $data['testResults'] = json_decode($gmc->doNormal("testCruiseDataTransfer", json_encode($gmData)), true);

        $data['title'] = 'Configuration';
        $data['cruiseDataTransfers'] = $this->_cruiseDataTransfersModel->getCruiseDataTransfers("longName");
        $data['javascript'] = array('cruiseDataTransfers');
        $data['filter'] = $_GET['filter'] ?? '';

        #additional data needed for view
        $data['testCruiseDataTransferName'] = $cruiseDataTransfer->longName;

        View::rendertemplate('header',$data);
        View::render('Config/cruiseDataTransfers',$data);
        View::rendertemplate('footer',$data);
    }
    
    public function run($id) {
        
        $this->_cruiseDataTransfersModel->setStartingCruiseDataTransfer($id);

        $_warehouseModel = new \Models\Warehouse();
        $gmData['siteRoot'] = DIR;
        $gmData['shipboardDataWarehouse'] = $_warehouseModel->getShipboardDataWarehouseConfig();
        $gmData['cruiseID'] = $_warehouseModel->getCruiseID();
        $gmData['cruiseDataTransfer'] = $this->_cruiseDataTransfersModel->getCruiseDataTransfer($id)[0];
        $gmData['cruiseDataTransfer']->enable = "1";
        $gmData['systemStatus'] = "On";

        
        # create the gearman client
        $gmc= new \GearmanClient();

        # add the default server (localhost)
        $gmc->addServer();

        #submit job to Gearman
        $job_handle = $gmc->doBackground("runCruiseDataTransfer", json_encode($gmData));
    
        sleep(1);
        
        $filter = $_GET['filter'] ? '?filter='.$_GET['filter'] : "";
        Url::redirect('config/cruiseDataTransfers'.$filter);
    }
        
    public function stop($id) {

        $this->_cruiseDataTransfersModel->setStoppingCruiseDataTransfer($id);
        
        $gmData = array(
            'pid' => $this->_cruiseDataTransfersModel->getCruiseDataTransfer($id)[0]->pid
        );

        //var_dump($gmData);
        
        # create the gearman client
        $gmc= new \GearmanClient();

        # add the default server (localhost)
        $gmc->addServer();

        #submit job to Gearman
        $job_handle = $gmc->doBackground("stopJob", json_encode($gmData));
    
        sleep(1);

        $filter = $_GET['filter'] ? '?filter='.$_GET['filter'] : "";    
        Url::redirect('config/cruiseDataTransfers'.$filter);
    }
}
