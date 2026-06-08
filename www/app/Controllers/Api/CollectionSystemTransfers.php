<?php
/*
 * api/collectionSystemTransfers - RESTful api interface to collection system
 * transfers.
 *
 * @license   https://opensource.org/licenses/MIT
 * @author Webb Pinner - webbpinner@gmail.com
 * @version 2.9
 * @date 2022-07-01
 */

namespace Controllers\Api;
use Core\Controller;

class CollectionSystemTransfers extends Controller {


    /**
    * The collectionSystemTransferModel object.
    * @var model
    */
    private $_collectionSystemTransfersModel;

    /**
    * Sets the username for the given user instance. If the username
    * is already set, it will be overwritten. Throws an invalid
    * argument exception if the provided username is of an invalid
    * format.
    *
    * @param string $sUsername The username string to set
    *
    * @return  User
    * @throws  InvalidArgumentException
    * @todo    Check to make sure the username isn't already taken
    *
    * @since   2012-07-07
    * @author  Bruno Skvorc <bruno@skvorc.me>
    *
    * @edit    2012-07-08<br />
    *          John Doe <john@doe.com><br />
    *          Changed some essential
    *          functionality for the better<br/>
    *          #edit3392
    */
    public function __construct(){
        $this->_collectionSystemTransfersModel = new \Models\Config\CollectionSystemTransfers();
    }

    private function _is_worker_request(): bool {
        $token = $_SERVER['HTTP_X_WORKER_TOKEN'] ?? '';
        return defined('WORKER_API_KEY') && WORKER_API_KEY !== '' && hash_equals(WORKER_API_KEY, $token);
    }

    private function _strip_credentials(array $rows): array {
        return array_map(function($row) {
            unset($row->rsyncPass, $row->smbPass, $row->sshPass);
            return $row;
        }, $rows);
    }

    public function getCollectionSystemTransfers(){
        $result = $this->_collectionSystemTransfersModel->getCollectionSystemTransfers();
        if (!$this->_is_worker_request()) {
            $result = $this->_strip_credentials($result);
        }
        echo json_encode($result);
    }

    public function getActiveCollectionSystemTransfers($sortField = 'name'){
        $result = $this->_collectionSystemTransfersModel->getActiveCollectionSystemTransfers($sortField);
        if (!$this->_is_worker_request()) {
            $result = $this->_strip_credentials($result);
        }
        echo json_encode($result);
    }

    public function getCruiseOnlyCollectionSystemTransfers(){
        $result = $this->_collectionSystemTransfersModel->getCruiseOnlyCollectionSystemTransfers();
        if (!$this->_is_worker_request()) {
            $result = $this->_strip_credentials($result);
        }
        echo json_encode($result);
    }

    public function getLoweringOnlyCollectionSystemTransfers(){
        $result = $this->_collectionSystemTransfersModel->getLoweringOnlyCollectionSystemTransfers();
        if (!$this->_is_worker_request()) {
            $result = $this->_strip_credentials($result);
        }
        echo json_encode($result);
    }

    public function getCollectionSystemTransfer($id){
        $result = $this->_collectionSystemTransfersModel->getCollectionSystemTransfer($id);
        if (!$this->_is_worker_request()) {
            $result = $this->_strip_credentials($result);
        }
        echo json_encode($result);
    }

    // getCollectionSystemTransfersStatuses - return the names and statuses of the collection system transfers.
	public function getCollectionSystemTransfersStatuses() {
        echo json_encode($this->_collectionSystemTransfersModel->getCollectionSystemTransfersStatuses());
    }

    // setErrorCollectionSystemTransfersStatuses
	public function setErrorCollectionSystemTransfer($id) {
        $this->_collectionSystemTransfersModel->setErrorCollectionSystemTransfer($id);
    }

    // setRunningCollectionSystemTransfersStatuses
	public function setRunningCollectionSystemTransfer($id) {
        $return = array();
        if(isset($_POST['jobPid'])){
            $this->_collectionSystemTransfersModel->setRunningCollectionSystemTransfer($id, $_POST['jobPid']);
            $return['status'] = 'success';
        } else {
            $return['status'] = 'error';
            $return['message'] = 'missing POST data';
        }
        echo json_encode($return);
    }


    // setIdleCollectionSystemTransfersStatuses
	public function setIdleCollectionSystemTransfer($id) {
        $this->_collectionSystemTransfersModel->setIdleCollectionSystemTransfer($id);
    }

}