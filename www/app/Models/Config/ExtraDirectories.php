<?php

namespace models\config;
use Core\Model;

class ExtraDirectories extends Model {

    public function getExtraDirectories($required = false, $only_required = false, $sort = "name"){

        if (!in_array($sort, array("name", "longName"))) {
            $sort = 'name';
        }

        if ( $required && ! $only_required ) {
            return $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories ORDER BY ".$sort);
        }
        elseif ( $required && $only_required ) {
            return $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories WHERE required = :required ORDER BY ".$sort, array(':required' => '1'));
        }
        elseif ( ! $required ) {
            return $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories WHERE required = :required ORDER BY ".$sort, array(':required' => '0'));
        }
    }

    public function getActiveExtraDirectories(){

        $_warehouseModel = new \Models\Warehouse();
        if ($_warehouseModel->getShowLoweringComponents()) {
            return $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories WHERE enable = :enable ORDER BY name", array(':enable' => 1));
        }
        return $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories WHERE cruiseOrLowering = :cruiseOrLowering AND enable = :enable ORDER BY name", array(':cruiseOrLowering' => 0, ':enable' => 1));

    }

    // public function getRequiredExtraDirectories($sort = "name"){

    //     return $this->getExtraDirectories(true, true, $sort);

    // }

    public function getExtraDirectory($id){
        return $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories WHERE extraDirectoryID = :id",array(':id' => $id));
    }
    
    public function getExtraDirectoryByName($name){
        return $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories WHERE name = :name",array(':name' => $name));
    }
    
    public function insertExtraDirectory($data){
        $this->db->insert(PREFIX."ExtraDirectories",$data);
    }
    
    public function updateExtraDirectory($data,$where){
        $this->db->update(PREFIX."ExtraDirectories",$data, $where);
    }
    
    public function deleteExtraDirectory($where){

        $cruiseDataTransfers = new \Models\Config\CruiseDataTransfers();
        $cruiseDataTransfers->clearExtraDirectory($where['extraDirectoryID']);

        $extraDirectory = $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories WHERE extraDirectoryID = :id",array(':id' => $where['extraDirectoryID']))[0];
        if(strcmp($extraDirectory->required, '0') === 0 ){
            $this->db->delete(PREFIX."ExtraDirectories", $where);
        } 
    }
    
    public function enableExtraDirectory($id){
        $data = array('enable' => 1); 
        $where = array('extraDirectoryID' => $id);
        $this->db->update(PREFIX."ExtraDirectories",$data, $where);
    }
    
    public function disableExtraDirectory($id){
        $data = array('enable' => 0); 
        $where = array('extraDirectoryID' => $id);
        $this->db->update(PREFIX."ExtraDirectories",$data, $where);
    }
    
    public function getExtraDirectoriesConfig(){
        return $this->db->select("SELECT * FROM ".PREFIX."ExtraDirectories ORDER BY extraDirectoryID");
    }

}