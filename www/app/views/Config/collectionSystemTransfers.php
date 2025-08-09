<?php

use Core\Error;
use Helpers\Session;
?>

    <div class="row">
        <div class="col-lg-12">
            <?php echo Error::display(Session::pull('message'), 'alert alert-success'); ?>
        </div>
    </div>

    <div class="row">
        <div class="col-lg-12">
            <div class="tabbable" style="margin-bottom: 18px;">
                <ul class="nav nav-tabs">
                    <li class=""><a id="main" href="<?php echo DIR; ?>config">Main</a></li>
                    <li class="active"><a id="collectionSystemTransfers" href="<?php echo DIR; ?>config/collectionSystemTransfers">Collection System Transfers</a></li>
                    <li class=""><a id="extraDirectories" href="<?php echo DIR; ?>config/extraDirectories">Extra Directories</a></li>
                    <li class=""><a id="cruiseDataTransfers" href="<?php echo DIR; ?>config/cruiseDataTransfers"><?php echo CRUISE_NAME; ?> Data Transfers</a></li>
                    <li class=""><a id="shipToShoreTransfers" href="<?php echo DIR; ?>config/shipToShoreTransfers">Ship-to-Shore Transfers</a></li>
                    <li class=""><a id="system" href="<?php echo DIR; ?>config/system">System</a></li>
                </ul>
            </div>
        </div>
    </div>
    <div class="row">
        <div  id="transfers" class="col-lg-7 col-md-12">
            <div style="padding-bottom: 10px">
	        <input id="transfer-filter" class="search" placeholder="Filter" value="<?php echo $data['filter']; ?>"/>
                <a class="pull-right btn btn-sm btn-primary" href="<?php echo DIR; ?>config/collectionSystemTransfers/add">
                    Add New Transfer
                </a>
            </div>
            <table class='table table-striped table-hover table-bordered responsive'>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Action</th>
                        <th style='width:20px;'>Enabled</th>
                    </tr>
                </thead>
                <tbody class="list">
<?php
    if($data['collectionSystemTransfers']){
        foreach($data['collectionSystemTransfers'] as $row){
?>
                    <tr>
                        <td class="name"><?php echo $row->longName; ?></td>
                        <td class="actions">
                            <a href='<?php echo DIR; ?>config/collectionSystemTransfers/edit/<?php echo $row->collectionSystemTransferID; ?>'>Edit</a> /
                            <a href='#confirmDeleteModal' data-toggle="modal" data-item-name="Collection System Transfer" data-delete-url="<?php echo DIR; ?>config/collectionSystemTransfers/delete/<?php echo $row->collectionSystemTransferID; ?>">Delete</a> /
<?php
            if ( !$data['showLoweringComponents'] && $row->cruiseOrLowering === '1') {
?>
                            <span class="text-muted">Test</span> /
<?php
            } else {
?>
                            <a href='<?php echo DIR; ?>config/collectionSystemTransfers/test/<?php echo $row->collectionSystemTransferID; echo $data['filter']!='' ? '?filter='.$data['filter'] : ''; ?>'>Test</a> /
<?php
            }
?>

<?php
            if ( !$data['showLoweringComponents'] && $row->cruiseOrLowering === '1') {
?>
                            <span class="text-muted">Run</span>
<?php
            } else {

                if($row->status === "1"){
?>
                                <a id="runStop<?php echo $row->collectionSystemTransferID; ?>" href='<?php echo DIR; ?>config/collectionSystemTransfers/stop/<?php echo $row->collectionSystemTransferID; ?>'>Stop</a>
 <?php
                } else {
?>
                                <a id="runStop<?php echo $row->collectionSystemTransferID; ?>" href='<?php echo DIR; ?>config/collectionSystemTransfers/run/<?php echo $row->collectionSystemTransferID; ?>'>Run</a>
<?php
                }
            }

            if($row->status === "3") {
?>
                            <span class="pull-right"><i class="fa fa-warning text-danger"></i></span>
<?php
            }
?>
                        </td>
                        <td style='text-align:center'>
<?php
            if ( !$data['showLoweringComponents'] && $row->cruiseOrLowering === '1') {
                if($row->enable === "0"){
?>
                            <div class="btn btn-xs btn-danger disabled">Off</div>
<?php
                } else {
?>
                            <div class="btn btn-xs btn-success disabled">On</div>
<?php
                }

            } else {

                if($row->enable === "0"){
?>
                            <a class="btn btn-xs btn-danger" href='<?php echo DIR; ?>config/collectionSystemTransfers/enable/<?php echo $row->collectionSystemTransferID;?> '>Off</a>
<?php
                } else {
?>
                            <a class="btn btn-xs btn-success" href='<?php echo DIR; ?>config/collectionSystemTransfers/disable/<?php echo $row->collectionSystemTransferID; ?>'>On</a>
<?php
                }
            }
?>
                        </td>
                    </tr>
<?php
        }
    }
