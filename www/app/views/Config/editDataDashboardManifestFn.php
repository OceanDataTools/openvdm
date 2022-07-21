<?php

use Core\Error;
use Helpers\Form;

var_dump($data);
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
                    <li class=""><a id="main" href="<?php echo DIR; ?>config">Main</a></li>
                    <li class=""><a id="collectionSystemTransfers" href="<?php echo DIR; ?>config/collectionSystemTransfers">Collection System Transfers</a></li>
                    <li class=""><a id="extraDirectories" href="<?php echo DIR; ?>config/extraDirectories">Extra Directories</a></li>
                    <li class=""><a id="cruiseDataTransfers" href="<?php echo DIR; ?>config/cruiseDataTransfers"><?php echo LOWERING_NAME; ?> Data Transfers</a></li>
                    <li class=""><a id="shipToShoreTransfers" href="<?php echo DIR; ?>config/shipToShoreTransfers">Ship-to-Shore Transfers</a></li>
                    <li class="active"><a id="system" href="<?php echo DIR; ?>config/system">System</a></li>
                </ul>
            </div>
        </div>
    </div>
    <div class="row">
        <div class="col-lg-6">
            <div class="panel panel-default">
                <div class="panel-heading">Edit Data Dashboard Manifest File</div>
                <div class="panel-body">
                    <?php echo Form::open( array('role'=>'form', 'method'=>'post')); ?>
                        <div class="row">
                            <div class="col-lg-12">
                                <div class="form-group"><label>File Name</label><?php echo Form::input( array('class'=>'form-control', 'name'=>'dataDashboardManifestFn', 'value'=>$data['dataDashboardManifestFn'])); ?></div>
                            </div>
                        </div>
                        <div class="row">    
                            <div class="col-lg-12">
                                <?php echo Form::submit(array('name'=>'submit', 'class'=>'btn btn-primary', 'value'=>'Update')); ?>
                                <a href="<?php echo DIR; ?>config/system" class="btn btn-danger">Cancel</a>
                            </div>
                        </div>    
                    <?php echo Form::close(); ?>
                </div>
            </div>
        </div>
        <div class="col-lg-6">
            <h3>Page Guide</h3>
            <p>This form is for editing the name of the Data Dashboard manifest filename.</p>
            <p>The <strong>File Name</strong> field is the file name (i.e. manifest.json).  The filename should end in '.json' and contain no spaces.</p>
            <p>Click the <strong>Update</strong> button to submit the changes to OpenVDM.  Click the <strong>Cancel</strong> button to exit this form.</p>
        </div>
    </div>
