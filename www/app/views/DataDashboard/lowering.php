<?php
use Helpers\Url;
$loweringID  = ((!empty($_GET['loweringID']) && in_array($_GET['loweringID'], $data['loweringIDs'])) ? $_GET['loweringID'] : $data['loweringID']);
rsort($data['loweringIDs']);
?>

<?php # echo '<pre>'; print_r($data['placeholders'][0]['dataFiles']); echo '</pre>';?>
        <div class="row">
            <div class="col-lg-12">
                <div class="pull-right">
                    <form  class="form-inline">
                        <div class="form-group">
                            <label for="lowering_sel"><?php echo LOWERING_NAME; ?>:</label>
                            <select class="form-control inline" id="lowering_sel" onchange="window.location.href = window.location.href.split('?')[0] + '?loweringID=' + this[selectedIndex].value">
<?php
    for($i = 0; $i < sizeof($data['loweringIDs']); $i++){
?>
                                <option value="<?php echo $data['loweringIDs'][$i]; ?>" <?php echo ($loweringID == $data['loweringIDs'][$i] ? "selected" : "")?>><?php echo $data['loweringIDs'][$i]; ?></option>
<?php
    }
?>
                            </select>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-lg-12">
                <div class="panel">
                    <div class="panel-body">
                        <div class="row">
                            <div class="col-lg-12">
