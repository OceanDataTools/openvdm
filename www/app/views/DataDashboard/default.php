<?php
use Helpers\Url;
$loadingImage = '<img height="50" src="' . Url::templatePath() . 'images/loading.gif"/>';
?>
        <div class="row">
            <div class="col-lg-12">
                <div class="panel">
                    <div class="panel-body">
                        <div class="row">
                            <div class="col-lg-12">
<?php
    for($i = 0; $i < sizeof($data['placeholders']); $i++){
        // A card with no files for any of its data types isn't shown (#310)
        $filecount = 0;
        for($j=0; $j < sizeof($data['placeholders'][$i]['dataFiles']); $j++){
            $filecount += sizeof($data['placeholders'][$i]['dataFiles'][$j]);
        }
        if ($filecount == 0) {
            continue;
        }
?>
                                <div class="panel panel-default">
<?php
        for($j=0; $j < sizeof($data['placeholders'][$i]['dataFiles']); $j++){
?>
                                <a id="<?php echo (!empty($data['placeholders'][$i]['dataFiles'][$j]) ? $data['placeholders'][$i]['dataFiles'][$j][0]['type'] : ''); ?>"></a>
<?php
        }
?>
                                    <div class="panel-heading">
                                        <?php echo $data['placeholders'][$i]['heading'];?><?php echo ($data['placeholders'][$i]['plotType'] == 'chart'? '<i id="' . $data['placeholders'][$i]['id'] . '_expand-btn" class="expand-btn pull-right btn btn-sm btn-default fa fa-expand"></i><i id="' . $data['placeholders'][$i]['id'] . '_zoom-reset-btn" class="zoom-reset-btn pull-right btn btn-sm btn-default fa fa-rotate-left hidden"></i>': ''); ?>
                                    </div>
                                    <div class="panel-body">
                                    <<?php echo (strcmp($data['placeholders'][$i]['plotType'], 'map') === 0? 'div': 'canvas'); ?> class="<?php echo $data['placeholders'][$i]['plotType']; ?>" id="<?php echo $data['placeholders'][$i]['id'];?>_placeholder" style="min-height:<?php echo (strcmp($data['placeholders'][$i]['plotType'], 'map') === 0? '493': '200'); ?>px;">
                                    </<?php echo (strcmp($data['placeholders'][$i]['plotType'], 'map') === 0? 'div': 'canvas'); ?>>
                                    </div>
                                    <div class="panel-footer">
                                        <div class="objectList" id="<?php echo $data['placeholders'][$i]['id'];?>_objectList-placeholder">
                                            <form>
<?php
        for($j = 0; $j < sizeof($data['placeholders'][$i]['dataArray']); $j++){
?>
                                                <div class="row">

<?php
            if(is_array($data['placeholders'][$i]['dataFiles'][$j]) && sizeof($data['placeholders'][$i]['dataFiles'][$j]) > 0){
                if (strcmp($data['placeholders'][$i]['plotType'], 'map') === 0) {
?>
                                                    <div class="col-lg-12">
                                                        <strong><?php echo $data['placeholders'][$i]['dataFiles'][$j][0]['type']; ?></strong>
                                                        <div class="pull-right">
                                                            <div class="btn btn-xs btn-default selectAll" >Select All</div>
                                                            <div class="btn btn-xs btn-default clearAll" >Clear All</div>
                                                        </div>
                                                    </div>
<?php
                }
?>
<?php
                if(strcmp($data['placeholders'][$i]['dataArray'][$j]['visType'], 'geoJSON')===0) {
?>
                                                    <div class='col-lg-12'>
                                                        <input class='lp-checkbox' type="checkbox" value="<?php echo $data['placeholders'][$i]['dataFiles'][$j][0]['type'];?>" checked> Latest Position
                                                    </div>
                                                    <div class='col-lg-12'>
<?php
                    for($k = sizeof($data['placeholders'][$i]['dataFiles'][$j])-1; $k >= 0; $k--){
?>
                                                    <span class='file-entry'>
                                                        <input class='<?php echo $data['placeholders'][$i]['dataArray'][$j]['visType']; ?>-checkbox' type="checkbox" value="<?php echo $data['placeholders'][$i]['dataFiles'][$j][0]['type'] . '/' . $data['placeholders'][$i]['dataFiles'][$j][$k]['dd_json'];?>" checked> <?php echo end(explode('/',$data['placeholders'][$i]['dataFiles'][$j][$k]['raw_data']));?>
                                                        <a href="<?php echo $data['dataWarehouseApacheDir'] . '/' . $data['placeholders'][$i]['dataFiles'][$j][$k]['raw_data']; ?>" download target="_blank"><i class="fa fa-download"></i></a>
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
                    for($k = sizeof($data['placeholders'][$i]['dataFiles'][$j])-1; $k >= 0; $k--){
?>
                                                    <span class='file-entry'>
                                                        <input class='<?php echo $data['placeholders'][$i]['dataArray'][$j]['visType']; ?>-checkbox' type="checkbox" value="<?php echo $data['placeholders'][$i]['dataFiles'][$j][0]['type'] . '/' . $data['placeholders'][$i]['dataFiles'][$j][$k]['dd_json'];?>" checked> <?php echo end(explode('/',$data['placeholders'][$i]['dataFiles'][$j][$k]['raw_data']));?>
                                                        <a href="<?php echo $data['dataWarehouseApacheDir'] . '/' . $data['placeholders'][$i]['dataFiles'][$j][$k]['raw_data']; ?>" download target="_blank"><i class="fa fa-download"></i></a>
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
                    for($k = sizeof($data['placeholders'][$i]['dataFiles'][$j])-1; $k >= 0; $k--){
?>
                                                        <span class='file-entry'>
                                                            <input class='<?php echo $data['placeholders'][$i]['dataArray'][$j]['visType']; ?>-radio' <?php echo (isset($data['placeholders'][$i]['dataArray'][$j]['profileOptions']) ? "data-profile='" . htmlspecialchars(json_encode($data['placeholders'][$i]['dataArray'][$j]['profileOptions']), ENT_QUOTES) . "' " : ''); ?>name="<?php echo $data['placeholders'][$i]['dataFiles'][$j][$k]['type'];?>" type="radio" value="<?php echo $data['placeholders'][$i]['dataFiles'][$j][$k]['dd_json'];?>"  <?php echo ($k === sizeof($data['placeholders'][$i]['dataFiles'][$j])-1? 'checked' : '');   ?>> <?php echo end(explode('/',$data['placeholders'][$i]['dataFiles'][$j][$k]['raw_data']));?>
                                                            <a href="<?php echo $data['dataWarehouseApacheDir'] . '/' . $data['placeholders'][$i]['dataFiles'][$j][$k]['raw_data']; ?>" download target="_blank"><i class="fa fa-download"></i></a>
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
?>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