?>
                </tbody>
            </table>
        </div>
        <div class="col-lg-5 col-md-12">
            <h3>Page Guide</h3>
            <p>This page is for managing Collection System Transfers.  A Collection System Transfer is an OpenVDM-managed file transfer from a data acqusition system to the Shipboard Data Warehouse.</p>
            <p>Clicking an <strong class="text-primary">Edit</strong> link will redirect you to the corresponding "Edit Collection System Transfer Form" where you can modify the Collection System Transfer settings.</p>
            <p>Clicking a <strong class="text-primary">Delete</strong> link will permanently delete the corresponding Collection System Transfer. There is a confirmation window so don't worry about accidental clicks.</p>
            <p>Clicking a <strong class="text-primary">Test</strong> link will verify the corresponding Collection System Transfer configuration is valid. A window will appear displaying the test results.  If there is a <i class="fa fa-warning text-danger"></i> in a row, the corresponding Collection System Transfer has encountered and error.  Click <strong class="text-primary">Test</strong> to diagnose the problem.</p>
            <p>Clicking a <strong class="text-primary">Run</strong> link will manually trigger the corresponding Collection System Transfer to start.  If the Collection System Transfer is currently running, this link is not present</p>
            <p>Clicking a <strong class="text-primary">Stop</strong> link will manually trigger the corresponding Collection System Transfer to stop immediately.  If the Collection System Transfer is not currently running, this link is not present</p>
            <p>The button in the <strong>Enabled</strong> column shows whether an automated collection system transfer is enabled.  Click the button to enable/disable automated data transfer for the cooresponding Collection System Transfer.</p>
            <p>Click the <strong>Add New Transfer</strong> button to add a new Collection System Transfer.</p>
        </div>
    </div>

<div class="modal fade" id="confirmDeleteModal" tabindex="-1" role="dialog">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>
                <h4 class="modal-title" id="myModalLabel">Delete Confirmation</h4>
            </div>
            <div class="modal-body">Are you sure you want to delete this <span id="modelDeleteItemName"></span>?  This cannot be undone!</div>
            <div class="modal-footer">
                <a href='' class="btn btn-danger" data-dismiss="modal">Cancel</a>
                <a href='doesnotexist' class="btn btn-primary" id="modalDeleteLink">Yup!</a>
            </div>
        </div> <!-- /.modal-content -->
    </div> <!-- /.modal-dialog -->
</div> <!-- /.modal -->

<?php
    if($data['testResults']) {
?>
<div class="modal fade" id="testResultsModal" tabindex="-1" role="dialog">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <button type="button" class="close" data-dismiss="modal" aria-hidden="true">&times;</button>
                <h4 class="modal-title" id="myModalLabel">Test Results for <?php echo $data['testCollectionSystemTransferName'] ?></h4>
            </div>
            <div class="modal-body">
                <ui class="list-unstyled">
<?php
    for($i=0; $i<(sizeof($data['testResults']['parts']))-1; $i++){
?>
                    <li><i class="fa fa-<?php echo (strcmp($data['testResults']['parts'][$i]['result'], "Pass") ? "times text-danger" : "check text-success"); ?>"></i> <?php echo $data['testResults']['parts'][$i]['partName']; ?></li>
<?php
    }
?>
                    <li><strong><i class="fa fa-<?php echo (strcmp($data['testResults']['parts'][sizeof($data['testResults']['parts'])-1]['result'], "Pass") ? "times text-danger" : "check text-success"); ?>"></i> <?php echo $data['testResults']['parts'][sizeof($data['testResults']['parts'])-1]['partName']; ?></strong></li>
                </ui>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-primary" data-dismiss="modal">Close</button>
            </div>
        </div> <!-- /.modal-content -->
    </div> <!-- /.modal-dialog -->
</div> <!-- /.modal -->
<?php
    }
?>
