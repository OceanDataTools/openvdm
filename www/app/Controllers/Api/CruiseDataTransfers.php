<?php
/*
 * api/cruiseDataTransfers - RESTful api interface to cruise data transfers
 *
 * @license   https://opensource.org/licenses/MIT
 * @author Webb Pinner - webbpinner@gmail.com
 * @version 2.9
 * @date 2022-07-01
*/

namespace Controllers\Api;
use Core\Controller;
use Helpers\TransferCredentials;

class CruiseDataTransfers extends Controller {

    private $_cruiseDataTransfersModel;

    public function __construct(){
        $this->_cruiseDataTransfersModel = new \Models\Config\CruiseDataTransfers();
    }

    public function getCruiseDataTransfers(){
        $result = $this->_cruiseDataTransfersModel->getCruiseDataTransfers();
        $result = TransferCredentials::forResponse($result);
        echo json_encode($result);
    }

    public function getCruiseDataTransfer($id){
        $result = $this->_cruiseDataTransfersModel->getCruiseDataTransfer($id);
        $result = TransferCredentials::forResponse($result);
        echo json_encode($result);
    }

    public function getRequiredCruiseDataTransfers(){
        $result = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfers();
        $result = TransferCredentials::forResponse($result);
        echo json_encode($result);
    }

    public function getRequiredCruiseDataTransfer($id){
        $result = $this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfer($id);
        $result = TransferCredentials::forResponse($result);
        echo json_encode($result);
    }

    // getCruiseDataTransfersStatuses - return the names and statuses of the cruise data transfers.
	public function getCruiseDataTransfersStatuses() {
        echo json_encode($this->_cruiseDataTransfersModel->getCruiseDataTransfersStatuses());
    }

    // getCruiseDataTransfersStatuses - return the names and statuses of the cruise data transfers.
	public function getRequiredCruiseDataTransfersStatuses() {
        echo json_encode($this->_cruiseDataTransfersModel->getRequiredCruiseDataTransfersStatuses());
    }

    // setStoppingCruiseDataTransfer
    public function setStoppingCruiseDataTransfer($id) {
        $this->_cruiseDataTransfersModel->setStoppingCruiseDataTransfer($id);
    }

    // setErrorCruiseDataTransfer
	public function setErrorCruiseDataTransfer($id) {
        $this->_cruiseDataTransfersModel->setErrorCruiseDataTransfer($id);
    }

    // setRunningCruiseDataTransfer
	public function setRunningCruiseDataTransfer($id) {
        $return = array();
        if(isset($_POST['jobPid'])){
            $this->_cruiseDataTransfersModel->setRunningCruiseDataTransfer($id, $_POST['jobPid']);
            $return['status'] = 'success';
        } else {
            $return['status'] = 'error';
            $return['message'] = 'missing POST data';
        }
        echo json_encode($return);
    }

    // setIdlerCruiseDataTransfer
	public function setIdleCruiseDataTransfer($id) {
        $this->_cruiseDataTransfersModel->setIdleCruiseDataTransfer($id);
    }

}
