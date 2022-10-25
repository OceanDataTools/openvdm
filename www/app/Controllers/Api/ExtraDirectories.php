<?php
/*
 * api/extraDirectories - RESTful api interface to extra directories.
 *
 * @license   https://opensource.org/licenses/MIT
 * @author Webb Pinner - webbpinner@gmail.com
 * @version 2.9
 * @date 2022-07-01
 */

namespace Controllers\Api;
use Core\Controller;

class ExtraDirectories extends Controller {

    private $_extraDirectoriesModel;

    public function __construct(){
        $this->_extraDirectoriesModel = new \Models\Config\ExtraDirectories();
    }

    public function getExtraDirectories(){

        echo json_encode($this->_extraDirectoriesModel->getExtraDirectories());
    }
    
    public function getActiveExtraDirectories(){
        echo json_encode($this->_extraDirectoriesModel->getActiveExtraDirectories());
    }

    public function getExtraDirectory($id){

        echo json_encode($this->_extraDirectoriesModel->getExtraDirectory($id));
    }

    public function getRequiredExtraDirectories(){

        echo json_encode($this->_extraDirectoriesModel->getExtraDirectories(true, true));
    }

}