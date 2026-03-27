<?php

namespace Models\Config;
use Core\Model;

class Auth extends Model {

    public function getHash($username) {
        $data = $this->db->select("SELECT password FROM ".PREFIX."Users WHERE username = :username",
            array(':username' => $username));
        return isset($data[0]) ? $data[0]->password : null;
    }

    public function getUserID($username) {
        $data = $this->db->select("SELECT userID FROM ".PREFIX."Users WHERE username = :username",
            array(':username' => $username));
        return isset($data[0]) ? $data[0]->userID : null;
    }

    public function updateUser($data, $where) {
        $this->db->update(PREFIX."Users",$data,$where);
    }

}
