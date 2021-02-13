<?php
/*
 * api/tasks - RESTful api interface to OpenVDM tasks
 *
 * @license   https://opensource.org/licenses/MIT
 * @author Webb Pinner - webbpinner@gmail.com
 * @version 2.6
 * @date 2021-02-13
 */

namespace Controllers\Api;
use Core\Controller;

class Tasks extends Controller {

    private $_tasksModel;

    public function __construct(){
        $this->_tasksModel = new \Models\Config\Tasks();
    }

    public function getTasks(){
        echo json_encode($this->_tasksModel->getTasks());
    }
    
    public function getActiveTasks(){
        echo json_encode($this->_tasksModel->getActiveTasks());
    }

    public function getCruiseOnlyTasks(){
        echo json_encode($this->_tasksModel->getCruiseOnlyTasks());
    }

    public function getLoweringOnlyTasks(){
        echo json_encode($this->_tasksModel->getLoweringOnlyTasks());
    }

    public function getTask($id){
        echo json_encode($this->_tasksModel->getTask($id));
    }
    
    // getProcessesStatuses - return the names and statuses of the collection system transfers.
	public function getTaskStatuses() {
        echo json_encode($this->_tasksModel->getTaskStatuses());
    }
    
    // setErrorProcess
	public function setErrorTask($id) {
        $this->_tasksModel->setErrorTask($id);
    }
    
    // setRunningProcess
	public function setRunningTask($id) {
        $return = array();
        if(isset($_POST['jobPid'])){
            $this->_tasksModel->setRunningTask($id, $_POST['jobPid']);
            $return['status'] = 'success';
        } else {
            $return['status'] = 'error';
            $return['message'] = 'missing POST data';
        }
        echo json_encode($return);
    }

    // setIdleProcess
	public function setIdleTask($id) {
        $this->_tasksModel->setIdleTask($id);
    }

}