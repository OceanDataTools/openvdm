<?php

namespace controllers\config;
use Core\Controller;
use Core\View;
use Helpers\Url;
use Helpers\Session;

class ExtraDirectories extends Controller {

    private $_extraDirectoriesModel;

    private function _buildCruiseOrLoweringOptions() {

        $output = array(array('id'=>'cruiseOrLowering0', 'name'=>'cruiseOrLowering', 'value'=>'0', 'label'=>CRUISE_NAME), array('id'=>'cruiseOrLowering1', 'name'=>'cruiseOrLowering', 'value'=>'1', 'label'=>LOWERING_NAME));
        return $output;
    }

    private function updateDestinationDirectory() {
        $_warehouseModel = new \Models\Warehouse();
        $warehouseConfig = $_warehouseModel->getShipboardDataWarehouseConfig();
        $cruiseID = $_warehouseModel->getCruiseID();

        if(is_dir($warehouseConfig['shipboardDataWarehouseBaseDir'] . '/' . $cruiseID)) {
            $gmData['siteRoot'] = DIR;
            $gmData['shipboardDataWarehouse'] = $warehouseConfig;
            $gmData['cruiseID'] = $cruiseID;

            # create the gearman client
            $gmc= new \GearmanClient();

            # add the default server (localhost)
            $gmc->addServer();

            #submit job to Gearman
            $job_handle = $gmc->doBackground("rebuildCruiseDirectory", json_encode($gmData));

            if($_warehouseModel->getShowLoweringComponents()) {
                $gmData['loweringID'] = $_warehouseModel->getLoweringID();
                $job_handle = $gmc->doBackground("rebuildLoweringDirectory", json_encode($gmData));
            }
        }

        ### There should be some error handling here
    }

    public function __construct(){
        if(!Session::get('loggedin')){
            Url::redirect('config/login');
        }

        $this->_extraDirectoriesModel = new \Models\Config\ExtraDirectories();
    }

    public function index(){
        $data['title'] = 'Configuration';
        $data['extraDirectories'] = $this->_extraDirectoriesModel->getExtraDirectories(false, false, "longName");
        $data['javascript'] = array();

        $warehouseModel = new \Models\Warehouse();
        $data['showLoweringComponents'] = $warehouseModel->getShowLoweringComponents();

        View::rendertemplate('header',$data);
        View::render('Config/extraDirectories',$data);
        View::rendertemplate('footer',$data);
    }

    public function add(){
        $_warehouseModel = new \Models\Warehouse();

        $data['title'] = 'Add Extra Directory';
        $data['javascript'] = array('extraDirectoriesFormHelper');
        $data['cruiseOrLoweringOptions'] = $this->_buildCruiseOrLoweringOptions();
        $data['showLoweringComponents'] = $_warehouseModel->getShowLoweringComponents();

        if(isset($_POST['submit'])){
            $name = $_POST['name'];
            $longName = $_POST['longName'];
            $cruiseOrLowering = isset($_POST['cruiseOrLowering']) ? $_POST['cruiseOrLowering'] : '0';
            $destDir = $_POST['destDir'];
            $enable = 0;

            if($name == ''){
                $error[] = 'Name is required';
            }

            if($longName == ''){
                $error[] = 'Long name is required';
            }

            if($destDir == ''){
                $error[] = 'Destination directory is required';
            }

            if(!$error){
                $postdata = array(
                    'name' => $name,
                    'longName' => $longName,
                    'cruiseOrLowering' => $cruiseOrLowering,
                    'destDir' => $destDir,
                    'enable' => $enable
                );

                $this->_extraDirectoriesModel->insertExtraDirectory($postdata);

                Session::set('message','Extra Directory Added');
                Url::redirect('config/extraDirectories');
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/addExtraDirectories',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function edit($id){
        $_warehouseModel = new \Models\Warehouse();

        $data['title'] = 'Edit Extra Directory';
        $data['javascript'] = array('extraDirectoriesFormHelper');
        $data['cruiseOrLoweringOptions'] = $this->_buildCruiseOrLoweringOptions();
        $data['showLoweringComponents'] = $_warehouseModel->getShowLoweringComponents();

        $data['row'] = $this->_extraDirectoriesModel->getExtraDirectory($id);

        if(isset($_POST['submit'])){
            $name = $_POST['name'];
            $longName = $_POST['longName'];
            $cruiseOrLowering = isset($_POST['cruiseOrLowering']) ? $_POST['cruiseOrLowering'] : '0';
            $destDir = $_POST['destDir'];

            if($name == ''){
                $error[] = 'Name is required';
            }

            if($longName == ''){
                $error[] = 'Long name is required';
            }

            if($destDir == ''){
                $error[] = 'Destination directory is required';
            }

            if(!$error){
                $postdata = array(
                    'name' => $name,
                    'longName' => $longName,
                    'cruiseOrLowering' => $cruiseOrLowering,
                    'destDir' => $destDir
                );


                $where = array('extraDirectoryID' => $id);
                $this->_extraDirectoriesModel->updateExtraDirectory($postdata,$where);

                if($data['row'][0]->destDir != $destDir){
                    $this->updateDestinationDirectory();
                }

                Session::set('message','Extra Directory Updated');
                Url::redirect('config/extraDirectories');
            } else {

                $data['row'][0]->name = $name;
                $data['row'][0]->longName = $longName;
                $data['row'][0]->cruiseOrLowering = $cruiseOrLowering;
                $data['row'][0]->destDir = $destDir;
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editExtraDirectories',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function delete($id){

        $where = array('extraDirectoryID' => $id);
        $this->_extraDirectoriesModel->deleteExtraDirectory($where);
        Session::set('message','Extra Directory Deleted');
        Url::redirect('config/extraDirectories');
    }

    public function enable($id) {
        $this->_extraDirectoriesModel->enableExtraDirectory($id);

        $this->updateDestinationDirectory();

        Url::redirect('config/extraDirectories');
    }

    public function disable($id) {
        $this->_extraDirectoriesModel->disableExtraDirectory($id);
        Url::redirect('config/extraDirectories');
    }

}
