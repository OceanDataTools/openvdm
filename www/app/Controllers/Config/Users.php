<?php

namespace Controllers\Config;
use Core\Controller;
use Core\View;
use Helpers\Password;
use Helpers\Session;
use Helpers\Url;

class Users extends Controller {

    private $_usersModel;

    public function __construct(){
        if(!Session::get('loggedin')){
            Url::redirect('config/login');
        }

        $this->_usersModel = new \Models\Config\Users();
    }

    public function index(){
        $data['title'] = 'Configuration';
        $data['users'] = $this->_usersModel->getUsers();
        View::rendertemplate('header',$data);
        View::render('Config/users',$data);
        View::rendertemplate('footer',$data);
    }

    public function addUser(){
        $data['title'] = 'Add User';

        if(isset($_POST['submit'])){
            $username = $_POST['username'];
            $password = $_POST['password'];

            if($username == ''){
                $error[] = 'Username is required';
            }

            if($password == ''){
                $error[] = 'Password is required';
            }

            if(strcmp($password, $_POST['password2']) !== 0) {
                $error[] = 'Passwords must match';
            }

            if(!$error){
                $postdata = array(
                    'username' => $username,
                    'password' => Password::make($password)//,
                );

                $this->_usersModel->insertUser($postdata);
                Session::set('message','User Added');
                Url::redirect('config/users');
            }
        }

        View::rendertemplate('header',$data);
        View::render('config/addUser',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function editUser($id){
        $data['title'] = 'Edit User';
        $data['row'] = $this->_usersModel->getUser($id);

        if(isset($_POST['submit'])){
            $username = $_POST['username'];
            $password = $_POST['password'];

            if($username == ''){
                $error[] = 'Username is required';
            }

            if($password == ''){
                $error[] = 'Password is required';
            }

            if(strcmp($password, $_POST['password2']) !== 0) {
                $error[] = 'Passwords must match';
            }



            if(!$error){
                $postdata = array(
                    'username' => $username,
                    'password' => Password::make($password)
                );

                $where = array('userID' => $id);
                $this->_usersModel->updateUser($postdata,$where);
                Session::set('message','User Updated');
                Url::redirect('config');
            }
        }

        View::rendertemplate('header',$data);
        View::render('Config/editUser',$data,$error);
        View::rendertemplate('footer',$data);
    }

    public function deleteUser($id){
        $where = array('userID' => $id);
        $this->_usersModel->deleteUser($where);
        Session::set('message','User Deleted');
        Url::redirect('config/users');
    }
}
