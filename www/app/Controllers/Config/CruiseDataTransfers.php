<?php

namespace Controllers\Config;
use Core\Controller;
use Core\View;
use Helpers\Url;
use Helpers\Session;
use Helpers\PendingPasswords;
use Helpers\FtpFields;
use Helpers\TransferFields;

class CruiseDataTransfers extends Controller {

    // Transfer types that aren't available for cruise data transfers: hidden
    // in the form, and rejected when submitted anyway (#210). Empty since FTP
    // Server destinations were added (#199).
    const UNSUPPORTED_TRANSFER_TYPES = array();

    private $_cruiseDataTransfersModel,
            $_collectionSystemTransfersModel,
            $_extraDirectoriesModel,
            $_transferTypesModel;

    // Transfer type choices for the form's Form::select(), as ID => name,
    // leaving out UNSUPPORTED_TRANSFER_TYPES (#226).
    private function _buildTransferTypesOptions() {
        $transferTypes = $this->_transferTypesModel->getTransferTypes();

        $output = array();

        foreach($transferTypes as $row){
            if (in_array((int)$row->transferTypeID, self::UNSUPPORTED_TRANSFER_TYPES, true)) {
                continue;
            }
            $output[$row->transferTypeID] = $row->transferType;
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
        $data['transferTypeOptions'] = $this->_buildTransferTypesOptions();
        $data['skipEmptyDirsOptions'] = $this->_buildSkipEmptyDirsOptions();
        $data['skipEmptyFilesOptions'] = $this->_buildSkipEmptyFilesOptions();
        $data['syncToDestOptions'] = $this->_buildSyncToDestOptions();
        $data['useSSHKeyOptions'] = $this->_buildUseSSHKeyOptions();
        $data['useLocalMountPointOptions'] = $this->_buildUseLocalMountPointOptions();
        $data['includeOVDMFilesOptions'] = $this->_buildIncludeOVDMFilesOptions();
        $data['collectionSystemTransfers'] = $this->_collectionSystemTransfersModel->getCollectionSystemTransfers();
        $data['extraDirectories'] = $this->_extraDirectoriesModel->getExtraDirectories(true);
        $error = [];

        if(isset($_POST['submit'])){
            $name = $_POST['name'] ?? '';
            $longName = $_POST['longName'] ?? '';
            $includeOVDMFiles = $_POST['includeOVDMFiles'] ?? '';
            $bandwidthLimit = $_POST['bandwidthLimit'] ?? '';
            $transferType = $_POST['transferType'] ?? '';
            $skipEmptyDirs = $_POST['skipEmptyDirs'] ?? '';
            $skipEmptyFiles = $_POST['skipEmptyFiles'] ?? '';
            $syncToDest = $_POST['syncToDest'] ?? '';
            $destDir = $_POST['destDir'] ?? '';
            $localDirIsMountPoint = $_POST['localDirIsMountPoint'] ?? '';
            $rsyncServer = $_POST['rsyncServer'] ?? '';
            $rsyncUser = $_POST['rsyncUser'] ?? '';
            $rsyncPass = $_POST['rsyncPass'] ?? '';
            $smbServer = $_POST['smbServer'] ?? '';
            $smbUser = $_POST['smbUser'] ?? '';
            $smbPass = $_POST['smbPass'] ?? '';
            $smbDomain = $_POST['smbDomain'] ?? '';
            $sshServer = $_POST['sshServer'] ?? '';
            $sshUser = $_POST['sshUser'] ?? '';
            $sshUseKey = $_POST['sshUseKey'] ?? '';
            $sshPass = $_POST['sshPass'] ?? '';
            $ftpServer = $_POST['ftpServer'] ?? '';
            $ftpUser = $_POST['ftpUser'] ?? '';
            $ftpPass = $_POST['ftpPass'] ?? '';
            $status = 3;
            $enable = 0;
            $excludedCollectionSystems = !empty($_POST['excludedCollectionSystems']) ? join(",", $_POST['excludedCollectionSystems']) : "";
            $excludedExtraDirectories = !empty($_POST['excludedExtraDirectories']) ? join(",", $_POST['excludedExtraDirectories']) : "";

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
            } elseif(in_array((int)$transferType, self::UNSUPPORTED_TRANSFER_TYPES, true)){
                $error[] = 'This transfer type is not available for cruise data transfers';
            }

            if($destDir == ''){
                $error[] = 'Destination Directory is required';
            } elseif($transferType != '' && $transferType != 1 && strpos($destDir, ':') !== false){
                // ':' marks an rclone remote:path, which only Local Directory
                // destinations use; the workers route Test Setup on it
                $error[] = "Destination Directory can't contain ':' — rclone remote:path destinations use the Local Directory transfer type";
            }

            if ($bandwidthLimit === '') {
                $bandwidthLimit = '0';
            } elseif(!((string)(int)$bandwidthLimit == $bandwidthLimit)) {
                $error[] = 'Transfer limit must be an integer';
            }

            $error = array_merge($error, FtpFields::check($transferType, $ftpServer, $ftpUser, $ftpPass));

            if ($transferType == 2) { // Rsync Server
                if($rsyncServer == ''){
                    $error[] = 'Rsync Server is required';
                }

                if($rsyncUser == ''){
                    $error[] = 'Rsync Username is required';
                }

                if($rsyncUser != 'anonymous' && $rsyncPass == ''){
                    $error[] = 'Rsync Password is required';
                }

            } elseif ($transferType == 3) { // SMB Share
                if($smbServer == ''){
                    $error[] = 'SMB Server is required';
                }

                if($smbUser == ''){
                    $error[] = 'SMB Username is required';
                }

                if($smbUser != 'guest' && $smbPass == ''){
                    $error[] = 'SMB Password is required';
                }

                if($smbDomain == ''){
                    $smbDomain = 'WORKGROUP';
                }

            } elseif ($transferType == 4) { // SSH Server
                if($sshServer == ''){
                    $error[] = 'SSH Server is required';
                }

                if($sshUser == ''){
                    $error[] = 'SSH Username is required';
                }

                if((($sshPass == '') || is_null($sshPass)) && ($sshUseKey == 0)){
                    $error[] = 'SSH Password is required';
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
                    'ftpServer' => $ftpServer,
                    'ftpUser' => $ftpUser,
                    'ftpPass' => $ftpPass,
                    'status' => $status,
                    'enable' => $enable,
                    'excludedCollectionSystems' => $excludedCollectionSystems,
                    'excludedExtraDirectories' => $excludedExtraDirectories,

                );

                $postdata = TransferFields::clearOthers($postdata);

                $this->_cruiseDataTransfersModel->insertCruiseDataTransfer($postdata);
                Session::set('message',CRUISE_NAME . ' Data Transfer Added');
                Url::redirect('config/cruiseDataTransfers');
            }
        } elseif(isset($_POST['inlineTest'])){
            $name = $_POST['name'] ?? '';
            $longName = $_POST['longName'] ?? '';
            $includeOVDMFiles = $_POST['includeOVDMFiles'] ?? '';
            $bandwidthLimit = $_POST['bandwidthLimit'] ?? '';
            $transferType = $_POST['transferType'] ?? '';
            $skipEmptyDirs = $_POST['skipEmptyDirs'] ?? '';
            $skipEmptyFiles = $_POST['skipEmptyFiles'] ?? '';
            $syncToDest = $_POST['syncToDest'] ?? '';
            $destDir = $_POST['destDir'] ?? '';
            $localDirIsMountPoint = $_POST['localDirIsMountPoint'] ?? '';
            $rsyncServer = $_POST['rsyncServer'] ?? '';
            $rsyncUser = $_POST['rsyncUser'] ?? '';
            $rsyncPass = $_POST['rsyncPass'] ?? '';
            $smbServer = $_POST['smbServer'] ?? '';
            $smbUser = $_POST['smbUser'] ?? '';
            $smbPass = $_POST['smbPass'] ?? '';
            $smbDomain = $_POST['smbDomain'] ?? '';
            $sshServer = $_POST['sshServer'] ?? '';
            $sshUser = $_POST['sshUser'] ?? '';
            $sshUseKey = $_POST['sshUseKey'] ?? '';
            $sshPass = $_POST['sshPass'] ?? '';
            $ftpServer = $_POST['ftpServer'] ?? '';
            $ftpUser = $_POST['ftpUser'] ?? '';
            $ftpPass = $_POST['ftpPass'] ?? '';
            $status = 3;
            $enable = 0;
            $excludedCollectionSystems = !empty($_POST['excludedCollectionSystems']) ? join(",", $_POST['excludedCollectionSystems']) : "";
            $excludedExtraDirectories = !empty($_POST['excludedExtraDirectories']) ? join(",", $_POST['excludedExtraDirectories']) : "";

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
            } elseif(in_array((int)$transferType, self::UNSUPPORTED_TRANSFER_TYPES, true)){
                $error[] = 'This transfer type is not available for cruise data transfers';
            }

            if($destDir == ''){
                $error[] = 'Destination Directory is required';
            } elseif($transferType != '' && $transferType != 1 && strpos($destDir, ':') !== false){
                // ':' marks an rclone remote:path, which only Local Directory
                // destinations use; the workers route Test Setup on it
                $error[] = "Destination Directory can't contain ':' — rclone remote:path destinations use the Local Directory transfer type";
            }

            if ($bandwidthLimit === '') {
                $bandwidthLimit = '0';
            } elseif(!((string)(int)$bandwidthLimit == $bandwidthLimit)){
                $error[] = 'Transfer limit must be an integer';
            }

            $error = array_merge($error, FtpFields::check($transferType, $ftpServer, $ftpUser, $ftpPass));

            if ($transferType == 2) { // Rsync Server
                if($rsyncServer == ''){
                    $error[] = 'Rsync Server is required';
                }

                if($rsyncUser == ''){
                    $error[] = 'Rsync Username is required';
                }

                if($rsyncUser != 'anonymous' && $rsyncPass == ''){
                    $error[] = 'Rsync Password is required';
                }

            } elseif ($transferType == 3) { // SMB Share
                if($smbServer == ''){
                    $error[] = 'SMB Server is required';
                }

                if($smbUser == ''){
                    $error[] = 'SMB Username is required';
                }

                if($smbUser != 'guest' && $smbPass == ''){
                    $error[] = 'SMB Password is required';
                }

                if($smbDomain == ''){
                    $smbDomain = 'WORKGROUP';
                }

            } elseif ($transferType == 4) { // SSH Server
                if($sshServer == ''){
                    $error[] = 'SSH Server is required';
                }

                if($sshUser == ''){
                    $error[] = 'SSH Username is required';
                }

                if((($sshPass == '') || is_null($sshPass)) && ($sshUseKey == 0)){
                    $error[] = 'SSH Password is required';
                }
            }

            if(!$error){
                $_warehouseModel = new \Models\Warehouse();
                $gmData['cruiseDataTransfer'] = (object)array(
                    'name' => $name,
                    'longName' => $longName,
                    'includeOVDMFiles' => (int)$includeOVDMFiles,
                    'bandwidthLimit' => (int)$bandwidthLimit,
                    'transferType' => (int)$transferType,
                    'skipEmptyDirs' => (int)$skipEmptyDirs,
                    'skipEmptyFiles' => (int)$skipEmptyFiles,
                    'syncToDest' => (int)$syncToDest,
                    'destDir' => $destDir,
                    'localDirIsMountPoint' => (int)$localDirIsMountPoint,
                    'rsyncServer' => $rsyncServer,
                    'rsyncUser' => $rsyncUser,
                    'rsyncPass' => $rsyncPass,
                    'smbServer' => $smbServer,
                    'smbUser' => $smbUser,
                    'smbPass' => $smbPass,
                    'smbDomain' => $smbDomain,
                    'sshServer' => $sshServer,
                    'sshUser' => $sshUser,
                    'sshUseKey' => (int)$sshUseKey,
                    'sshPass' => $sshPass,
                    'ftpServer' => $ftpServer,
                    'ftpUser' => $ftpUser,
                    'ftpPass' => $ftpPass,
                    'status' => 4,
                    'enable' => 0,
                    'excludedCollectionSystems' => $excludedCollectionSystems,
                    'excludedExtraDirectories' => $excludedExtraDirectories,
                );

                $gmData['cruiseDataTransfer'] = TransferFields::clearOthers($gmData['cruiseDataTransfer']);

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
        $error = [];

        # a fresh page load discards any password remembered from an earlier "Test Setup"
        if(!isset($_POST['submit']) && !isset($_POST['inlineTest'])){
            PendingPasswords::clear('cdt', $id);
        }

        if(isset($_POST['submit'])){
            $name = $_POST['name'] ?? '';
            $longName = $_POST['longName'] ?? '';
            $includeOVDMFiles = $_POST['includeOVDMFiles'] ?? '';
            $bandwidthLimit = $_POST['bandwidthLimit'] ?? '';
            $transferType = $_POST['transferType'] ?? '';
            $skipEmptyDirs = $_POST['skipEmptyDirs'] ?? '';
            $skipEmptyFiles = $_POST['skipEmptyFiles'] ?? '';
            $syncToDest = $_POST['syncToDest'] ?? '';
            $destDir = $_POST['destDir'] ?? '';
            $localDirIsMountPoint = $_POST['localDirIsMountPoint'] ?? '';
            $rsyncServer = $_POST['rsyncServer'] ?? '';
            $rsyncUser = $_POST['rsyncUser'] ?? '';
            $rsyncPass = $_POST['rsyncPass'] ?? '';
            $smbServer = $_POST['smbServer'] ?? '';
            $smbUser = $_POST['smbUser'] ?? '';
            $smbPass = $_POST['smbPass'] ?? '';
            $smbDomain = $_POST['smbDomain'] ?? '';
            $sshServer = $_POST['sshServer'] ?? '';
            $sshUser = $_POST['sshUser'] ?? '';
            $sshUseKey = $_POST['sshUseKey'] ?? '';
            $sshPass = $_POST['sshPass'] ?? '';
            $ftpServer = $_POST['ftpServer'] ?? '';
            $ftpUser = $_POST['ftpUser'] ?? '';
            $ftpPass = $_POST['ftpPass'] ?? '';
            $excludedCollectionSystems = !empty($_POST['excludedCollectionSystems']) ? join(",", $_POST['excludedCollectionSystems']) : "";
            $excludedExtraDirectories = !empty($_POST['excludedExtraDirectories']) ? join(",", $_POST['excludedExtraDirectories']) : "";

            $passwords = PendingPasswords::resolve('cdt', $id, array('rsyncPass' => $rsyncPass, 'smbPass' => $smbPass, 'sshPass' => $sshPass, 'ftpPass' => $ftpPass), $data['row'][0], false);
            $rsyncPass = $passwords['rsyncPass'];
            $smbPass = $passwords['smbPass'];
            $sshPass = $passwords['sshPass'];
            $ftpPass = $passwords['ftpPass'];

            // Don't send a password saved for another FTP login (#211)
            $ftpPass = FtpFields::resolvePassword($ftpUser, $ftpPass, $_POST['ftpPass'] ?? '', $data['row'][0]);

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
            } elseif(in_array((int)$transferType, self::UNSUPPORTED_TRANSFER_TYPES, true)){
                $error[] = 'This transfer type is not available for cruise data transfers';
            }

            if($destDir == ''){
                $error[] = 'Destination Directory is required';
            } elseif($transferType != '' && $transferType != 1 && strpos($destDir, ':') !== false){
                // ':' marks an rclone remote:path, which only Local Directory
                // destinations use; the workers route Test Setup on it
                $error[] = "Destination Directory can't contain ':' — rclone remote:path destinations use the Local Directory transfer type";
            }

            if ($bandwidthLimit === '') {
                $bandwidthLimit = '0';
            } else if(!((string)(int)$bandwidthLimit == $bandwidthLimit)){
                $error[] = 'Transfer limit must be an integer';
            }

            $error = array_merge($error, FtpFields::check($transferType, $ftpServer, $ftpUser, $ftpPass));

            if ($transferType == 2) { //rsync
                if($rsyncServer == ''){
                    $error[] = 'Rsync Server is required';
                }

                if($rsyncUser == ''){
                    $error[] = 'Rsync Username is required';
                }

                if($rsyncUser != 'anonymous' && $rsyncPass == ''){
                    $error[] = 'Rsync Password is required';
                }

            } elseif ($transferType == 3) { //smb
                if($smbServer == ''){
                    $error[] = 'SMB Server is required';
                }

                if($smbUser == ''){
                    $error[] = 'SMB Username is required';
                }

//                if($smbUser != 'guest' && $smbPass == ''){
//                    $error[] = 'SMB Password is required';
//                }

                if($smbDomain == ''){
                    $smbDomain = 'WORKGROUP';
                }
            } elseif ($transferType == 4) { // SSH Server
                if($sshServer == ''){
                    $error[] = 'SSH Server is required';
                }

                if($sshUser == ''){
                    $error[] = 'SSH Username is required';
                }

                if((($sshPass == '') || is_null($sshPass)) && ($sshUseKey == 0)){
                    $error[] = 'SSH Password is required';
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
                    'ftpServer' => $ftpServer,
                    'ftpUser' => $ftpUser,
                    'ftpPass' => $ftpPass,
                    'excludedCollectionSystems' => $excludedCollectionSystems,
                    'excludedExtraDirectories' => $excludedExtraDirectories,
                );

                $where = array('cruiseDataTransferID' => $id);
                $postdata = TransferFields::clearOthers($postdata);
                $this->_cruiseDataTransfersModel->updateCruiseDataTransfer($postdata,$where);

                $filter = !empty($_GET['filter']) ? '?filter='.$_GET['filter'] : "";
                PendingPasswords::clear('cdt', $id);
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
                $data['row'][0]->smbServer = $smbServer;
                $data['row'][0]->smbUser = $smbUser;
                $data['row'][0]->smbDomain = $smbDomain;
                $data['row'][0]->sshServer = $sshServer;
                $data['row'][0]->sshUser = $sshUser;
                $data['row'][0]->sshUseKey = $sshUseKey;
                $data['row'][0]->ftpServer = $ftpServer;
                $data['row'][0]->ftpUser = $ftpUser;
                $data['row'][0]->excludedCollectionSystems = $excludedCollectionSystems;
                $data['row'][0]->excludedExtraDirectories = $excludedExtraDirectories;
            }
        } else if(isset($_POST['inlineTest'])){

            $name = $_POST['name'] ?? '';
            $longName = $_POST['longName'] ?? '';
            $includeOVDMFiles = $_POST['includeOVDMFiles'] ?? '';
            $bandwidthLimit = $_POST['bandwidthLimit'] ?? '';
            $transferType = $_POST['transferType'] ?? '';
            $skipEmptyDirs = $_POST['skipEmptyDirs'] ?? '';
            $skipEmptyFiles = $_POST['skipEmptyFiles'] ?? '';
            $syncToDest = $_POST['syncToDest'] ?? '';
            $destDir = $_POST['destDir'] ?? '';
            $localDirIsMountPoint = $_POST['localDirIsMountPoint'] ?? '';
            $rsyncServer = $_POST['rsyncServer'] ?? '';
            $rsyncUser = $_POST['rsyncUser'] ?? '';
            $rsyncPass = $_POST['rsyncPass'] ?? '';
            $smbServer = $_POST['smbServer'] ?? '';
            $smbUser = $_POST['smbUser'] ?? '';
            $smbPass = $_POST['smbPass'] ?? '';
            $smbDomain = $_POST['smbDomain'] ?? '';
            $sshServer = $_POST['sshServer'] ?? '';
            $sshUser = $_POST['sshUser'] ?? '';
            $sshUseKey = $_POST['sshUseKey'] ?? '';
            $sshPass = $_POST['sshPass'] ?? '';
            $ftpServer = $_POST['ftpServer'] ?? '';
            $ftpUser = $_POST['ftpUser'] ?? '';
            $ftpPass = $_POST['ftpPass'] ?? '';
            $excludedCollectionSystems = !empty($_POST['excludedCollectionSystems']) ? join(",", $_POST['excludedCollectionSystems']) : "";
            $excludedExtraDirectories = !empty($_POST['excludedExtraDirectories']) ? join(",", $_POST['excludedExtraDirectories']) : "";

            $passwords = PendingPasswords::resolve('cdt', $id, array('rsyncPass' => $rsyncPass, 'smbPass' => $smbPass, 'sshPass' => $sshPass, 'ftpPass' => $ftpPass), $data['row'][0], true);
            $rsyncPass = $passwords['rsyncPass'];
            $smbPass = $passwords['smbPass'];
            $sshPass = $passwords['sshPass'];
            $ftpPass = $passwords['ftpPass'];

            // Don't send a password saved for another FTP login (#211)
            $ftpPass = FtpFields::resolvePassword($ftpUser, $ftpPass, $_POST['ftpPass'] ?? '', $data['row'][0]);

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
            } elseif(in_array((int)$transferType, self::UNSUPPORTED_TRANSFER_TYPES, true)){
                $error[] = 'This transfer type is not available for cruise data transfers';
            }

            if($destDir == ''){
                $error[] = 'Destination Directory is required';
            } elseif($transferType != '' && $transferType != 1 && strpos($destDir, ':') !== false){
                // ':' marks an rclone remote:path, which only Local Directory
                // destinations use; the workers route Test Setup on it
                $error[] = "Destination Directory can't contain ':' — rclone remote:path destinations use the Local Directory transfer type";
            }

            if ($bandwidthLimit === '') {
                $bandwidthLimit = '0';
            } elseif(!((string)(int)$bandwidthLimit == $bandwidthLimit)){
                $error[] = 'Transfer limit must be an integer';
            }

            $error = array_merge($error, FtpFields::check($transferType, $ftpServer, $ftpUser, $ftpPass));

            if ($transferType == 2) { //rsync
                if($rsyncServer == ''){
                    $error[] = 'Rsync Server is required';
                }

                if($rsyncUser == ''){
                    $error[] = 'Rsync Username is required';
                }

                if($rsyncUser != 'anonymous' && $rsyncPass == ''){
                    $error[] = 'Rsync Password is required';
                }

            } elseif ($transferType == 3) { //smb
                if($smbServer == ''){
                    $error[] = 'SMB Server is required';
                }

                if($smbUser == ''){
                    $error[] = 'SMB Username is required';
                }

//                if($smbUser != 'guest' && $smbPass == ''){
//                    $error[] = 'SMB Password is required';
//                }

                if($smbDomain == ''){
                    $smbDomain = 'WORKGROUP';
                }
            } elseif ($transferType == 4) { //ssh
                if($sshServer == ''){
                    $error[] = 'SSH Server is required';
                }

                if($sshUser == ''){
                    $error[] = 'SSH Username is required';
                }

                if((($sshPass == '') || is_null($sshPass)) && ($sshUseKey == 0)){
                    $error[] = 'SSH Password is required';
                }
            }

            if(!$error){

                $gmData['cruiseDataTransfer'] = $this->_cruiseDataTransfersModel->getCruiseDataTransfer($id)[0];

                $gmData['cruiseDataTransfer']->name = $name;
                $gmData['cruiseDataTransfer']->longName = $longName;
                $gmData['cruiseDataTransfer']->includeOVDMFiles = (int)$includeOVDMFiles;
                $gmData['cruiseDataTransfer']->bandwidthLimit = (int)$bandwidthLimit;
                $gmData['cruiseDataTransfer']->transferType = (int)$transferType;
                $gmData['cruiseDataTransfer']->skipEmptyDirs = (int)$skipEmptyDirs;
                $gmData['cruiseDataTransfer']->skipEmptyFiles = (int)$skipEmptyFiles;
                $gmData['cruiseDataTransfer']->syncToDest = (int)$syncToDest;
                $gmData['cruiseDataTransfer']->destDir = $destDir;
                $gmData['cruiseDataTransfer']->localDirIsMountPoint = (int)$localDirIsMountPoint;
                $gmData['cruiseDataTransfer']->rsyncServer = $rsyncServer;
                $gmData['cruiseDataTransfer']->rsyncUser = $rsyncUser;
                $gmData['cruiseDataTransfer']->rsyncPass = $rsyncPass;
                $gmData['cruiseDataTransfer']->smbServer = $smbServer;
                $gmData['cruiseDataTransfer']->smbUser = $smbUser;
                $gmData['cruiseDataTransfer']->smbPass = $smbPass;
                $gmData['cruiseDataTransfer']->smbDomain = $smbDomain;
                $gmData['cruiseDataTransfer']->sshServer = $sshServer;
                $gmData['cruiseDataTransfer']->sshUser = $sshUser;
                $gmData['cruiseDataTransfer']->sshUseKey = (int)$sshUseKey;
                $gmData['cruiseDataTransfer']->sshPass = $sshPass;
                $gmData['cruiseDataTransfer']->ftpServer = $ftpServer;
                $gmData['cruiseDataTransfer']->ftpUser = $ftpUser;
                $gmData['cruiseDataTransfer']->ftpPass = $ftpPass;
                $gmData['cruiseDataTransfer']->excludedCollectionSystems = $excludedCollectionSystems;
                $gmData['cruiseDataTransfer']->excludedExtraDirectories = $excludedExtraDirectories;

                $gmData['cruiseDataTransfer'] = TransferFields::clearOthers($gmData['cruiseDataTransfer']);

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
            $data['row'][0]->smbServer = $smbServer;
            $data['row'][0]->smbUser = $smbUser;
            $data['row'][0]->smbDomain = $smbDomain;
            $data['row'][0]->sshServer = $sshServer;
            $data['row'][0]->sshUser = $sshUser;
            $data['row'][0]->sshUseKey = $sshUseKey;
            $data['row'][0]->ftpServer = $ftpServer;
            $data['row'][0]->ftpUser = $ftpUser;
            $data['row'][0]->excludedCollectionSystems = $excludedCollectionSystems;
            $data['row'][0]->excludedExtraDirectories = $excludedExtraDirectories;

        }

        $data['pendingPasswords'] = PendingPasswords::flags('cdt', $id);

        View::rendertemplate('header',$data);
        View::render('Config/editCruiseDataTransfers',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function delete($id){

        $where = array('cruiseDataTransferID' => $id);
        $this->_cruiseDataTransfersModel->deleteCruiseDataTransfer($where);
        $filter = !empty($_GET['filter']) ? '?filter='.$_GET['filter'] : "";
        Session::set('message','Collection System Transfer Deleted');
        Url::redirect('config/cruiseDataTransfers'.$filter);
    }

    public function enable($id) {

        $this->_cruiseDataTransfersModel->enableCruiseDataTransfer($id);
        $filter = !empty($_GET['filter']) ? '?filter='.$_GET['filter'] : "";
        Url::redirect('config/cruiseDataTransfers'.$filter);
    }

    public function disable($id) {

        $this->_cruiseDataTransfersModel->disableCruiseDataTransfer($id);
        $filter = !empty($_GET['filter']) ? '?filter='.$_GET['filter'] : "";
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

        $filter = !empty($_GET['filter']) ? '?filter='.$_GET['filter'] : "";
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

        $filter = !empty($_GET['filter']) ? '?filter='.$_GET['filter'] : "";
        Url::redirect('config/cruiseDataTransfers'.$filter);
    }
}
