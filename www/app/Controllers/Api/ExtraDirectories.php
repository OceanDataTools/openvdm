<?php
/*
 * api/extraDirectories - RESTful api interface to extra directories.
 *
 * @license   https://opensource.org/licenses/MIT
 * @author Webb Pinner - webbpinner@gmail.com
 * @version 2.6
 * @date 2021-02-13
 */

namespace Controllers\Api;
use Core\Controller;

class ExtraDirectories extends Controller {

    private $_model;

    public function __construct(){
        $this->_model = new \Models\Config\ExtraDirectories();
    }

    public function getExtraDirectories(){

        echo json_encode($this->_model->getExtraDirectories());
    }
    
    public function getExtraDirectory($id){

        echo json_encode($this->_model->getExtraDirectory($id));
    }

    public function getRequiredExtraDirectories(){

        echo json_encode($this->_model->getRequiredExtraDirectories());
    }

}