<?php
    $cardsShown = 0;
    for($i = 0; $i < sizeof($data['placeholders']); $i++){
        // Each data type's files for the selected lowering. A card with none
        // for any of its data types isn't shown (#310).
        $loweringFiles = array();
        $filecount = 0;
        for($j=0; $j < sizeof($data['placeholders'][$i]['dataFiles']); $j++){
            $loweringFiles[$j] = array_values(array_filter($data['placeholders'][$i]['dataFiles'][$j], function($dataFile) use($loweringID) {
                return preg_match("/$loweringID/", $dataFile['dd_json']);
            }));
            $filecount += sizeof($loweringFiles[$j]);
        }
        if ($filecount == 0) {
            continue;
        }
        $cardsShown++;
?>
                                <div class="panel panel-default">
<?php
        for($j=0; $j < sizeof($loweringFiles); $j++){
?>
                                <a id="<?php echo (!empty($loweringFiles[$j]) ? $loweringFiles[$j][0]['type'] : ''); ?>"></a>
<?php
        }
?>
                                    <div class="panel-heading"><?php echo $data['placeholders'][$i]['heading'];?><?php echo ($data['placeholders'][$i]['plotType'] == 'chart'? '<i id="' . $data['placeholders'][$i]['id'] . '_expand-btn" class="expand-btn pull-right btn btn-sm btn-default fa fa-expand"></i><i id="' . $data['placeholders'][$i]['id'] . '_zoom-reset-btn" class="zoom-reset-btn pull-right btn btn-sm btn-default fa fa-rotate-left hidden"></i>': ''); ?>
                                    </div>
                                    <div class="panel-body">
                                        <?php $tag = (strcmp($data['placeholders'][$i]['plotType'], 'map') === 0? 'div': 'canvas'); ?><<?php echo $tag; ?> class="<?php echo $data['placeholders'][$i]['plotType']; ?>" id="<?php echo $data['placeholders'][$i]['id'];?>_placeholder" style="min-height:<?php echo (strcmp($data['placeholders'][$i]['plotType'], 'map') === 0? '493': '200'); ?>px;"></<?php echo $tag; ?>>
                                    </div>
                                    <div class="panel-footer">
                                        <div class="objectList" id="<?php echo $data['placeholders'][$i]['id'];?>_objectList-placeholder">
                                            <form>
<?php
        for($j = 0; $j < sizeof($data['placeholders'][$i]['dataArray']); $j++){
            $dataFiles = $loweringFiles[$j];
?>
                                                <div class="row">
                                                    <div class="col-lg-12"><strong><?php echo (sizeof($dataFiles) > 0 ? $dataFiles[0]['type'] : ''); ?></strong><?php echo (strcmp($data['placeholders'][$i]['plotType'], 'map') === 0 && sizeof($dataFiles) > 0? '<div class="pull-right"><div class="btn btn-xs btn-default selectAll" >Select All</div> <div class="btn btn-xs btn-default clearAll" >Clear All</div></div>': ''); ?></div>
<?php
            if(sizeof($dataFiles) > 0){
                if(strcmp($data['placeholders'][$i]['dataArray'][$j]['visType'], 'geoJSON')===0) {
?>
                                                    <div class='col-lg-12'>
                                                        <input class='se-checkbox' type="checkbox" value="<?php echo $dataFiles[0]['type'];?>" checked> Start/End Positions
                                                    </div>
                                                    <div class='col-lg-12'>
<?php
                    for($k = sizeof($dataFiles)-1; $k >= 0; $k--){
?>
                                                    <span class='file-entry'>
                                                        <input class='<?php echo $data['placeholders'][$i]['dataArray'][$j]['visType']; ?>-checkbox' type="checkbox" value="<?php echo $dataFiles[$k]['type'] . '/' . $dataFiles[$k]['dd_json'];?>" checked> <?php echo end(explode('/',$dataFiles[$k]['raw_data']));?>
                                                        <a href="<?php echo $data['dataWarehouseApacheDir'] . '/' . $dataFiles[$k]['raw_data']; ?>" download target="_blank"><i class="fa fa-download"></i></a>
                                                    </span>
<?php
                    }
?>
                                                    </div>
<?php
                } else if(strcmp($data['placeholders'][$i]['dataArray'][$j]['visType'], 'tms')===0) {
?>
                                                    <div class='col-lg-12'>
<?php
                    for($k = sizeof($dataFiles)-1; $k >= 0; $k--){
?>
                                                    <span class='file-entry'>
                                                        <input class='<?php echo $data['placeholders'][$i]['dataArray'][$j]['visType']; ?>-checkbox' type="checkbox" value="<?php echo $dataFiles[$k]['type'] . '/' . $dataFiles[$k]['dd_json'];?>" checked> <?php echo end(explode('/',$dataFiles[$k]['raw_data']));?>
                                                        <a href="<?php echo $data['dataWarehouseApacheDir'] . '/' . $dataFiles[$k]['raw_data']; ?>" download target="_blank"><i class="fa fa-download"></i></a>
                                                    </span>
<?php
                    }
?>
                                                    </div>
<?php
                } else if(in_array($data['placeholders'][$i]['dataArray'][$j]['visType'], array('json', 'json-reversedY', 'json-reversedY-inverted', 'json-inverted', 'json-profile'), true)) {
                    // A chart; json-profile entries carry their options for dashboardCharts.js (#274)
?>
                                                    <div class="form-group col-lg-12">
<?php
                    for($k = sizeof($dataFiles)-1; $k >= 0; $k--){
?>
                                                        <span class='file-entry'>
                                                            <input class='<?php echo $data['placeholders'][$i]['dataArray'][$j]['visType']; ?>-radio' <?php echo (isset($data['placeholders'][$i]['dataArray'][$j]['profileOptions']) ? "data-profile='" . htmlspecialchars(json_encode($data['placeholders'][$i]['dataArray'][$j]['profileOptions']), ENT_QUOTES) . "' " : ''); ?>name="<?php echo $dataFiles[$k]['type'];?>" type="radio" value="<?php echo $dataFiles[$k]['dd_json'];?>"  <?php echo ($k === sizeof($dataFiles)-1? 'checked' : '');   ?>> <?php echo end(explode('/',$dataFiles[$k]['raw_data']));?>
                                                            <a href="<?php echo $data['dataWarehouseApacheDir'] . '/' . $dataFiles[$k]['raw_data']; ?>" download target="_blank"><i class="fa fa-download"></i></a>
                                                        </span>
<?php
                    }
?>
                                                    </div>
<?php
                } else {
?>
                                                    <div class='col-lg-12'>No data found</div>
<?php
                }
            }
?>
                                                </div>
<?php
        }
?>
                                            </form>
                                        </div>
                                    </div>
                                </div>
<?php
    }
    if ($cardsShown == 0) {
?>
                                <p>No data found for <?php echo LOWERING_NAME . ' ' . htmlspecialchars($loweringID); ?>.</p>
<?php
    }
?>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
