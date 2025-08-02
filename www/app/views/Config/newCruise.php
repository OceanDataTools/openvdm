<?php

use Core\Error;
use Helpers\Form;

?>

    <div class="row">
        <div class="col-lg-12">
            <?php echo Error::display($error); ?>
        </div>
    </div>

    <div class="row">
        <div class="col-lg-12">
            <div class="tabbable" style="margin-bottom: 18px;">
                <ul class="nav nav-tabs">
                    <li class="active"><a id="main" href="<?php echo DIR; ?>config">Main</a></li>
                    <li class=""><a id="collectionSystemTransfers" href="<?php echo DIR; ?>config/collectionSystemTransfers">Collection System Transfers</a></li>
                    <li class=""><a id="extraDirectories" href="<?php echo DIR; ?>config/extraDirectories">Extra Directories</a></li>
                    <li class=""><a id="cruiseDataTransfers" href="<?php echo DIR; ?>config/cruiseDataTransfers"><?php echo CRUISE_NAME; ?> Data Transfers</a></li>
                    <li class=""><a id="shipToShoreTransfers" href="<?php echo DIR; ?>config/shipToShoreTransfers">Ship-to-Shore Transfers</a></li>
                    <li class=""><a id="system" href="<?php echo DIR; ?>config/system">System</a></li>
                </ul>
            </div>
        </div>
    </div>

    <div class="row">
        <div class="col-lg-6">
            <div class="panel panel-default">
                <div class="panel-heading">Create New <?php echo CRUISE_NAME; ?></div>
                <div class="panel-body">
                    <?php echo Form::open(array('role'=>'form', 'method'=>'post')); ?>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> ID</label>
                                    <?php echo Form::input(array('class'=>'form-control', 'type'=>'text', 'name'=>'cruiseID', 'value'=>$data['cruiseID'])); ?>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> Name</label>
                                    <?php echo Form::input(array('class'=>'form-control', 'type'=>'text', 'name'=>'cruiseName', 'value'=>$data['cruiseName'])); ?>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> PI</label>
                                    <?php echo Form::input(array('class'=>'form-control', 'type'=>'text', 'name'=>'cruisePI', 'value'=>$data['cruisePI'])); ?>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> Location</label>
                                    <?php echo Form::input(array('class'=>'form-control', 'type'=>'text', 'name'=>'cruiseLocation', 'value'=>$data['cruiseLocation'])); ?>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> Start Date/Time (UTC)</label>
                                    <div class="input-group date datetimepickerToday">
                                        <?php echo Form::input(array('class'=>'form-control', 'type'=>'text', 'name'=>'cruiseStartDate', 'value'=>$data['cruiseStartDate'])); ?>
                                        <span class="input-group-addon"><i class="fa fa-calendar"></i></span>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> Start Port</label>
                                    <?php echo Form::input(array('class'=>'form-control', 'type'=>'text', 'name'=>'cruiseStartPort', 'value'=>$data['cruiseStartPort'])); ?>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> End Date/Time (UTC)</label>
                                    <div class="input-group date datetimepicker">
                                        <?php echo Form::input(array('class'=>'form-control', 'type'=>'text', 'name'=>'cruiseEndDate', 'value'=>$data['cruiseEndDate'])); ?>
                                        <span class="input-group-addon"><i class="fa fa-calendar"></i></span>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> End Port</label>
                                    <?php echo Form::input(array('class'=>'form-control', 'type'=>'text', 'name'=>'cruiseEndPort', 'value'=>$data['cruiseEndPort'])); ?>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-lg-12">
                                <label>Collection Systems</label>
                                <table class='table table-striped table-hover table-bordered responsive'>
                                    <tr>
                                        <th>Name</th>
                                        <th style='width:20px;'>Enabled</th>
                                    </tr>
<?php
    if($data['collectionSystemTransfers']){
        foreach($data['collectionSystemTransfers'] as $row){
?>
                                    <tr>
                                        <td><?php echo $row->longName; echo ($row->status === "3"? '<span class="pull-right"><i class="fa fa-warning text-danger"></i></span>': ''); ?></td>
                                        <td style='text-align:center'>
<?php
            if($row->enable === "0"){
                echo '                                            ' . Form::submit(array('name'=>'enableCS' . $row->collectionSystemTransferID, 'class'=>'btn btn-xs btn-primary btn-danger', 'value'=>'Off'));
            } else {
                echo '                                            ' . Form::submit(array('name'=>'disableCS' . $row->collectionSystemTransferID, 'class'=>'btn btn-xs btn-primary btn-success', 'value'=>'On'));
            }
?>
                                        </td>
                                    </tr>
<?php
        }
    }
?>
                                </table>
                                <label>Other Options</label>
                                <table class='table table-striped table-hover table-bordered responsive'>
                                    <tr>
                                        <th>Name</th>
                                        <th style='width:20px;'>Enabled</th>
                                    </tr>
                                    <tr>
                                        <td>Show Lowering Components</td><td style='width:20px; text-align:center'><?php echo $data['showLoweringComponents'] === True ? Form::submit(array('name'=>'hideLoweringComponents', 'class'=>'btn btn-xs btn-success', 'value'=>'On')): Form::submit(array('name'=>'showLoweringComponents', 'class'=>'btn btn-xs btn-danger', 'value'=>'Off')); ?></td>
                                    </tr>
                                    <tr>
                                        <td>Ship-to-Shore Transfers</td><td style='width:20px; text-align:center'><?php echo $data['shipToShoreTransfersEnable'] === '1' ? Form::submit(array('name'=>'disableSSDW', 'class'=>'btn btn-xs btn-success', 'value'=>'On')): Form::submit(array('name'=>'enableSSDW', 'class'=>'btn btn-xs btn-danger', 'value'=>'Off')); ?></td>
                                    </tr>
                                </table>

                                <?php echo Form::submit(array('name'=>'submit', 'class'=>'btn btn-primary', 'value'=>'Create')); ?>
                                <a href="<?php echo DIR; ?>config" class="btn btn-danger">Cancel</a>
                            </div>
                        </div>
                    <?php echo Form::close(); ?>
                </div>
            </div>
        </div>
        <div class="col-lg-6">
            <h3>Page Guide</h3>
            <p>This page is for creating a new cruiseID and associated cruise data directory.  This page is NOT for configuring OpenVDM to use a previously created cruiseID.  If you are trying to configure OpenVDM to use a previously created cruiseID click <a href="<?php echo DIR; ?>config/editCruise">here</a>.</p>
            <p>The <strong><?php echo CRUISE_NAME; ?> ID</strong> is the unique indentifier for the cruise (i.e. CS1801)</p>
            <p>The <strong><?php echo CRUISE_NAME; ?> Start/End Date/Time </strong> is the designated start/end date/time of the cruise. This is exported as part of the cruise finialization process and optionally used for identifying files that should be skipped during file transfers.  The required format of this date/time is yyyy/mm/dd HH:MM (i.e. 2018/01/01 00:00).</p>
            <p>The <strong><?php echo CRUISE_NAME; ?> Start/End Port </strong> is the designated starting and ending ports of the cruise. This is exported as part of the cruise finialization process.</p>
            <p>The <strong>Collection Systems</strong> table is for specifying what collection system will be used during the cruise.  These can always be changed later from the Collection System Transfers tab.</p>
            <p>Click the <strong>Create</strong> button to save the change and exit back to the main configuration page.  If you enter a cruiseID for a cruise that already exists you will be asked to enter a different cruiseID.</p>
            <p>Click the <strong>Cancel</strong> button to exit back to the main configuration page without creating a new cruise.</p>
        </div>
    </div>
