<?php

namespace Models\Config;
use Core\Model;

class Messages extends Model {

    public function getMessages($limit, $search=''){
        if($search !== ''){
            return $this->db->select("SELECT * FROM ".PREFIX."Messages WHERE messageTitle LIKE '%".$search."%' OR messageBody LIKE '%".$search."%' ORDER BY messageID DESC " . $limit);
        }
        return $this->db->select("SELECT * FROM ".PREFIX."Messages ORDER BY messageID DESC " . $limit);
    }
    
    public function getMessagesTotal($search=''){
        if($search !== ''){
            return sizeof($this->db->select("SELECT messageID FROM ".PREFIX."Messages WHERE messageTitle LIKE '%".$search."%' OR messageBody LIKE '%".$search."%'"));
        }
        return sizeof($this->db->select("SELECT messageID FROM ".PREFIX."Messages"));
    }

    public function getNewMessages($limit, $search='') {
        if($search !== ''){
            return $this->db->select("SELECT * FROM ".PREFIX."Messages WHERE messageViewed = 0 AND messageTitle LIKE '%".$search."%' OR messageBody LIKE '%".$search."%' ORDER BY messageID DESC " . $limit);
        }
        return $this->db->select("SELECT * FROM ".PREFIX."Messages WHERE messageViewed = 0 ORDER BY messageID DESC " . $limit);
    }
    
    public function getNewMessagesTotal($search=''){
        if($search !== ''){
            return sizeof($this->db->select("SELECT messageID FROM ".PREFIX."Messages WHERE messageViewed = 0 AND messageTitle LIKE '%".$search."%' OR messageBody LIKE '%".$search."%'"));    
        }   
        return sizeof($this->db->select("SELECT messageID FROM ".PREFIX."Messages WHERE messageViewed = 0"));
    }

    public function getMessage($id){
        return $this->db->select("SELECT * FROM ".PREFIX."Messages WHERE messageID = :id",array(':id' => $id));
    }
    
    public function insertMessage($data){
        if(!isset($data['messageTS'])) {
            $data['messageTS'] = gmdate('Y-m-d H:i:s');         
            $data['messageViewed'] = 0;
        }

        if(strlen($data['messageBody'] > 10000)){
            $data['messageBody'] = substr($data['messageBody'], 0, 10000);
        }

        $this->db->insert(PREFIX."Messages",$data);
    }
    
    public function updateMessage($data,$where){
        $this->db->update(PREFIX."Messages",$data, $where);
    }
    
    public function viewedMessage($id){
        $data['messageViewed'] = 1;
        $where['messageID'] = $id;
        $this->db->update(PREFIX."Messages",$data, $where);
    }
    
    public function viewAllMessages(){
        $data['messageViewed'] = 1;
        $where['messageViewed'] = 0;
        $this->db->update(PREFIX."Messages", $data, $where);
    }
    
    public function deleteMessage($where){
        $this->db->delete(PREFIX."Messages", $where);
    }
    
    public function deleteAllMessages(){
        $this->db->truncate(PREFIX."Messages");
    }
}
