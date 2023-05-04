<?php
/*
 * api/transferLogs - RESTful api interface to collection system and ship-
 * to-shore transfers logs.
 *
 * @license   https://opensource.org/licenses/MIT
 * @author Webb Pinner - webbpinner@gmail.com
 * @version 2.9
 * @date 2022-07-01
 */

namespace Controllers\Api;
use Core\Controller;

class TransferLogs extends Controller {

    private $_model;

    public function __construct(){

        $this->_model = new \Models\TransferLogs();
    }
    
    public function getExcludeLogsSummary() {
        echo json_encode($this->_model->getExcludeLogsSummary());
    }

    public function getShipboardLogsSummary($count = 0) {
        echo json_encode($this->_model->getShipboardLogsSummary($count));
    }

    public function getShipToShoreLogsSummary($count = 0) {
        echo json_encode($this->_model->getShipToShoreLogsSummary($count));
    }
}