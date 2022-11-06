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
                <div class="panel-heading">Edit Current <?php echo CRUISE_NAME; ?></div>
                <div class="panel-body">
                    <?php echo Form::open(array('role'=>'form', 'method'=>'post')); ?>
                        <div class="row">
                            <div class="col-lg-12">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> ID</label>
<?php
    if(is_array($data['cruises']) && sizeof($data['cruises']) > 0) {
?>
                                    <select name="cruiseID" class="form-control">
<?php
        for($i=0;$i<sizeof($data['cruises']); $i++){
?>
                                        <option value="<?php echo $data['cruises'][$i]; ?>"<?php echo ' ' . ($data['cruiseID'] == $data['cruises'][$i] ? 'selected':'');?>><?php echo $data['cruises'][$i]; ?></option>
<?php
        }
    } else {
?>
                                    <select name="cruiseID" class="form-control disabled">
                                        <option>No <?php echo CRUISE_NAME; ?> Available</option>
<?php
    }
?>
                                    </select>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label><?php echo CRUISE_NAME; ?> Start Date/Time (UTC)</label>
                                    <div id="cruiseStartDate", class="input-group date datetimepicker">
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
                                    <div  id="cruiseEndDate", class="input-group date datetimepicker">
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
                                <label>Other Options</label>
                                <table class='table table-striped table-hover table-bordered responsive'>
                                    <tr>
                                        <th>Name</th>
                                        <th style='width:20px;'>Enabled</th>
                                    </tr>
                                    <tr>
                                        <td>Show <?php echo LOWERING_NAME; ?> Components</td><td style='width:20px; text-align:center'><?php echo $data['showLoweringComponents'] === True ? Form::submit(array('name'=>'hideLoweringComponents', 'class'=>'btn btn-xs btn-success', 'value'=>'On')): Form::submit(array('name'=>'showLoweringComponents', 'class'=>'btn btn-xs btn-danger', 'value'=>'Off')); ?></td>
                                    </tr>
                                </table>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-lg-12">
                                <?php echo Form::submit(array('name'=>'submit', 'class'=>'btn btn-primary', 'value'=>'Update')); ?>
                                <a href="<?php echo DIR; ?>config" class="btn btn-danger">Cancel</a>
                            </div>
                        </div>    
                    <?php echo Form::close(); ?>
                </div>
            </div>
        </div>
        <div class="col-lg-6">
            <h3>Page Guide</h3>
            <p>This page is for configuring OpenVDM to use a previously created cruiseID.  This page is NOT for creating a new cruiseID (and associated cruise data directory).  If you are trying to create a new cruiseID (and cruise data directory) click <a href="<?php echo DIR; ?>config/setupNewCruise">here</a>.</p>
            <p>The <strong><?php echo CRUISE_NAME; ?> ID</strong> is the unique indentifier for the cruise (i.e. CS1801)</p>
            <p>The <strong><?php echo CRUISE_NAME; ?> Start/End Date/Time </strong> is the designated start/end date/time of the cruise. This is exported as part of the cruise finialization process and optionally used for identifying files that should be skipped during file transfers.  The required format of this date/time is yyyy/mm/dd HH:MM (i.e. 2018/01/01 00:00).</p>
            <p>The <strong><?php echo CRUISE_NAME; ?> Start/End Port </strong> is the designated starting and ending ports of the cruise. This is exported as part of the cruise finialization process.</p>
            <p>Click the <strong>Update</strong> button to save the change and exit back to the main configuration page.  If you enter a cruiseID for a cruise that does not exist you will be asked to enter a different cruiseID.</p>
            <p>Click the <strong>Cancel</strong> button to revert back to the previous cruiseID and exit back to the main configuration page.</p>
        </div>
    </div>
